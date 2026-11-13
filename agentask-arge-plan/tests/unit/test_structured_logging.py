"""Yapılandırılmış log: alanlar, izinli liste, redaksiyon, istisna güvenliği ve bağlam ayrımı."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

from agentask.application.errors import Forbidden
from agentask.application.observability import (
    SOFTWARE,
    current_correlation_id,
    current_log_context,
    log_context,
    log_event,
)
from agentask.domain.redaction import redact_structural, redact_text
from agentask.infrastructure.logging import JsonFormatter, TextFormatter

logger = logging.getLogger("agentask.test.logging")
Logs = Callable[[], list[dict[str, Any]]]


def test_event_has_required_fields_and_context(json_logs: Logs) -> None:
    with log_context(correlation_id="corr-1234", run_id="run-1", step_id=3):
        log_event(
            logger, "step_done", duration_ms=12, outcome="success", error_code="X", error_kind="business"
        )
    line = json_logs()[-1]
    assert line["event"] == "step_done" and line["level"] == "INFO" and line["ts"].endswith("+00:00")
    expected = {"correlation_id": "corr-1234", "run_id": "run-1", "step_id": 3, "duration_ms": 12}
    assert expected.items() <= line.items()
    assert line["outcome"] == "success" and line["error_code"] == "X" and line["category"] == "system"


def test_only_allowed_fields_are_written(json_logs: Logs) -> None:
    log_event(
        logger,
        "x",
        value="00456",
        prompt="Müşteri 12345",
        dom="<input value='gizli'>",
        cookies="a=b",
        actor="ayse",
        audit=True,
    )
    line = json_logs()[-1]
    assert line["actor"] == "ayse" and line["category"] == "audit"
    assert not {"value", "prompt", "dom", "cookies"} & set(line)
    assert "00456" not in json.dumps(line)


@pytest.mark.parametrize(
    ("text", "secrets", "kept"),
    [
        ("mongodb://admin:mongo-pass@db:27017/x", ["admin", "mongo-pass"], "db:27017/x"),
        ("https://u:p4ss@host/a?token=abc123&x=1#frag", ["p4ss", "abc123", "frag"], "host/a"),
        ("gidiliyor https://h/p?musteri=00456.", ["00456"], "https://h/p"),
        ("Authorization: Bearer abc.def-ghi", ["abc.def-ghi"], "Authorization"),
        ("headers Cookie: sid=topsecret; other=value", ["topsecret", "value"], "Cookie"),
        ("Set-Cookie: JSESSIONID=abc1234", ["abc1234"], "Set-Cookie"),
        ("password=hunter2 sonra", ["hunter2"], "sonra"),
        ('{"api_key": "k-123456", "n": 1}', ["k-123456"], "api_key"),
        ("şifre: gizli123", ["gizli123"], "şifre"),
        ("X-Amz-Signature=abcdef012345", ["abcdef012345"], "X-Amz"),
        ("hesap TR330006100519786457841326", ["TR3300061005"], "hesap"),
        ("kart 4111 1111 1111 1111", ["4111"], "kart"),
        ("jwt eyJhbGciOi.eyJzdWIiOiIx.c2lnbmF0dXJl", ["eyJhbGciOi"], "jwt"),
    ],
)
def test_redaction(text: str, secrets: list[str], kept: str) -> None:
    masked = redact_text(text)
    assert kept in masked, masked
    assert not [s for s in secrets if s in masked], masked


def test_structural_redaction_keeps_identifiers() -> None:
    assert redact_structural("run-Ab3dE6gH9jK2mN5pQ8") == "run-Ab3dE6gH9jK2mN5pQ8"


def test_legacy_message_is_redacted(json_logs: Logs) -> None:
    logger.warning("baglanti_hatasi uri=%s", "mongodb://u:sifre123@h/db")
    line = json_logs()[-1]
    assert line["event"] == "baglanti_hatasi" and "sifre123" not in json.dumps(line)


def _raise_foreign() -> None:
    raise RuntimeError("password=hunter2 müşteri 00456 https://u:p@h/?a=b")


def test_foreign_exception_message_is_never_written(json_logs: Logs) -> None:
    try:
        try:
            raise ValueError("iç neden 00456")
        except ValueError:
            _raise_foreign()
    except RuntimeError as exc:
        log_event(logger, "boom", level=logging.ERROR, exc_info=exc, error_kind=SOFTWARE)
    line = json_logs()[-1]
    text = json.dumps(line, ensure_ascii=False)
    assert line["exc_type"] == "RuntimeError" and line["exc_chain"] == ["ValueError"]
    assert any("_raise_foreign" in frame for frame in line["stack"])
    assert "hunter2" not in text and "00456" not in text and "exc_message" not in line
    assert not any(frame.startswith("/") for frame in line["stack"])  # tam yol yazılmaz


def test_pydantic_input_value_is_not_logged(json_logs: Logs) -> None:
    class Model(BaseModel):
        number: int

    try:
        Model.model_validate({"number": "müşteri-00456"})
    except ValueError as exc:
        logger.exception("dogrulama", exc_info=exc)
    assert "00456" not in json.dumps(json_logs()[-1], ensure_ascii=False)


def test_own_safe_message_is_kept(json_logs: Logs) -> None:
    log_event(logger, "x", level=logging.ERROR, exc_info=Forbidden())
    assert json_logs()[-1]["exc_message"] == Forbidden.safe_message


def test_text_format_uses_same_protection() -> None:
    record = logging.LogRecord("n", logging.INFO, "f", 1, "ev token=abc123", None, None)
    assert "abc123" not in TextFormatter().format(record)
    assert "abc123" not in JsonFormatter().format(record)


async def test_context_is_isolated_between_concurrent_tasks() -> None:
    seen: dict[str, tuple[str | None, str | None]] = {}

    async def request(n: int) -> None:
        with log_context(correlation_id=f"corr-{n}"):
            await asyncio.sleep(0.01 * (5 - n % 5))

            async def background() -> None:
                await asyncio.sleep(0.005)
                seen[f"bg-{n}"] = (current_correlation_id(), str(current_log_context().get("run_id")))

            with log_context(run_id=f"run-{n}"):
                task = asyncio.create_task(background())
            seen[f"req-{n}"] = (current_correlation_id(), current_log_context().get("run_id"))
            await task

    await asyncio.gather(*(request(n) for n in range(20)))
    for n in range(20):
        assert seen[f"req-{n}"] == (f"corr-{n}", None)
        assert seen[f"bg-{n}"] == (f"corr-{n}", f"run-{n}")
    assert current_correlation_id() is None
