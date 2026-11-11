"""Definições → Modelo: escolher o fornecedor de LLM (OpenRouter, Anthropic, OpenAI, LM Studio, outro), a chave
e os modelos. As chaves nunca voltam completas nas respostas; só os últimos caracteres, para as reconhecer."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.security import require
from backend.auth.permissions import SETTINGS_MANAGE
from backend.dependencies import active_llm_config, get_llm_settings
from backend.models import LLMProviderConfig
from backend.services.llm_providers import PROVIDERS, build_client, with_defaults

# Só quem gere as configurações (admin): mexe nas chaves e no que todos os utilizadores usam.
router = APIRouter(prefix="/settings/llm", tags=["settings"], dependencies=[Depends(require(SETTINGS_MANAGE))])


class ProviderUpdate(BaseModel):
    # None mantém a chave guardada; "" apaga-a.
    api_key: str | None = None
    base_url: str = ""
    chat_model: str = ""
    utility_model: str = ""
    activate: bool = True


def _key_hint(key: str) -> str:
    return f"…{key[-4:]}" if len(key) > 8 else ("guardada" if key else "")


def _state() -> dict:
    saved = {config.provider: config for config in get_llm_settings().list_providers()}
    active = active_llm_config()
    providers = []
    for spec in PROVIDERS.values():
        config = saved.get(spec.id)
        # Sem nada guardado, o fornecedor que vem do .env aparece com os valores de lá.
        if config is None and spec.id == active.provider:
            config = active
        config = config or LLMProviderConfig(provider=spec.id)
        providers.append(
            {
                "id": spec.id,
                "label": spec.label,
                "hint": spec.hint,
                "needs_key": spec.needs_key,
                "has_key": bool(config.api_key),
                "key_hint": _key_hint(config.api_key),
                "base_url": config.base_url,
                "chat_model": config.chat_model,
                "utility_model": config.utility_model,
                "default_base_url": spec.base_url,
                "default_chat_model": spec.chat_model,
                "default_utility_model": spec.utility_model,
            }
        )
    return {
        "active": active.provider,
        # "env": ainda nada guardado na aplicação, está a usar o .env.
        "source": "database" if active.provider in saved and saved[active.provider].active else "env",
        "providers": providers,
    }


def _merge(provider: str, payload: ProviderUpdate) -> LLMProviderConfig:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Fornecedor desconhecido: {provider}")
    current = get_llm_settings().get(provider)
    if current is None and active_llm_config().provider == provider:
        current = active_llm_config()  # primeira gravação a partir do .env: herda a chave de lá
    api_key = payload.api_key.strip() if payload.api_key is not None else (current.api_key if current else "")
    config = LLMProviderConfig(
        provider=provider,
        api_key=api_key,
        base_url=payload.base_url.strip(),
        chat_model=payload.chat_model.strip(),
        utility_model=payload.utility_model.strip(),
        active=payload.activate,
    )
    spec = PROVIDERS[provider]
    filled = with_defaults(config)
    if not filled.base_url:
        raise HTTPException(status_code=422, detail="Indica o URL da API.")
    if not filled.chat_model:
        raise HTTPException(status_code=422, detail="Indica o modelo de chat.")
    if spec.needs_key and not config.api_key:
        raise HTTPException(status_code=422, detail=f"O {spec.label} precisa de uma chave de API.")
    return config


@router.get("")
def get_llm_state() -> dict:
    return _state()


@router.put("/{provider}")
def save_provider(provider: str, payload: ProviderUpdate) -> dict:
    config = _merge(provider, payload)
    if not config.active:
        # Guardar sem ativar não pode desligar o fornecedor que está em uso.
        current = get_llm_settings().get(provider)
        config.active = bool(current and current.active)
    get_llm_settings().save(config)
    return _state()


@router.post("/{provider}/test")
def test_provider(provider: str, payload: ProviderUpdate) -> dict:
    """Pedido mínimo com os valores do formulário (sem os guardar) aos dois modelos."""
    config = _merge(provider, payload)
    results = {}
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
