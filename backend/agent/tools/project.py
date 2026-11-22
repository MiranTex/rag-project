"""Tools do caderno de um projeto: ler as entradas e propor alterações.

Só entram no agente quando a conversa decorre num projeto (ver api/agent.py). Não conhecem nenhum assunto: as
secções, as referências e os estados são os que o projeto define. As propostas não são gravadas aqui; vão para a
interface como eventos "proposal" e a pessoa aceita ou rejeita cada uma."""

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.agent.tools.base import ProjectWorkspace, ToolContext, ToolError, ToolResult, tool
from backend.research.models import NotebookItem

PREVIEW_CHARS = 400
MAX_LISTED = 80


def _workspace(context: ToolContext) -> ProjectWorkspace:
    if context.workspace is None:
        raise ToolError("Esta conversa não decorre num projeto.")
    return context.workspace


def _section_titles(workspace: ProjectWorkspace) -> dict[str, str]:
    return {s.key: s.title for s in workspace.project.structure.sections}


def _find_item(workspace: ProjectWorkspace, reference: str) -> NotebookItem:
    """Encontra uma entrada pelo item_id ou pela referência (RF-001…), sem distinguir maiúsculas."""
    reference = reference.strip()
    items = workspace.repository.list_items(workspace.project.project_id)
    for item in items:
        if item.item_id == reference:
            return item
    matches = [item for item in items if item.ref and item.ref.lower() == reference.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ToolError(f"Há {len(matches)} entradas com a referência {reference}; usa o item_id.")
    raise ToolError(f"Entrada não encontrada: {reference}. Usa list_project_items para ver as que existem.")


def _view(item: NotebookItem, sections: dict[str, str], full: bool = False) -> dict:
    text = item.text if full else item.text[:PREVIEW_CHARS] + ("…" if len(item.text) > PREVIEW_CHARS else "")
    view = {
        "item_id": item.item_id,
        "ref": item.ref,
        "section": sections.get(item.section, item.section),
        "section_key": item.section,
        "status": item.status,
        "kind": item.kind,
        "title": item.title,
        "text": text,
    }
    if full:
        view["fields"] = item.fields
        view["sources"] = item.source.get("sources", [])
    return view


class ListItemsParams(BaseModel):
    section: str | None = Field(default=None, description="Chave ou título de uma secção do projeto (opcional).")
    query: str | None = Field(default=None, description="Texto a procurar no título e no conteúdo (opcional).")
    status: str | None = Field(default=None, description="Só entradas com este estado (opcional).")


@tool(
    name="list_project_items",
    description=(
        "Lista as entradas do caderno do projeto (referência, secção, estado, título e o início do texto). "
        "Usa antes de propor alterações, para saber o que já existe e não duplicar."
    ),
    params=ListItemsParams,
)
def list_project_items(params: ListItemsParams, context: ToolContext) -> ToolResult:
    workspace = _workspace(context)
    sections = _section_titles(workspace)
    items = workspace.repository.list_items(workspace.project.project_id, query=params.query.strip() if params.query else None)
    if params.section:
        wanted = params.section.strip().lower()
        keys = {key for key, title in sections.items() if wanted in (key.lower(), title.lower())}
        items = [item for item in items if item.section in keys]
    if params.status:
        items = [item for item in items if item.status.lower() == params.status.strip().lower()]
    order = {key: n for n, key in enumerate(sections)}
    items.sort(key=lambda i: (order.get(i.section, len(order)), i.ref or "~", i.created_at))
    shown = items[:MAX_LISTED]
    return ToolResult(
        content={
            "total": len(items),
            "shown": len(shown),
            "items": [_view(item, sections) for item in shown],
        },
        summary=f"{len(items)} entrada(s) no caderno",
    )


class GetItemParams(BaseModel):
    item: str = Field(description="item_id ou referência da entrada (ex.: RF-001).")


@tool(name="get_project_item", description="Lê uma entrada do caderno do projeto por inteiro.", params=GetItemParams)
def get_project_item(params: GetItemParams, context: ToolContext) -> ToolResult:
    workspace = _workspace(context)
    item = _find_item(workspace, params.item)
    return ToolResult(content=_view(item, _section_titles(workspace), full=True), summary=f"Entrada {item.ref or item.title[:40]}")


class ItemChange(BaseModel):
    action: Literal["create", "update"]
    item: str | None = Field(default=None, description="Na alteração: item_id ou referência da entrada a alterar.")
    section: str | None = Field(default=None, description="Chave da secção (ver a estrutura do projeto).")
    ref: str | None = Field(default=None, max_length=64, description="Referência curta, seguindo a numeração da secção.")
    title: str | None = None
    text: str | None = None
    status: str | None = Field(default=None, description="Um dos estados do projeto.")
    reason: str = Field(default="", description="Porquê desta alteração, numa frase (de onde vem, o que corrige).")


class ProposeParams(BaseModel):
    changes: list[ItemChange] = Field(min_length=1, max_length=30)


@tool(
    name="propose_item_changes",
    description=(
        "Propõe entradas novas ou alterações a entradas existentes do caderno do projeto. Não grava nada: a "
        "pessoa vê cada proposta e aceita ou rejeita. Na alteração, indica só os campos que mudam."
    ),
    params=ProposeParams,
)
def propose_item_changes(params: ProposeParams, context: ToolContext) -> ToolResult:
    workspace = _workspace(context)
    structure = workspace.project.structure
    sections = _section_titles(workspace)
    proposals, errors = [], []

    def resolve_section(value: str | None) -> str | None:
        if value is None:
            return None
        wanted = value.strip().lower()
        for key, title in sections.items():
            if wanted in (key.lower(), title.lower()):
                return key
        if wanted:
            raise ToolError(f"secção desconhecida '{value}' (existem: {', '.join(sections) or 'nenhuma'})")
        return ""

    def resolve_status(value: str | None) -> str | None:
        if value is None:
            return None
        status = value.strip().lower()
        if status and status not in structure.statuses:
            raise ToolError(f"estado desconhecido '{value}' (existem: {', '.join(structure.statuses) or 'nenhum'})")
        return status

    for n, change in enumerate(params.changes, start=1):
        try:
            section, status = resolve_section(change.section), resolve_status(change.status)
            fields = {
                key: value
                for key, value in {
                    "section": section,
                    "ref": change.ref.strip() if change.ref is not None else None,
                    "title": change.title.strip() if change.title is not None else None,
                    "text": change.text.strip() if change.text is not None else None,
                    "status": status,
                }.items()
                if value is not None
            }
            proposal = {"proposal_id": str(uuid4()), "action": change.action, "reason": change.reason.strip()}
            if change.action == "create":
                if not (fields.get("title") or fields.get("text")):
                    raise ToolError("uma entrada nova precisa de título ou texto")
                fields.setdefault("status", structure.statuses[0] if structure.statuses else "")
                proposal["changes"] = fields
            else:
                if not change.item:
                    raise ToolError("indica a entrada a alterar em 'item'")
                item = _find_item(workspace, change.item)
                changed = {key: value for key, value in fields.items() if getattr(item, key) != value}
                if not changed:
                    raise ToolError(f"a proposta não muda nada em {change.item}")
                proposal.update(
                    item_id=item.item_id,
                    changes=changed,
                    before={key: getattr(item, key) for key in changed} | {"ref": item.ref, "title": item.title},
                )
            proposal["section_title"] = sections.get(fields.get("section", ""), "")
            proposals.append(proposal)
        except ToolError as exc:
            errors.append(f"alteração {n}: {exc}")

    if not proposals:
        raise ToolError("; ".join(errors))
    note = "Propostas enviadas à pessoa; só ficam no caderno se forem aceites. Não digas que já foram aplicadas."
    if not workspace.can_edit:
        note += " Esta pessoa só pode ler o projeto: quem edita terá de as aplicar."
    return ToolResult(
        content={"proposed": len(proposals), "errors": errors, "note": note},
        summary=f"{len(proposals)} proposta(s) de alteração" + (f", {len(errors)} recusada(s)" if errors else ""),
        proposals=proposals,
    )


PROJECT_TOOLS = [list_project_items, get_project_item, propose_item_changes]
