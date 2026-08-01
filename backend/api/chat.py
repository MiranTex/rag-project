import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.config import get_settings
from backend.dependencies import get_rag_pipeline
from backend.models import AskRequest, AskResponse
from backend.services.rag_pipeline import SYSTEM_PROMPT

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ask", response_model=AskResponse)
def ask_question(payload: AskRequest) -> AskResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pergunta inválida.")

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


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/ask-stream")
def ask_question_stream(payload: AskRequest) -> StreamingResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pergunta inválida.")

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
                yield _sse_event("sources", {"sources": [src.model_dump() for src in sources]})
                if payload.include_debug:
                    yield _sse_event("expanded_queries", {"expanded_queries": expanded})
                    yield _sse_event(
                        "diagnostics",
                        {"retrieval_diagnostics": [item.model_dump() for item in diagnostics]},
                    )
                for token in tokens:
                    yield _sse_event("token", {"token": token})
                yield _sse_event("done", {"answer": "".join(tokens)})
                return

            user_prompt, sources, diagnostics = pipeline.build_user_prompt_with_debug(
                question=question,
                top_k=top_k,
                document_id=payload.document_id,
                retrieval_mode=retrieval_mode,
                keyword_top_k=payload.keyword_top_k,
            )
            yield _sse_event("sources", {"sources": [src.model_dump() for src in sources]})
            if payload.include_debug:
                yield _sse_event(
                    "diagnostics",
                    {"retrieval_diagnostics": [item.model_dump() for item in diagnostics]},
                )

            answer_tokens: list[str] = []
            for token in pipeline.lmstudio_client.chat_stream(SYSTEM_PROMPT, user_prompt):
                answer_tokens.append(token)
                yield _sse_event("token", {"token": token})

            yield _sse_event("done", {"answer": "".join(answer_tokens)})
        except Exception as exc:
            yield _sse_event("error", {"detail": str(exc)})

    return StreamingResponse(stream(), media_type="text/event-stream")
