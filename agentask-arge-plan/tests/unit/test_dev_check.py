"""Geliştirme kontrol komutu: başarısızlık gizlenmez (exit 1), atlananlar listelenir, Docker zorunlu değil."""

from __future__ import annotations

import pytest
from tools.dev_check import __main__ as dev_check


def test_failure_is_reported_with_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []

    def fake(name: str, command: list[str]) -> dev_check.Result:
        calls.append(command)
        return dev_check.Result(name, 1 if name == "typecheck" else 0, 0.0, ["x.py:1: BLOCKED: örnek"])

    monkeypatch.setattr(dev_check, "run", fake)
    assert dev_check.main([]) == 1
    out = capsys.readouterr().out
    assert "HATA   typecheck" in out and "SONUÇ: BAŞARISIZ (typecheck)" in out
    assert "ATLANDI/BLOCKED x.py:1: BLOCKED: örnek" in out and "docker testleri" in out
    assert len(calls) == 4  # biri başarısız olsa da bütün kontroller çalıştı
    assert calls[3][calls[3].index("-m") : calls[3].index("-m") + 2] == ["-m", "not docker"]


def test_real_subprocess_exit_code_is_propagated() -> None:
    import sys

    ok = dev_check.run("ok", [sys.executable, "-c", "print('SKIPPED [1] a.py:2: BLOCKED: y')"])
    bad = dev_check.run("bad", [sys.executable, "-c", "raise SystemExit(3)"])
    assert ok.code == 0 and ok.skipped == ["a.py:2: BLOCKED: y"] and bad.code == 3
