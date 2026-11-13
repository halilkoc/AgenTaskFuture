"""Yapılandırılmış log bağlamı ve olay yardımcısı. Bağlam contextvars ile tutulur: eşzamanlı istekler
birbirine karışmaz, arka plan görevi başlatıldığı isteğin bağlamını devralır.

Yalnız infrastructure/logging'deki izinli alanlar çıktıya yazılır. Değer, prompt veya DOM içeriği alan olarak
verilmemelidir; verilse de izinli listede olmadığı için yazılmaz.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType
from typing import Any

BUSINESS = "business"  # beklenen iş/kullanım hatası (yetki, doğrulama, hedef bulunamadı...)
SOFTWARE = "software"  # beklenmeyen yazılım hatası

_EMPTY: Mapping[str, Any] = MappingProxyType({})
_context: ContextVar[Mapping[str, Any]] = ContextVar("agentask_log_context", default=_EMPTY)


def current_log_context() -> Mapping[str, Any]:
    return _context.get()


def current_correlation_id() -> str | None:
    value = _context.get().get("correlation_id")
    return str(value) if value else None


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    token = _context.set({**_context.get(), **{k: v for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _context.reset(token)


def bind_log_context(**fields: Any) -> None:
    """Geçerli görevin kalanı için bağlam ekler (kimlik gibi istek ortasında öğrenilen bilgiler)."""
    _context.set({**_context.get(), **{k: v for k, v in fields.items() if v is not None}})


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    audit: bool = False,
    exc_info: BaseException | None = None,
    **fields: Any,
) -> None:
    """Tek yapılandırılmış olay. audit=True: kullanıcı/iş olayı (category=audit)."""
    payload = {k: v for k, v in fields.items() if v is not None}
    payload["category"] = "audit" if audit else "system"
    logger.log(level, event, extra={"agentask_event": event, "agentask_fields": payload}, exc_info=exc_info)
