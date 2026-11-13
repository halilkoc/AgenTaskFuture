"""Log ve teşhis metinlerinden sırların ayıklanması.

Bu bir son savunmadır; asıl koruma log alanlarının izinli listeyle sınırlı olmasıdır (infrastructure/logging).
Kapsanan: URL kullanıcı bilgisi ve sorgu değerleri, Authorization/Cookie başlıkları, Bearer/Basic değerleri,
gizli adlı anahtar=değer çiftleri ve domain/sensitive'in tanıdığı kart, T.C. kimlik, IBAN, JWT, kimlik bilgisi
benzeri diziler. Doğal metinde geçen müşteri adı gibi değerleri tanıyamaz; bu yüzden yabancı istisna mesajları
hiç loglanmaz.
"""

from __future__ import annotations

import re

from agentask.domain.sensitive import scan

MASK = "***"
_MAX_TEXT = 2000
_URL = re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.-]*)://([^\s\"'<>]+)")
_HEADER = re.compile(r"(?i)\b(proxy-authorization|authorization|set-cookie|cookie)(\"?\s*[:=]\s*)[^\r\n]*")
_SCHEME_VALUE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{4,}")
_KEY_NAMES = (
    r"[\w.-]*(?:password|passwd|pwd|parola|şifre|sifre|token|secret|api[_-]?key|access[_-]?key|"
    r"signing[_-]?key|credential|jsessionid|sessionid|signature)[\w.-]*|pin|otp|cvv|cvc"
)
_KEY_VALUE = re.compile(
    rf"(?i)(?<![\w.-])({_KEY_NAMES})(?![\w.-])(\"?'?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)


def _mask_url(match: re.Match[str]) -> str:
    scheme, rest = match.group(1), match.group(2)
    trailing = ""
    while rest and rest[-1] in ".,;:)]}":
        trailing = rest[-1] + trailing
        rest = rest[:-1]
    rest, had_fragment, _ = rest.partition("#")
    rest, had_query, _ = rest.partition("?")
    authority, slash, path = rest.partition("/")
    # Kullanıcı bilgisi içinde '@' geçebilir; son '@' ayraçtır.
    if "@" in authority:
        authority = f"{MASK}@{authority.rsplit('@', 1)[1]}"
    suffix = f"?{MASK}" if had_query else ""
    suffix += f"#{MASK}" if had_fragment else ""
    return f"{scheme}://{authority}{slash}{path}{suffix}{trailing}"


def redact_structural(text: str) -> str:
    """URL, başlık ve gizli adlı anahtar=değer maskesi. Kimlik alanlarına da uygulanabilir."""
    text = _HEADER.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)
    text = _URL.sub(_mask_url, text)
    text = _SCHEME_VALUE.sub(lambda m: f"{m.group(1)} {MASK}", text)
    return _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


def redact_text(text: str) -> str:
    """Serbest metin: yapısal maske + kart/kimlik/IBAN/JWT/kimlik bilgisi benzeri diziler."""
    masked = redact_structural(text)[:_MAX_TEXT]
    for finding in reversed(scan(masked)):
        if finding.kind != "secret_keyword":
            masked = f"{masked[: finding.start]}[gizli]{masked[finding.end :]}"
    return masked
