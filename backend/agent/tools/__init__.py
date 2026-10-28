from backend.agent.tools.base import Tool, ToolContext, ToolError, ToolRegistry, ToolResult
from backend.agent.tools.calculations import calculate, date_add, date_difference, percentage_change
from backend.agent.tools.documents import list_documents, read_document, search_documents
from backend.agent.tools.exports import export_csv, export_document

# Para acrescentar uma tool: criá-la com @tool num módulo deste pacote e adicioná-la aqui.
ALL_TOOLS: list[Tool] = [
    list_documents,
    search_documents,
    read_document,
    calculate,
    percentage_change,
    date_difference,
    date_add,
    export_csv,
    export_document,
]


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for item in ALL_TOOLS:
        registry.register(item)
    return registry


__all__ = ["Tool", "ToolContext", "ToolError", "ToolRegistry", "ToolResult", "build_registry"]
