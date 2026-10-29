from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.agent.profiles import BLOCKED_MESSAGE, DEFAULT_PROFILE, PROFILES, AgentProfile
from backend.agent.runner import AgentRunner
from backend.agent.tools import ToolContext
from backend.api.sse import sse_event
from backend.config import get_settings
from backend.dependencies import (
    get_export_store,
    get_lmstudio_client,
    get_rag_pipeline,
    get_registry,
    get_scope_guard,
    get_tool_registry,
    get_vector_store,
)
from backend.models import AgentAskRequest, AgentProfileInfo

router = APIRouter(prefix="/agent", tags=["agent"])

HISTORY_TURNS = 6


@router.get("/profiles", response_model=list[AgentProfileInfo])
def list_profiles() -> list[AgentProfileInfo]:
    registry = get_tool_registry()
    return [
        AgentProfileInfo(
            name=profile.name,
            label=profile.label,
            description=profile.description,
            tools=[t.name for t in registry.select(profile.tool_names)],
        )
        for profile in PROFILES.values()
    ]


def _resolve_profile(payload: AgentAskRequest) -> AgentProfile:
    profile = PROFILES.get(payload.profile or DEFAULT_PROFILE)
    if profile is None:
        raise HTTPException(status_code=400, detail=f"Perfil desconhecido: {payload.profile}")
    return profile


def _build_runner(payload: AgentAskRequest, profile: AgentProfile) -> AgentRunner:
    settings = get_settings()
    scope_note = None
    if payload.document_id:
        document = get_registry().find_by_id(payload.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Documento não encontrado.")
        scope_note = (
            f"O utilizador selecionou o documento '{document.filename}' (document_id={document.document_id}); "
            "as pesquisas ficam restringidas a ele por defeito."
        )

    context = ToolContext(
        pipeline=get_rag_pipeline(),
        vector_store=get_vector_store(),
        registry=get_registry(),
        export_store=get_export_store(),
        top_k=settings.top_k,
        default_document_id=payload.document_id,
    )
    return AgentRunner(
        llm=get_lmstudio_client(),
        tools=get_tool_registry().select(profile.tool_names),
        system_prompt=profile.system_prompt(scope_note),
        context=context,
        max_steps=settings.agent_max_steps,
    )


def _history_messages(payload: AgentAskRequest) -> list[dict]:
    messages: list[dict] = []
    for turn in payload.history[-HISTORY_TURNS:]:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer})
    return messages


@router.post("/ask-stream")
def ask_agent_stream(payload: AgentAskRequest) -> StreamingResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pergunta inválida.")

    profile = _resolve_profile(payload)
    runner = _build_runner(payload, profile)
    history = _history_messages(payload)
    guard_enabled = get_settings().guard_enabled

    def stream() -> Iterator[str]:
        try:
            if guard_enabled:
                decision = get_scope_guard().check(
                    question,
                    history,
                    document_names=[d.filename for d in get_registry().list_documents() if d.status == "indexed"],
                    blocked_categories=profile.blocked_categories,
                )
                yield sse_event("guard", vars(decision))
                if not decision.allowed:
                    yield sse_event("answer", {"answer": BLOCKED_MESSAGE, "steps": 0, "blocked": True})
                    yield sse_event("done", {})
                    return

            for event in runner.run(question, history):
                yield sse_event(event.type, event.data)
            yield sse_event("done", {})
        except Exception as exc:
            yield sse_event("error", {"detail": str(exc)})

    return StreamingResponse(stream(), media_type="text/event-stream")
