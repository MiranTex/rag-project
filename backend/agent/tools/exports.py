from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.agent.tools.base import ExportRef, ToolContext, ToolResult, tool
from backend.services.document_writer import write_csv, write_docx, write_markdown


class ExportCsvParams(BaseModel):
    filename: str = Field(description="Nome do ficheiro, sem extensão (ex.: 'clausulas-contrato').")
    columns: list[str] = Field(min_length=1, description="Cabeçalhos das colunas.")
    rows: list[list[str | int | float | None]] = Field(
        min_length=1,
        description="Linhas de dados; cada linha tem um valor por coluna, pela mesma ordem.",
    )

    @model_validator(mode="after")
    def check_row_width(self) -> "ExportCsvParams":
        for index, row in enumerate(self.rows, start=1):
            if len(row) != len(self.columns):
                raise ValueError(f"A linha {index} tem {len(row)} valores mas há {len(self.columns)} colunas.")
        return self


@tool(
    name="export_csv",
    description=(
        "Exporta dados tabulares extraídos dos documentos para um ficheiro CSV (separador ';', abre no Excel). "
        "Devolve o nome do ficheiro criado."
    ),
    params=ExportCsvParams,
    side_effect=True,
)
def export_csv(params: ExportCsvParams, ctx: ToolContext) -> ToolResult:
    path = ctx.export_store.reserve_path(params.filename, "csv")
    write_csv(path, params.columns, params.rows)
    return ToolResult(
        content={"file": path.name, "rows": len(params.rows), "columns": params.columns},
        summary=f"{path.name} ({len(params.rows)} linhas)",
        exports=[ExportRef(name=path.name, format="csv")],
    )


class ExportDocumentParams(BaseModel):
    filename: str = Field(description="Nome do ficheiro, sem extensão (ex.: 'resumo-contrato').")
    title: str = Field(description="Título do documento.")
    content: str = Field(
        description="Conteúdo em markdown: títulos (#, ##), listas (-, 1.), tabelas (| a | b |) e **negrito**."
    )
    format: Literal["docx", "md"] = Field(default="docx", description="docx (Word) ou md (markdown).")


@tool(
    name="export_document",
    description=(
        "Cria um novo documento (Word .docx ou markdown) a partir de conteúdo em markdown, "
        "por exemplo um resumo ou relatório. Devolve o nome do ficheiro criado."
    ),
    params=ExportDocumentParams,
    side_effect=True,
)
def export_document(params: ExportDocumentParams, ctx: ToolContext) -> ToolResult:
    path = ctx.export_store.reserve_path(params.filename, params.format)
    if params.format == "docx":
        write_docx(path, params.title, params.content)
    else:
        write_markdown(path, params.title, params.content)
    return ToolResult(
        content={"file": path.name, "format": params.format},
        summary=path.name,
        exports=[ExportRef(name=path.name, format=params.format)],
    )
