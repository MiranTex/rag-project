from fastapi import APIRouter

from backend.config import get_settings
from backend.dependencies import get_job_queue, get_lmstudio_client, get_vector_store

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict:
    lmstudio_ok = False
    chroma_ok = False

    try:
        lmstudio_ok = get_lmstudio_client().health()
    except Exception:
        lmstudio_ok = False

    try:
        chroma_ok = bool(get_vector_store().heartbeat())
    except Exception:
        chroma_ok = False

    try:
        jobs = get_job_queue().counts()
    except Exception:
        jobs = None

    status = "ok" if lmstudio_ok and chroma_ok else "degraded"
    settings = get_settings()
    return {
        "status": status,
        "lmstudio": lmstudio_ok,
        "chroma": chroma_ok,
        # Trabalhos por estado (queued, running, failed, done); None se a base de dados não responder.
        "jobs": jobs,
        "rerank_profiles": {
            "default": settings.parse_rerank_weights("default"),
            "grounding": settings.parse_rerank_weights("grounding"),
        },
    }
