"""Bağlantı ve seçimle ekran geçişi: tasarımdan Asistan'a; yanlış/belirsiz durumda tek gönderim (lab)."""

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
PATH = "/pages/transitions"


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    yield from mongo_app(make_env_file, lab, tmp_path, "agentask_triggers")


async def target_field(flow: Flow) -> str:
    async def read() -> str:
        return str(
            await flow.handle.page.get_by_role("region", name="Hedef")
            .get_by_label("Hedef Alan")
            .input_value()
        )

    return str(await flow.in_server(read()))


async def goto_target(flow: Flow) -> None:
    await flow.goto("/pages/transition-target")


async def finish(flow: Flow) -> None:
    # Her adım kendi ekranı açıkken doğrulanır: ilk ekranın adımı kaydedilir, sonra hedef ekranda devam.
    await flow.ui.get_by_role("button", name="Taslağı kaydet").click()
    await expect(flow.ui.locator("#pd-draft-status")).to_contain_text("Kaydetme tamamlanmadı", timeout=30000)
    await goto_target(flow)
    await flow.save()
    cards = await flow.reopen()
    await expect(cards).to_have_count(2)
    await flow.goto(PATH)
    panel = flow.panel
    await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
    await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
    await expect(panel).to_contain_text("tanıtıldı", timeout=15000)
    await goto_target(flow)
    await expect(panel.get_by_label("Tarayıcıda şu an açık olan ekran")).to_be_visible()
    await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
    await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
    await expect(panel).to_contain_text("Tanımlı:", timeout=15000)
    await flow.goto(PATH)
    await flow.confirm_and_try(0)
    await flow.confirm_and_try(1)
    assert await target_field(flow) == "Yazıldı"
    await flow.publish(PATH)
    await flow.assistant_open(flow.name, PATH)
    await flow.assistant_start(ack=flow.name.startswith("Seçimle"))
    assert await target_field(flow) == "Yazıldı"


async def add_target_fill(flow: Flow) -> None:
    editor = await flow.add("Alan doldur")
    await goto_target(flow)
    await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
    await editor.get_by_role("button", name="Hedef bölümündeki Hedef Alan alanını seç").click()
    await expect(editor.locator("[id$='-check']")).to_have_text("Ekranda tek olarak bulundu.", timeout=10000)
    await editor.get_by_label("Sabit değer").check()
    await editor.get_by_label("Yazılacak değer").fill("Yazıldı")


async def test_link_transition_end_to_end(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        flow = await open_flow(browser, app_server, lab, "Bağlantıyla geç", PATH)
        editor = await flow.add("Ekrana geç")
        await editor.get_by_role("button", name="Ekrandaki düğmeleri listele").click()
        await editor.get_by_role("button", name="Detaya git düğmesini seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(
            "Ekranda tek olarak bulundu.", timeout=10000
        )
        await expect(editor).to_contain_text("bağlantısı")
        await editor.get_by_label("Düğmeye basınca açılacak ekranın adı").fill("Hedef ekran")
        await editor.get_by_label("Bu düğmenin yalnız ekran değiştirdiğini biliyorum").check()
        await add_target_fill(flow)
        await flow.goto(PATH)
        await finish(flow)
        await browser.close()


async def test_choice_transition_end_to_end(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        flow = await open_flow(browser, app_server, lab, "Seçimle geç", PATH)
        editor = await flow.pick("Seçim yap", "Başlangıç bölümündeki İşlem Türü alanını seç")
        await expect(editor.locator(".pd-optlist")).to_contain_text("Hedefe Git", timeout=10000)
        await editor.get_by_label("Sabit seçenek").check()
        await editor.get_by_label("Seçilecek seçenek").select_option(label="Hedefe Git")
        await editor.get_by_label("Kayıt veya ekran değişikliği tetikleyebilir / emin değilim").check()
        await editor.get_by_label("Bu seçim başka bir ekrana geçirir").check()
        await editor.get_by_label("Seçimden sonra açılacak ekranın adı").fill("Hedef ekran")
        await add_target_fill(flow)
        await flow.goto(PATH)
        await finish(flow)
        await browser.close()
