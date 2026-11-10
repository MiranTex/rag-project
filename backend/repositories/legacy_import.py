import logging
from pathlib import Path

from backend.models import DocumentMetadata
from backend.repositories.contracts import DocumentRepository, ExtractionRepository
from backend.services.document_registry import DocumentRegistry
from backend.services.extraction_review import ExtractionStore

logger = logging.getLogger(__name__)


def import_legacy_json(
    documents: DocumentRepository,
    extractions: ExtractionRepository,
    registry_path: str = "backend/storage/documents.json",
    extractions_dir: str = "backend/storage/extractions",
) -> int:
    """Importa o registo e as extrações em JSON (versão anterior à base de dados). Só corre com a base vazia;
    no fim renomeia o documents.json para .imported, que fica como cópia de segurança."""
    path = Path(registry_path)
    if not path.exists() or documents.list_documents():
        return 0

    legacy_documents = DocumentRegistry(str(path))
    legacy_extractions = ExtractionStore(extractions_dir)
    imported = 0
    for info in legacy_documents.list_documents():
        documents.add_or_replace(info)
        pages = legacy_extractions.load(info.document_id)
        if pages:
            extractions.save(info.document_id, pages)
        metadata = legacy_extractions.load_metadata(info.document_id)
        if metadata != DocumentMetadata():
            extractions.save_metadata(info.document_id, metadata)
        imported += 1

    path.rename(path.with_name(path.name + ".imported"))
    logger.info("Importados %d documento(s) do registo JSON para a base de dados", imported)
    return imported
