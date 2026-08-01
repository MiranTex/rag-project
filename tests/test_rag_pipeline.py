from backend.services.rag_pipeline import RagPipeline, build_answer_prompt, score_candidate


def test_hybrid_score_prefers_keyword_overlap() -> None:
    relevant = score_candidate(
        question="gestão de contratos",
        chunk_text="Resumo sobre gestão de contratos e processos",
        vector_score=0.8,
    )
    irrelevant = score_candidate(
        question="gestão de contratos",
        chunk_text="texto sem relação com contratos",
        vector_score=0.9,
    )

    assert relevant > irrelevant


def test_answer_prompt_is_more_strict_with_context() -> None:
    prompt = build_answer_prompt("O que diz o documento?", "Contexto relevante sobre contratos")

    assert "Baseia-te apenas no contexto recuperado." in prompt
    assert "Não inventes factos" in prompt
    assert "cita sempre a fonte" in prompt
    assert "Fontes usadas:" in prompt
    assert "Formato obrigatório:" in prompt


class _FakeVectorStore:
    def query(self, query_embedding: list[float], top_k: int, document_id: str | None = None) -> list[dict]:
        return [
            {
                "text": "Trecho genérico sem muita relação com a pergunta.",
                "metadata": {
                    "document_id": "doc-1",
                    "filename": "memoria.pdf",
                    "page": 10,
                    "chunk_index": 20,
                    "document_chunk_count": 30,
                },
                "score": 0.91,
            },
            {
                "text": "Resumo sobre gestão de contratos, projetos, orçamento e estado do projeto.",
                "metadata": {
                    "document_id": "doc-1",
                    "filename": "memoria.pdf",
                    "page": 1,
                    "chunk_index": 1,
                    "document_chunk_count": 30,
                },
                "score": 0.83,
            },
        ]


class _FakeLMStudioClient:
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        return "ok"


def test_build_user_prompt_with_debug_returns_diagnostics(monkeypatch) -> None:
    monkeypatch.setattr("backend.services.rag_pipeline.embed_query", lambda model_name, question: [0.1, 0.2])
    pipeline = RagPipeline(
        embedding_model="fake-model",
        vector_store=_FakeVectorStore(),
        lmstudio_client=_FakeLMStudioClient(),
    )

    prompt, sources, diagnostics = pipeline.build_user_prompt_with_debug(
        question="gestão de contratos",
        top_k=2,
    )

    assert "Contexto recuperado" in prompt
    assert len(sources) == 2
    assert len(diagnostics) == 2
    assert diagnostics[0].final_score >= diagnostics[1].final_score
    assert diagnostics[0].position_penalty >= diagnostics[1].position_penalty
    assert sources[0].page == 1


def test_pipeline_uses_instance_default_rerank_weights(monkeypatch) -> None:
    monkeypatch.setattr("backend.services.rag_pipeline.embed_query", lambda model_name, question: [0.1, 0.2])
    pipeline = RagPipeline(
        embedding_model="fake-model",
        vector_store=_FakeVectorStore(),
        lmstudio_client=_FakeLMStudioClient(),
        rerank_weights={"vector": 0.2, "keyword": 0.6, "position": 0.1, "density": 0.1},
    )

    _, _, diagnostics = pipeline.build_user_prompt_with_debug(
        question="gestão de contratos",
        top_k=2,
    )

    assert len(diagnostics) == 2
    assert diagnostics[0].final_score >= diagnostics[1].final_score


def test_pipeline_allows_per_call_rerank_weight_override(monkeypatch) -> None:
    monkeypatch.setattr("backend.services.rag_pipeline.embed_query", lambda model_name, question: [0.1, 0.2])
    pipeline = RagPipeline(
        embedding_model="fake-model",
        vector_store=_FakeVectorStore(),
        lmstudio_client=_FakeLMStudioClient(),
        rerank_weights={"vector": 0.6, "keyword": 0.25, "position": 0.1, "density": 0.05},
    )

    _, _, default_diag = pipeline.build_user_prompt_with_debug(
        question="gestão de contratos",
        top_k=2,
    )
    _, _, override_diag = pipeline.build_user_prompt_with_debug(
        question="gestão de contratos",
        top_k=2,
        rerank_weights={"vector": 0.1, "keyword": 0.7, "position": 0.1, "density": 0.1},
    )

    assert len(default_diag) == len(override_diag) == 2
    assert any(a.final_score != b.final_score for a, b in zip(default_diag, override_diag, strict=False))
