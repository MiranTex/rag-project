import json
from collections.abc import Iterator

import requests


class LMStudioClient:
    """Cliente para qualquer API no formato OpenAI (/chat/completions): LM Studio, OpenRouter, OpenAI, a camada
    de compatibilidade da Anthropic... (ver services/llm_providers.py)."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        max_tokens: int = 900,
        extra_headers: dict[str, str] | None = None,
        send_temperature: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.headers.update(extra_headers or {})
        # Os modelos Claude atuais rejeitam temperature com 400 ("deprecated for this model").
        self.send_temperature = send_temperature

    def _temperature(self, temperature: float) -> dict:
        return {"temperature": temperature} if self.send_temperature else {}

    @staticmethod
    def _check(response: requests.Response) -> None:
        """Como raise_for_status, mas com a mensagem do fornecedor (o motivo de um 400 vem no corpo)."""
        if not response.ok:
            raise requests.HTTPError(
                f"{response.status_code} {response.reason} ({response.url}): {response.text[:500]}",
                response=response,
            )

    def ping(self) -> None:
        """Pedido mínimo ao modelo: confirma URL, chave e nome do modelo. Lança erro com a resposta do fornecedor."""
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json={"model": self.model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
            headers=self.headers,
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")

    def health(self) -> bool:
        response = requests.get(f"{self.base_url}/models", headers=self.headers, timeout=5)
        return response.ok

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **self._temperature(temperature),
            "max_tokens": self.max_tokens,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self.headers,
            timeout=120,
        )
        self._check(response)
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float = 0.2,
    ) -> dict:
        """Chamada no formato OpenAI com suporte a tool calling; devolve a mensagem do assistente."""
        payload: dict = {
            "model": self.model,
            "messages": messages,
            **self._temperature(temperature),
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self.headers,
            timeout=120,
        )
        self._check(response)
        return response.json()["choices"][0]["message"]

    def chat_stream(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> Iterator[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **self._temperature(temperature),
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self.headers,
            timeout=120,
            stream=True,
        )
        self._check(response)

        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue

            data_block = line[5:].strip()
            if data_block == "[DONE]":
                break

            try:
                payload = json.loads(data_block)
            except json.JSONDecodeError:
                continue

            choices = payload.get("choices", [])
            if not choices:
                continue

            delta = choices[0].get("delta", {})
            token = delta.get("content")
            if token:
                yield token
