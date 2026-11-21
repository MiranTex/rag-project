"""Contrato dos storages de ficheiros (disco local e S3) e do que corre por cima deles (exports, memória).

O S3 corre com o moto (S3 falso em memória) quando está instalado, e contra um servidor real (ex.: SeaweedFS,
MinIO) se TEST_S3_ENDPOINT estiver definida, com TEST_S3_BUCKET (já criado), TEST_S3_ACCESS_KEY_ID e
TEST_S3_SECRET_ACCESS_KEY. Sem nenhum dos dois, esses testes ficam por correr (skip).
"""

import os
import uuid

import pytest

from backend.config import Settings
from backend.services.export_store import ExportStore
from backend.services.memory import SessionMemory
from backend.services.object_storage import LocalStorage, S3Storage, storage_for


@pytest.fixture(params=["local", "s3-moto", "s3"])
def storage(request, tmp_path):
    if request.param == "local":
        yield LocalStorage(tmp_path / "files")
    elif request.param == "s3-moto":
        moto = pytest.importorskip("moto")
        import boto3

        with moto.mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket="app")
            yield S3Storage("", "app", prefix="uploads", client=client)
    else:
        endpoint = os.environ.get("TEST_S3_ENDPOINT")
        if not endpoint:
            pytest.skip("TEST_S3_ENDPOINT não definida")
        store = S3Storage(
            endpoint,
            os.environ.get("TEST_S3_BUCKET", "app"),
            prefix=f"tests-{uuid.uuid4().hex[:8]}",
            access_key_id=os.environ.get("TEST_S3_ACCESS_KEY_ID", ""),
            secret_access_key=os.environ.get("TEST_S3_SECRET_ACCESS_KEY", ""),
        )
        yield store
        for item in store.list("") + store.list("u-ana") + store.list("memory"):
            store.delete(item.key)


def test_put_get_exists_delete(storage):
    assert storage.get("a.pdf") is None and not storage.exists("a.pdf")
    storage.put("a.pdf", b"v1")
    storage.put("a.pdf", b"v2")
    assert storage.get("a.pdf") == b"v2" and storage.exists("a.pdf")
    storage.delete("a.pdf")
    storage.delete("a.pdf")  # apagar o que não existe não é erro
    assert storage.get("a.pdf") is None


def test_list_only_direct_children(storage):
    storage.put("a.pdf", b"123")
    storage.put("u-ana/resumo.md", b"# Resumo")
    storage.put("u-ana/dados.csv", b"a;b")
    storage.put("u-rui/outro.md", b"x")

    assert {(o.key, o.size) for o in storage.list("")} == {("a.pdf", 3)}
    assert {o.key for o in storage.list("u-ana/")} == {"u-ana/resumo.md", "u-ana/dados.csv"}
    assert storage.list("ninguem/") == []
    assert all(o.modified.tzinfo is not None for o in storage.list("u-ana/"))


def test_local_copy_gives_a_readable_path(storage):
    storage.put("doc.pdf", b"%PDF-1.4 conteudo")
    with storage.local_copy("doc.pdf") as path:
        assert path.read_bytes() == b"%PDF-1.4 conteudo"
        assert path.suffix == ".pdf"
    with pytest.raises(FileNotFoundError), storage.local_copy("falta.pdf"):
        pass


@pytest.mark.parametrize("key", ["", "../fora.txt", "a/../../fora.txt", "/abs.txt", "a//b.txt", "a\\b.txt"])
def test_rejects_keys_outside_the_area(storage, key):
    with pytest.raises(ValueError):
        storage.put(key, b"x")


def test_local_storage_writes_atomically(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.put("a.pdf", b"v1")
    storage.put("a.pdf", b"v2")
    assert [p.name for p in tmp_path.iterdir()] == ["a.pdf"]


def test_export_store_on_each_storage(storage):
    exports = ExportStore(storage).for_owner("u-ana")
    first = exports.create("Relatório final", "md", lambda path: path.write_text("# Um", encoding="utf-8"))
    second = exports.create("Relatório final", "md", lambda path: path.write_text("# Dois", encoding="utf-8"))

    assert (first, second) == ("Relatorio-final.md", "Relatorio-final-2.md")
    assert exports.read(second) == b"# Dois"
    assert {f.name for f in exports.list_files()} == {first, second}
    assert ExportStore(storage).for_owner("u-rui").list_files() == []
    assert exports.read("../u-rui/x.md") is None and exports.read("nada.md") is None


def test_session_memory_on_each_storage(storage):
    memory = SessionMemory(storage=storage, prefix="memory")
    memory.remember("sess-1", "O que é o RAG?", "Recuperação e geração.")
    assert "O que é o RAG?" in SessionMemory(storage=storage, prefix="memory").get_context("sess-1")
    assert memory.get_context("outra") == ""
    assert storage.exists("memory/sess-1.json")


def test_storage_for_uses_s3_only_with_endpoint(tmp_path):
    local = Settings(_env_file=None, upload_dir=str(tmp_path / "up"), export_dir=str(tmp_path / "ex"))
    assert isinstance(storage_for(local, "uploads"), LocalStorage)
    assert storage_for(local, "exports").root == tmp_path / "ex"

    s3 = Settings(
        _env_file=None,
        storage_endpoint="http://files:8333",
        storage_bucket="app",
        storage_access_key_id="chave",
        storage_secret_access_key="segredo",
    )
    uploads = storage_for(s3, "uploads")
    assert isinstance(uploads, S3Storage)
    assert (uploads.bucket, uploads.prefix) == ("app", "uploads/")
    assert uploads.client.meta.endpoint_url == "http://files:8333"
    assert uploads.client.meta.config.s3["addressing_style"] == "path"
    assert storage_for(s3, "exports").prefix == "exports/"
    with pytest.raises(ValueError):
        storage_for(s3, "outra")
