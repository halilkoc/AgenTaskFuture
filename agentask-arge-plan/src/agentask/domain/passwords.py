"""Geçici admin girişi için parola hash'i (scrypt; yalnız standart kitaplık). Düz metin parola saklanmaz."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

MIN_PASSWORD_LENGTH = 12
_N, _R, _P = 2**15, 8, 1
_MAX_MEM = 128 * 1024 * 1024
_FORMAT = re.compile(r"^scrypt:(\d{1,8}):(\d{1,2}):(\d{1,2}):([A-Za-z0-9_-]{16,}):([A-Za-z0-9_-]{32,})$")


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAX_MEM, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt:{_N}:{_R}:{_P}:{_encode(salt)}:{_encode(_derive(password, salt, _N, _R, _P))}"


def _parsed(stored: str) -> tuple[int, int, int, bytes, bytes] | None:
    match = _FORMAT.fullmatch(stored)
    if match is None:
        return None
    n, r, p = int(match[1]), int(match[2]), int(match[3])
    if n < 2**14 or n > 2**18 or n & (n - 1) or not 1 <= r <= 16 or not 1 <= p <= 4:
        return None
    return n, r, p, _decode(match[4]), _decode(match[5])


def is_valid_hash(stored: str) -> bool:
    return _parsed(stored) is not None


def verify_password(password: str, stored: str) -> bool:
    parsed = _parsed(stored)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    return hmac.compare_digest(_derive(password, salt, n, r, p), expected)
