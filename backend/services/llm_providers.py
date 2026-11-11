"""Fornecedores de LLM escolhidos na aplicação (Definições → Modelo), não no .env.

Todos falam o formato OpenAI (/chat/completions), por isso o mesmo cliente serve para todos; muda o URL, a
chave, os nomes dos modelos e alguns headers. A configuração ativa é lida da base de dados a cada pedido, por
isso trocar de fornecedor ou de chave vale logo, também nos workers que correm noutro processo.

Sem nada guardado, vale o .env (OPEN_ROUTER_API_KEY / LM_STUDIO_*), como antes."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal

from backend.config import Settings, get_settings
from backend.models import LLMProviderConfig
from backend.services.lmstudio_client import LMStudioClient


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    base_url: str
    chat_model: str
    utility_model: str
    needs_key: bool
    # Limite das respostas de chat; None usa LM_STUDIO_MAX_TOKENS.
    max_tokens: int | None = None
    extra_headers: tuple[tuple[str, str], ...] = ()
    # Os modelos Claude atuais rejeitam o parâmetro temperature (400 "deprecated for this model").
    send_temperature: bool = True
    # Ajuda mostrada no formulário.
    hint: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    spec.id: spec
    for spec in (
        ProviderSpec(
            id="openrouter",
            label="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            chat_model="anthropic/claude-sonnet-5.5",
            utility_model="anthropic/claude-haiku-5.5",
            needs_key=True,
            hint="Modelos no formato fornecedor/modelo, ex.: anthropic/claude-sonnet-5.5.",
        ),
        ProviderSpec(
            id="anthropic",
            label="Anthropic",
            base_url="https://api.anthropic.com/v1",
            chat_model="claude-sonnet-5-5",
            utility_model="claude-haiku-5-5",
            needs_key=True,
            max_tokens=8192,
            extra_headers=(("anthropic-version", "2023-06-01"),),
            send_temperature=False,
            hint="Chave de console.anthropic.com. Modelos sem prefixo, ex.: claude-sonnet-5-5.",
        ),
        ProviderSpec(
            id="openai",
            label="OpenAI",
            base_url="https://api.openai.com/v1",
            chat_model="",
            utility_model="",
            needs_key=True,
            hint="Chave de platform.openai.com.",
        ),
        ProviderSpec(
            id="lmstudio",
            label="LM Studio (local)",
            base_url="http://127.0.0.1:1234/v1",
            chat_model="local-model",
            utility_model="",
            needs_key=False,
            hint="Servidor local do LM Studio. No Docker: http://host.docker.internal:1234/v1.",
        ),
        ProviderSpec(
            id="custom",
            label="Outro (compatível com OpenAI)",
            base_url="",
            chat_model="",
            utility_model="",
            needs_key=False,
            hint="Qualquer API com /chat/completions no formato OpenAI (Groq, Together, Ollama, vLLM...).",
        ),
    )
}


def with_defaults(config: LLMProviderConfig) -> LLMProviderConfig:
    """Preenche URL e modelos em branco com os valores por defeito do fornecedor."""
    spec = PROVIDERS[config.provider]
    return config.model_copy(
        update={
            "base_url": config.base_url or spec.base_url,
            "chat_model": config.chat_model or spec.chat_model,
            "utility_model": config.utility_model or spec.utility_model,
        }
    )


def env_fallback(settings: Settings) -> LLMProviderConfig:
    """Configuração do .env, para instalações que ainda não escolheram fornecedor na aplicação."""
    if settings.open_router_api_key:
        return LLMProviderConfig(
            provider="openrouter",
            api_key=settings.open_router_api_key,
            base_url=settings.open_router_base_url,
            chat_model=settings.open_router_chat_model,
            utility_model=settings.guard_model,
            active=True,
        )
    return LLMProviderConfig(
        provider="lmstudio",
        base_url=settings.lm_studio_base_url,
        chat_model=settings.lm_studio_chat_model,
        active=True,
    )


Role = Literal["chat", "utility"]


def build_client(config: LLMProviderConfig, role: Role = "chat") -> LMStudioClient:
    config = with_defaults(config)
    spec = PROVIDERS[config.provider]
    model = config.utility_model if role == "utility" and config.utility_model else config.chat_model
    headers = dict(spec.extra_headers)
    if config.provider == "anthropic" and config.api_key:
        # A camada OpenAI da Anthropic aceita Bearer; x-api-key cobre também /models (health).
        headers["x-api-key"] = config.api_key
    return LMStudioClient(
        base_url=config.base_url,
        model=model,
        api_key=config.api_key,
        max_tokens=spec.max_tokens or get_settings().lm_studio_max_tokens,
        extra_headers=headers,
        send_temperature=spec.send_temperature,
    )


class ConfigurableLLM:
    """Mesma interface do LMStudioClient, mas cada chamada usa o fornecedor ativo nesse momento."""

    def __init__(self, resolve: Callable[[], LLMProviderConfig], role: Role = "chat") -> None:
        self._resolve = resolve
        self.role = role

    def _client(self) -> LMStudioClient:
        return build_client(self._resolve(), self.role)

    @property
    def model(self) -> str:
        return self._client().model

    def health(self) -> bool:
        return self._client().health()

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        return self._client().chat(system_prompt, user_prompt, temperature)

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float = 0.2,
    ) -> dict:
        return self._client().complete(messages, tools=tools, tool_choice=tool_choice, temperature=temperature)

    def chat_stream(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> Iterator[str]:
        return self._client().chat_stream(system_prompt, user_prompt, temperature)
