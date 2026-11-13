"""Serbest metinde hassas veri ŞÜPHESİ tespiti.

Bu modül eksiksiz bir DLP değildir ve bütün hassas verilerin yakalandığını iddia etmez. Amacı karar vermektir:
şüphe varsa metin modele gönderilmez, değer parametre olarak bağlanmaz ve kullanıcıdan secret'ı serbest metne
yazmadan, yapılandırılmış/güvenli yoldan girmesi istenir. Bulgular değeri değil, yalnız türü ve konumu taşır.

Kapsanan türler: secret anahtar kelimesi (parola, şifre, pin, otp, cvv, token, api key, secret …), Luhn
geçerli kart numarası, checksum geçerli T.C. kimlik numarası, TR IBAN, JWT benzeri token, yüksek entropili
kimlik bilgisi benzeri dizi. Kapsanmayanlar (örnek): e-posta/telefon gibi kişisel veriler, doğal dilde
anlatılmış secret'lar, kodlanmış/bölünmüş değerler.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_KEYWORD = re.compile(
    r"(?i)(?<![\w])(parola\w*|şifre\w*|sifre\w*|password|passwd|pass\s?code|pin|otp|cvv|cvc|"
    r"güvenlik\s+kodu|guvenlik\s+kodu|tek\s+kullanımlık|token|api[\s_-]?key|secret|gizli\s+anahtar)(?![\w])"
)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_TCKN = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")
_IBAN = re.compile(r"(?i)(?<![A-Z0-9])TR\d{2}(?:[ ]?\d){22}(?![0-9])")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}")
_TOKENISH = re.compile(r"(?<![\w-])[A-Za-z0-9_\-+/=]{20,}(?![\w-])")


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    start: int
    end: int

    def __repr__(self) -> str:  # değer asla görünmez
        return f"Finding({self.kind}@{self.start}:{self.end})"


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _tckn(n: str) -> bool:
    d = [int(c) for c in n]
    if d[0] == 0:
        return False
    tenth = ((sum(d[0:9:2]) * 7) - sum(d[1:8:2])) % 10
    return tenth == d[9] and sum(d[:10]) % 10 == d[10]


def _entropy(text: str) -> float:
    counts = Counter(text)
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def scan(text: str) -> list[Finding]:
    findings: list[Finding] = []
    taken: list[tuple[int, int]] = []

    def add(kind: str, start: int, end: int) -> None:
        if any(s < end and start < e for s, e in taken):
            return
        taken.append((start, end))
        findings.append(Finding(kind, start, end))

    for m in _KEYWORD.finditer(text):
        add("secret_keyword", m.start(), m.end())
    for m in _IBAN.finditer(text):
        add("iban", m.start(), m.end())
    for m in _JWT.finditer(text):
        add("token", m.start(), m.end())
    for m in _CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            add("payment_card", m.start(), m.end())
    for m in _TCKN.finditer(text):
        if _tckn(m.group(0)):
            add("national_id", m.start(), m.end())
    for m in _TOKENISH.finditer(text):
        token = m.group(0)
        if re.search(r"[A-Za-z]", token) and re.search(r"\d", token) and _entropy(token) >= 3.5:
            add("credential_like", m.start(), m.end())
    return sorted(findings, key=lambda f: f.start)


def kinds(text: str) -> list[str]:
    return sorted({f.kind for f in scan(text)})


def is_sensitive(text: str) -> bool:
    return bool(scan(text))
