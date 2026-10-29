from backend.models import DocumentInfo, DocumentMetadata
from backend.services.document_naming import clean_name, render_name, suggest_name, unique_name
from backend.services.document_registry import DocumentRegistry
from backend.services.document_renamer import DocumentRenamer
from backend.services.document_types import load_document_types

TYPES = load_document_types("backend/document_types.json")
INFO = DocumentInfo(document_id="d", filename="scan_0042.pdf", sha256="x", created_at="2026-10-29T10:00:00+00:00", chunk_count=0)


def _suggest(type_key, **metadata):
    doc_type = TYPES.types[type_key]
    return suggest_name(DocumentMetadata(document_type=type_key, **metadata), doc_type, TYPES.name_pattern_for(doc_type), INFO)


def test_render_name_drops_empty_parts_and_optional_groups():
    pattern = "{code} - {title}[ (v{version})]"
    assert render_name(pattern, {"code": "PR-07", "title": "Acessos", "version": "3"}) == "PR-07 - Acessos (v3)"
    assert render_name(pattern, {"code": "", "title": "Acessos", "version": ""}) == "Acessos"
    assert render_name("{year} - {title}", {"year": "", "title": "Relatório"}) == "Relatório"


def test_suggest_name_uses_type_pattern():
    assert _suggest("generic", title="Relatório de Atividades", year=2023) == "2023 - Relatório de Atividades.pdf"
    assert (
        _suggest("academic", title="Recomendação de Livros", year=2024, authors=["Ana Martins", "Rui Sá"])
        == "2024 - Recomendação de Livros - Ana Martins.pdf"
    )
    assert (
        _suggest("procedure", title="Gestão de Acessos", fields={"code": "PR-07", "version": "3"})
        == "PR-07 - Gestão de Acessos (v3).pdf"
    )
    # Sem título não há sugestão: o nome original diz mais do que "2024.pdf".
    assert _suggest("generic", year=2024) == ""


def test_suggest_name_shortens_long_titles_on_word_boundary():
    name = _suggest("generic", title="Estudo " * 30, year=2021)
    assert name.startswith("2021 - Estudo") and name.endswith("….pdf")
    assert len(name) <= 120 + len(".pdf")


def test_clean_name_removes_forbidden_characters():
    assert clean_name('  Ata 3/2024: "Direção"?  ') == "Ata 3 2024 Direção.pdf"
    assert clean_name("relatorio.PDF") == "relatorio.pdf"
    assert clean_name(" / ") == ""


def test_unique_name_appends_counter_ignoring_case():
    taken = {"2024 - Ata.pdf", "2024 - ata (2).pdf"}
    assert unique_name("2024 - ATA.pdf", taken) == "2024 - ATA (3).pdf"
    assert unique_name("Outro.pdf", taken) == "Outro.pdf"


class _Store:
    def __init__(self):
        self.updates = []

    def update_document_metadata(self, document_id, updates):
        self.updates.append((document_id, updates))
        return 1

    def list_chunks(self, document_id=None):
        return []


class _Keywords:
    def index_document(self, document_id, chunks):
        pass


def test_renaming_a_legacy_document_pins_its_file_on_disk(tmp_path):
    registry = DocumentRegistry(str(tmp_path / "docs.json"))
    # Documento antigo: guardado em disco com o nome original, sem storage_name.
    registry.add_or_replace(INFO.model_copy(update={"filename": "Anara dos Santos (1).pdf", "status": "indexed"}))
    store = _Store()
    renamer = DocumentRenamer(registry, store, _Keywords(), store, TYPES)

    renamed = renamer.rename("d", None, DocumentMetadata(document_type="generic", title="Estudo de Reações", year=2021))

    assert renamed.filename == "2021 - Estudo de Reações.pdf"
    assert renamed.storage_name == "Anara dos Santos (1).pdf"
    assert renamed.original_filename == "Anara dos Santos (1).pdf"
    # Indexado: o nome muda nos excertos e no índice de documentos.
    assert store.updates == [("d", {"filename": renamed.filename})] * 2
