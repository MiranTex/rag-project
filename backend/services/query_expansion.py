"""Multi-Query RAG — query expansion service.

Asks the LLM to rephrase the original question N times so that vector
retrieval covers a broader semantic space.  On any failure the function
returns an empty list; callers must always be able to fall back to the
original question alone.
"""
from __future__ import annotations

import re

from backend.services.lmstudio_client import LMStudioClient

_EXPANSION_SYSTEM = (
    "Es um especialista em recuperacao de informacao. "
    "A tua unica tarefa e reformular a pergunta fornecida."
)

_EXPANSION_TEMPLATE = """\
Dado a pergunta original abaixo, gera exatamente {n} versoes alternativas da mesma pergunta.
Cada versao deve:
- Ter o mesmo significado essencial
- Usar vocabulario ou estrutura diferente
- Ser independente e auto-contida

Responde APENAS com as versoes, uma por linha, sem numeracao, sem prefixos, sem explicacoes.

Pergunta original: {question}
"""


def expand_query(
    question: str,
    client: LMStudioClient,
    n: int = 3,
    temperature: float = 0.6,
) -> list[str]:
    """Return up to *n* alternative phrasings of *question*.

    Guarantees: never raises; on any error returns [].
    """
    prompt = _EXPANSION_TEMPLATE.format(n=n, question=question.strip())
    try:
        raw = client.chat(
            system_prompt=_EXPANSION_SYSTEM,
            user_prompt=prompt,
            temperature=temperature,
        )
    except Exception:
        return []

    results: list[str] = []
    for line in raw.splitlines():
        # tolerate LLM adding bullets / numbers despite instructions
        cleaned = re.sub(r"^[\s\-\d\.\)\*]+", "", line).strip()
        if cleaned and cleaned.lower() != question.strip().lower():
            results.append(cleaned)
        if len(results) >= n:
            break

    return results
