import json
import logging
from collections.abc import Iterator
from typing import Protocol

from backend.agent.events import AgentEvent
from backend.agent.tools.base import SourceRef, Tool, ToolContext, ToolError

logger = logging.getLogger(__name__)


class ChatCompletionClient(Protocol):
    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> dict: ...


class AgentRunner:
    """Loop do agente: o modelo pede tools, executamos, devolvemos o resultado, até haver resposta final."""

    def __init__(
        self,
        llm: ChatCompletionClient,
        tools: list[Tool],
        system_prompt: str,
        context: ToolContext,
        max_steps: int = 8,
        max_result_chars: int = 24_000,
    ) -> None:
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.system_prompt = system_prompt
        self.context = context
        self.max_steps = max_steps
        self.max_result_chars = max_result_chars

    def run(self, question: str, history: list[dict] | None = None) -> Iterator[AgentEvent]:
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}, *(history or [])]
        messages.append({"role": "user", "content": question})
        schemas = [t.schema() for t in self.tools.values()]
        sources: dict[tuple[str, int], SourceRef] = {}

        for step in range(1, self.max_steps + 1):
            # No último passo proíbe tools para forçar uma resposta final.
            last_step = step == self.max_steps
            message = self.llm.complete(
                messages,
                tools=schemas or None,
                tool_choice="none" if last_step and schemas else None,
            )
            tool_calls = message.get("tool_calls") or []
            text = (message.get("content") or "").strip()

            if not tool_calls:
                if sources:
                    yield AgentEvent("sources", {"sources": [vars(s) for s in sources.values()]})
                yield AgentEvent("answer", {"answer": text or "Não consegui chegar a uma resposta.", "steps": step})
                return

            if text:
                yield AgentEvent("thinking", {"text": text})
            messages.append({"role": "assistant", "content": text, "tool_calls": tool_calls})

            for call in tool_calls:
                yield from self._execute(call, messages, sources)

    def _execute(
        self,
        call: dict,
        messages: list[dict],
        sources: dict[tuple[str, int], SourceRef],
    ) -> Iterator[AgentEvent]:
        name = call["function"]["name"]
        raw_arguments = call["function"].get("arguments") or "{}"
        tool = self.tools.get(name)
        try:
            shown_arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError:
            shown_arguments = {"raw": raw_arguments}
        yield AgentEvent(
            "tool_call",
            {"id": call["id"], "name": name, "arguments": shown_arguments, "side_effect": bool(tool and tool.side_effect)},
        )

        ok = False
        summary = ""
        try:
            if tool is None:
                raise ToolError(f"Tool desconhecida: {name}")
            result = tool.run(raw_arguments, self.context)
            content, summary, ok = result.content, result.summary, True
            for ref in result.sources:
                sources.setdefault((ref.filename, ref.page), ref)
            for export in result.exports:
                yield AgentEvent("export", {"name": export.name, "format": export.format})
        except ToolError as exc:
            content, summary = {"error": str(exc)}, str(exc)
        except Exception as exc:
            logger.exception("Tool %s falhou", name)
            content, summary = {"error": f"Erro interno na tool: {exc}"}, f"erro interno: {exc}"

        logger.info("tool %s ok=%s: %s", name, ok, summary)
        yield AgentEvent("tool_result", {"id": call["id"], "name": name, "ok": ok, "summary": summary})

        serialized = json.dumps(content, ensure_ascii=False, default=str)
        if len(serialized) > self.max_result_chars:
            serialized = serialized[: self.max_result_chars] + " …[resultado cortado]"
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": serialized})
