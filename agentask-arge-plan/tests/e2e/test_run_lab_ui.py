"""İşlem Deneme ekranı uçtan uca: JSON yazmadan formdan plan kurma, çalıştırma, durumları ve iptali görme."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.async_api import Page, async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    lab.reset()
    settings = lab_settings(
        make_env_file,
        lab,
        RUN_DIRECTORY=str(tmp_path / "runs"),
        OUTCOME_TIMEOUT_MS="3000",
        RECONCILE_TIMEOUT_MS="3000",
        READINESS_TIMEOUT_MS="3000",
    )
    server = AppServer(create_app(settings))
    server.start()
    yield server
    server.stop()


async def open_lab_page(ui: Page, value: str) -> None:
    await ui.locator("[name=lab_page]").select_option(value)
    await ui.get_by_role("button", name="Deney ekranını aç").click()
    await expect(ui.locator(".rl-session")).to_contain_text(value)


async def run_and_wait(ui: Page, label: str) -> None:
    await ui.get_by_role("button", name="Çalıştır").click()
    await expect(ui.locator(".rl-run .badge")).to_have_text(label, timeout=20_000)


async def test_run_lab_screen_end_to_end(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ui = await browser.new_page()
        await ui.goto(f"http://127.0.0.1:{app_server.port}/designer/runs")
        await ui.get_by_role("button", name="Oturum aç").click()
        await expect(ui.locator(".rl-session")).to_contain_text("Oturum:")

        # Formdan adım: hedefi P2 ile doğrula, değer yaz, koşul ekle
        await open_lab_page(ui, "/pages/duplicates")
        await ui.locator(".rl-step [name=op]").select_option("ensure_value")
        await ui.locator(".rl-step [name=labels]").fill("Müşteri No")
        await ui.get_by_role("button", name="Hedefi doğrula (P2)").click()
        await expect(ui.locator(".rl-resolve")).to_contain_text("ambiguous")
        await ui.locator(".rl-step [name=region]").fill("Kefil")
        await ui.get_by_role("button", name="Hedefi doğrula (P2)").click()
        await expect(ui.locator(".rl-resolve")).to_contain_text("resolved")
        await ui.locator(".rl-step [name=value]").fill("00777")
        await ui.get_by_role("button", name="Adımı ekle").click()
        await ui.locator(".rl-step [name=op]").select_option("assert_condition")
        await ui.locator(".rl-step [name=expected]").fill("00777")
        await ui.get_by_role("button", name="Adımı ekle").click()
        await expect(ui.locator(".rl-plan li")).to_have_count(2)
        await run_and_wait(ui, "Başarılı")
        await expect(ui.locator(".rl-steps tr[data-state=succeeded]")).to_have_count(2)

        # Belirsiz hedef: işlem yapılmaz, duraklatılır
        await ui.locator(".rl-example").select_option("ambiguous")
        await run_and_wait(ui, "Duraklatıldı")
        await expect(ui.locator(".rl-steps")).to_contain_text("Bilinen başarısızlık")
        await expect(ui.locator(".rl-steps")).to_contain_text("TARGET_AMBIGUOUS")

        # Veri değiştiren onaylı aksiyon, yanıt kaybı ve uzlaştırma
        await open_lab_page(ui, "/pages/note-form")
        lab.set_scenario(lose_next_commit_response=True, lost_response_hang_ms=6000, client_timeout_ms=800)
        await ui.locator(".rl-example").select_option("note")
        await run_and_wait(ui, "Başarılı")
        await expect(ui.locator(".rl-steps")).to_contain_text("reconciliation")
        assert [c["text"] for c in lab.control("GET", "/__lab/state").json()["commits"]] == ["Müşteri arandı"]

        # Belirsiz sonuç: gönderim sonrası oturum düşer, uzlaştırma kanıtı okunamaz
        await open_lab_page(ui, "/pages/note-form")
        lab.set_scenario(lose_next_commit_response=True, lost_response_hang_ms=6000, client_timeout_ms=800)
        await ui.locator(".rl-example").select_option("note")
        await ui.get_by_role("button", name="Çalıştır").click()
        for _ in range(100):
            if len(lab.control("GET", "/__lab/state").json()["commits"]) == 2:
                break
            await asyncio.sleep(0.05)
        lab.control("POST", "/__lab/sessions/expire")
        await expect(ui.locator(".rl-run .badge")).to_have_text("Belirsiz", timeout=20_000)
        await expect(ui.locator(".rl-steps")).to_contain_text("Sonuç belirsiz")

        # İptal: başlamış adım biter, sonraki adım başlamaz
        lab.set_scenario(table_rows=40, page_size=10)
        await open_lab_page(ui, "/pages/table-paged")
        lab.set_scenario(delay_ms=600)
        await ui.locator(".rl-example").select_option("record")
        await ui.locator(".rl-step [name=op]").select_option("read")
        await ui.locator(".rl-step [name=kind]").select_option("table")
        await ui.locator(".rl-step [name=labels]").fill("Başvurular")
        await ui.locator(".rl-step [name=region]").fill("")
        await ui.get_by_role("button", name="Adımı ekle").click()
        await ui.get_by_role("button", name="Çalıştır").click()
        await asyncio.sleep(0.5)
        await ui.get_by_role("button", name="İptal et").click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("İptal edildi", timeout=20_000)
        await expect(ui.locator(".rl-steps")).to_contain_text("Atlandı (iptal)")
        lab.set_scenario(delay_ms=0)
        await browser.close()
