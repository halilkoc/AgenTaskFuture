"""R2B: Varsayılan .env.example ayarlarıyla sayfalar arası oturum kullanımı
(kullanıcı başına 1 etkileşimli oturum).

1) Designer'da oturum aç  2) hazırla + yeni oturum testi (+ onay/yayın)
3) Assistant'ta mevcut oturumu seç
4) izinli test işlemini çalıştır  5) Changes'te aynı oturum yönetimi
6) çakışan işlem ve başka kullanıcı reddi.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
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
            MONGO_DATABASE="agentask_e2e_xs",
        )
        assert settings.browser_max_sessions_per_user == 1  # .env.example varsayılanı; override yok
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()


async def select_existing(ui) -> None:  # type: ignore[no-untyped-def]
    await expect(ui.locator(".sp-quota")).to_contain_text("Etkileşimli oturum: 1/1")
    await expect(ui.locator(".sp-current")).to_have_text("Seçili oturum yok.")  # sessizce seçilmez/açılmaz
    await expect(ui.get_by_role("button", name="Yeni oturum aç")).to_be_disabled()
    await ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
    await expect(ui.locator(".sp-current")).to_contain_text("Seçili oturum:")


async def test_one_session_shared_across_pages(app_server: AppServer, lab: LabServer) -> None:
    base = f"http://127.0.0.1:{app_server.port}"
    async with async_playwright() as p, httpx.AsyncClient(base_url=base, timeout=30) as api:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page()
        # 1–2: Designer'da oturum, hazırlık ve yeni oturum testi (geçici doğrulama oturumu), onay ve yayın
        await flow.author_ready_draft(ui, app_server.port)
        await ui.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("Onaylandı")
        await ui.get_by_role("button", name="Yayımla").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("Yayımlandı ve etkin")
        overview = (await api.get("/api/sessions/overview")).json()
        assert len(overview["sessions"]) == 1 and overview["quota"]["verification_in_use"] == 0
        sid = overview["sessions"][0]["session_id"]

        # 3–4: Assistant'ta aynı oturum açıkça seçilir; adres değiştirilmez; izinli işlem çalışır
        await ui.goto(f"{base}/assistant")
        await expect(ui.locator(".sp-note")).to_contain_text("Önceki oturumunuz bulundu")
        await select_existing(ui)
        await expect(ui.locator(".sp-current")).to_contain_text("/pages/duplicates")
        await ui.locator("[name=prompt]").fill("Kefil müşteri numarasını gir")
        await ui.get_by_role("button", name="Yorumla").click()
        await ui.locator(".as-args [name=musteri_no]").fill("00456")
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-plan")).to_contain_text("etki")
        await ui.get_by_role("button", name="Başlat").click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=20_000)
        assert (await api.get("/api/sessions/overview")).json()["sessions"][0]["session_id"] == sid

        # 5: Changes'te aynı oturum yönetimi; seçim sayfa yenilenince backend'den doğrulanır
        await ui.goto(f"{base}/changes")
        await select_existing(ui)
        await ui.reload()
        await expect(ui.locator(".sp-current")).to_have_text("Seçili oturum yok.")
        await select_existing(ui)
        await ui.locator("[name=lab_page]").select_option("/pages/note-form")
        await ui.get_by_role("button", name="Ekranı aç").click()
        await expect(ui.locator(".sp-current")).to_contain_text("/pages/note-form")

        # 6a: çakışan işlem — oturumda süren run varken başka sayfa işlem başlatamaz
        catalog = (await api.get("/api/assistant/catalog", params={"application_id": "lab"})).json()
        release_id = catalog["operations"][0]["release_id"]
        run = (
            await api.post(
                "/api/assistant/execute",
                json={  # hedef bu ekranda yok → hazır olma beklemesi sürer
                    "application_id": "lab",
                    "session_id": sid,
                    "release_id": release_id,
                    "operation_id": "kefil_musteri_no",
                    "arguments": {"musteri_no": "1"},
                    "request_id": "busy-run",
                },
            )
        ).json()
        await ui.get_by_role("button", name="Ekranla karşılaştır").click()
        await expect(ui.locator(".tl-error")).to_contain_text("başka bir işlem sürüyor")
        await ui.get_by_role("button", name="Durumu yenile").click()
        await expect(ui.locator(".sp-current")).to_contain_text("meşgul (run)")
        await api.post(f"/api/runs/{run['run_id']}/cancel")
        for _ in range(100):
            state = (await api.get(f"/api/runs/{run['run_id']}")).json()["status"]
            if state not in {"running", "cancel_requested", "created"}:
                break
            await asyncio.sleep(0.2)

        # 6b: başka kullanıcı ne görebilir ne kullanabilir; saklı kimlik yetki değildir
        other = {"X-Dev-User": "mehmet", "X-Dev-Roles": "designer,operator"}
        assert (await api.get(f"/api/sessions/{sid}", headers=other)).status_code == 404
        assert (await api.post(f"/api/sessions/{sid}/observe", headers=other)).status_code == 404
        assert (await api.get("/api/sessions/overview", headers=other)).json()["sessions"] == []
        await ui.evaluate("() => localStorage.setItem('agentask.session', 'baskasinin-oturumu-xyz')")
        await ui.reload()
        await expect(ui.locator(".sp-note")).to_contain_text("Kayıtlı oturum artık geçerli değil")
        await expect(ui.locator(".sp-current")).to_have_text("Seçili oturum yok.")
        await browser.close()
