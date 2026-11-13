"""Beklenen yeni pencere ve isteğe bağlı pencere: tasarımdan İşlem Asistanı'na (lab + MongoDB)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from tests.conftest import EnvFileFactory
from tests.e2e.flow_helpers import Flow, mongo_app, open_flow
from tests.e2e.support import AppServer
from tests.support_lab import LabServer

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
WINDOWS = "/pages/windows"
MODAL = "/pages/optional-modal"


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    yield from mongo_app(make_env_file, lab, tmp_path, "agentask_windows")


async def echo(flow: Flow) -> str:
    async def read() -> str:
        return str(await flow.handle.page.locator("#echo").text_content())

    return str(await flow.in_server(read()))


async def open_design_window(flow: Flow) -> None:
    async def click() -> None:
        await flow.handle.page.get_by_role("button", name="Pencere Aç", exact=True).click()

    await flow.in_server(click())
    await flow.ui.locator("#pd-window-design").click(timeout=10000)
    await expect(flow.ui.locator("#pd-window-main")).to_be_visible(timeout=10000)


async def design_main(flow: Flow) -> None:
    await flow.ui.locator("#pd-window-main").click()
    await expect(flow.ui.locator("#pd-window-design")).to_be_visible(timeout=10000)


async def test_new_window_from_design_to_assistant(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        flow = await open_flow(browser, app_server, lab, "Pencerede not yaz", WINDOWS)
        editor = await flow.add("Ekrana geç")
        await editor.get_by_role("button", name="Ekrandaki düğmeleri listele").click()
        await editor.get_by_role("button", name="Ana bölümündeki Pencere Aç düğmesini seç").click()
        await editor.get_by_label("Düğmeye basınca açılacak ekranın adı").fill("Pencere formu")
        await editor.get_by_label("Bu düğmenin yalnız ekran değiştirdiğini biliyorum").check()
        await editor.get_by_label("Bu düğme yeni pencere açıyor").check()

        await open_design_window(flow)
        editor = await flow.pick("Alan doldur", "Pencere Formu bölümündeki Pencere Notu alanını seç")
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill("Penceredeki not")
        await flow.add("Ana pencereye dön")

        await design_main(flow)
        await flow.ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(flow.ui.locator("#pd-draft-status")).to_contain_text(
            "Kaydetme tamamlanmadı", timeout=30000
        )
        await flow.ui.locator("#pd-window-design").click()
        await expect(flow.ui.locator("#pd-window-main")).to_be_visible(timeout=10000)
        await flow.save()
        cards = await flow.reopen()
        await expect(cards).to_have_count(3)
        await cards.nth(2).click()
        await expect(flow.editor.get_by_label("Sistem kapatsın")).to_be_checked()
        await cards.nth(0).click()
        await expect(flow.editor.get_by_label("Bu düğme yeni pencere açıyor")).to_be_checked()

        panel = flow.panel
        await design_main(flow)
        await flow.introduce_screen()
        await flow.ui.locator("#pd-window-design").click()
        await expect(flow.ui.locator("#pd-window-main")).to_be_visible(timeout=10000)
        await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)

        await design_main(flow)
        await flow.ui.get_by_role("button", name="Listelenen 1 pencereyi kapat").click()
        await expect(flow.ui.locator("#pd-window-design")).to_be_hidden(timeout=10000)
        await flow.goto(WINDOWS)
        for i in range(3):
            await flow.confirm_and_try(i)
        assert await echo(flow) == "Penceredeki not"

        await flow.publish(WINDOWS)
        await flow.assistant_open(flow.name, WINDOWS)
        await flow.assistant_start(ack=False)
        assert await echo(flow) == "Penceredeki not"
        assert not flow.handle.adopted and flow.handle.observer.new_windows == 0  # açık pencere kalmadı
        await browser.close()


async def test_optional_dialog_from_design_to_assistant(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        flow = await open_flow(browser, app_server, lab, "Bilgi penceresi", MODAL)
        for label, value in (("Birinci", "bir"), ("İkinci", "iki")):
            editor = await flow.pick("Alan doldur", f"Bilgiler bölümündeki {label} alanını seç")
            await editor.get_by_label("Sabit değer").check()
            await editor.get_by_label("Yazılacak değer").fill(value)
        await flow.save()
        cards = await flow.reopen()
        await expect(cards).to_have_count(2)

        panel = flow.panel
        await panel.get_by_label("Pencerenin adı").fill("Bilgilendirme")
        await panel.get_by_label("Pencerede geçen metin").fill("Kaydınız işleniyor")
        await panel.get_by_label("Basılacak düğme").fill("Tamam")
        await panel.locator("#pd-dlg-add").click()
        await expect(flow.ui.locator("#pd-runpanel-status")).to_contain_text("onaylayın")
        await panel.get_by_label("Bu pencere yalnız bilgi verir; düğme kayıt yapmaz").check()
        await panel.locator("#pd-dlg-add").click()
        await expect(panel.locator("#pd-optional-dialogs")).to_contain_text("Bilgilendirme")

        await flow.introduce_screen()
        for i in range(2):
            await flow.confirm_and_try(i)
        await flow.publish(MODAL)

        await flow.assistant_open(flow.name, f"{MODAL}?mode=info")
        await flow.assistant_start(ack=False)

        async def state() -> tuple[str | None, str]:
            page = flow.handle.page
            return await page.locator("#clicks").get_attribute("data-ok"), await page.get_by_label(
                "İkinci"
            ).input_value()

        assert await flow.in_server(state()) == ("1", "iki")
        await browser.close()
