"""Tarayıcı motoru seçimi: varsayılan, uyumsuz ayarın reddi ve --doctor çıktısı (indirme yok)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentask.config import ConfigurationError, load_settings
from agentask.config.settings import BrowserEngine
from agentask.diagnostics import FAIL, OK, run_doctor
from tests.conftest import EnvFileFactory


def test_missing_engine_defaults_to_chromium_for_old_env_files(make_env_file: EnvFileFactory) -> None:
    assert load_settings(make_env_file(BROWSER_ENGINE=None)).browser_engine is BrowserEngine.CHROMIUM


@pytest.mark.parametrize("engine", ["chromium", "firefox"])
def test_each_engine_is_accepted_without_custom_binary(make_env_file: EnvFileFactory, engine: str) -> None:
    settings = load_settings(make_env_file(BROWSER_ENGINE=engine, BROWSER_EXECUTABLE_PATH=""))
    assert settings.browser_engine.value == engine and settings.browser_executable_path is None


def test_invalid_engine_names_the_setting_and_allowed_values(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(BROWSER_ENGINE="edge"))
    text = "\n".join(exc.value.problems)
    assert "BROWSER_ENGINE" in text and all(name in text for name in ("chromium", "firefox", "webkit"))


def test_webkit_is_refused_with_the_reason_instead_of_failing_later(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(BROWSER_ENGINE="webkit", BROWSER_EXECUTABLE_PATH=""))
    text = "\n".join(exc.value.problems)
    assert "BROWSER_ENGINE=webkit bu sürümde kullanılamaz" in text and "yönlendirme" in text
    assert "chromium veya firefox" in text


@pytest.mark.parametrize("engine", ["firefox"])
def test_custom_binary_is_refused_for_non_chromium(make_env_file: EnvFileFactory, engine: str) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(BROWSER_ENGINE=engine, BROWSER_EXECUTABLE_PATH="/opt/tarayici/ozel"))
    text = "\n".join(exc.value.problems)
    assert "BROWSER_EXECUTABLE_PATH" in text and f"BROWSER_ENGINE={engine}" in text
    assert "/opt/tarayici" not in text  # değer yazdırılmaz


def test_custom_binary_still_allowed_for_chromium(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(BROWSER_ENGINE="chromium", BROWSER_EXECUTABLE_PATH="/opt/edge"))
    assert settings.browser_executable_path == Path("/opt/edge")


@pytest.mark.parametrize("engine", ["firefox"])
def test_doctor_reports_missing_engine_without_downloading_or_falling_back(
    make_env_file: EnvFileFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    empty = tmp_path / "tarayicilar"
    empty.mkdir()
    monkeypatch.setenv(
        "PLAYWRIGHT_BROWSERS_PATH", str(empty)
    )  # doctor'ın yazdığı değer test sonunda geri alınır
    settings = load_settings(
        make_env_file(
            CATALOG_BACKEND="disabled",
            BROWSER_ENGINE=engine,
            PLAYWRIGHT_BROWSERS_PATH=str(empty),
            RUN_DIRECTORY=str(tmp_path / "r"),
            DRAFT_DIRECTORY=str(tmp_path / "d"),
            ARTIFACT_DIRECTORY=str(tmp_path / "a"),
        )
    )
    lines: list[str] = []
    code = run_doctor(settings, lines.append)
    text = "\n".join(lines)
    assert code == 1
    assert f"[{OK}] Tarayıcı motoru: BROWSER_ENGINE={engine}" in text
    assert f"[{FAIL}] Tarayıcı dosyası: {engine} dosyaları bu makinede yok" in text
    assert f"playwright install {engine}" in text
    assert f"[{FAIL}] Tarayıcı başlatma: denenmedi" in text
    assert "açıldı" not in text and "chromium" not in text.lower()
    assert list(empty.iterdir()) == []  # kontrol kendi başına tarayıcı indirmedi
