from __future__ import annotations

import math
from collections import Counter, defaultdict

from backend.services.text_processing import tokenize_text


class KeywordIndex:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._chunks: dict[str, dict] = {}
        self._document_to_chunk_keys: dict[str, set[str]] = defaultdict(set)
        self._postings: dict[str, set[str]] = defaultdict(set)
        self._doc_freq: Counter[str] = Counter()
        self._avg_doc_len = 0.0

    def rebuild(self, items: list[dict]) -> None:
        self._chunks.clear()
        self._document_to_chunk_keys.clear()
        self._postings.clear()
        self._doc_freq.clear()
        self._avg_doc_len = 0.0

        for item in items:
            metadata = item["metadata"]
            self.index_chunk(text=item["text"], metadata=metadata)

    def index_document(self, document_id: str, chunks: list[dict]) -> None:
        self.remove_document(document_id)
        for chunk in chunks:
            self.index_chunk(text=chunk["text"], metadata=chunk["metadata"])

    def index_chunk(self, text: str, metadata: dict) -> None:
        chunk_key = self._chunk_key_from_metadata(metadata)
        tokens = tokenize_text(text)
        term_freq = Counter(tokens)
        unique_terms = set(term_freq)

        self._chunks[chunk_key] = {
            "text": text,
            "metadata": metadata,
            "term_freq": term_freq,
            "length": len(tokens),
        }
        self._document_to_chunk_keys[metadata["document_id"]].add(chunk_key)

        for term in unique_terms:
            if chunk_key not in self._postings[term]:
                self._postings[term].add(chunk_key)
                self._doc_freq[term] += 1

        self._recompute_avg_doc_len()

    def remove_document(self, document_id: str) -> None:
        chunk_keys = list(self._document_to_chunk_keys.get(document_id, set()))
        for chunk_key in chunk_keys:
            chunk = self._chunks.pop(chunk_key, None)
            if not chunk:
                continue
            for term in set(chunk["term_freq"]):
                postings = self._postings.get(term)
                if not postings:
                    continue
                postings.discard(chunk_key)
                if postings:
                    self._doc_freq[term] = len(postings)
                else:
                    self._postings.pop(term, None)
                    self._doc_freq.pop(term, None)
        self._document_to_chunk_keys.pop(document_id, None)
        self._recompute_avg_doc_len()

    def search(self, query_text: str, top_k: int, document_id: str | None = None) -> list[dict]:
        query_terms = tokenize_text(query_text)
        if not query_terms or not self._chunks:
            return []

        candidate_keys: set[str] = set()
        for term in query_terms:
            candidate_keys.update(self._postings.get(term, set()))

        if document_id is not None:
            candidate_keys &= self._document_to_chunk_keys.get(document_id, set())

        if not candidate_keys:
            return []

        raw_scores: list[tuple[str, float]] = []
        total_docs = max(len(self._chunks), 1)
        avg_doc_len = self._avg_doc_len or 1.0

        for chunk_key in candidate_keys:
            chunk = self._chunks[chunk_key]
            score = 0.0
            doc_len = chunk["length"] or 1
            for term in query_terms:
                tf = chunk["term_freq"].get(term, 0)
                if tf == 0:
                    continue
                doc_freq = self._doc_freq.get(term, 0)
                idf = math.log(1.0 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / avg_doc_len))
                score += idf * (numerator / denominator)
            if score > 0:
                raw_scores.append((chunk_key, score))

        raw_scores.sort(key=lambda item: item[1], reverse=True)
        top_scores = raw_scores[:top_k]
        max_score = top_scores[0][1] if top_scores else 1.0

        results: list[dict] = []
        for chunk_key, score in top_scores:
            chunk = self._chunks[chunk_key]
            results.append(
                {
                    "text": chunk["text"],
                    "metadata": chunk["metadata"],
                    "score": score / max_score if max_score else 0.0,
                }
            )
        return results

    def _recompute_avg_doc_len(self) -> None:
        if not self._chunks:
            self._avg_doc_len = 0.0
            return
        total_length = sum(chunk["length"] for chunk in self._chunks.values())
        self._avg_doc_len = total_length / len(self._chunks)

    @staticmethod
    def _chunk_key_from_metadata(metadata: dict) -> str:
        return f"{metadata['document_id']}|{metadata['page']}|{metadata['chunk_index']}"