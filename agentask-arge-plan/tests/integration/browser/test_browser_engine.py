"""Seçili tarayıcı motoru: uygulama yalnız onu başlatır; bulunamazsa başka motora geçmeden açık hata verir."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentask.application.errors import DependencyUnavailable
from agentask.config import Settings, load_settings
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.conftest import EnvFileFactory
from tests.support_browser import engine_name
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
UA_MARK = {"chromium": "Chrome/", "firefox": "Firefox/"}


async def test_application_launches_exactly_the_selected_engine(
    factory: PlaywrightContextFactory, browser_settings: Settings, lab: LabServer
) -> None:
    assert browser_settings.browser_engine.value == engine_name()
    handle = await factory.create_context("ayse")
    await handle.navigate(f"{lab.primary}/login")
    assert factory._browser is not None and factory._browser.browser_type.name == engine_name()
    agent = await handle.page.evaluate("navigator.userAgent")
    assert UA_MARK[engine_name()] in agent
    if engine_name() != "chromium":
        assert "Chrome/" not in agent


@pytest.mark.parametrize("engine", ["firefox"])
async def test_missing_engine_fails_clearly_without_falling_back(
    make_env_file: EnvFileFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    empty = tmp_path / "tarayicilar"
    empty.mkdir()
    monkeypatch.setenv(
        "PLAYWRIGHT_BROWSERS_PATH", str(empty)
    )  # fabrikanın yazdığı değer test sonunda geri alınır
    settings = load_settings(
        make_env_file(BROWSER_ENGINE=engine, BROWSER_HEADLESS="true", PLAYWRIGHT_BROWSERS_PATH=str(empty))
    )
    broken = PlaywrightContextFactory(settings)
    try:
        with pytest.raises(DependencyUnavailable) as exc:
            await broken.create_context("ayse")
        assert f"BROWSER_ENGINE={engine}" in exc.value.safe_message
        assert str(empty) not in exc.value.safe_message
        assert not broken.is_running and broken._browser is None  # Chromium dahil hiçbir tarayıcı açılmadı
    finally:
        await broken.shutdown()
    assert list(empty.iterdir()) == []  # indirme yapılmadı
