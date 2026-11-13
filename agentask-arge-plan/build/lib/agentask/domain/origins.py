"""Origin kuralları: hedef uygulamaya yalnızca izinli origin'lerde gidilir."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

_ALWAYS_ALLOWED = frozenset({"about:blank"})


def normalize_origin(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("origin http(s)://host[:port] biçiminde olmalı")
    if parts.path not in {"", "/"} or parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError("origin yol, sorgu veya kimlik bilgisi içeremez")
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def origin_of(url: str) -> str | None:
    """URL'nin origin'i; http(s) değilse veya kimlik bilgisi içeriyorsa None."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


class OriginPolicy:
    def __init__(self, allowed: Iterable[str]) -> None:
        self._allowed = frozenset(normalize_origin(item) for item in allowed)

    @property
    def allowed(self) -> frozenset[str]:
        return self._allowed

    def allows(self, url: str) -> bool:
        if url in _ALWAYS_ALLOWED:
            return True
        origin = origin_of(url)
        return origin is not None and origin in self._allowed
