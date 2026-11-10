import os
import tempfile

# Rede de segurança: um teste que chegue às dependências reais (por exemplo, por desfazer um monkeypatch) usa
# uma base de dados e uma pasta temporárias e um Chroma inexistente, nunca os dados do volume da aplicação.
# Tem de correr antes de qualquer get_settings() (que fica em cache), por isso está ao nível do módulo.
_sandbox = tempfile.mkdtemp(prefix="rag-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_sandbox}/tests.db"
os.environ["UPLOAD_DIR"] = f"{_sandbox}/uploads"
os.environ["EXPORT_DIR"] = f"{_sandbox}/exports"
os.environ["CHROMA_HOST"] = "chroma-indisponivel-nos-testes"
