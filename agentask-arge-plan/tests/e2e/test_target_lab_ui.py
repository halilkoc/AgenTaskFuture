"""Deneme ekranı uçtan uca: gerçek HTTP sunucusu + ekranı kullanan ayrı tarayıcı + oturum tarayıcısı."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from typing import Any

import pytest
from playwright.async_api import async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer) -> Iterator[AppServer]:
    lab.reset()
    server = AppServer(create_app(lab_settings(make_env_file, lab)))
    server.start()
    yield server
    server.stop()


async def test_target_lab_screen_end_to_end(app_server: AppServer, lab: LabServer) -> None:
    sessions = app_server.app.state.container.sessions
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ui = await browser.new_page()
        await ui.goto(f"http://127.0.0.1:{app_server.port}/designer/targets")
        await ui.get_by_role("button", name="Oturum aç").click()
        await expect(ui.get_by_text("Oturum: ")).to_be_visible()
        sid = (await ui.locator(".tl-session-id").inner_text()).removeprefix("Oturum: ")

        async def lab_login() -> None:
            handle = sessions.peek("dev.user", sid)
            await handle.navigate(f"{lab.primary}/login")
            await handle.page.get_by_label("Kullanıcı adı").fill("ayse")
            await handle.page.get_by_role("button", name="Giriş yap").click()
            await handle.page.wait_for_url(f"{lab.primary}/")

        await in_server(lab_login())

        await ui.get_by_label("Adres").fill(f"{lab.primary}/pages/duplicates")
        await ui.get_by_role("button", name="Git").click()
        await expect(ui.get_by_text("Açıldı:")).to_be_visible()

        await ui.get_by_role("button", name="Ekranı gözlemle").click()
        await expect(ui.locator(".tl-observe table")).to_contain_text("Müşteri No")
        await expect(ui.locator(".tl-observe")).to_contain_text("kapsam: tam")

        await ui.get_by_label("Etiketler (virgülle)").fill("Müşteri No")
        await ui.get_by_role("button", name="Ara").click()
        await expect(ui.locator(".tl-result .badge")).to_have_text("ambiguous")
        await ui.get_by_label("Bölüm").fill("Kefil")
        await ui.get_by_role("button", name="Ara").click()
        await expect(ui.locator(".tl-result .badge")).to_have_text("resolved")
        await expect(ui.locator(".tl-spec")).to_contain_text('"region": "Kefil"')

        await ui.get_by_role("button", name="Seçimi başlat").click()
        await expect(ui.locator(".tl-pick")).to_contain_text("Seçim açık")

        async def pick_save() -> None:
            page = sessions.peek("dev.user", sid).page
            save = page.get_by_role("region", name="Başvuran").get_by_role("button", name="Kaydet")
            box = await save.bounding_box()
            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

        await in_server(pick_save())
        await expect(ui.locator(".tl-pick")).to_contain_text(
            "Seçilen: Kaydet · düğme · Başvuran", timeout=10_000
        )
        await ui.get_by_role("button", name="Seçimi durdur").click()
        await ui.get_by_role("button", name="Oturumu kapat").click()
        await expect(ui.locator(".tl-session-id")).to_have_text("Oturum yok")
        await browser.close()
