"""Respostas estruturadas do LLM (JSON) através de uma tool forçada, como na ficha dos documentos.

Tudo o que usa isto tem uma alternativa sem LLM: se o modelo estiver em baixo ou responder mal, devolve None e
quem chama mostra só o que encontrou na base (excertos, contagens) em vez de falhar."""

import json
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class ChatCompletionClient(Protocol):
    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float = 0.2,
    ) -> dict: ...


def ask_json(
    llm: ChatCompletionClient | None,
    system: str,
    user: str,
    name: str,
    description: str,
    schema: dict,
) -> dict | None:
    if llm is None:
        return None
    tool = {"type": "function", "function": {"name": name, "description": description, "parameters": schema}}
    try:
        message = llm.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": name}},
            temperature=0.0,
        )
        result = json.loads(message["tool_calls"][0]["function"]["arguments"])
    except Exception:
        logger.warning("Resposta estruturada do LLM falhou (%s)", name, exc_info=True)
        return None
    return result if isinstance(result, dict) else None
