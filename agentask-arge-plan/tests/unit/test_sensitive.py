"""Hassas veri şüphe tespiti (R1). Tam kapsam iddiası yoktur; amaç şüphede modele göndermemek ve sormaktır."""

from __future__ import annotations

import pytest

from agentask.domain.sensitive import scan


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("parolam Gizli-123! olsun", "secret_keyword"),
        ("Şifre: abc", "secret_keyword"),
        ("my password is hunter2", "secret_keyword"),
        ("OTP 908172 gir", "secret_keyword"),
        ("api key sk-live-abc", "secret_keyword"),
        ("kart 4111 1111 1111 1111 ile", "payment_card"),
        ("TC 10000000146 numaralı", "national_id"),
        ("IBAN TR33 0006 1005 1978 6457 8413 26", "iban"),
        ("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl", "token"),
        ("anahtar AKIAIOSFODNN7EXAMPLEa9Zx22 kullan", "credential_like"),
    ],
)
def test_detects_suspected_sensitive_data(text: str, kind: str) -> None:
    assert kind in {f.kind for f in scan(text)}


@pytest.mark.parametrize(
    "text",
    [
        "Kefil müşteri numarasını 00123 olarak gir",
        "B-1027 başvurusunu bul",
        "Vakaya not ekle: 'Müşteri arandı'",
        "Şube olarak Konak seç",
        "12345678901 sayısı geçersiz TCKN",
    ],
)
def test_business_text_not_flagged(text: str) -> None:
    assert scan(text) == []


def test_findings_never_contain_the_value() -> None:
    findings = scan("parolam Gizli-123! ve kart 4111111111111111")
    rendered = repr(findings)
    assert "Gizli-123!" not in rendered and "4111111111111111" not in rendered
    assert all(f.start < f.end for f in findings)
