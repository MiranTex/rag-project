import chromadb
from chromadb.api.models.Collection import Collection


class VectorStore:
    def __init__(self, host: str, port: int, collection_name: str) -> None:
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection_name = collection_name
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self) -> Collection:
        return self.client.get_or_create_collection(name=self.collection_name)

    def heartbeat(self) -> int:
        return self.client.heartbeat()

    def upsert_chunks(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def delete_document(self, document_id: str) -> None:
        self.collection.delete(where={"document_id": document_id})

    def list_chunks(self, document_id: str | None = None) -> list[dict]:
        where = {"document_id": document_id} if document_id else None
        result = self.collection.get(where=where, include=["metadatas", "documents"])

        items: list[dict] = []
        docs = result.get("documents", [])
        metas = result.get("metadatas", [])
        for doc, meta in zip(docs, metas, strict=False):
            items.append(
                {
                    "text": doc,
                    "metadata": meta,
                }
            )
        return items

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
        document_id: str | None = None,
    ) -> list[dict]:
        where = {"document_id": document_id} if document_id else None
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["metadatas", "documents", "distances"],
        )

        items: list[dict] = []
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances, strict=False):
            score = 1.0 / (1.0 + float(dist))
            items.append(
                {
                    "text": doc,
                    "metadata": meta,
                    "score": score,
                }
            )
        return items
