from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _normalize_turns(turns: list[dict[str, str]] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for turn in turns or []:
        if not isinstance(turn, dict):
            continue
        question = str(turn.get("question", "")).strip()
        answer = str(turn.get("answer", "")).strip()
        if question or answer:
            normalized.append({"question": question, "answer": answer})
    return normalized


class SessionMemory:
    """Simple JSON-backed memory service for chat sessions."""

    def _extract_topics(self, text: str) -> list[str]:
        words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", text.lower())
        stop_words = {
            "o",
            "a",
            "de",
            "do",
            "da",
            "e",
            "em",
            "para",
            "que",
            "com",
            "uma",
            "um",
            "as",
            "os",
            "no",
            "na",
            "se",
            "por",
            "mais",
            "esta",
            "este",
            "isso",
            "sobre",
            "como",
            "qual",
            "quais",
            "tudo",
            "muito",
            "pelo",
            "pela",
            "ao",
            "aos",
            "não",
            "nao",
            "um",
        }
        filtered = [word for word in words if len(word) > 3 and word not in stop_words]
        return list(dict.fromkeys(filtered))[:5]

    def _build_summary(self, turns: list[dict[str, str]], existing_summary: str | None = None) -> str:
        if not turns:
            return existing_summary or ""

        recent_texts = []
        for turn in turns[-4:]:
            if turn.get("question"):
                recent_texts.append(turn["question"])
            if turn.get("answer"):
                recent_texts.append(turn["answer"])
        if not recent_texts:
            return existing_summary or ""

        summary_text = " | ".join(recent_texts)
        if len(summary_text) > 220:
            summary_text = summary_text[:220].rstrip() + "..."
        return summary_text

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        self.storage_dir = Path(storage_dir or "backend/storage/memory")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        return self.storage_dir / f"{session_id}.json"

    def get_context(self, session_id: str) -> str:
        path = self._session_path(session_id)
        if not path.exists():
            return ""

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ""

        summary = payload.get("summary", "")
        topics = payload.get("topics", [])
        turns = _normalize_turns(payload.get("turns"))
        parts: list[str] = []
        if summary:
            parts.append(summary)
        if topics:
            parts.append("Tópicos relevantes: " + ", ".join(topics))
        if turns:
            turn_lines = []
            for turn in turns[-4:]:
                if turn.get("question"):
                    turn_lines.append(f"- Pergunta: {turn['question']}")
                if turn.get("answer"):
                    turn_lines.append(f"  Resposta: {turn['answer']}")
            if turn_lines:
                parts.append("Interações recentes:\n" + "\n".join(turn_lines))
        return "\n".join(parts)

    def remember(self, session_id: str, question: str, answer: str | None = None, topics: list[str] | None = None) -> None:
        path = self._session_path(session_id)
        payload: dict[str, Any] = {"summary": "", "topics": [], "turns": []}
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {"summary": "", "topics": [], "turns": []}

        existing_topics = [str(item) for item in payload.get("topics", [])]
        new_topics = [str(topic) for topic in (topics or [])]
        combined_topics = list(dict.fromkeys(existing_topics + new_topics))

        question_snippet = question.strip()
        answer_snippet = (answer or "").strip()
        turns = _normalize_turns(payload.get("turns"))
        turns.append({"question": question_snippet, "answer": answer_snippet})
        if len(turns) > 8:
            turns = turns[-8:]

        summary = self._build_summary(turns, existing_summary=str(payload.get("summary", "")))
        inferred_topics = self._extract_topics(" ".join([turn.get("question", "") for turn in turns] + [turn.get("answer", "") for turn in turns]))
        payload["summary"] = summary
        payload["topics"] = list(dict.fromkeys(combined_topics + inferred_topics))[:8]
        payload["turns"] = turns
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
