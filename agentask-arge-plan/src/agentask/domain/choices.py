"""Seçim alanı (dropdown) kuralları: seçenek eşleştirme, kararlı değer ve sunum. Tarayıcıdan bağımsızdır.

- Eşleşme yalnız tam metin eşitliğidir (büyük/küçük harf ve boşluk dışında fark kabul edilmez); kısmi/bulanık
  eşleşme ve sıra numarası yoktur. Türkçe harf farkları ayrıdır (Çek ≠ Cek).
- Görünen etiket ile uygulamanın alttaki değeri ayrı tutulur. Kaydedilmiş değer varsa çalışma anında etiketle
  birlikte aynı seçeneği göstermelidir.
- Eksik, devre dışı, yinelenen veya boş değerli (yer tutucu) seçenekte seçim yapılmaz.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

_SPACES = re.compile(r"\s+")
_GENERATED = re.compile(
    r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[a-z]{0,4}(?=[0-9a-f]*\d)[0-9a-f]{8,})$",
    re.IGNORECASE,
)
_MAX_STABLE_VALUE = 120


def choice_key(text: str) -> str:
    """Seçenek karşılaştırma anahtarı: Türkçe harf çevirimi + boşluk sadeleştirme; aksan KALDIRILMAZ."""
    folded = unicodedata.normalize("NFKC", text).replace("İ", "i").replace("I", "ı").casefold()
    return _SPACES.sub(" ", folded).strip()


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    label: str
    value: str | None
    enabled: bool = True
    selected: bool = False

    @property
    def placeholder(self) -> bool:
        return self.value == ""


class ChoiceIssue(StrEnum):
    MISSING = "missing"
    DUPLICATE = "duplicate"
    DISABLED = "disabled"
    PLACEHOLDER = "placeholder"
    VALUE_MISMATCH = "value_mismatch"


CHOICE_ISSUE_TEXT = {
    ChoiceIssue.MISSING: "Seçenek bulunamadı; seçim yapılmadı.",
    ChoiceIssue.DUPLICATE: "Seçenek birden fazla kez geçiyor; seçim yapılmadı.",
    ChoiceIssue.DISABLED: "Seçenek şu anda devre dışı; seçim yapılmadı.",
    ChoiceIssue.PLACEHOLDER: "Bu satır bir yer tutucu; gerçek bir seçenek değil, seçim yapılmadı.",
    ChoiceIssue.VALUE_MISMATCH: "Görünen seçenek aynı ancak uygulamadaki değeri farklı; seçim yapılmadı.",
}


def pick_option(
    options: list[ChoiceOption] | tuple[ChoiceOption, ...], label: str, expected_value: str | None = None
) -> tuple[ChoiceOption | None, ChoiceIssue | None]:
    wanted = choice_key(label)
    found = [o for o in options if choice_key(o.label) == wanted]
    if not found:
        return None, ChoiceIssue.MISSING
    if len(found) > 1:
        return None, ChoiceIssue.DUPLICATE
    option = found[0]
    if option.placeholder:
        return None, ChoiceIssue.PLACEHOLDER
    if expected_value is not None and option.value != expected_value:
        return None, ChoiceIssue.VALUE_MISMATCH
    if not option.enabled:
        return None, ChoiceIssue.DISABLED
    return option, None


def _index_like(options: list[ChoiceOption] | tuple[ChoiceOption, ...]) -> bool:
    values = [o.value for o in options if o.value]
    if len(values) < 2 or not all(v.isdigit() for v in values):
        return False
    numbers = [int(v) for v in values]
    return numbers[0] in {0, 1} and numbers == list(range(numbers[0], numbers[0] + len(numbers)))


def stable_value(option: ChoiceOption, options: list[ChoiceOption] | tuple[ChoiceOption, ...]) -> str | None:
    """Kataloğa yazılabilecek anlamlı değer; sıra numarası gibi görünen veya üretilmiş kimlikler saklanmaz."""
    value = option.value
    if not value or not value.strip() or len(value) > _MAX_STABLE_VALUE:
        return None
    if _GENERATED.match(value) or _index_like(options):
        return None
    return value


def describe_options(
    options: list[ChoiceOption] | tuple[ChoiceOption, ...],
) -> list[dict[str, str | bool | None]]:
    """Analiste/iş kullanıcısına sunulacak liste. Seçilemeyenler nedeniyle işaretlenir, gizlenmez."""
    counts: dict[str, int] = {}
    for option in options:
        key = choice_key(option.label)
        counts[key] = counts.get(key, 0) + 1
    out: list[dict[str, str | bool | None]] = []
    for option in options:
        state = (
            "placeholder"
            if option.placeholder
            else "duplicate"
            if counts[choice_key(option.label)] > 1
            else "disabled"
            if not option.enabled
            else "ok"
        )
        out.append(
            {
                "label": option.label,
                "value": stable_value(option, options),
                "state": state,
                "selected": option.selected,
            }
        )
    return out
