"""Beyan edilen biçimde tarih çözümleme. Geçersiz tarih (31.02) None döner; hiçbir zaman tahmin edilmez."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

DateFormat = Literal["DD.MM.YYYY", "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"]
_PATTERNS: dict[str, str] = {
    "DD.MM.YYYY": "%d.%m.%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "YYYY-MM-DD": "%Y-%m-%d",
}


def _strict(text: str, pattern: str) -> date | None:
    try:
        parsed = datetime.strptime(text, pattern).date()
    except ValueError:
        return None
    return parsed if parsed.strftime(pattern) == text else None  # 1.2.2026 gibi eksik biçimler kabul edilmez


def parse_date(text: str, date_format: str) -> date | None:
    """Beyan edilen biçim veya (tarayıcının type=date değeri için) ISO biçimi."""
    value = text.strip()
    return _strict(value, _PATTERNS[date_format]) or _strict(value, _PATTERNS["YYYY-MM-DD"])


def format_date(value: date, date_format: str) -> str:
    return value.strftime(_PATTERNS[date_format])
