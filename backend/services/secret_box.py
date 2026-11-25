"""Cifra das chaves de API guardadas por utilizadores e projetos (Fernet: AES-128-CBC + HMAC).

A chave mestra vem de CREDENTIALS_SECRET_KEY (só do .env, nunca editável na aplicação). Qualquer texto serve:
deriva-se dele a chave Fernet. Sem ela, a aplicação recusa guardar chaves próprias em vez de as guardar em claro.
Mudar a chave mestra torna ilegíveis as chaves já guardadas: as pessoas têm de as voltar a colar."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretBoxUnavailable(RuntimeError):
    """Sem CREDENTIALS_SECRET_KEY não se guardam nem leem chaves próprias."""


class SecretBox:
    def __init__(self, master_key: str) -> None:
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(master_key.encode()).digest())) if master_key else None

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def _require(self) -> Fernet:
        if self._fernet is None:
            raise SecretBoxUnavailable(
                "As chaves de API próprias estão desligadas: falta CREDENTIALS_SECRET_KEY na configuração do servidor."
            )
        return self._fernet

    def encrypt(self, value: str) -> str:
        return self._require().encrypt(value.encode()).decode() if value else ""

    def decrypt(self, value: str) -> str:
        """Texto da chave; "" se estiver vazia ou tiver sido cifrada com outra chave mestra."""
        if not value:
            return ""
        try:
            return self._require().decrypt(value.encode()).decode()
        except InvalidToken:
            return ""
