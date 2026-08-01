from backend.models import RetrievalDiagnostic, SourceChunk
from backend.services.embeddings import embed_query
from backend.services.keyword_index import KeywordIndex
from backend.services.lmstudio_client import LMStudioClient
from backend.services.query_expansion import expand_query
from backend.services.reranker import rerank_hybrid, scores_to_dict
from backend.services.text_processing import tokenize_text_set
from backend.services.vector_store import VectorStore


SYSTEM_PROMPT = """
És um assistente de estudo em PT-PT.
Responde apenas com base no contexto fornecido.
Se o contexto não for suficiente, diz claramente que não tens informação suficiente.
Inclui sempre uma resposta objetiva e curta.
""".strip()


def _tokenize(text: str) -> set[str]:
    return tokenize_text_set(text)


def score_candidate(question: str, chunk_text: str, vector_score: float) -> float:
    question_tokens = _tokenize(question)
    chunk_tokens = _tokenize(chunk_text)
    overlap = len(question_tokens & chunk_tokens)
    overlap_bonus = overlap * 0.15
    return vector_score + overlap_bonus


def build_answer_prompt(question: str, context_text: str) -> str:
    return (
        "Pergunta do utilizador:\n"
        f"{question}\n\n"
        "Contexto recuperado:\n"
        f"{context_text}\n\n"
        "Instruções:\n"
        "- Responde em PT-PT, de forma objetiva e concisa.\n"
        "- Baseia-te apenas no contexto recuperado.\n"
        "- Não inventes factos. Se o contexto não for suficiente, diz claramente que não tens informação suficiente.\n"
        "- Quando houver contexto relevante, resume em frases curtas e cita sempre a fonte e a página no fim.\n"
        "- Formato obrigatório:\n"
        "  Resposta: <conteúdo objetivo>\n"
        "  Fontes usadas: [ficheiro, p.X], [ficheiro, p.Y]\n"
        "- Se não houver contexto suficiente: Resposta: Informação insuficiente no contexto recuperado."
    )


class RagPipeline:
    def __init__(
        self,
        embedding_model: str,
        vector_store: VectorStore,
        keyword_index: KeywordIndex | None,
        lmstudio_client: LMStudioClient,
        rerank_weights: dict[str, float] | None = None,
        retrieval_mode_default: str = "hybrid",
        keyword_candidate_multiplier: int = 2,
    ) -> None:
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        self.keyword_index = keyword_index
        self.lmstudio_client = lmstudio_client
        self.rerank_weights = rerank_weights
        self.retrieval_mode_default = retrieval_mode_default
        self.keyword_candidate_multiplier = max(keyword_candidate_multiplier, 1)

    def ask(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[str, list[SourceChunk]]:
        answer, sources, _ = self.ask_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
            retrieval_mode=retrieval_mode,
            keyword_top_k=keyword_top_k,
        )
        return answer, sources

    def ask_with_debug(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[str, list[SourceChunk], list[RetrievalDiagnostic]]:
        user_prompt, sources, diagnostics = self.build_user_prompt_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
            rerank_weights=rerank_weights,
            retrieval_mode=retrieval_mode,
            keyword_top_k=keyword_top_k,
        )

        answer = self.lmstudio_client.chat(SYSTEM_PROMPT, user_prompt)
        return answer, sources, diagnostics

    def _retrieve_sources(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[list[SourceChunk], list[RetrievalDiagnostic]]:
        active_mode = retrieval_mode or self.retrieval_mode_default
        vector_limit = max(top_k * 2, top_k + 4)
        lexical_limit = keyword_top_k or max(top_k * self.keyword_candidate_multiplier, top_k + 4)

        candidates_by_key: dict[str, tuple[SourceChunk, float, float]] = {}

        if active_mode in {"vector", "hybrid"}:
            query_embedding = embed_query(self.embedding_model, question)
            results = self.vector_store.query(
                query_embedding=query_embedding,
                top_k=vector_limit,
                document_id=document_id,
            )
            for item in results:
                meta = item["metadata"]
                vector_score = float(item["score"])
                chunk = self._build_source_chunk(meta=meta, text=item["text"], vector_score=vector_score, lexical_score=0.0)
                self._merge_candidate(candidates_by_key, chunk, vector_score=vector_score, lexical_score=0.0)

        if active_mode in {"keyword", "hybrid"} and self.keyword_index is not None:
            lexical_results = self.keyword_index.search(
                query_text=question,
                top_k=lexical_limit,
                document_id=document_id,
            )
            for item in lexical_results:
                meta = item["metadata"]
                lexical_score = float(item["score"])
                chunk = self._build_source_chunk(meta=meta, text=item["text"], vector_score=0.0, lexical_score=lexical_score)
                self._merge_candidate(candidates_by_key, chunk, vector_score=0.0, lexical_score=lexical_score)

        candidates = list(candidates_by_key.values())

        active_weights = rerank_weights or self.rerank_weights
        reranked = rerank_hybrid(question, candidates, weights=active_weights)

        sources: list[SourceChunk] = []
        diagnostics: list[RetrievalDiagnostic] = []
        for chunk, ranking_scores in reranked[:top_k]:
            score_map = scores_to_dict(ranking_scores)
            chunk.score = ranking_scores.final_score
            sources.append(chunk)
            diagnostics.append(
                RetrievalDiagnostic(
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page=chunk.page,
                    chunk_index=chunk.chunk_index,
                    document_chunk_count=chunk.document_chunk_count,
                    text_preview=(chunk.text[:200] + "...") if len(chunk.text) > 200 else chunk.text,
                    retrieval_mode=active_mode,
                    **score_map,
                )
            )

        return sources, diagnostics

    def build_user_prompt(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[str, list[SourceChunk]]:
        user_prompt, sources, _ = self.build_user_prompt_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
            retrieval_mode=retrieval_mode,
            keyword_top_k=keyword_top_k,
        )
        return user_prompt, sources

    def build_user_prompt_with_debug(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[str, list[SourceChunk], list[RetrievalDiagnostic]]:
        sources, diagnostics = self._retrieve_sources(
            question=question,
            top_k=top_k,
            document_id=document_id,
            rerank_weights=rerank_weights,
            retrieval_mode=retrieval_mode,
            keyword_top_k=keyword_top_k,
        )

        context_blocks: list[str] = []
        for chunk in sources:
            context_blocks.append(
                f"Documento: {chunk.filename} | Página: {chunk.page}\nTrecho: {chunk.text}"
            )

        context_text = "\n\n".join(context_blocks) if context_blocks else "Sem contexto recuperado."
        user_prompt = build_answer_prompt(question, context_text)
        return user_prompt, sources, diagnostics

    def ask_stream(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[list[str], list[SourceChunk]]:
        tokens, sources, _ = self.ask_stream_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
            retrieval_mode=retrieval_mode,
            keyword_top_k=keyword_top_k,
        )
        return tokens, sources

    def ask_stream_with_debug(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[list[str], list[SourceChunk], list[RetrievalDiagnostic]]:
        user_prompt, sources, diagnostics = self.build_user_prompt_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
            rerank_weights=rerank_weights,
            retrieval_mode=retrieval_mode,
            keyword_top_k=keyword_top_k,
        )
        tokens = list(self.lmstudio_client.chat_stream(SYSTEM_PROMPT, user_prompt))
        return tokens, sources, diagnostics

    # ------------------------------------------------------------------
    # Multi-Query RAG
    # ------------------------------------------------------------------

    def _retrieve_sources_multi_query(
        self,
        question: str,
        top_k: int,
        n_expansions: int = 3,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[list[SourceChunk], list[RetrievalDiagnostic], list[str]]:
        """Expand the question, retrieve for every variant, deduplicate,
        then rerank the merged candidate pool."""
        expanded = expand_query(question, self.lmstudio_client, n=n_expansions)
        all_queries = [question] + expanded

        active_mode = retrieval_mode or self.retrieval_mode_default
        vector_limit = max(top_k * 2, top_k + 4)
        lexical_limit = keyword_top_k or max(top_k * self.keyword_candidate_multiplier, top_k + 4)
        seen: dict[str, tuple[SourceChunk, float, float]] = {}

        for q in all_queries:
            if active_mode in {"vector", "hybrid"}:
                q_embedding = embed_query(self.embedding_model, q)
                results = self.vector_store.query(
                    query_embedding=q_embedding,
                    top_k=vector_limit,
                    document_id=document_id,
                )
                for item in results:
                    meta = item["metadata"]
                    vector_score = float(item["score"])
                    chunk = self._build_source_chunk(meta=meta, text=item["text"], vector_score=vector_score, lexical_score=0.0)
                    self._merge_candidate(seen, chunk, vector_score=vector_score, lexical_score=0.0)

            if active_mode in {"keyword", "hybrid"} and self.keyword_index is not None:
                lexical_results = self.keyword_index.search(
                    query_text=q,
                    top_k=lexical_limit,
                    document_id=document_id,
                )
                for item in lexical_results:
                    meta = item["metadata"]
                    lexical_score = float(item["score"])
                    chunk = self._build_source_chunk(meta=meta, text=item["text"], vector_score=0.0, lexical_score=lexical_score)
                    self._merge_candidate(seen, chunk, vector_score=0.0, lexical_score=lexical_score)

        active_weights = rerank_weights or self.rerank_weights
        reranked = rerank_hybrid(question, list(seen.values()), weights=active_weights)

        sources: list[SourceChunk] = []
        diagnostics: list[RetrievalDiagnostic] = []
        for chunk, ranking_scores in reranked[:top_k]:
            score_map = scores_to_dict(ranking_scores)
            chunk.score = ranking_scores.final_score
            sources.append(chunk)
            diagnostics.append(
                RetrievalDiagnostic(
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page=chunk.page,
                    chunk_index=chunk.chunk_index,
                    document_chunk_count=chunk.document_chunk_count,
                    text_preview=(chunk.text[:200] + "...") if len(chunk.text) > 200 else chunk.text,
                    retrieval_mode=active_mode,
                    **score_map,
                )
            )

        return sources, diagnostics, expanded

    def ask_multi_query(
        self,
        question: str,
        top_k: int,
        n_expansions: int = 3,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[str, list[SourceChunk], list[RetrievalDiagnostic], list[str]]:
        """Full Multi-Query RAG: expand → retrieve → rerank → answer."""
        sources, diagnostics, expanded = self._retrieve_sources_multi_query(
            question=question,
            top_k=top_k,
            n_expansions=n_expansions,
            document_id=document_id,
            rerank_weights=rerank_weights,
            retrieval_mode=retrieval_mode,
            keyword_top_k=keyword_top_k,
        )
        context_blocks = [
            f"Documento: {c.filename} | P\u00e1gina: {c.page}\nTrecho: {c.text}"
            for c in sources
        ]
        context_text = "\n\n".join(context_blocks) if context_blocks else "Sem contexto recuperado."
        user_prompt = build_answer_prompt(question, context_text)
        answer = self.lmstudio_client.chat(SYSTEM_PROMPT, user_prompt)
        return answer, sources, diagnostics, expanded

    def ask_multi_query_stream(
        self,
        question: str,
        top_k: int,
        n_expansions: int = 3,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
        retrieval_mode: str | None = None,
        keyword_top_k: int | None = None,
    ) -> tuple[list[str], list[SourceChunk], list[RetrievalDiagnostic], list[str]]:
        """Streaming variant of Multi-Query RAG."""
        sources, diagnostics, expanded = self._retrieve_sources_multi_query(
            question=question,
            top_k=top_k,
            n_expansions=n_expansions,
            document_id=document_id,
            rerank_weights=rerank_weights,
            retrieval_mode=retrieval_mode,
            keyword_top_k=keyword_top_k,
        )
        context_blocks = [
            f"Documento: {c.filename} | P\u00e1gina: {c.page}\nTrecho: {c.text}"
            for c in sources
        ]
        context_text = "\n\n".join(context_blocks) if context_blocks else "Sem contexto recuperado."
        user_prompt = build_answer_prompt(question, context_text)
        tokens = list(self.lmstudio_client.chat_stream(SYSTEM_PROMPT, user_prompt))
        return tokens, sources, diagnostics, expanded

    @staticmethod
    def _candidate_key(meta: dict) -> str:
        return f"{meta['document_id']}|{meta['page']}|{meta['chunk_index']}"

    @staticmethod
    def _build_source_chunk(meta: dict, text: str, vector_score: float, lexical_score: float) -> SourceChunk:
        return SourceChunk(
            document_id=meta["document_id"],
            filename=meta["filename"],
            page=int(meta["page"]),
            chunk_index=int(meta["chunk_index"]),
            score=max(vector_score, lexical_score),
            text=text,
            document_chunk_count=(
                int(meta["document_chunk_count"])
                if meta.get("document_chunk_count") is not None
                else None
            ),
            lexical_score=lexical_score,
        )

    def _merge_candidate(
        self,
        candidates_by_key: dict[str, tuple[SourceChunk, float, float]],
        chunk: SourceChunk,
        vector_score: float,
        lexical_score: float,
    ) -> None:
        key = self._candidate_key(
            {
                "document_id": chunk.document_id,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
            }
        )
        existing = candidates_by_key.get(key)
        if existing is None:
            chunk.lexical_score = lexical_score
            candidates_by_key[key] = (chunk, vector_score, lexical_score)
            return

        existing_chunk, existing_vector, existing_lexical = existing
        merged_vector = max(existing_vector, vector_score)
        merged_lexical = max(existing_lexical, lexical_score)
        existing_chunk.lexical_score = merged_lexical
        existing_chunk.score = max(merged_vector, merged_lexical)
        candidates_by_key[key] = (existing_chunk, merged_vector, merged_lexical)
