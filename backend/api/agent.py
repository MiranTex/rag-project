from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.agent.profiles import BLOCKED_MESSAGE, DEFAULT_PROFILE, PROFILES, AgentProfile
from backend.agent.runner import AgentRunner
from backend.agent.tools import ToolContext
from backend.agent.tools.base import ProjectWorkspace
from backend.agent.tools.project import PROJECT_TOOLS
from backend.api.security import require
from backend.api.sse import sse_event, stop_on_disconnect
from backend.auth.permissions import CHAT_SELECT_DOCUMENT, CHAT_USE, AuthenticatedUser
from backend.config import get_settings
from backend.dependencies import (
    get_document_types,
    get_export_store,
    get_extraction_store,
    get_lmstudio_client,
    get_profile_store,
    get_rag_pipeline,
    get_registry,
    get_research_repository,
    get_scope_guard,
    get_tool_registry,
    get_vector_store,
)
from backend.models import AgentAskRequest, AgentProfileInfo
from backend.research.access import load_project, project_scope
from backend.research.models import Project

router = APIRouter(prefix="/agent", tags=["agent"])

HISTORY_TURNS = 6


@router.get("/profiles", response_model=list[AgentProfileInfo], dependencies=[Depends(require(CHAT_USE))])
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


def project_note(project: Project, document_count: int, item_count: int, can_edit: bool) -> str:
    """O que o agente sabe do projeto. Genérico: o objetivo, as secções e os estados são os do próprio projeto."""
    lines = [f"A conversa decorre no projeto '{project.title}'."]
    if project.question:
        lines.append(f"Objetivo do projeto: {project.question}")
    if project.description:
        lines.append(f"Descrição: {project.description}")
    if project.structure.sections:
        lines.append("Secções do caderno (chave: título — o que entra):")
        lines += [f"- {s.key}: {s.title}" + (f" — {s.description}" if s.description else "") for s in project.structure.sections]
    if project.structure.statuses:
        lines.append(f"Estados possíveis de uma entrada, por ordem: {', '.join(project.structure.statuses)}.")
    if document_count:
        lines.append(f"As pesquisas estão limitadas aos {document_count} documento(s) fixados no projeto.")
    else:
        lines.append(
            "O projeto ainda não tem documentos fixados: as pesquisas não encontram nada. Trabalha a partir do caderno "
            "e do que a pessoa disser, e sugere fixar documentos quando for preciso apoiar algo numa fonte."
        )
    lines.append(
        f"O caderno tem {item_count} entrada(s): usa list_project_items e get_project_item para as conhecer antes de "
        "responder sobre o que o projeto já tem."
    )
    lines.append(
        "Quando a pessoa pedir para acrescentar, corrigir ou completar o projeto (ou quando a tua resposta trouxer "
        "conteúdo que claramente pertence ao caderno), usa propose_item_changes: uma entrada por ideia, na secção "
        "certa, a seguir a numeração de referências que já existe, com a origem [ficheiro, p.X] no texto quando vier "
        "dos documentos. As propostas só ficam no caderno quando a pessoa as aceitar; nunca digas que já alteraste."
    )
    if not can_edit:
        lines.append("Esta pessoa só pode ler e comentar o projeto: pode ver propostas, mas não as aplicar.")
    return "\n".join(lines)


def _build_runner(payload: AgentAskRequest, profile: AgentProfile, user: AuthenticatedUser) -> AgentRunner:
    settings = get_settings()
    scope_note = None
    if payload.document_id:
        if not user.can(CHAT_SELECT_DOCUMENT):
            raise HTTPException(status_code=403, detail="Sem permissão para escolher um documento.")
        document = get_registry().find_by_id(payload.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Documento não encontrado.")
        scope_note = (
            f"O utilizador selecionou o documento '{document.filename}' (document_id={document.document_id}); "
            "as pesquisas ficam restringidas a ele por defeito."
        )
    scope = project_scope(payload.project_id, user, allow_empty=True)
    workspace = None
    if scope is not None:
        project, role = load_project(payload.project_id, user)
        repository = get_research_repository()
        workspace = ProjectWorkspace(project=project, repository=repository, can_edit=role != "viewer")
        scope_note = project_note(project, len(scope), repository.count_items(project.project_id), workspace.can_edit)

    context = ToolContext(
        pipeline=get_rag_pipeline(),
        vector_store=get_vector_store(),
        registry=get_registry(),
        export_store=get_export_store().for_owner(user.user_id),
        top_k=settings.top_k,
        default_document_id=payload.document_id,
        extraction_store=get_extraction_store(),
        document_types=get_document_types(),
        profile_store=get_profile_store(),
        embedding_model=settings.embedding_model,
        scope_document_ids=scope,
        workspace=workspace,
    )
    tools = get_tool_registry().select(profile.tool_names)
    if workspace is not None:
        tools = [*tools, *PROJECT_TOOLS]
    return AgentRunner(
        llm=get_lmstudio_client(),
        tools=tools,
        system_prompt=profile.system_prompt(scope_note, settings.knowledge_base_description),
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
def ask_agent_stream(payload: AgentAskRequest, user: AuthenticatedUser = Depends(require(CHAT_USE))) -> StreamingResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pergunta inválida.")

    profile = _resolve_profile(payload)
    runner = _build_runner(payload, profile, user)
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

    return StreamingResponse(
        stop_on_disconnect(stream(), f"Run do agente ({question[:60]})"),
        media_type="text/event-stream",
    )
