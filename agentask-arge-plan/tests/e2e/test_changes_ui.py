"""Uçtan uca: yayımlanmış işlemin elemanı ekranda değişince /changes etkiyi gösterir ve onarım taslağı
açar; /runs."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e import test_designer_ui as flow
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_browser import ui_engine
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod

pytestmark = [pytest.mark.browser, pytest.mark.mongo]


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    with ephemeral_mongod() as uri:
        if uri is None:
            pytest.skip("BLOCKED: mongod bulunamadı")
        lab.reset()
        settings = lab_settings(
            make_env_file,
            lab,
            RUN_DIRECTORY=str(tmp_path / "runs"),
            DRAFT_DIRECTORY=str(tmp_path / "drafts"),
            CATALOG_BACKEND="mongo",
            MONGO_URI=uri,
            MONGO_DATABASE="agentask_e2e_ch",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()


async def test_changes_and_runs_screens(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page()
        await flow.author_ready_draft(ui, app_server.port)
        await ui.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("Onaylandı")
        await ui.get_by_role("button", name="Yayımla").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("Yayımlandı ve etkin")

        lab.set_scenario(guarantor_customer_label="Müşteri Numarası")
        await ui.goto(f"http://127.0.0.1:{app_server.port}/changes")
        await expect(ui.locator("[name=operation] option")).to_have_count(1)
        # Sayfa değişti: yeni oturum açılmaz; tasarımcının etkileşimli oturumu listeden açıkça seçilir.
        await expect(ui.locator(".sp-quota")).to_contain_text("Etkileşimli oturum: 1/1")
        await expect(ui.get_by_role("button", name="Yeni oturum aç")).to_be_disabled()
        await ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
        await expect(ui.locator(".sp-current")).to_contain_text("Seçili oturum:")
        await ui.locator("[name=lab_page]").select_option("/pages/duplicates")
        await ui.get_by_role("button", name="Ekranı aç").click()
        await expect(ui.locator(".ch-session")).to_contain_text("/pages/duplicates")
        await ui.get_by_role("button", name="Ekranla karşılaştır").click()
        await expect(ui.locator(".ch-result tr[data-status=not_found]")).to_contain_text("Müşteri Numarası")
        await expect(ui.locator(".ch-result")).to_contain_text("kefil_musteri_no r1 — nedenler: element:")
        await ui.get_by_role("button", name="Onarım taslağı oluştur").click()
        await expect(ui.locator(".ch-result")).to_contain_text("Onarım taslağı açıldı")
        await ui.locator("[name=kind]").select_option("textbox")
        await ui.get_by_role("button", name="Etkilenen işlemleri bul").click()
        await expect(ui.locator(".ch-dependency")).to_contain_text("adapter:textbox")

        await ui.goto(f"http://127.0.0.1:{app_server.port}/runs")
        await expect(ui.locator(".rn-metrics")).to_contain_text("Toplam")
        await ui.locator(".rn-list").get_by_role("button", name="Ayrıntı").first.click()
        await expect(ui.locator(".rn-detail")).to_contain_text("succeeded")
        await browser.close()
