"""Hash de palavras-passe com scrypt (biblioteca padrão), no formato scrypt$n$r$p$salt$hash."""

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)
