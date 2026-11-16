"""Tasarımcıdan onay + yayın ve /catalogs incelemesi — gerçek (geçici) MongoDB ile uçtan uca."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
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
            MONGO_DATABASE="agentask_e2e",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()


async def test_approve_publish_and_review(app_server: AppServer, lab: LabServer) -> None:
    from tests.e2e import test_designer_ui as flow

    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page()
        await flow.author_ready_draft(ui, app_server.port)
        await ui.get_by_role("button", name="Yayımla").click()
        await expect(ui.locator(".tl-error")).to_contain_text("Onay yok")
        await ui.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("Onaylandı: dev.user")
        await expect(ui.locator(".dz-review")).to_contain_text("güncel")
        await ui.get_by_role("button", name="Yayımla").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("Yayımlandı ve etkin: rel-")
        await expect(ui.locator(".dz-publish")).to_contain_text("kefil_musteri_no r1")

        await ui.goto(f"http://127.0.0.1:{app_server.port}/catalogs")
        await expect(ui.locator(".ct-list")).to_contain_text("etkin: rel-")
        await ui.locator(".ct-list").get_by_role("button", name="Ayrıntı").first.click()
        await expect(ui.locator(".ct-detail")).to_contain_text("ETKİN")
        await expect(ui.locator(".ct-detail")).to_contain_text(
            "kefil_musteri_no r1 — Kefil müşteri numarasını gir"
        )
        await browser.close()
