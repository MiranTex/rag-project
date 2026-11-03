"""Configurações que se podem alterar na aplicação (página de configurações), por cima das do .env.

Só entram as funcionais: as de infraestrutura (base de dados, Chroma, modelos, autenticação, pastas) ficam no
.env porque mudá-las com a aplicação a correr não faz sentido ou exige reiniciar. Cada entrada descreve como o
frontend mostra o campo e os limites validados ao guardar."""

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import TypeAdapter, ValidationError

from backend.config import Settings

SettingKind = Literal["text", "textarea", "int", "float", "bool", "choice", "weights"]

RERANK_FACTORS = ("vector", "lexical", "keyword", "position", "density")


@dataclass(frozen=True)
class EditableSetting:
    key: str
    label: str
    help: str
    group: str
    kind: SettingKind
    choices: tuple[str, ...] = field(default=())
    minimum: float | None = None
    maximum: float | None = None


CATALOG: tuple[EditableSetting, ...] = (
    EditableSetting(
        "knowledge_base_description",
        "Descrição da base de conhecimento",
        "Uma frase sobre os documentos desta base. Usada pelo agente, pelo filtro de âmbito e na ficha dos documentos.",
        "Base de conhecimento",
        "textarea",
    ),
    EditableSetting(
        "top_k", "Excertos por resposta", "Quantos excertos dos documentos entram em cada resposta.", "Pesquisa", "int",
        minimum=1, maximum=20,
    ),
    EditableSetting(
        "retrieval_mode_default",
        "Modo de pesquisa",
        "hybrid combina significado e palavras-chave; vector só significado; keyword só palavras-chave.",
        "Pesquisa",
        "choice",
        choices=("hybrid", "vector", "keyword"),
    ),
    EditableSetting(
        "rerank_weights_default",
        "Pesos da ordenação",
        "Peso de cada fator ao ordenar os excertos encontrados (não precisam de somar 1).",
        "Pesquisa",
        "weights",
    ),
    EditableSetting(
        "agent_max_steps", "Passos do agente", "Máximo de ferramentas que o agente usa antes de responder.", "Agente", "int",
        minimum=1, maximum=20,
    ),
    EditableSetting(
        "guard_enabled",
        "Filtro de âmbito",
        "Recusa perguntas fora do âmbito da base de conhecimento antes de chegarem ao agente.",
        "Agente",
        "bool",
    ),
    EditableSetting(
        "require_separate_approver",
        "Aprovação por outra pessoa",
        "Quem carrega (ou extrai de novo) um documento não o pode aprovar. Desliga a aprovação automática.",
        "Documentos",
        "bool",
    ),
    EditableSetting(
        "auto_approve_clean_documents",
        "Aprovar automaticamente documentos sem alertas",
        "Documentos sem alertas na extração são indexados sem revisão.",
        "Documentos",
        "bool",
    ),
    EditableSetting(
        "metadata_extraction_enabled",
        "Propor a ficha com o modelo",
        "Na extração, o modelo propõe tipo, título, autores, ano e restantes campos da ficha.",
        "Documentos",
        "bool",
    ),
    EditableSetting(
        "auto_rename_documents",
        "Nome automático",
        "No upload, o documento recebe um nome gerado da ficha (ex.: \"2024 - Título\").",
        "Documentos",
        "bool",
    ),
    EditableSetting("ocr_enabled", "OCR", "Ler páginas digitalizadas (sem camada de texto) com o Tesseract.", "Documentos", "bool"),
    EditableSetting(
        "ocr_languages", "Línguas do OCR", "Códigos do Tesseract separados por + (ex.: por+eng).", "Documentos", "text"
    ),
    EditableSetting(
        "review_max_garbled_ratio",
        "Limite de texto ilegível",
        "Fração de caracteres estranhos a partir da qual uma página fica com alerta na revisão (0 a 1).",
        "Documentos",
        "float",
        minimum=0,
        maximum=1,
    ),
)

BY_KEY = {setting.key: setting for setting in CATALOG}


def _validate_weights(value: Any) -> str:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise ValueError("Pesos inválidos (JSON).") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Pesos têm de ser um objeto {fator: peso}.")
    if unknown := set(parsed) - set(RERANK_FACTORS):
        raise ValueError(f"Fatores desconhecidos: {', '.join(sorted(unknown))}")
    weights: dict[str, float] = {}
    for factor, weight in parsed.items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0:
            raise ValueError(f"O peso de {factor} tem de ser um número maior ou igual a 0.")
        weights[factor] = float(weight)
    if sum(weights.values()) <= 0:
        raise ValueError("Pelo menos um peso tem de ser maior do que 0.")
    return json.dumps(weights)


def validate_setting(key: str, value: Any) -> Any:
    """Valor pronto a guardar, ou ValueError com uma mensagem para o utilizador."""
    setting = BY_KEY.get(key)
    if setting is None:
        raise ValueError(f"Configuração desconhecida ou não editável: {key}")
    if setting.kind == "weights":
        return _validate_weights(value)
    # Em Python, True é um int: sem isto, "top_k": true passaria como 1.
    if setting.kind != "bool" and isinstance(value, bool):
        raise ValueError(f"{setting.label}: valor inválido.")
    try:
        value =TypeAdapter(Settings.model_fields[key].annotation).validate_python(value, strict=setting.kind == "bool")
    except ValidationError as exc:
        raise ValueError(f"{setting.label}: valor inválido.") from exc
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError(f"{setting.label}: não pode ficar vazio.")
    if setting.choices and value not in setting.choices:
        raise ValueError(f"{setting.label}: tem de ser {', '.join(setting.choices)}.")
    if setting.minimum is not None and value < setting.minimum:
        raise ValueError(f"{setting.label}: mínimo {setting.minimum:g}.")
    if setting.maximum is not None and value > setting.maximum:
        raise ValueError(f"{setting.label}: máximo {setting.maximum:g}.")
    return value
