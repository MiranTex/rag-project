from functools import lru_cache

from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def load_embedding_model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)


def embed_texts(model_name: str, texts: list[str]) -> list[list[float]]:
    model = load_embedding_model(model_name)
    vectors = model.encode(texts, normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]


def embed_query(model_name: str, question: str) -> list[float]:
    model = load_embedding_model(model_name)
    vector = model.encode([question], normalize_embeddings=True)[0]
    return vector.tolist()
