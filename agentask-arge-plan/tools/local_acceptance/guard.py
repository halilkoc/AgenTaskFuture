"""Kabul koşusunun pytest eklentisi: uygulama yalnız yerel/geçici ayarlarla kurulabilir; başarısızlıkta
sır içermeyen teşhis ve ekran görüntüsü saklanır. Trace veya ağ kaydı alınmaz."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import threading
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import tests.e2e.support as e2e_support
from playwright.async_api import BrowserType
from playwright.async_api._context_manager import PlaywrightContextManager

import agentask.presentation.app as app_module
from tools.local_acceptance.safety import redact, settings_violations

OUTPUT = Path(os.environ.get("AGENTASK_ACCEPTANCE_DIR", "."))
TEMP_ROOT = Path(os.environ.get("AGENTASK_ACCEPTANCE_BASETEMP", "."))
MAIN_THREAD = threading.get_ident()
ENGINE = os.environ.get("AGENTASK_TEST_BROWSER_ENGINE", "chromium")
_launches: dict[str, dict[str, int]] = {"arayuz": {}, "hedef": {}}
_browsers: list[Any] = []
_servers: list[Any] = []


class IsolationViolationError(RuntimeError):
    pass


def _case_dir() -> Path:
    current = os.environ.get("PYTEST_CURRENT_TEST", "bilinmeyen").split(" ")[0]
    path = OUTPUT / "failures" / re.sub(r"[^A-Za-z0-9_.-]+", "_", current)[-120:]
    path.mkdir(parents=True, exist_ok=True)
    return path


_real_create_app = app_module.create_app


def guarded_create_app(settings: Any, *args: Any, **kwargs: Any) -> Any:
    mongo = settings.mongo_uri.get_secret_value() if settings.catalog_backend.value == "mongo" else None
    problems = settings_violations(
        [str(o) for o in settings.target_allowed_origins],
        str(settings.target_base_url),
        mongo,
        [Path(settings.run_directory), Path(settings.draft_directory), Path(settings.artifact_directory)],
        TEMP_ROOT,
    )
    if problems:
        raise IsolationViolationError("; ".join(sorted(set(problems))))
    return _real_create_app(settings, *args, **kwargs)


app_module.create_app = guarded_create_app
_real_server_init = e2e_support.AppServer.__init__


def _tracked_server_init(self: Any, app: Any) -> None:
    _real_server_init(self, app)
    _servers.append(self)


e2e_support.AppServer.__init__ = _tracked_server_init  # type: ignore[method-assign]
_real_launch = BrowserType.launch


async def _tracked_launch(self: Any, *args: Any, **kwargs: Any) -> Any:
    # Test arayüzü ana iş parçacığında, uygulamanın hedef tarayıcısı sunucu iş parçacığında başlatılır.
    ui = threading.get_ident() == MAIN_THREAD
    counts = _launches["arayuz" if ui else "hedef"]
    counts[self.name] = counts.get(self.name, 0) + 1
    if self.name != ENGINE:
        raise IsolationViolationError(f"seçili motor {ENGINE} iken {self.name} başlatılmak istendi")
    browser = await _real_launch(self, *args, **kwargs)
    if ui:  # yalnız test arayüzü; uygulamanın sayfaları sunucudan alınır
        _browsers.append(browser)
    return browser


def pytest_sessionfinish(session: pytest.Session) -> None:
    text = json.dumps(_launches, ensure_ascii=False, indent=2)
    (OUTPUT / "browser-launches.json").write_text(text, encoding="utf-8")


BrowserType.launch = _tracked_launch  # type: ignore[method-assign]
_real_exit = PlaywrightContextManager.__aexit__


async def _capture_ui(directory: Path) -> None:
    index = 0
    for browser in _browsers:
        for context in browser.contexts:
            for page in context.pages:
                with contextlib.suppress(Exception):
                    await page.screenshot(path=str(directory / f"arayuz-{index}.png"), timeout=3000)
                    index += 1


def _capture_targets(directory: Path) -> None:
    async def shot(path: Path, page: Any) -> None:
        await page.screenshot(path=str(path), timeout=3000)

    index = 0
    for server in _servers:
        sessions = getattr(getattr(server.app.state, "container", None), "sessions", None)
        for record in list(getattr(sessions, "_records", {}).values()):
            with contextlib.suppress(Exception):
                server.run(shot(directory / f"hedef-{index}.png", record.handle.page))
                index += 1


async def _capturing_exit(self: Any, *args: Any) -> None:
    # Uygulama kapanışı `__aexit__()`'i argümansız da çağırır (2026-11-13 koşusunda bulundu).
    exc_type = args[0] if args else None
    if exc_type is not None and exc_type is not GeneratorExit:
        directory = _case_dir()
        with contextlib.suppress(Exception):
            await _capture_ui(directory)
        with contextlib.suppress(Exception):
            await asyncio.get_running_loop().run_in_executor(None, _capture_targets, directory)
    _browsers.clear()
    await _real_exit(self, *args)


PlaywrightContextManager.__aexit__ = _capturing_exit  # type: ignore[method-assign]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, Any, None]:
    outcome = yield
    report = outcome.get_result()
    if report.when == "teardown":
        _servers.clear()
    if not report.failed:
        return
    os.environ.setdefault("PYTEST_CURRENT_TEST", item.nodeid)
    directory = _case_dir()
    diagnosis = {
        "test": item.nodeid,
        "asama": report.when,
        "ozet": redact(str(report.longrepr))[-6000:],
        "ekran_goruntuleri": sorted(p.name for p in directory.glob("*.png")),
        "trace_veya_ag_kaydi": False,
    }
    text = json.dumps(diagnosis, ensure_ascii=False, indent=2)
    (directory / "tani.json").write_text(text, encoding="utf-8")
