"""Akış Tasarımcısı yerleşim regresyonu (lab, Chromium; WebKit ayrı ve Safari yerine geçmez).

Senaryo: gerçek oturum paneli açık (uzun adres), kesinti mesajı görünür, uzun akış adı, birkaç adım, adım
seçili. Ölçülen (layout_probe): panel örtüşmesi (kaydırırken de), panel içi yatay taşma, kırpılan
metin/kontrol, başka öğenin örttüğü kontrol ve sayfa düzeyi yatay taşma. Yakınlaştırma, pencerenin CSS piksel
genişliğinin zoom oranına bölünmesi ve piksel yoğunluğunun artırılmasıyla taklit edilir (tarayıcı
zoom'unun yerleşim etkisi).
Ekran görüntüleri ve ölçüm sonucu test geçici klasörüne (tmp_path/layout) yazılır.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Page, async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.layout_probe import probe
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_browser import ui_engine
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
OWNER = "dev.user"
LONG_NAME = "Kefil ve başvuran müşteri numaralarını güncelleyip teminat ekranına geçen uzun adlı akış"

# (pencere genişliği, zoom)
VIEWS = [
    (1440, 1.0),
    (1280, 1.0),
    (1024, 1.0),
    (820, 1.0),
    (390, 1.0),
    (1280, 1.25),
    (1280, 1.5),
    (1440, 1.5),
]


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer) -> Iterator[AppServer]:
    lab.reset()
    server = AppServer(create_app(lab_settings(make_env_file, lab)))
    server.start()
    yield server
    server.stop()


async def prepare(ui: Page, app_server: AppServer, lab: LabServer, sid: str | None) -> str:
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    await ui.goto(f"http://127.0.0.1:{app_server.port}/prototype/designer")
    await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
    await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill(LONG_NAME)
    toggle = ui.locator("#pd-left-toggle")
    if await toggle.is_visible() and await toggle.get_attribute("aria-expanded") == "false":
        await toggle.click()  # dar pencere: sol panel akış içinde açılır
    for name in ("Alan doldur", "Ekrana geç", "Alan doldur"):
        await ui.locator("#pd-components").get_by_role("button", name=name).click()
    await ui.get_by_role("button", name="Gerçek oturum", exact=True).click()
    sessions = app_server.app.state.container.sessions
    first = sid is None
    if sid is None:
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
        sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
        handle = sessions.peek(OWNER, sid)
        await in_server(handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next=/pages/duplicates"))
        tail = "/".join(f"cok-uzun-adres-parcasi-{i}" for i in range(10))
        await in_server(handle.page.evaluate(f"history.replaceState(null, '', '/pages/duplicates/{tail}')"))
    else:
        handle = sessions.peek(OWNER, sid)
    await ui.get_by_role("button", name="Yenile").click()
    await ui.get_by_label("Tarayıcı oturumu").select_option(sid)

    if first:
        await in_server(
            handle.page.evaluate(
                "setTimeout(() => window.confirm('Kayıt silinsin mi? ' + 'uzun '.repeat(20)), 10)"
            )
        )
    await expect(ui.locator("#pd-real-intr")).to_contain_text("Müdahale gerekiyor", timeout=10000)
    await ui.locator(".pd-card__main").nth(0).click()  # adım seçili
    return sid


@pytest.mark.parametrize("theme", ["light", "dark"])
async def test_designer_layout_has_no_overlap_or_clipping(
    app_server: AppServer, lab: LabServer, theme: str, tmp_path: Path
) -> None:
    shots = tmp_path / "layout"
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        problems: dict[str, Any] = {}
        sid: str | None = None
        for width, zoom in VIEWS:
            ctx = await browser.new_context(
                viewport={"width": int(width / zoom), "height": int(900 / zoom)},
                device_scale_factor=zoom,
                color_scheme=theme,  # type: ignore[arg-type]
            )
            ui = await ctx.new_page()
            sid = await prepare(ui, app_server, lab, sid)
            found = await probe(ui)
            if shots:  # görsel inceleme için her zaman kaydedilir
                shots.mkdir(parents=True, exist_ok=True)
                await ui.screenshot(path=f"{shots}/{theme}-{width}-{int(zoom * 100)}.png", full_page=True)
                await ui.evaluate("window.scrollTo(0, document.documentElement.scrollHeight * 0.45)")
                await ui.screenshot(path=f"{shots}/{theme}-{width}-{int(zoom * 100)}-kaydirilmis.png")
                await ui.evaluate("window.scrollTo(0, 0)")
            bad = {k: v for k, v in found.items() if v}
            if bad:
                problems[f"{width}@{int(zoom * 100)}%"] = bad
            await ctx.close()
        await browser.close()
    if shots:
        import json

        Path(f"{shots}/problems-{theme}.json").write_text(json.dumps(problems, ensure_ascii=False, indent=1))
    assert not problems, problems


async def test_left_panel_collapses_in_flow_and_keeps_state(app_server: AppServer, lab: LabServer) -> None:
    """Dar pencerede sol panel akış içinde açılır/kapanır (örtmez); kesinti gelince açılır; seçili adım ve
    oturum korunur. Geniş pencerede düğme görünmez."""
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ctx = await browser.new_context(viewport={"width": 1024, "height": 900})
        ui = await ctx.new_page()
        sid = await prepare(ui, app_server, lab, None)
        toggle = ui.locator("#pd-left-toggle")
        await expect(toggle).to_be_visible()
        await expect(ui.locator("#pd-left-alert")).to_be_visible()  # kesinti rozeti
        await toggle.click()
        await expect(toggle).to_have_attribute("aria-expanded", "false")
        await expect(ui.locator("#pd-components")).to_be_hidden()
        flow_top = (await ui.locator("#pd-flow").bounding_box())["y"]
        left_bottom = await ui.locator("#pd-left").bounding_box()
        assert left_bottom["y"] + left_bottom["height"] <= flow_top  # akış içinde; üstüne binmez
        assert not (await probe(ui))["overlaps"]
        assert "is-selected" in (await ui.locator(".pd-card").nth(0).get_attribute("class") or "")
        await toggle.click()
        await expect(ui.locator("#pd-components")).to_be_visible()
        assert await ui.get_by_label("Tarayıcı oturumu").input_value() == sid  # oturum korunur
        await ui.set_viewport_size({"width": 1440, "height": 900})
        await expect(toggle).to_be_hidden()
        await expect(ui.locator("#pd-components")).to_be_visible()
        await ctx.close()
        await browser.close()


async def test_layout_in_webkit_engine(app_server: AppServer, lab: LabServer) -> None:
    """Playwright WebKit motoru (gerçek Safari değildir)."""
    async with async_playwright() as p:
        try:
            browser = await p.webkit.launch()
        except Exception as exc:
            pytest.skip(f"BLOCKED: WebKit kurulu değil ({type(exc).__name__})")
        problems: dict[str, Any] = {}
        sid: str | None = None
        for width in (1440, 1024, 390):
            ctx = await browser.new_context(viewport={"width": width, "height": 900})
            ui = await ctx.new_page()
            sid = await prepare(ui, app_server, lab, sid)
            bad = {k: v for k, v in (await probe(ui)).items() if v}
            if bad:
                problems[str(width)] = bad
            await ctx.close()
        await browser.close()
    assert not problems, problems
