"""As funções da área de pesquisa que na interface usam o LLM da plataforma (estado da arte, matriz, esqueleto, mapa
do tema, lacunas, verificação de afirmações), em versão para agentes externos: a plataforma dá o material (os
mesmos excertos, fichas e contagens, sem LLM) e as regras; o agente da pessoa escreve. O resultado volta por
save_matrix (matriz) ou por propose_item_changes (rascunhos para o caderno, que a equipa aceita).

Também os prompts MCP: fluxos prontos que aparecem como comandos (/…) no Claude Code e no claude.ai."""

from mcp import types
from pydantic import BaseModel, Field

from backend.agent.tools.base import ToolError
from backend.api.research_projects import MAX_MATRIX_DOCUMENTS
from backend.dependencies import get_extraction_store, get_registry, get_research_repository
from backend.research.access import load_project, project_document_ids
from backend.research.bibliography import bibliography
from backend.research.discovery import check_claims, gaps, theme_map
from backend.research.library import indexed_cards
from backend.research.writing import fill_matrix, skeleton, state_of_art_sources
from backend.services.search_filters import SearchFilters

# Importado de server.py só dentro das funções (server.py importa este módulo ao montar as tools).

STATE_OF_ART_RULES = """Escreve o estado da arte em português, só com o que está nestes excertos:
- Organiza por temas (subtítulos ##), não documento a documento; compara e relaciona os trabalhos.
- Cada frase termina com a citação no formato [ficheiro, p.X] (usa filename e page do excerto).
- Não acrescentes factos do teu conhecimento; se os excertos não chegam para um ponto, não o escrevas.
- No fim, a bibliografia que vem em "bibliography".
Para o deixar no projeto, usa propose_item_changes (uma entrada com o texto, basis "documents"): a equipa aceita ou não."""

MATRIX_RULES = """Para cada documento e dimensão, escreve um resumo de uma frase do que os excertos dizem; se não falam
da dimensão, escreve "Não referido". Usa só os excertos. Guarda com save_matrix (as notas da equipa mantêm-se)."""

SKELETON_RULES = """Para cada secção, escreve 2 a 4 perguntas concretas a que ela deve responder sobre o tema, apoiadas
nos excertos "relevant" (do projeto) e nos "examples" (como outros trabalhos da base escreveram essa secção).
Para o deixar no projeto, usa propose_item_changes (uma entrada por secção, ou uma só com o índice)."""


def _caller_context(caller, project_id: str | None):
    from backend.mcp_server.server import _project_context

    return _project_context(caller.user, project_id)


def _filters(context) -> SearchFilters:
    return SearchFilters(document_ids=context.scope_document_ids)


def _project_cards(caller, project_id: str, needs: str = "viewer"):
    project, _ = load_project(project_id, caller.user, needs)
    ids = project_document_ids(project_id)
    if not ids:
        raise ToolError("O projeto não tem documentos fixados: fixa-os na interface (separador Documentos) primeiro.")
    return project, indexed_cards(get_registry(), get_extraction_store(), ids)


# ---- Estado da arte ----


class StateOfArtParams(BaseModel):
    project_id: str = Field(description="Id do projeto (ver list_projects).")
    topic: str = Field(default="", description="Tema; vazio usa o objetivo do projeto.")
    max_documents: int = Field(default=8, ge=1, le=15, description="Quantos documentos fixados usar.")


def _state_of_art(caller, arguments: dict) -> dict:
    params = StateOfArtParams.model_validate(arguments)
    project, cards = _project_cards(caller, params.project_id)
    cards = cards[: params.max_documents]
    topic = params.topic.strip() or project.question or project.title
    sources = state_of_art_sources(topic, cards, _caller_context(caller, params.project_id))
    return {"topic": topic, "how_to_write": STATE_OF_ART_RULES, "sources": sources, "bibliography": bibliography(cards, "apa")}


# ---- Matriz de literatura ----


class MatrixParams(BaseModel):
    project_id: str = Field(description="Id do projeto (ver list_projects).")
    dimensions: list[str] = Field(min_length=1, max_length=6, description="Colunas da matriz, ex.: Método, Amostra, Resultados.")


class CellSummary(BaseModel):
    document_id: str
    dimension: str
    summary: str = Field(max_length=600)


class SaveMatrixParams(MatrixParams):
    summaries: list[CellSummary] = Field(min_length=1, max_length=60, description="Um resumo por documento e dimensão.")


def _matrix_cells(caller, project_id: str, dimensions: list[str], needs: str = "viewer") -> dict:
    _, cards = _project_cards(caller, project_id, needs)
    if not 2 <= len(cards) <= MAX_MATRIX_DOCUMENTS:
        raise ToolError(f"A matriz precisa de 2 a {MAX_MATRIX_DOCUMENTS} documentos fixados no projeto (tem {len(cards)}).")
    dimensions = [d.strip() for d in dimensions if d.strip()]
    filled = fill_matrix(cards, dimensions, _caller_context(caller, project_id), None)
    filled["documents"] = {c.document_id: c.title or c.filename for c in cards}
    return filled


def _matrix_material(caller, arguments: dict) -> dict:
    params = MatrixParams.model_validate(arguments)
    filled = _matrix_cells(caller, params.project_id, params.dimensions)
    current = get_research_repository().get_matrix(params.project_id) or {}
    return {"how_to_fill": MATRIX_RULES, **filled, "team_notes": current.get("notes", {})}


def _save_matrix(caller, arguments: dict) -> dict:
    from backend.mcp_server.server import _now

    params = SaveMatrixParams.model_validate(arguments)
    # Mesmo papel do botão "Preencher" da interface: quem edita o projeto.
    filled = _matrix_cells(caller, params.project_id, params.dimensions, needs="editor")
    unknown = []
    for cell in params.summaries:
        target = filled["cells"].get(cell.document_id, {}).get(cell.dimension.strip())
        if target is None:
            unknown.append(f"{cell.document_id}/{cell.dimension}")
        else:
            target["summary"] = cell.summary.strip()
    if unknown:
        raise ToolError(f"Células que não existem na matriz: {', '.join(unknown[:5])}. Usa os document_id e as dimensões de matrix_material.")
    repo = get_research_repository()
    data = repo.get_matrix(params.project_id) or {}
    data.update(dimensions=filled["dimensions"], cells=filled["cells"], filled_by=caller.via)
    data.setdefault("notes", {})
    repo.save_matrix(params.project_id, data, _now())
    return {"saved_cells": len(params.summaries), "note": f"Matriz guardada no projeto (separador Matriz), preenchida via {caller.via}."}


# ---- Esqueleto, mapa do tema, lacunas, afirmações ----


class SkeletonParams(BaseModel):
    topic: str = Field(min_length=3)
    work_type: str = Field(default="", description="Tipo de trabalho (chave, ver list_documents); vazio usa o do projeto ou o geral.")
    project_id: str | None = Field(default=None, description="Projeto: os excertos relevantes vêm dos documentos fixados nele.")


def _skeleton(caller, arguments: dict) -> dict:
    params = SkeletonParams.model_validate(arguments)
    context = _caller_context(caller, params.project_id)
    work_type = params.work_type
    if not work_type and params.project_id:
        work_type = get_research_repository().get_project(params.project_id).work_type
    if work_type and work_type not in context.document_types.types:
        raise ToolError(f"Tipo de trabalho desconhecido: {work_type}. Tipos: {sorted(context.document_types.types)}")
    result = skeleton(params.topic, work_type, context.scope_document_ids, context, None)
    return {"how_to_use": SKELETON_RULES, **result}


class TopicParams(BaseModel):
    topic: str = Field(min_length=3)
    project_id: str | None = Field(default=None, description="Limita aos documentos fixados neste projeto.")
    max_documents: int = Field(default=15, ge=3, le=40)


def _theme_map(caller, arguments: dict) -> dict:
    params = TopicParams.model_validate(arguments)
    context = _caller_context(caller, params.project_id)
    result = theme_map(params.topic, _filters(context), params.max_documents, context, None)
    result["note"] = "Os nomes dos grupos são as palavras-chave mais comuns; dá-lhes tu um nome a partir dos documentos de cada grupo."
    return result


def _gaps(caller, arguments: dict) -> dict:
    params = TopicParams.model_validate(arguments)
    context = _caller_context(caller, params.project_id)
    result = gaps(params.topic, _filters(context), min(params.max_documents, 20), context, None)
    result["note"] = "Sem sugestões automáticas: propõe tu as lacunas a partir das questões em aberto e da cobertura, citando [ficheiro, p.X]."
    return result


class ClaimsParams(BaseModel):
    text: str = Field(min_length=40, max_length=20_000, description="O texto a verificar (uma afirmação por frase).")
    project_id: str | None = Field(default=None, description="Verifica só contra os documentos fixados neste projeto.")


def _check_claims(caller, arguments: dict) -> dict:
    params = ClaimsParams.model_validate(arguments)
    context = _caller_context(caller, params.project_id)
    result = check_claims(params.text, _filters(context), context, None)
    result["note"] = (
        "Para cada afirmação, decide tu pelos excertos: apoiada, contradita ou sem apoio, citando [ficheiro, p.X]. "
        "Não uses conhecimento geral para dar uma afirmação como apoiada."
    )
    return result


# ---- Registo ----


def _schema(params: type[BaseModel]) -> dict:
    schema = params.model_json_schema()
    schema.pop("title", None)
    return schema


def workflow_tools() -> list:
    from backend.mcp_server.server import McpTool

    def tool(name: str, description: str, params: type[BaseModel], run, write: bool = False):
        return McpTool(types.Tool(name=name, description=description, inputSchema=_schema(params)), run, write=write)

    return [
        tool(
            "state_of_art_sources",
            "Material para escreveres o estado da arte de um projeto: excertos numerados dos documentos fixados (com "
            "autor, ano, ficheiro e página), a bibliografia em APA e as regras de escrita.",
            StateOfArtParams,
            _state_of_art,
        ),
        tool(
            "matrix_material",
            "Material para preencheres a matriz de literatura de um projeto: por documento fixado e por dimensão, os "
            "excertos encontrados, e as notas que a equipa já escreveu.",
            MatrixParams,
            _matrix_material,
        ),
        tool(
            "save_matrix",
            "Guarda a matriz de literatura do projeto com os teus resumos (um por documento e dimensão). Substitui o "
            "preenchimento anterior; as notas da equipa mantêm-se. Só para quem edita o projeto.",
            SaveMatrixParams,
            _save_matrix,
            write=True,
        ),
        tool(
            "work_skeleton",
            "Esqueleto de um trabalho escrito: as secções do tipo de trabalho, com excertos relevantes e exemplos de "
            "como outros trabalhos da base as escreveram. Tu escreves as perguntas de cada secção.",
            SkeletonParams,
            _skeleton,
        ),
        tool(
            "theme_map",
            "Panorama de um tema na base (ou num projeto): documentos agrupados por subtema, pessoas, anos, palavras-chave "
            "e referências mais citadas.",
            TopicParams,
            _theme_map,
        ),
        tool(
            "find_gaps",
            "O que fica em aberto sobre um tema: trabalho futuro e limitações que os documentos referem, e que aspetos "
            "do tema estão pouco cobertos.",
            TopicParams,
            _gaps,
        ),
        tool(
            "check_claims",
            "Para cada afirmação de um texto, os excertos mais próximos da base, para decidires se está apoiada, "
            "contradita ou sem apoio.",
            ClaimsParams,
            _check_claims,
        ),
    ]


# ---- Prompts (comandos prontos) ----

PROMPTS = {
    "estado-da-arte": (
        "Escreve o rascunho do estado da arte de um projeto, só com os documentos fixados, e propõe-no ao caderno.",
        [("projeto", "Nome ou id do projeto", True), ("tema", "Tema (opcional; por defeito o objetivo do projeto)", False)],
        "Escreve o estado da arte do projeto «{projeto}»{tema_txt}. Passos: encontra o projeto com list_projects; chama "
        "state_of_art_sources; escreve o texto seguindo as regras que vêm em how_to_write; mostra-mo; e, se eu concordar, "
        "propõe-no ao caderno com propose_item_changes.",
    ),
    "preencher-matriz": (
        "Preenche a matriz de literatura de um projeto com resumos apoiados nos excertos.",
        [("projeto", "Nome ou id do projeto", True), ("dimensoes", "Colunas, separadas por vírgulas (ex.: Método, Amostra, Resultados)", True)],
        "Preenche a matriz de literatura do projeto «{projeto}» com as dimensões: {dimensoes}. Encontra o projeto com "
        "list_projects, chama matrix_material, escreve um resumo por célula seguindo how_to_fill, mostra-me a tabela e, "
        "se eu concordar, guarda com save_matrix.",
    ),
    "verificar-texto": (
        "Verifica as afirmações de um texto contra a base de conhecimento (ou um projeto).",
        [("texto", "O texto a verificar", True), ("projeto", "Projeto (opcional)", False)],
        "Verifica este texto contra a base{projeto_txt}. Usa check_claims e, para cada afirmação, diz se está apoiada, "
        "contradita ou sem apoio, com as citações [ficheiro, p.X]:\n\n{texto}",
    ),
    "esqueleto": (
        "Monta o esqueleto de um trabalho escrito, com perguntas por secção e o que ler.",
        [("tema", "Tema do trabalho", True), ("projeto", "Projeto (opcional)", False)],
        "Monta o esqueleto de um trabalho sobre «{tema}»{projeto_txt}. Usa work_skeleton, escreve as perguntas de cada "
        "secção seguindo how_to_use e indica o que ler em cada uma. Se eu concordar, propõe-no ao caderno.",
    ),
}


def list_prompts() -> list[types.Prompt]:
    return [
        types.Prompt(
            name=name,
            description=description,
            arguments=[types.PromptArgument(name=arg, description=desc, required=required) for arg, desc, required in args],
        )
        for name, (description, args, _template) in PROMPTS.items()
    ]


def get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
    if name not in PROMPTS:
        raise ValueError(f"Prompt desconhecido: {name}")
    description, args, template = PROMPTS[name]
    values = {arg: (arguments or {}).get(arg, "").strip() for arg, _desc, _required in args}
    missing = [arg for arg, _desc, required in args if required and not values[arg]]
    if missing:
        raise ValueError(f"Falta: {', '.join(missing)}")
    values["tema_txt"] = f", sobre «{values['tema']}»" if values.get("tema") and name == "estado-da-arte" else ""
    values["projeto_txt"] = f" (projeto «{values['projeto']}»)" if values.get("projeto") else ""
    text = template.format(**values)
    return types.GetPromptResult(
        description=description,
        messages=[types.PromptMessage(role="user", content=types.TextContent(type="text", text=text))],
    )
