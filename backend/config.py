from functools import lru_cache
from pathlib import Path
import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    lm_studio_base_url: str = "http://127.0.0.1:1234/v1"
    lm_studio_chat_model: str = "local-model"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    chroma_host: str = "127.0.0.1"
    chroma_port: int = 8001
    chroma_collection: str = "rag_documents"

    top_k: int = 4
    chunk_size: int = 1000
    chunk_overlap: int = 150
    upload_dir: str = "data/uploads"
    rerank_weights_default: str = '{"vector": 0.60, "keyword": 0.25, "position": 0.10, "density": 0.05}'
    rerank_weights_grounding: str = '{"vector": 0.45, "keyword": 0.30, "position": 0.20, "density": 0.05}'

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def parse_rerank_weights(self, profile: str = "default") -> dict[str, float]:
        raw = self.rerank_weights_default if profile == "default" else self.rerank_weights_grounding
        parsed = json.loads(raw)
        return {
            "vector": float(parsed.get("vector", 0.60)),
            "keyword": float(parsed.get("keyword", 0.25)),
            "position": float(parsed.get("position", 0.10)),
            "density": float(parsed.get("density", 0.05)),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    return settings
