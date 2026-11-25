"""Tools do caderno de um projeto: ler as entradas e os comentários da equipa, e propor alterações.

Só entram no agente quando a conversa decorre num projeto (ver api/agent.py). Não conhecem nenhum assunto: as
secções, as referências e os estados são os que o projeto define. As propostas não são gravadas aqui; vão para a
interface como eventos "proposal" e a pessoa aceita ou rejeita cada uma."""

import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.agent.tools.base import ProjectWorkspace, ToolContext, ToolError, ToolResult, tool
from backend.research.models import Comment, NotebookItem

PREVIEW_CHARS = 400
MAX_LISTED = 80
MAX_COMMENTS = 60

# Origem do conteúdo de uma proposta; fica no source da entrada (source.basis) e aparece no caderno.
Basis = Literal["documents", "assistant", "mixed"]
# Uma citação no formato pedido ao agente: [ficheiro, p.X].
CITATION = re.compile(r"\[[^\[\]]+,\s*p\.?\s*\d+")


def _workspace(context: ToolContext) -> ProjectWorkspace:
    if context.workspace is None:
        raise ToolError("Esta conversa não decorre num projeto.")
    return context.workspace


def _section_titles(workspace: ProjectWorkspace) -> dict[str, str]:
    return {s.key: s.title for s in workspace.project.structure.sections}


def find_item(workspace: ProjectWorkspace, reference: str) -> NotebookItem:
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


def _comment_view(comment: Comment, names: dict[str, str], refs: dict[str, str] | None = None) -> dict:
    view = {"author": names.get(comment.author_id, "?"), "date": comment.created_at[:10], "text": comment.text}
    if comment.via:
        # Escrito por um agente externo em nome do autor (o nome do token).
        view["via"] = comment.via
    if refs is not None:
        # Entrada comentada (referência ou título); None: comentário ao projeto em geral.
        view["item"] = refs.get(comment.item_id, comment.item_id) if comment.item_id else None
    return view


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
    counts: dict[str | None, int] = {}
    for comment in workspace.repository.list_comments(workspace.project.project_id):
        counts[comment.item_id] = counts.get(comment.item_id, 0) + 1
    return ToolResult(
        content={
            "total": len(items),
            "shown": len(shown),
            "items": [_view(item, sections) | {"comments": counts.get(item.item_id, 0)} for item in shown],
            "project_comments": counts.get(None, 0),
        },
        summary=f"{len(items)} entrada(s) no caderno",
    )


class GetItemParams(BaseModel):
    item: str = Field(description="item_id ou referência da entrada (ex.: RF-001).")


@tool(
    name="get_project_item",
    description="Lê uma entrada do caderno do projeto por inteiro, com os comentários da equipa sobre ela.",
    params=GetItemParams,
)
def get_project_item(params: GetItemParams, context: ToolContext) -> ToolResult:
    workspace = _workspace(context)
    item = find_item(workspace, params.item)
    comments = [c for c in workspace.repository.list_comments(workspace.project.project_id) if c.item_id == item.item_id]
    names = workspace.user_names() if comments else {}
    view = _view(item, _section_titles(workspace), full=True) | {"comments": [_comment_view(c, names) for c in comments]}
    return ToolResult(content=view, summary=f"Entrada {item.ref or item.title[:40]}")


class ListCommentsParams(BaseModel):
    item: str | None = Field(default=None, description="Só os comentários desta entrada (item_id ou referência); vazio: todos.")
    query: str | None = Field(default=None, description="Texto a procurar nos comentários (opcional).")


@tool(
    name="list_project_comments",
    description=(
        "Lista os comentários da equipa no projeto (ao projeto em geral e às entradas do caderno), dos mais recentes "
        "para os mais antigos, com autor, data e a entrada comentada. Usa para saber o que a equipa discutiu, "
        "pediu ou deixou em aberto."
    ),
    params=ListCommentsParams,
)
def list_project_comments(params: ListCommentsParams, context: ToolContext) -> ToolResult:
    workspace = _workspace(context)
    comments = workspace.repository.list_comments(workspace.project.project_id)
    if params.item:
        item_id = find_item(workspace, params.item).item_id
        comments = [c for c in comments if c.item_id == item_id]
    if params.query and params.query.strip():
        wanted = params.query.strip().lower()
        comments = [c for c in comments if wanted in c.text.lower()]
    comments.sort(key=lambda c: c.created_at, reverse=True)
    shown = comments[:MAX_COMMENTS]
    refs = {i.item_id: i.ref or i.title[:60] for i in workspace.repository.list_items(workspace.project.project_id)} if shown else {}
    names = workspace.user_names() if shown else {}
    return ToolResult(
        content={"total": len(comments), "shown": len(shown), "comments": [_comment_view(c, names, refs) for c in shown]},
        summary=f"{len(comments)} comentário(s)",
    )


class ItemChange(BaseModel):
    action: Literal["create", "update"]
    item: str | None = Field(default=None, description="Na alteração: item_id ou referência da entrada a alterar.")
    section: str | None = Field(default=None, description="Chave da secção (ver a estrutura do projeto).")
    ref: str | None = Field(default=None, max_length=64, description="Referência curta, seguindo a numeração da secção.")
    title: str | None = None
    text: str | None = None
    status: str | None = Field(default=None, description="Um dos estados do projeto.")
    reason: str = Field(default="", description="Porquê desta alteração, numa frase (de onde vem, o que corrige).")
    basis: Basis = Field(
        default="assistant",
        description=(
            "De onde vem o título/texto: documents (tudo dos documentos, com citações [ficheiro, p.X] no texto), "
            "assistant (contributo teu: ideia, rascunho, conhecimento geral) ou mixed (as duas coisas)."
        ),
    )


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
            if "title" in fields or "text" in fields:
                # A origem só conta quando o conteúdo muda (mudar o estado ou a secção não a altera).
                if change.basis == "documents" and not CITATION.search(fields.get("text", "")):
                    raise ToolError("basis=documents precisa de citações [ficheiro, p.X] no texto; cita ou usa mixed/assistant")
                proposal["basis"] = change.basis
            if change.action == "create":
                if not (fields.get("title") or fields.get("text")):
                    raise ToolError("uma entrada nova precisa de título ou texto")
                fields.setdefault("status", structure.statuses[0] if structure.statuses else "")
                proposal["changes"] = fields
            else:
                if not change.item:
                    raise ToolError("indica a entrada a alterar em 'item'")
                item = find_item(workspace, change.item)
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


PROJECT_TOOLS = [list_project_items, get_project_item, list_project_comments, propose_item_changes]
