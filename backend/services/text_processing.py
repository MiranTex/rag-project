import re


TOKEN_PATTERN = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")


def tokenize_text(text: str) -> list[str]:
    return [token for token in TOKEN_PATTERN.findall(text.lower()) if token]


def tokenize_text_set(text: str) -> set[str]:
    return set(tokenize_text(text))