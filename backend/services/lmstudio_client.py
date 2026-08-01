import json
from collections.abc import Iterator

import requests


class LMStudioClient:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def health(self) -> bool:
        response = requests.get(f"{self.base_url}/models", timeout=5)
        return response.ok

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def chat_stream(self, system_prompt: str, user_prompt: str) -> Iterator[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "stream": True,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=120,
            stream=True,
        )
        response.raise_for_status()

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
