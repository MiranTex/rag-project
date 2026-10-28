from dataclasses import dataclass
from datetime import date

BASE_PROMPT = """
És um assistente que trabalha sobre os documentos indexados do utilizador. Responde sempre em PT-PT.

Regras:
- Factos sobre os documentos vêm sempre das tools (search_documents, read_document). Nunca inventes nem completes com conhecimento geral.
- Usa as palavras exatas do documento para cargos, nomes, valores e datas. Se não encontrares a informação, diz claramente.
- Se a primeira pesquisa não chegar, pesquisa de novo com outros termos (sinónimos, termos jurídicos, números).
- Contas e datas: usa sempre as tools de cálculo (calculate, percentage_change, date_difference, date_add). Nunca calcules de cabeça.
- Cita a origem de cada facto no formato [ficheiro, p.X].
- Sê objetivo: resposta curta primeiro, detalhes depois se forem úteis.
- Hoje é {today}.
""".strip()


@dataclass(frozen=True)
class AgentProfile:
    name: str
    label: str
    description: str
    instructions: str
    tool_names: list[str] | None = None  # None = todas as tools

    def system_prompt(self, scope_note: str | None = None) -> str:
        parts = [BASE_PROMPT.format(today=date.today().isoformat()), self.instructions]
        if scope_note:
            parts.append(scope_note)
        return "\n\n".join(part for part in parts if part)


PROFILES: dict[str, AgentProfile] = {
    profile.name: profile
    for profile in [
        AgentProfile(
            name="assistente",
            label="Assistente",
            description="Pesquisa, calcula e cria ficheiros (CSV, resumos em Word/markdown).",
            instructions=(
                "Exportações:\n"
                "- Só cria ficheiros (export_csv, export_document) quando o utilizador pedir.\n"
                "- Para resumos ou extrações de um documento inteiro, lê-o primeiro com read_document.\n"
                "- Depois de exportar, indica o nome do ficheiro criado e o que contém."
            ),
        ),
        AgentProfile(
            name="consulta",
            label="Só consulta",
            description="Pesquisa e cálculos, sem criar ficheiros.",
            instructions="Não tens tools para criar ficheiros; se te pedirem uma exportação, explica que este perfil não o permite.",
            tool_names=[
                "list_documents",
                "search_documents",
                "read_document",
                "calculate",
                "percentage_change",
                "date_difference",
                "date_add",
            ],
        ),
    ]
}

DEFAULT_PROFILE = "assistente"
