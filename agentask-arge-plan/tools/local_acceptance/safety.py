"""Yalıtım kuralları: yalnız yerel adresler ve geçici dizinler. Saf fonksiyonlar; sır yazdırmaz."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import urlsplit

GUARDED_ENV = (
    "TARGET_BASE_URL",
    "TARGET_ALLOWED_ORIGINS",
    "LAB_PRIMARY_ORIGIN",
    "LAB_SECONDARY_ORIGIN",
    "MONGO_URI",
    "AUTOMATION_APPLICATIONS_JSON",
    "LLM_BASE_URL",
    "S3_ENDPOINT_URL",
)
_URL = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"',\]\}]+")
_KEYS = r"(SESSION_SIGNING_KEY|ADMIN_PASSWORD_HASH|PASSWORD|SECRET|TOKEN)"
_SECRET_PATTERNS = (
    (re.compile(r"scrypt\$[^\s\"']+"), "scrypt$***"),
    (re.compile(_KEYS + r"(\s*[=:]\s*)[^\s\"',]+", re.I), r"\1\2***"),
    (
        re.compile(r"(agentask_admin_session|Set-Cookie|Cookie|Authorization)(\s*[=:]\s*)[^\n]+", re.I),
        r"\1\2***",
    ),
    (re.compile(r"(bu-test-parolasi|kabul-test-parolasi)-\d+"), "***"),
    (re.compile(r"mongodb(\+srv)?://[^@\s/]+@"), "mongodb://***@"),
)


def is_loopback_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").strip("[]")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def non_local_urls(text: str) -> list[str]:
    return [u for u in _URL.findall(text) if not is_loopback_url(u)]


def env_violations(environ: Mapping[str, str]) -> list[str]:
    """Kabuğa verilmiş yerel olmayan adres: koşu reddedilir. Yalnız anahtar adı döner, değer yazılmaz."""
    return [key for key in GUARDED_ENV if environ.get(key) and non_local_urls(environ[key])]


def settings_violations(
    origins: Iterable[str],
    base_url: str | None,
    mongo_uri: str | None,
    directories: Iterable[Path],
    temp_root: Path,
) -> list[str]:
    problems: list[str] = []
    for origin in [*origins, *([base_url] if base_url else [])]:
        if not is_loopback_url(origin):
            problems.append("yerel olmayan hedef adres")
    if mongo_uri and non_local_urls(mongo_uri):
        problems.append("yerel olmayan MongoDB adresi")
    root = temp_root.resolve()
    for directory in directories:
        resolved = directory.resolve()
        if root != resolved and root not in resolved.parents:
            problems.append(f"geçici alan dışında dizin: {directory.name}")
    return problems


def redact(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
