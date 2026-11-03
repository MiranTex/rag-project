from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.security import require
from backend.api.sse import sse_event, stop_on_disconnect
from backend.auth.permissions import CHAT_SELECT_DOCUMENT, CHAT_USE, AuthenticatedUser
from backend.config import get_settings
from backend.dependencies import get_rag_pipeline
from backend.models import AskRequest, AskResponse
from backend.services.rag_pipeline import SYSTEM_PROMPT

router = APIRouter(prefix="/chat", tags=["chat"])


def _validated(payload: AskRequest, user: AuthenticatedUser) -> str:
    """Pergunta limpa; restringir a um documento (document_id) exige permissão própria."""
    if payload.document_id and not user.can(CHAT_SELECT_DOCUMENT):
        raise HTTPException(status_code=403, detail="Sem permissão para escolher um documento.")
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pergunta inválida.")
    return question


@router.post("/ask", response_model=AskResponse)
def ask_question(payload: AskRequest, user: AuthenticatedUser = Depends(require(CHAT_USE))) -> AskResponse:
    question = _validated(payload, user)

    settings = get_settings()
    top_k = payload.top_k or settings.top_k
    retrieval_mode = payload.retrieval_mode or settings.retrieval_mode_default

    pipeline = get_rag_pipeline()
    if payload.multi_query:
        answer, sources, diagnostics, expanded = pipeline.ask_multi_query(
            question=question,
            top_k=top_k,
            document_id=payload.document_id,
            n_expansions=payload.multi_query_n,
            retrieval_mode=retrieval_mode,
            keyword_top_k=payload.keyword_top_k,
        )
        return AskResponse(
            answer=answer,
            sources=sources,
            retrieval_diagnostics=diagnostics if payload.include_debug else None,
            expanded_queries=expanded if payload.include_debug else None,
        )

    if payload.include_debug:
        answer, sources, diagnostics = pipeline.ask_with_debug(
            question=question,
            top_k=top_k,
            document_id=payload.document_id,
            retrieval_mode=retrieval_mode,
            keyword_top_k=payload.keyword_top_k,
        )
        return AskResponse(
            answer=answer,
            sources=sources,
            retrieval_diagnostics=diagnostics,
        )

    answer, sources = pipeline.ask(
        question=question,
        top_k=top_k,
        document_id=payload.document_id,
        retrieval_mode=retrieval_mode,
        keyword_top_k=payload.keyword_top_k,
    )
    return AskResponse(answer=answer, sources=sources)


@router.post("/ask-stream")
def ask_question_stream(payload: AskRequest, user: AuthenticatedUser = Depends(require(CHAT_USE))) -> StreamingResponse:
    question = _validated(payload, user)

    settings = get_settings()
    top_k = payload.top_k or settings.top_k
    retrieval_mode = payload.retrieval_mode or settings.retrieval_mode_default

    pipeline = get_rag_pipeline()

    def stream() -> Iterator[str]:
        try:
            if payload.multi_query:
                tokens, sources, diagnostics, expanded = pipeline.ask_multi_query_stream(
                    question=question,
                    top_k=top_k,
                    document_id=payload.document_id,
                    n_expansions=payload.multi_query_n,
                    retrieval_mode=retrieval_mode,
                    keyword_top_k=payload.keyword_top_k,
                )
                yield sse_event("sources", {"sources": [src.model_dump() for src in sources]})
                if payload.include_debug:
                    yield sse_event("expanded_queries", {"expanded_queries": expanded})
                    yield sse_event(
                        "diagnostics",
                        {"retrieval_diagnostics": [item.model_dump() for item in diagnostics]},
                    )
                for token in tokens:
                    yield sse_event("token", {"token": token})
                yield sse_event("done", {"answer": "".join(tokens)})
                return

            user_prompt, sources, diagnostics = pipeline.build_user_prompt_with_debug(
                question=question,
                top_k=top_k,
                document_id=payload.document_id,
                retrieval_mode=retrieval_mode,
                keyword_top_k=payload.keyword_top_k,
            )
            yield sse_event("sources", {"sources": [src.model_dump() for src in sources]})
            if payload.include_debug:
                yield sse_event(
                    "diagnostics",
                    {"retrieval_diagnostics": [item.model_dump() for item in diagnostics]},
                )

            answer_tokens: list[str] = []
            for token in pipeline.lmstudio_client.chat_stream(SYSTEM_PROMPT, user_prompt):
                answer_tokens.append(token)
                yield sse_event("token", {"token": token})

            yield sse_event("done", {"answer": "".join(answer_tokens)})
        except Exception as exc:
            yield sse_event("error", {"detail": str(exc)})

    return StreamingResponse(
        stop_on_disconnect(stream(), f"Resposta RAG ({question[:60]})"),
        media_type="text/event-stream",
    )
