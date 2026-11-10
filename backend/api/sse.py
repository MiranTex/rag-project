import json
import logging
from collections.abc import AsyncIterator, Iterator

from starlette.concurrency import iterate_in_threadpool

logger = logging.getLogger(__name__)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stop_on_disconnect(events: Iterator[str], label: str) -> AsyncIterator[str]:
    """Consome o gerador síncrono numa thread e regista quando o cliente desliga a meio (botão "parar").

    Ao desligar, o Starlette cancela este gerador e o síncrono deixa de ser avançado: o passo em curso
    (chamada ao LLM ou tool) termina, mas nenhum passo seguinte corre.
    """
    finished = False
    try:
        async for chunk in iterate_in_threadpool(events):
            yield chunk
        finished = True
    finally:
        if not finished:
            logger.info("%s interrompida pelo cliente", label)
