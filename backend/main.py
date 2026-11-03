import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.agent import router as agent_router
from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.documents import build_job_runner
from backend.api.documents import router as documents_router
from backend.api.exports import router as exports_router
from backend.api.health import router as health_router
from backend.api.users import router as users_router
from backend.auth.authenticators import ensure_bootstrap_admin
from backend.config import get_settings
from backend.dependencies import get_authenticator, get_job_queue, get_users
from backend.services.job_startup import recover_interrupted_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")



@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Workers da fila de extração/indexação dentro da API (INDEXING_WORKERS=0 se correrem à parte)."""
    settings = get_settings()
    ensure_bootstrap_admin(settings, get_users())
    get_authenticator()  # configuração de autenticação inválida falha já no arranque
    recover_interrupted_jobs(get_job_queue(), settings.job_stale_minutes)
    runner = build_job_runner()
    if settings.indexing_workers > 0:
        runner.start(settings.indexing_workers)
    try:
        yield
    finally:
        runner.stop()


app = FastAPI(title="RAG Study API", version="0.1.0", lifespan=lifespan)

# A sessão vai no cabeçalho Authorization (não em cookies), por isso não são precisas credenciais CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().split_list(get_settings().cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(agent_router)
app.include_router(exports_router)


@app.get("/")
def root() -> dict:
    return {"message": "RAG API ativa"}
