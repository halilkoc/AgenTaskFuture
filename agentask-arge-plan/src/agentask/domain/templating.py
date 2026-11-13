"""Güvenli metin şablonu: yalnız `{parametre_adi}` yer tutucuları. Python format dili (öznitelik/indeks
erişimi,
biçim belirteçleri) kullanılmaz; başka süslü parantez içeren şablon geçersizdir."""

from __future__ import annotations

import re

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]{0,30})\}")


def is_valid(template: str) -> bool:
    stripped = _PLACEHOLDER.sub("", template)
    return "{" not in stripped and "}" not in stripped


def placeholders(template: str) -> set[str]:
    return set(_PLACEHOLDER.findall(template))


def render(template: str, values: dict[str, str]) -> str:
    if not is_valid(template):
        raise ValueError("invalid_template")

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise ValueError(f"missing_argument:{name}")
        return values[name]

    return _PLACEHOLDER.sub(sub, template)
