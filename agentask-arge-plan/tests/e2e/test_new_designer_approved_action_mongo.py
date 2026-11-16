"""Yeni tasarımcıda “Onaylı işlem”: deneme → yeni oturum → yayın → Asistan; mükerrer kayıt yok (lab)."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any

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
OWNER = "dev.user"
PATH = "/pages/note-form"
NOTE = "Aday not metni"


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
            MONGO_DATABASE="agentask_action",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()
        lab.reset()


async def test_approved_action_through_designer_and_assistant(app_server: AppServer, lab: LabServer) -> None:
    sessions = app_server.app.state.container.sessions
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    def commits() -> list[str]:
        return [c["text"] for c in lab.control("GET", "/__lab/state").json()["commits"]]

    base = f"http://127.0.0.1:{app_server.port}"
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await ui.goto(f"{base}/prototype/designer")
        await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Not kaydet")
        await ui.get_by_role("button", name="Gerçek oturum").click()
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
        sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
        handle = sessions.peek(OWNER, sid)
        await in_server(handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next={PATH}"))

        editor = ui.locator("#pd-editor")
        await ui.locator("#pd-components").get_by_role("button", name="Alan doldur").click()
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Not alanını seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(
            "Ekranda tek olarak bulundu.", timeout=10000
        )
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill(NOTE)
        await ui.locator("#pd-components").get_by_role("button", name="Onaylı işlem").click()
        await editor.get_by_label("Hangi onaylı işlem?").select_option(
            label="Vakaya not ekle (deney, veri değiştirir)"
        )
        await expect(editor).to_contain_text("veri değiştirir")
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill(NOTE)
        await ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi", timeout=30000)
        assert commits() == []  # tanımlama ve kaydetme işlem yapmaz

        panel = ui.locator("#pd-runpanel")
        status = ui.locator("#pd-runpanel-status")
        await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)
        steps = panel.locator(".pd-live__step")
        await expect(steps.nth(1)).to_contain_text("Vakaya not ekle")
        for i in range(2):
            step = steps.nth(i)
            for box in await step.locator("[data-ack]").all():
                await box.check()
            await step.get_by_role("button", name="Onayla", exact=True).click()
            await expect(step).to_contain_text("Denemeye hazır", timeout=10000)
            await step.get_by_label("Bu deneme hedef uygulamada işlem yapabilir").check()
            await step.get_by_role("button", name="Gerçek dene").click()
            await expect(step).to_contain_text("Sistem doğrulaması: BAŞARILI", timeout=25000)
            await step.get_by_role("button", name="Sonucu onayla").click()
            await expect(step).to_contain_text("Hazır", timeout=10000)
        assert commits() == [NOTE]

        await panel.get_by_label("Başlangıç ekranı (deney uygulamasındaki yol)").fill(PATH)
        await panel.get_by_role("button", name="Yeni oturum testi").click()
        await expect(status).to_contain_text("Yeni oturum testi tamamlandı: BAŞARILI", timeout=40000)
        assert commits() == [NOTE, NOTE]
        await panel.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(status).to_contain_text("Onaylandı (yayıncı)", timeout=10000)
        await panel.get_by_role("button", name="Yayımla").click()
        await expect(status).to_contain_text("Yayımlandı ve etkin: rel-", timeout=15000)

        # Yayın, seçilen aksiyonun güncel davranış özetine bağlı.
        actions = await (await ui.request.get(f"{base}/api/actions")).json()
        fingerprint = next(a for a in actions["actions"] if a["title"].startswith("Vakaya not"))[
            "fingerprint"
        ]
        drafts = await (await ui.request.get(f"{base}/api/drafts")).json()
        saved = await (await ui.request.get(f"{base}/api/drafts/{drafts[0]['draft_id']}")).json()
        pinned = next(s for s in saved["steps"] if s["op"] == "invoke_approved_action")
        assert pinned["action_hash"] == fingerprint

        async def run_from_assistant() -> str:
            await ui.goto(f"{base}/assistant")
            await ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
            await ui.locator("[name=lab_page]").select_option(PATH)
            await ui.get_by_role("button", name="Ekranı aç").click()
            await expect(ui.locator(".as-session")).to_contain_text(PATH)
            await ui.locator(".as-ready-wrap summary").click()
            await ui.locator(".as-ready").get_by_role("button", name="Not kaydet").click()
            await ui.get_by_role("button", name="Planı göster").click()
            await expect(ui.locator(".as-ack-wrap")).to_be_visible()
            await expect(ui.locator(".as-plan")).to_contain_text("veri değiştirir")
            await ui.locator("[name=ack]").check()
            await ui.get_by_role("button", name="Başlat").click()
            await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=40000)
            return (await ui.locator(".as-support").inner_text()).split(": ", 1)[1]

        # Normal çalıştırma: tek yeni not.
        first = await run_from_assistant()
        assert commits() == [NOTE] * 3
        # Yanıt kaybında uzlaştırılır, yeniden gönderilmez: yine tek yeni not.
        lab.control("PUT", "/__lab/scenario", json={"lose_next_commit_response": True})
        second = await run_from_assistant()
        assert commits() == [NOTE] * 4
        assert first != second
        await browser.close()
