import json

from backend.services.document_structure import (
    classify_heading,
    find_abstract,
    find_keywords,
    find_references,
    split_sections,
)
from backend.services.document_types import load_document_types, parse_document_types
from backend.services.metadata_extraction import propose_metadata

TYPES = load_document_types("backend/document_types.json")
ACADEMIC = TYPES.types["academic"].sections

THESIS_PAGES = [
    (
        1,
        "Universidade Lusófona\nLicenciatura em Engenharia Informática\n"
        "Sistema de Recomendação de Livros com Aprendizagem Automática\nAna Martins\n"
        "Orientador: Prof. Doutor João Silva\nLisboa, 2024",
    ),
    (
        2,
        "Resumo\nEste trabalho apresenta um sistema de recomendação para bibliotecas.\n"
        "Palavras-chave: recomendação; aprendizagem automática; bibliotecas\n"
        "Abstract\nThis work presents a recommender system for libraries.\n"
        "Keywords: recommendation, machine learning",
    ),
    (
        3,
        "Índice\n1 Introdução 1\n2 Estado da arte .......... 3\n3 Arquitetura do sistema 5\n4 Conclusões 9\nReferências 10",
    ),
    (
        4,
        "1. Introdução\nAs bibliotecas têm catálogos grandes.\n2. Estado da arte\nOs trabalhos anteriores usam filtragem colaborativa.",
    ),
    (
        5,
        "CAPÍTULO 3\nArquitetura do sistema\nO sistema tem três módulos.\n3.1 Recolha de dados\nOs dados vêm do catálogo.",
    ),
    (
        6,
        "4. Conclusões\nO sistema melhora as sugestões.\n4.1 Trabalho futuro\nIntegrar com o catálogo nacional.\n"
        "Referências\nSilva, J. (2020). Sistemas de recomendação. Lisboa: Editora.\n"
        "AGGARWAL, C. Recommender systems: the text-\nbook. Springer, 2016.\n"
        "[3] Smith, A. Deep learning for libraries, 2019.",
    ),
]


def test_classify_heading_recognises_numbered_and_bilingual_titles():
    assert classify_heading("1. Introdução", ACADEMIC) == "introduction"
    assert classify_heading("REVISÃO DA LITERATURA", ACADEMIC) == "literature"
    assert classify_heading("5.2 Trabalho futuro", ACADEMIC) == "future_work"
    assert classify_heading("Conclusões e trabalhos futuros", ACADEMIC) == "conclusion"
    assert classify_heading("Referências Bibliográficas", ACADEMIC) == "references"
    assert classify_heading("Abstract", ACADEMIC) == "abstract"
    assert classify_heading("3 Arquitetura do sistema", ACADEMIC) == "chapter"
    assert classify_heading("Apresentação e Discussão dos Resultados", ACADEMIC) == "results"
    assert classify_heading("Anexo 2", ACADEMIC) == "appendix"


def test_classify_heading_strips_page_counter_and_keeps_titles_ending_in_numbers():
    # Cabeçalho "N/80" que o pypdf cola à primeira linha da página.
    assert classify_heading("13/80 Introdução", ACADEMIC) == "introduction"
    assert classify_heading("70/80 Bibliografia", ACADEMIC) == "references"
    # Fora do índice, um título pode terminar num número.
    assert classify_heading("16/80 2 COVID – 19", ACADEMIC) == "chapter"


def test_classify_heading_ignores_table_of_contents_and_sentences():
    assert classify_heading("1 Introdução 1", ACADEMIC, in_toc=True) is None
    assert classify_heading("2 Estado da arte .......... 3", ACADEMIC) is None
    assert classify_heading("1. A EMPREGADORA é uma sociedade comercial.", ACADEMIC) is None
    assert classify_heading("3.1 Recolha de dados", ACADEMIC) is None
    assert classify_heading("Os resultados mostram uma melhoria clara", ACADEMIC) is None


def test_split_sections_assigns_every_segment():
    segments, headings = split_sections(THESIS_PAGES, ACADEMIC)

    assert [(h.section, h.page) for h in headings] == [
        ("abstract", 2),
        ("abstract", 2),
        ("front_matter", 3),
        ("introduction", 4),
        ("literature", 4),
        ("chapter", 5),
        ("conclusion", 6),
        ("future_work", 6),
        ("references", 6),
    ]
    assert headings[5].text == "CAPÍTULO 3 Arquitetura do sistema"
    by_section = {}
    for segment in segments:
        by_section[segment.section] = by_section.get(segment.section, "") + segment.text
    assert "Ana Martins" in by_section["front_matter"]
    assert "três módulos" in by_section["chapter"]
    assert "Recolha de dados" in by_section["chapter"]
    assert "catálogo nacional" in by_section["future_work"]


def test_split_sections_leaves_unstructured_documents_without_sections():
    pages = [(1, "CONTRATO DE TRABALHO\nCláusula 1.ª\nA retribuição é de 1500 euros.\nAnexo\nHorário")]

    segments, headings = split_sections(pages, ACADEMIC)

    assert headings == []
    assert all(segment.section is None for segment in segments)


def test_abstract_keywords_and_references():
    segments, headings = split_sections(THESIS_PAGES, ACADEMIC)

    assert find_abstract(segments, headings) == "Este trabalho apresenta um sistema de recomendação para bibliotecas."
    assert find_keywords(THESIS_PAGES[1][1]) == ["recomendação", "aprendizagem automática", "bibliotecas"]
    assert find_references(segments) == [
        "Silva, J. (2020). Sistemas de recomendação. Lisboa: Editora.",
        "AGGARWAL, C. Recommender systems: the textbook. Springer, 2016.",
        "[3] Smith, A. Deep learning for libraries, 2019.",
    ]


class _FakeLLM:
    def __init__(self, arguments=None, error=None):
        self.arguments = arguments
        self.error = error
        self.prompts = []
        self.systems = []
        self.tools = []

    def complete(self, messages, tools=None, tool_choice=None, temperature=0.2):
        self.prompts.append(messages[-1]["content"])
        self.systems.append(messages[0]["content"])
        self.tools.append(tools)
        if self.error:
            raise self.error
        return {"tool_calls": [{"function": {"arguments": json.dumps(self.arguments)}}]}


def test_propose_metadata_combines_rules_and_llm():
    llm = _FakeLLM(
        {
            "document_type": "academic",
            "title": "Sistema de Recomendação de Livros  com Aprendizagem Automática",
            "authors": ["Ana Martins"],
            "advisors": ["Prof. Doutor João Silva"],
            "year": "2024",
            "course": "Licenciatura em Engenharia Informática",
            "institution": "Universidade Lusófona",
            # Campo de outro tipo: não entra na ficha de um trabalho académico.
            "department": "Biblioteca",
            "keywords": ["sistemas de recomendação"],
        }
    )

    metadata = propose_metadata(THESIS_PAGES, TYPES, llm, "Repositório de trabalhos finais de curso.")

    assert metadata.auto_filled
    assert metadata.document_type == "academic"
    assert metadata.title == "Sistema de Recomendação de Livros com Aprendizagem Automática"
    assert metadata.fields == {
        "advisors": ["João Silva"],
        "course": "Licenciatura em Engenharia Informática",
        "institution": "Universidade Lusófona",
    }
    assert metadata.year == 2024
    # As palavras-chave escritas no documento ganham às deduzidas pelo modelo.
    assert metadata.keywords == ["recomendação", "aprendizagem automática", "bibliotecas"]
    assert metadata.abstract.startswith("Este trabalho apresenta")
    assert len(metadata.references) == 3
    assert "[Página 1]" in llm.prompts[0]
    assert "Repositório de trabalhos finais de curso." in llm.systems[0]


def test_propose_metadata_keeps_rule_based_fields_when_llm_fails():
    metadata = propose_metadata(THESIS_PAGES, TYPES, _FakeLLM(error=RuntimeError("offline")))

    assert not metadata.auto_filled
    assert metadata.document_type == "generic"
    assert metadata.title == ""
    assert metadata.abstract.startswith("Este trabalho apresenta")
    assert metadata.keywords == ["recomendação", "aprendizagem automática", "bibliotecas"]


def test_references_keep_author_lists_that_wrap_onto_a_new_line():
    segments, _ = split_sections(
        [
            (1, "Resumo\nTexto.\n1 Introdução\nTexto."),
            (
                2,
                "Referências\nAcosta, A. L., Xavier, F., Chaves, L. S. M.,\n"
                "Raat, H., & Zhou, H. (2020). A scoping review. Journal, 3(1).\n"
                "Amorim, M. A. L. (2013). Pharmacovigilance. Lisboa.",
            ),
        ],
        ACADEMIC,
    )

    assert find_references(segments) == [
        "Acosta, A. L., Xavier, F., Chaves, L. S. M., Raat, H., & Zhou, H. (2020). A scoping review. Journal, 3(1).",
        "Amorim, M. A. L. (2013). Pharmacovigilance. Lisboa.",
    ]


def test_keywords_prefer_portuguese_and_tolerate_spacing():
    text = "Keywords: vaccines, adverse reactions\nPalavras -Chave: vacinas; reações adversas"
    assert find_keywords(text) == ["vacinas", "reações adversas"]
    assert find_keywords("Keywords: vaccines, adverse reactions") == ["vaccines", "adverse reactions"]


def test_record_tool_offers_every_type_and_its_fields():
    llm = _FakeLLM({"document_type": "procedure", "title": "Gestão de acessos", "authors": [], "year": 2023, "keywords": []})
    propose_metadata([(1, "PR-07 Gestão de acessos")], TYPES, llm)

    properties = llm.tools[0][0]["function"]["parameters"]["properties"]
    assert properties["document_type"]["enum"] == ["generic", "academic", "procedure"]
    assert properties["course"]["description"].startswith("(só academic)")
    assert "department" in properties and "organization" in properties


PROCEDURE_PAGES = [
    (
        1,
        "PR-07 Gestão de acessos\n1. Objetivo\nDefinir como se pedem acessos.\n2. Âmbito\nTodos os colaboradores.\n"
        "3. Responsabilidades\nO responsável aprova.\n4. Descrição do procedimento\nO pedido é feito no portal.",
    )
]


def test_non_academic_type_uses_its_own_sections():
    segments, headings = split_sections(PROCEDURE_PAGES, TYPES.types["procedure"].sections)
    assert [h.section for h in headings] == ["purpose", "scope", "responsibilities", "procedure"]

    # Com as secções de um trabalho académico nenhum título é conhecido, e linhas numeradas antes do primeiro
    # título reconhecido podem ser listas: o documento fica sem estrutura.
    _, headings = split_sections(PROCEDURE_PAGES, ACADEMIC)
    assert headings == []


def test_document_types_config_is_validated():
    base = {"types": {"a": {"label": "A", "fields": [], "sections": []}}}
    assert parse_document_types(base).default == "a"

    bad_field = {"types": {"a": {"fields": [{"key": "title", "label": "Título"}]}}}
    bad_section = {"types": {"a": {"sections": [{"key": "chapter", "patterns": ["x"]}]}}}
    bad_default = {"default": "b", "types": {"a": {}}}
    for config in (bad_field, bad_section, bad_default):
        try:
            parse_document_types(config)
        except ValueError:
            continue
        raise AssertionError(f"configuração aceite: {config}")
