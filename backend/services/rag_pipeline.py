import re

from backend.models import RetrievalDiagnostic, SourceChunk
from backend.services.embeddings import embed_query
from backend.services.lmstudio_client import LMStudioClient
from backend.services.reranker import rerank_hybrid, scores_to_dict
from backend.services.vector_store import VectorStore


SYSTEM_PROMPT = """
És um assistente de estudo em PT-PT.
Responde apenas com base no contexto fornecido.
Se o contexto não for suficiente, diz claramente que não tens informação suficiente.
Inclui sempre uma resposta objetiva e curta.
""".strip()


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", text.lower()) if token}


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
        lmstudio_client: LMStudioClient,
        rerank_weights: dict[str, float] | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        self.lmstudio_client = lmstudio_client
        self.rerank_weights = rerank_weights

    def ask(self, question: str, top_k: int, document_id: str | None = None) -> tuple[str, list[SourceChunk]]:
        answer, sources, _ = self.ask_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
        )
        return answer, sources

    def ask_with_debug(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
    ) -> tuple[str, list[SourceChunk], list[RetrievalDiagnostic]]:
        user_prompt, sources, diagnostics = self.build_user_prompt_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
            rerank_weights=rerank_weights,
        )

        answer = self.lmstudio_client.chat(SYSTEM_PROMPT, user_prompt)
        return answer, sources, diagnostics

    def _retrieve_sources(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
    ) -> tuple[list[SourceChunk], list[RetrievalDiagnostic]]:
        query_embedding = embed_query(self.embedding_model, question)
        results = self.vector_store.query(
            query_embedding=query_embedding,
            top_k=max(top_k * 2, top_k + 4),
            document_id=document_id,
        )

        candidates: list[tuple[SourceChunk, float]] = []
        for item in results:
            meta = item["metadata"]
            vector_score = float(item["score"])
            candidates.append(
                (
                    SourceChunk(
                        document_id=meta["document_id"],
                        filename=meta["filename"],
                        page=int(meta["page"]),
                        chunk_index=int(meta["chunk_index"]),
                        score=vector_score,
                        text=item["text"],
                        document_chunk_count=(
                            int(meta["document_chunk_count"])
                            if meta.get("document_chunk_count") is not None
                            else None
                        ),
                    ),
                    vector_score,
                )
            )

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
                    **score_map,
                )
            )

        return sources, diagnostics

    def build_user_prompt(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
    ) -> tuple[str, list[SourceChunk]]:
        user_prompt, sources, _ = self.build_user_prompt_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
        )
        return user_prompt, sources

    def build_user_prompt_with_debug(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
    ) -> tuple[str, list[SourceChunk], list[RetrievalDiagnostic]]:
        sources, diagnostics = self._retrieve_sources(
            question=question,
            top_k=top_k,
            document_id=document_id,
            rerank_weights=rerank_weights,
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
    ) -> tuple[list[str], list[SourceChunk]]:
        tokens, sources, _ = self.ask_stream_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
        )
        return tokens, sources

    def ask_stream_with_debug(
        self,
        question: str,
        top_k: int,
        document_id: str | None = None,
        rerank_weights: dict[str, float] | None = None,
    ) -> tuple[list[str], list[SourceChunk], list[RetrievalDiagnostic]]:
        user_prompt, sources, diagnostics = self.build_user_prompt_with_debug(
            question=question,
            top_k=top_k,
            document_id=document_id,
            rerank_weights=rerank_weights,
        )
        tokens = list(self.lmstudio_client.chat_stream(SYSTEM_PROMPT, user_prompt))
        return tokens, sources, diagnostics
