import asyncio
import logging

from backend.api.sse import stop_on_disconnect


def _events():
    yield "a"
    yield "b"


async def _consume(limit=None):
    stream = stop_on_disconnect(_events(), "teste")
    received = []
    async for chunk in stream:
        received.append(chunk)
        if limit and len(received) == limit:
            # Equivalente ao Starlette cancelar o stream quando o cliente desliga.
            await stream.aclose()
            break
    return received


def test_full_stream_is_not_logged_as_interrupted(caplog):
    with caplog.at_level(logging.INFO, logger="backend.api.sse"):
        assert asyncio.run(_consume()) == ["a", "b"]
    assert "interrompida" not in caplog.text


def test_closing_mid_stream_logs_interruption(caplog):
    with caplog.at_level(logging.INFO, logger="backend.api.sse"):
        assert asyncio.run(_consume(limit=1)) == ["a"]
    assert "teste interrompida pelo cliente" in caplog.text
