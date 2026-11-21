"""Ficheiros da aplicação (PDFs carregados, exports, memória das conversas) num disco local ou num storage
compatível com S3 (ex.: SeaweedFS no Base Stack, onde os contentores não têm disco persistente).

Cada área ("uploads", "exports") é um ObjectStorage com chaves relativas ("<id>.pdf", "<utilizador>/resumo.md").
Em disco, a área é a pasta UPLOAD_DIR ou EXPORT_DIR, como antes; no S3, um prefixo no bucket STORAGE_BUCKET.
"""

import mimetypes
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Protocol

AREAS = ("uploads", "exports")


@dataclass
class StoredObject:
    key: str
    size: int
    modified: datetime


class ObjectStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...

    def get(self, key: str) -> bytes | None:
        """Conteúdo do ficheiro, ou None se não existir."""

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Apaga o ficheiro; não faz nada se não existir."""

    def list(self, prefix: str = "") -> list[StoredObject]:
        """Ficheiros diretamente debaixo de `prefix` (ex.: "u-ana/"), sem descer a subpastas."""

    def local_copy(self, key: str):
        """Context manager com um caminho local para o ficheiro (pypdfium2, tesseract e pypdf precisam de um
        caminho). Em disco é o próprio ficheiro; no S3, uma cópia temporária apagada no fim."""


def _check_key(key: str) -> str:
    parts = key.split("/")
    if not key or key.startswith("/") or "\\" in key or any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Chave de ficheiro inválida: {key!r}")
    return key


class LocalStorage:
    """Ficheiros numa pasta local (comportamento de sempre, sem S3 configurado)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        path = (self.root / _check_key(key)).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"Chave de ficheiro inválida: {key!r}")
        return path

    def put(self, key: str, content: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Escrita atómica: um leitor concorrente nunca vê o ficheiro truncado a meio da escrita.
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_bytes(content)
        tmp.replace(target)

    def get(self, key: str) -> bytes | None:
        path = self.path(key)
        return path.read_bytes() if path.is_file() else None

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def list(self, prefix: str = "") -> list[StoredObject]:
        folder = self.path(prefix.rstrip("/")) if prefix.strip("/") else self.root
        if not folder.is_dir():
            return []
        objects = []
        for p in folder.iterdir():
            if p.is_file() and not p.name.startswith("."):
                stat = p.stat()
                key = f"{prefix.rstrip('/')}/{p.name}" if prefix.strip("/") else p.name
                objects.append(StoredObject(key=key, size=stat.st_size, modified=datetime.fromtimestamp(stat.st_mtime, UTC)))
        return objects

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        path = self.path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        yield path


class S3Storage:
    """Ficheiros num bucket S3 (boto3) debaixo de um prefixo. O SeaweedFS precisa de endereçamento path-style."""

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        prefix: str = "",
        region: str = "us-east-1",
        access_key_id: str = "",
        secret_access_key: str = "",
        client=None,
    ) -> None:
        self.bucket = bucket
        self.prefix = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3",
                endpoint_url=endpoint or None,
                region_name=region or None,
                aws_access_key_id=access_key_id or None,
                aws_secret_access_key=secret_access_key or None,
                config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5, "mode": "standard"}),
            )
        self.client = client

    def _key(self, key: str) -> str:
        return self.prefix + _check_key(key)

    @staticmethod
    def _missing(error: Exception) -> bool:
        code = getattr(error, "response", {}).get("Error", {}).get("Code", "")
        return code in ("404", "NoSuchKey", "NotFound")

    def put(self, key: str, content: bytes) -> None:
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=content, ContentType=content_type)

    def get(self, key: str) -> bytes | None:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except Exception as error:
            if self._missing(error):
                return None
            raise

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception as error:
            if self._missing(error):
                return False
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))

    def list(self, prefix: str = "") -> list[StoredObject]:
        folder = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
        if folder:
            _check_key(folder.rstrip("/"))
        objects = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix + folder, Delimiter="/"):
            for item in page.get("Contents", []):
                name = item["Key"][len(self.prefix + folder) :]
                if name and not name.startswith("."):
                    modified = item["LastModified"]
                    if modified.tzinfo is None:
                        modified = modified.replace(tzinfo=UTC)
                    objects.append(StoredObject(key=folder + name, size=int(item["Size"]), modified=modified))
        return objects

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        content = self.get(key)
        if content is None:
            raise FileNotFoundError(key)
        fd, name = tempfile.mkstemp(prefix="rag-", suffix=Path(key).suffix)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            yield Path(name)
        finally:
            Path(name).unlink(missing_ok=True)


@lru_cache(maxsize=16)
def _s3(endpoint: str, bucket: str, prefix: str, region: str, access_key_id: str, secret_access_key: str) -> S3Storage:
    # Um cliente boto3 por área (é thread-safe e caro de criar).
    return S3Storage(endpoint, bucket, prefix, region, access_key_id, secret_access_key)


def storage_for(settings, area: str) -> ObjectStorage:
    """S3 quando STORAGE_ENDPOINT está definido; senão a pasta local da área (UPLOAD_DIR ou EXPORT_DIR)."""
    if area not in AREAS:
        raise ValueError(f"Área de ficheiros desconhecida: {area}")
    if settings.storage_endpoint:
        return _s3(
            settings.storage_endpoint,
            settings.storage_bucket,
            area,
            settings.storage_region,
            settings.storage_access_key_id,
            settings.storage_secret_access_key,
        )
    return LocalStorage(settings.upload_dir if area == "uploads" else settings.export_dir)
