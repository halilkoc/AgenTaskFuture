"""Log yapılandırması. Dış telemetri yok; yalnızca stdout (konteyner/süreç yöneticisi toplar).

Çıktı yalnız izinli alanlardan oluşur; bilinmeyen alan yazılmaz. Yabancı istisnaların mesajı (Playwright çağrı
günlüğü, pydantic girdi değeri, sürücü URI'si içerebilir) yazılmaz: tür, zincir ve dosya:satır:fonksiyon
yeterlidir.
Yalnız bu projenin kendi yazdığı güvenli mesajlar maskeden geçirilerek yazılır.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import traceback
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any

from agentask.application.controls import AdapterError
from agentask.application.errors import ApplicationError
from agentask.application.observability import current_log_context
from agentask.config.settings import LogFormat, LogLevel
from agentask.domain.redaction import redact_structural, redact_text

ALLOWED_FIELDS = (
    "category",
    "correlation_id",
    "run_id",
    "step_id",
    "op",
    "duration_ms",
    "outcome",
    "status",
    "reason",
    "error_code",
    "error_kind",
    "actor",
    "resource_type",
    "resource_id",
    "application_id",
    "operation_id",
    "release_id",
    "revision",
    "run_kind",
    "resume",
    "steps",
    "attempts",
    "action",
    "count",
    "session_id",
    "method",
    "path",
    "status_code",
)
_ALLOWED = frozenset(ALLOWED_FIELDS)
_MAX_FIELD = 300
_EVENT_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
_MAX_FRAMES = 15
# Bu projenin kendi yazdığı, kullanıcıya gösterilmek üzere güvenli olan mesajlar.
_OWN_MESSAGE = (ApplicationError, AdapterError)


def _clean(value: Any) -> str | int | float | bool | None:
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return redact_structural(value)[:_MAX_FIELD]
    return None  # yapılandırılmış nesneler loga taşınmaz


def _frame(frame: traceback.FrameSummary) -> str:
    parts = PurePath(frame.filename).parts[-3:]  # tam dosya yolu (kullanıcı/sunucu adı) yazılmaz
    return f"{'/'.join(parts)}:{frame.lineno}:{frame.name}"


def _exception_fields(exc_info: Any) -> dict[str, Any]:
    kind, exc, tb = exc_info
    chain: list[str] = []
    link = exc.__cause__ or exc.__context__ if exc is not None else None
    while link is not None and len(chain) < 5:
        chain.append(type(link).__name__)
        link = link.__cause__ or link.__context__
    out: dict[str, Any] = {
        "exc_type": kind.__name__ if kind else None,
        "stack": [_frame(f) for f in traceback.extract_tb(tb)[-_MAX_FRAMES:]],
    }
    if chain:
        out["exc_chain"] = chain
    if isinstance(exc, _OWN_MESSAGE):
        text = exc.safe_message if isinstance(exc, ApplicationError) else exc.message
        out["exc_message"] = redact_text(text)
    return out


def _legacy_event(message: str) -> str:
    """Eski biçim "olay_adı anahtar=değer" iletilerinde olay adı ilk sözcüktür; diğerleri genel 'log'dur."""
    first = message.split(" ", 1)[0]
    return first if _EVENT_NAME.fullmatch(first) else "log"


def _render(record: logging.LogRecord) -> dict[str, Any]:
    event = getattr(record, "agentask_event", None)
    message = None if event else redact_text(record.getMessage())
    payload: dict[str, Any] = {
        "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
        "level": record.levelname,
        "event": event or _legacy_event(message or ""),
        "logger": record.name,
    }
    merged = {**current_log_context(), **getattr(record, "agentask_fields", {})}
    legacy = getattr(record, "correlation_id", None)
    if legacy and "correlation_id" not in merged:
        merged["correlation_id"] = legacy
    for name in ALLOWED_FIELDS:
        if name in merged and (value := _clean(merged[name])) is not None:
            payload[name] = value
    if message and (" " in message or payload["event"] == "log"):
        payload["message"] = message
    if record.exc_info and record.exc_info[0] is not None:
        payload.update(_exception_fields(record.exc_info))
    return payload


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(_render(record), ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """LOG_FORMAT=text: aynı alan ve maskeleme kuralları, okunur tek satır."""

    def format(self, record: logging.LogRecord) -> str:
        data = _render(record)
        head = f"{data.pop('ts')} {data.pop('level')} {data.pop('event')}"
        data.pop("logger", None)
        return " ".join([head, *(f"{k}={v}" for k, v in data.items())])


def configure_logging(level: LogLevel, fmt: LogFormat) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt is LogFormat.JSON else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.value)
    for name in ("httpx", "httpcore", "pymongo", "asyncio"):  # istek ayrıntısı/imzalı adres yazmasınlar
        logging.getLogger(name).setLevel(max(logging.WARNING, logging.getLevelName(level.value)))
