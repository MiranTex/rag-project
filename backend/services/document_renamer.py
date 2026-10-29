import logging
from threading import Lock

from backend.models import DocumentInfo, DocumentMetadata
from backend.services.document_naming import clean_name, suggest_name, unique_name
from backend.services.document_registry import DocumentRegistry
from backend.services.document_types import DocumentTypes
from backend.services.keyword_index import KeywordIndex
from backend.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


class RenameError(ValueError):
    pass


class DocumentRenamer:
    """Nome dos documentos no sistema. É gerado da ficha proposta no upload e depois não muda sozinho (nem com
    correções da ficha, nem ao extrair de novo). Num documento indexado, um nome mudado à mão chega também aos
    excertos e ao índice de documentos, para as fontes e citações mostrarem o nome novo."""

    def __init__(
        self,
        registry: DocumentRegistry,
        vector_store: VectorStore,
        keyword_index: KeywordIndex,
        profile_store: VectorStore,
        document_types: DocumentTypes,
        auto_rename: bool = True,
    ) -> None:
        self.registry = registry
        self.vector_store = vector_store
        self.keyword_index = keyword_index
        self.profile_store = profile_store
        self.document_types = document_types
        self.auto_rename = auto_rename
        self._lock = Lock()

    def suggestion(self, info: DocumentInfo, metadata: DocumentMetadata) -> str:
        doc_type = self.document_types.get(metadata.document_type)
        return suggest_name(metadata, doc_type, self.document_types.name_pattern_for(doc_type), info)

    def _taken(self, document_id: str) -> set[str]:
        return {d.filename for d in self.registry.list_documents() if d.document_id != document_id}

    @staticmethod
    def _pin_storage(info: DocumentInfo) -> DocumentInfo:
        """Documentos antigos estão em disco com o nome original: fixa-o antes de o nome mudar."""
        if info.storage_name:
            return info
        return info.model_copy(update={"storage_name": info.filename, "original_filename": info.original_filename or info.filename})

    def name_at_upload(self, info: DocumentInfo, metadata: DocumentMetadata) -> DocumentInfo:
        """Nome de um documento acabado de carregar, a partir da ficha proposta (não grava). Sem título na
        ficha fica o nome original."""
        suggestion = self.suggestion(info, metadata) if self.auto_rename else ""
        if not suggestion:
            return info
        return info.model_copy(update={"filename": unique_name(suggestion, self._taken(info.document_id)), "name_source": "suggested"})

    def rename(self, document_id: str, name: str | None, metadata: DocumentMetadata) -> DocumentInfo:
        """Muda o nome (None volta ao sugerido) e propaga-o se o documento já estiver indexado."""
        with self._lock:
            info = self.registry.find_by_id(document_id)
            if info is None:
                raise RenameError("Documento não encontrado.")
            if name and name.strip():
                cleaned = clean_name(name)
                if not cleaned:
                    raise RenameError("Nome inválido.")
                renamed = self._pin_storage(info).model_copy(
                    update={"filename": unique_name(cleaned, self._taken(document_id)), "name_source": "manual"}
                )
            else:
                suggestion = self.suggestion(info, metadata)
                if not suggestion:
                    raise RenameError("A ficha não tem título: não há nome sugerido.")
                renamed = self._pin_storage(info).model_copy(
                    update={"filename": unique_name(suggestion, self._taken(document_id)), "name_source": "suggested"}
                )
            self.save(info, renamed)
            return renamed

    def save(self, before: DocumentInfo, after: DocumentInfo) -> None:
        """Grava no registo e, se o documento estiver indexado e o nome mudou, nos índices."""
        if before.filename != after.filename and after.status == "indexed":
            updates = {"filename": after.filename}
            count = self.vector_store.update_document_metadata(after.document_id, updates)
            self.profile_store.update_document_metadata(after.document_id, updates)
            self.keyword_index.index_document(after.document_id, self.vector_store.list_chunks(after.document_id))
            logger.info("%s renomeado para %s (%d excertos)", before.filename, after.filename, count)
        self.registry.add_or_replace(after)
