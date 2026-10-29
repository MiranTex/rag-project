import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from backend.services.document_registry import DocumentRegistry
from backend.services.document_types import DocumentTypes
from backend.services.export_store import ExportStore
from backend.services.extraction_review import ExtractionStore
from backend.services.rag_pipeline import RagPipeline
from backend.services.vector_store import VectorStore


class ToolError(Exception):
    """Erro esperado de uma tool; a mensagem é devolvida ao modelo para ele poder corrigir o pedido."""


@dataclass
class ToolContext:
    """Dependências a que as tools têm acesso. Criado por pedido."""

    pipeline: RagPipeline
    vector_store: VectorStore
    registry: DocumentRegistry
    export_store: ExportStore
    top_k: int = 4
    default_document_id: str | None = None
    # Ficha dos documentos, tipos configurados e índice de documentos (um vetor por documento).
    extraction_store: ExtractionStore | None = None
    document_types: DocumentTypes | None = None
    profile_store: VectorStore | None = None
    embedding_model: str = ""


@dataclass
class SourceRef:
    filename: str
    page: int
    document_id: str


@dataclass
class ExportRef:
    name: str
    format: str


@dataclass
class ToolResult:
    content: Any  # o que o modelo recebe (serializado em JSON)
    summary: str  # linha curta para mostrar na interface
    sources: list[SourceRef] = field(default_factory=list)
    exports: list[ExportRef] = field(default_factory=list)


@dataclass
class Tool:
    name: str
    description: str
    params: type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], ToolResult]
    side_effect: bool = False  # True se a tool cria/altera algo fora da conversa

    def schema(self) -> dict:
        parameters = self.params.model_json_schema()
        parameters.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }

    def run(self, raw_arguments: str | dict, context: ToolContext) -> ToolResult:
        try:
            arguments = json.loads(raw_arguments or "{}") if isinstance(raw_arguments, str) else raw_arguments
            params = self.params.model_validate(arguments)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ToolError(f"Argumentos inválidos para {self.name}: {exc}") from exc
        return self.handler(params, context)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool duplicada: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def select(self, names: list[str] | None) -> list[Tool]:
        """Tools de um perfil; None significa todas."""
        if names is None:
            return self.all()
        missing = [name for name in names if name not in self._tools]
        if missing:
            raise ValueError(f"Tools desconhecidas: {missing}")
        return [self._tools[name] for name in names]


def tool(
    name: str,
    description: str,
    params: type[BaseModel],
    side_effect: bool = False,
) -> Callable[[Callable[[Any, ToolContext], ToolResult]], Tool]:
    """Decorator que transforma uma função `(params, context) -> ToolResult` numa Tool."""

    def decorator(func: Callable[[Any, ToolContext], ToolResult]) -> Tool:
        return Tool(name=name, description=description, params=params, handler=func, side_effect=side_effect)

    return decorator
