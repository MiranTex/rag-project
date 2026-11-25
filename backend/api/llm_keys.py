"""Chaves de API próprias: a de cada pessoa (A minha conta) e a de cada projeto (Definições do projeto).

Quem paga um pedido decide-se em choose_llm (services/llm_providers.py): projeto, senão pessoa, senão plataforma.
As chaves ficam cifradas e nunca voltam nas respostas (só os últimos caracteres, e só a quem as pode mudar).
Só fornecedores de URL fixo (OWN_KEY_PROVIDERS): o URL não é escolhido por quem guarda a chave."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.security import current_user, require
from backend.auth.permissions import RESEARCH_USE, AuthenticatedUser
from backend.dependencies import get_llm_credentials, get_secret_box, resolve_llm
from backend.models import CredentialScope, LLMProviderConfig
from backend.research.access import load_project
from backend.services.llm_providers import OWN_KEY_PROVIDERS, PROVIDERS, build_client, with_defaults
from backend.services.secret_box import SecretBoxUnavailable

router = APIRouter(tags=["llm-keys"])

can_research = require(RESEARCH_USE)


class OwnKeyUpdate(BaseModel):
    provider: str
    # None mantém a chave guardada (só se o fornecedor for o mesmo).
    api_key: str | None = None
    chat_model: str = ""
    utility_model: str = ""


def _key_hint(key: str) -> str:
    return f"…{key[-4:]}" if len(key) > 8 else "guardada"


def _providers() -> list[dict]:
    return [
        {
            "id": spec.id,
            "label": spec.label,
            "hint": spec.hint,
            "default_chat_model": spec.chat_model,
            "default_utility_model": spec.utility_model,
        }
        for spec in (PROVIDERS[p] for p in OWN_KEY_PROVIDERS)
    ]


def _key_view(config: LLMProviderConfig | None, show_hint: bool) -> dict | None:
    if config is None:
        return None
    return {
        "provider": config.provider,
        "provider_label": PROVIDERS[config.provider].label if config.provider in PROVIDERS else config.provider,
        # False: foi cifrada com outra CREDENTIALS_SECRET_KEY e tem de ser colada de novo.
        "readable": bool(config.api_key),
        "key_hint": _key_hint(config.api_key) if show_hint and config.api_key else "",
        "chat_model": config.chat_model,
        "utility_model": config.utility_model,
    }


def _stored(scope: CredentialScope, owner_id: str) -> LLMProviderConfig | None:
    return get_llm_credentials().get(scope, owner_id) if get_secret_box().available else None


def _merge(payload: OwnKeyUpdate, current: LLMProviderConfig | None) -> LLMProviderConfig:
    if payload.provider not in OWN_KEY_PROVIDERS:
        allowed = ", ".join(PROVIDERS[p].label for p in OWN_KEY_PROVIDERS)
        raise HTTPException(status_code=422, detail=f"Fornecedor não aceite para chaves próprias. Escolhe um destes: {allowed}.")
    if payload.api_key is not None and payload.api_key.strip():
        api_key = payload.api_key.strip()
    elif payload.api_key is None and current is not None and current.provider == payload.provider:
        api_key = current.api_key
    else:
        api_key = ""
    if not api_key:
        raise HTTPException(status_code=422, detail="Cola a chave de API.")
    config = LLMProviderConfig(
        provider=payload.provider,
        api_key=api_key,
        chat_model=payload.chat_model.strip(),
        utility_model=payload.utility_model.strip(),
        active=True,
    )
    if not with_defaults(config).chat_model:
        raise HTTPException(status_code=422, detail="Indica o modelo de chat.")
    return config


def _test(config: LLMProviderConfig) -> dict:
    """Pedido mínimo aos dois modelos com os valores do formulário (sem os guardar)."""
    results: dict[str, dict] = {}
    for role in ("chat", "utility"):
        client = build_client(config, role)
        if role == "utility" and client.model in {r["model"] for r in results.values()}:
            continue
        try:
            client.ping()
            results[role] = {"model": client.model, "ok": True, "error": ""}
        except Exception as exc:
            results[role] = {"model": client.model, "ok": False, "error": str(exc)}
    return {"ok": all(r["ok"] for r in results.values()), "results": results}


def _save(scope: CredentialScope, owner_id: str, payload: OwnKeyUpdate, user: AuthenticatedUser) -> None:
    config = _merge(payload, _stored(scope, owner_id))
    try:
        get_llm_credentials().save(scope, owner_id, config, user.user_id)
    except SecretBoxUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---- A minha chave ----


def _my_state(user: AuthenticatedUser) -> dict:
    return {
        "enabled": get_secret_box().available,
        "providers": _providers(),
        "key": _key_view(_stored("user", user.user_id), show_hint=True),
        # Fora dos projetos (ou num projeto sem chave própria), quem paga as perguntas desta pessoa.
        "effective": resolve_llm(user.user_id).source,
    }


@router.get("/me/llm-key")
def get_my_key(user: AuthenticatedUser = Depends(current_user)) -> dict:
    return _my_state(user)


@router.put("/me/llm-key")
def save_my_key(payload: OwnKeyUpdate, user: AuthenticatedUser = Depends(current_user)) -> dict:
    _save("user", user.user_id, payload, user)
    return _my_state(user)


@router.delete("/me/llm-key")
def delete_my_key(user: AuthenticatedUser = Depends(current_user)) -> dict:
    get_llm_credentials().delete("user", user.user_id)
    return _my_state(user)


@router.post("/me/llm-key/test")
def test_my_key(payload: OwnKeyUpdate, user: AuthenticatedUser = Depends(current_user)) -> dict:
    return _test(_merge(payload, _stored("user", user.user_id)))


# ---- Chave do projeto (só o dono a muda; os membros veem que existe e quem paga) ----


def _project_state(project_id: str, role: str, user: AuthenticatedUser) -> dict:
    is_owner = role == "owner"
    return {
        "enabled": get_secret_box().available,
        "providers": _providers(),
        "key": _key_view(_stored("project", project_id), show_hint=is_owner),
        "can_edit": is_owner,
        # Quem paga as perguntas desta pessoa dentro do projeto.
        "effective": resolve_llm(user.user_id, project_id).source,
    }


@router.get("/research/projects/{project_id}/llm-key")
def get_project_key(project_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    _, role = load_project(project_id, user)
    return _project_state(project_id, role, user)


@router.put("/research/projects/{project_id}/llm-key")
def save_project_key(project_id: str, payload: OwnKeyUpdate, user: AuthenticatedUser = Depends(can_research)) -> dict:
    load_project(project_id, user, "owner")
    _save("project", project_id, payload, user)
    return _project_state(project_id, "owner", user)


@router.delete("/research/projects/{project_id}/llm-key")
def delete_project_key(project_id: str, user: AuthenticatedUser = Depends(can_research)) -> dict:
    load_project(project_id, user, "owner")
    get_llm_credentials().delete("project", project_id)
    return _project_state(project_id, "owner", user)


@router.post("/research/projects/{project_id}/llm-key/test")
def test_project_key(project_id: str, payload: OwnKeyUpdate, user: AuthenticatedUser = Depends(can_research)) -> dict:
    load_project(project_id, user, "owner")
    return _test(_merge(payload, _stored("project", project_id)))
