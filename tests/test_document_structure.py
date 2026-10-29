import json

from backend.services.document_structure import (
    classify_heading,
    find_abstract,
    find_keywords,
    find_references,
    split_sections,
)
from backend.services.metadata_extraction import propose_metadata

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
    assert classify_heading("1. Introdução") == "introduction"
    assert classify_heading("REVISÃO DA LITERATURA") == "literature"
    assert classify_heading("5.2 Trabalho futuro") == "future_work"
    assert classify_heading("Conclusões e trabalhos futuros") == "conclusion"
    assert classify_heading("Referências Bibliográficas") == "references"
    assert classify_heading("Abstract") == "abstract"
    assert classify_heading("3 Arquitetura do sistema") == "development"
    assert classify_heading("Apresentação e Discussão dos Resultados") == "results"
    assert classify_heading("Anexo 2") == "appendix"


def test_classify_heading_strips_page_counter_and_keeps_titles_ending_in_numbers():
    # Cabeçalho "N/80" que o pypdf cola à primeira linha da página.
    assert classify_heading("13/80 Introdução") == "introduction"
    assert classify_heading("70/80 Bibliografia") == "references"
    # Fora do índice, um título pode terminar num número.
    assert classify_heading("16/80 2 COVID – 19") == "development"


def test_classify_heading_ignores_table_of_contents_and_sentences():
    assert classify_heading("1 Introdução 1", in_toc=True) is None
    assert classify_heading("2 Estado da arte .......... 3") is None
    assert classify_heading("1. A EMPREGADORA é uma sociedade comercial.") is None
    assert classify_heading("3.1 Recolha de dados") is None
    assert classify_heading("Os resultados mostram uma melhoria clara") is None


def test_split_sections_assigns_every_segment():
    segments, headings = split_sections(THESIS_PAGES)

    assert [(h.section, h.page) for h in headings] == [
        ("abstract", 2),
        ("abstract", 2),
        ("front_matter", 3),
        ("introduction", 4),
        ("literature", 4),
        ("development", 5),
        ("conclusion", 6),
        ("future_work", 6),
        ("references", 6),
    ]
    assert headings[5].text == "CAPÍTULO 3 Arquitetura do sistema"
    by_section = {}
    for segment in segments:
        by_section[segment.section] = by_section.get(segment.section, "") + segment.text
    assert "Ana Martins" in by_section["front_matter"]
    assert "três módulos" in by_section["development"]
    assert "Recolha de dados" in by_section["development"]
    assert "catálogo nacional" in by_section["future_work"]


def test_split_sections_leaves_unstructured_documents_without_sections():
    pages = [(1, "CONTRATO DE TRABALHO\nCláusula 1.ª\nA retribuição é de 1500 euros.\nAnexo\nHorário")]

    segments, headings = split_sections(pages)

    assert headings == []
    assert all(segment.section is None for segment in segments)


def test_abstract_keywords_and_references():
    segments, headings = split_sections(THESIS_PAGES)

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

    def complete(self, messages, tools=None, tool_choice=None, temperature=0.2):
        self.prompts.append(messages[-1]["content"])
        if self.error:
            raise self.error
        return {"tool_calls": [{"function": {"arguments": json.dumps(self.arguments)}}]}


def test_propose_metadata_combines_rules_and_llm():
    segments, headings = split_sections(THESIS_PAGES)
    llm = _FakeLLM(
        {
            "title": "Sistema de Recomendação de Livros  com Aprendizagem Automática",
            "authors": ["Ana Martins"],
            "advisors": ["Prof. Doutor João Silva"],
            "year": "2024",
            "course": "Licenciatura em Engenharia Informática",
            "institution": "Universidade Lusófona",
            "keywords": ["sistemas de recomendação"],
        }
    )

    metadata = propose_metadata(THESIS_PAGES, segments, headings, llm)

    assert metadata.auto_filled
    assert metadata.title == "Sistema de Recomendação de Livros com Aprendizagem Automática"
    assert metadata.advisors == ["João Silva"]
    assert metadata.year == 2024
    # As palavras-chave escritas no documento ganham às deduzidas pelo modelo.
    assert metadata.keywords == ["recomendação", "aprendizagem automática", "bibliotecas"]
    assert metadata.abstract.startswith("Este trabalho apresenta")
    assert len(metadata.references) == 3
    assert "[Página 1]" in llm.prompts[0]


def test_propose_metadata_keeps_rule_based_fields_when_llm_fails():
    segments, headings = split_sections(THESIS_PAGES)

    metadata = propose_metadata(THESIS_PAGES, segments, headings, _FakeLLM(error=RuntimeError("offline")))

    assert not metadata.auto_filled
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
        ]
    )

    assert find_references(segments) == [
        "Acosta, A. L., Xavier, F., Chaves, L. S. M., Raat, H., & Zhou, H. (2020). A scoping review. Journal, 3(1).",
        "Amorim, M. A. L. (2013). Pharmacovigilance. Lisboa.",
    ]


def test_keywords_prefer_portuguese_and_tolerate_spacing():
    text = "Keywords: vaccines, adverse reactions\nPalavras -Chave: vacinas; reações adversas"
    assert find_keywords(text) == ["vacinas", "reações adversas"]
    assert find_keywords("Keywords: vaccines, adverse reactions") == ["vaccines", "adverse reactions"]
