"""Redakte konfigürasyon hatası: girdi değerleri hiçbir zaman mesaja konmaz."""

from __future__ import annotations

from pydantic import ValidationError


class ConfigurationError(Exception):
    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("Geçersiz yapılandırma:\n- " + "\n- ".join(self.problems))

    @classmethod
    def from_validation_error(cls, exc: ValidationError) -> ConfigurationError:
        problems: list[str] = []
        for error in exc.errors(include_input=False, include_url=False, include_context=False):
            location = ".".join(str(part) for part in error["loc"]).upper()
            message = _safe_message(error["type"], error["msg"])
            problems.append(f"{location}: {message}" if location else message)
        return cls(problems)


_MESSAGES = {
    "missing": "zorunlu ayar eksik veya boş",
    "extra_forbidden": "bilinmeyen ayar anahtarı (yazım hatası olabilir)",
    "bool_parsing": "true/false olmalı",
    "int_parsing": "tam sayı olmalı",
    "greater_than": "pozitif olmalı",
    "greater_than_equal": "izin verilen alt sınırın altında",
    "less_than_equal": "izin verilen üst sınırın üzerinde",
    "enum": "izin verilen değerlerden biri olmalı",
    "url_parsing": "geçerli bir URL olmalı",
    "url_scheme": "URL şeması http veya https olmalı",
    "string_too_short": "boş olamaz",
    "string_pattern_mismatch": "izin verilmeyen karakter içeriyor",
    "too_short": "en az bir değer içermeli",
    "list_type": "JSON liste olmalı",
}


def _safe_message(error_type: str, raw_message: str) -> str:
    if error_type == "value_error":
        # Kendi validator mesajlarımız girdi değeri içermez; pydantic önekini atıyoruz.
        return raw_message.removeprefix("Value error, ")
    if error_type == "enum":
        # Pydantic enum mesajı izin verilen değerleri listeler, girdiyi değil.
        return raw_message
    return _MESSAGES.get(error_type, f"geçersiz değer ({error_type})")
