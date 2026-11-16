"""APPROVED_ACTION_SET=file: dosya değişir → eski yayın çalışmaz, kanıtı değişmez → yeniden bağlama."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from playwright.async_api import async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.flow_helpers import Flow
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_browser import ui_engine
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
OWNER = "dev.user"
PATH = "/pages/note-form"
NOTE = "Dosya aksiyon notu"
ACTION: dict[str, Any] = {
    "action_id": "kurum.not_ekle",
    "title": "Kurum notu ekle",
    "application_id": "lab",
    "target": {"kind": "button", "labels": ["Kaydet"]},
    "effect": "mutating",
    "retry_safe": False,
    "params": [{"name": "text", "title": "Not metni", "max_length": 500}],
    "requires_fields": [{"target": {"kind": "textbox", "labels": ["Not"]}, "param": "text"}],
    "outcome": {
        "evidence": {"kind": "status_text"},
        "success": {"mode": "prefix", "text": "Kaydedildi (Not #"},
    },
    "reconcile": {
        "reload": True,
        "evidence": {"kind": "list_items", "name": "Mevcut notlar"},
        "match": {"mode": "contains", "text": ": {text} ("},
    },
}


@pytest.fixture
def stack(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[Any]:
    with ephemeral_mongod() as uri:
        if uri is None:
            pytest.skip("BLOCKED: mongod bulunamadı")
        lab.reset()
        path = tmp_path / "actions.json"
        path.write_text(json.dumps({"actions": {ACTION["action_id"]: ACTION}}), encoding="utf-8")

        def start() -> AppServer:
            settings = lab_settings(
                make_env_file,
                lab,
                RUN_DIRECTORY=str(tmp_path / "runs"),
                DRAFT_DIRECTORY=str(tmp_path / "drafts"),
                CATALOG_BACKEND="mongo",
                MONGO_URI=uri,
                MONGO_DATABASE="agentask_file_action",
                APPROVED_ACTION_SET="file",
                APPROVED_ACTIONS_FILE=str(path),
            )
            server = AppServer(create_app(settings))
            server.start()
            return server

        yield start, path
        lab.reset()


async def test_changed_action_blocks_old_release_until_retested(stack: Any, lab: LabServer) -> None:
    start, path = stack
    server = start()
    base = f"http://127.0.0.1:{server.port}"
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await ui.goto(f"{base}/prototype/designer")
        await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Dosya notu")
        await ui.get_by_role("button", name="Gerçek oturum").click()
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
        sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
        await ui.request.post(
            f"{base}/api/sessions/{sid}/navigate",
            data={"url": f"{lab.primary}/__lab/autologin?user=ayse&next={PATH}"},
        )
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
        await editor.get_by_label("Hangi onaylı işlem?").select_option(label="Kurum notu ekle")
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill(NOTE)
        await ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi", timeout=30000)
        panel = ui.locator("#pd-runpanel")
        status = ui.locator("#pd-runpanel-status")
        await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)
        steps = panel.locator(".pd-live__step")
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
        await panel.get_by_label("Başlangıç ekranı (deney uygulamasındaki yol)").fill(PATH)
        await panel.get_by_role("button", name="Yeni oturum testi").click()
        await expect(status).to_contain_text("Yeni oturum testi tamamlandı: BAŞARILI", timeout=40000)
        await panel.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(status).to_contain_text("Onaylandı (yayıncı)", timeout=10000)
        await panel.get_by_role("button", name="Yayımla").click()
        await expect(status).to_contain_text("Yayımlandı ve etkin: rel-", timeout=15000)
        catalog = (await (await ui.request.get(f"{base}/api/assistant/catalog?application_id=lab")).json())[
            "operations"
        ]
        operation = catalog[0]
        release = await (
            await ui.request.get(f"{base}/api/catalogs/releases/{operation['release_id']}")
        ).json()
        drafts = await (await ui.request.get(f"{base}/api/drafts")).json()
        operation_hash = (await (await ui.request.get(f"{base}/api/actions")).json())["actions"][0][
            "fingerprint"
        ]
        await browser.close()
    server.stop()

    # Kurum dosyası değişti (aynı id, farklı davranış) ve uygulama yeniden başladı.
    changed = {
        **ACTION,
        "outcome": {**ACTION["outcome"], "success": {"mode": "prefix", "text": "Kaydedildi"}},
    }
    path.write_text(json.dumps({"actions": {ACTION["action_id"]: changed}}), encoding="utf-8")
    server = start()
    base = f"http://127.0.0.1:{server.port}"
    try:
        async with httpx.AsyncClient(base_url=base, timeout=20) as api:
            refused = await api.post(
                "/api/assistant/preview",
                json={
                    "application_id": "lab",
                    "release_id": operation["release_id"],
                    "operation_id": operation["operation_id"],
                    "arguments": {},
                },
            )
            assert refused.status_code == 422 and "action_changed" in refused.json()["details"]["reason"]
            assert "Yeniden test ve onay" in refused.json()["safe_message"]
            same = (await api.get(f"/api/catalogs/releases/{operation['release_id']}")).json()
            assert same["manifest_hash"] == release["manifest_hash"]  # eski yayın ve kanıtı değişmez
            draft = (await api.get(f"/api/drafts/{drafts[0]['draft_id']}")).json()
            assert any("action_changed" in i for i in draft["issues"])
            approve = await api.post(
                f"/api/drafts/{draft['draft_id']}/approve", json={"expected_revision": draft["revision"]}
            )
            assert approve.status_code == 409

        # Taslak yeniden açılıp kaydedilince yeni davranışa bağlanır; yeniden test edilmeden hazır sayılmaz.
        async with async_playwright() as p:
            browser = await ui_engine(p).launch()
            ui = await browser.new_page(viewport={"width": 1440, "height": 1000})
            await ui.goto(f"{base}/prototype/designer")
            await ui.get_by_role("button", name="Kayıtlı taslakları göster").click()
            await ui.get_by_role("button", name="“Dosya notu” taslağını aç").click()
            await ui.get_by_role("button", name="Yeni oturum aç").click()
            await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
            sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
            await ui.request.post(
                f"{base}/api/sessions/{sid}/navigate",
                data={"url": f"{lab.primary}/__lab/autologin?user=ayse&next={PATH}"},
            )
            await ui.get_by_role("button", name="Taslağı kaydet").click()
            await expect(ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi", timeout=30000)
            await browser.close()
        async with httpx.AsyncClient(base_url=base, timeout=20) as api:
            repinned = (await api.get(f"/api/drafts/{drafts[0]['draft_id']}")).json()
            assert not any("action_changed" in i for i in repinned["issues"]), repinned["issues"]
            action_step = next(s for s in repinned["steps"] if s["op"] == "invoke_approved_action")
            assert action_step["status"] != "ready_for_review"
            assert any("not_ready" in i for i in repinned["issues"])
            current = (await api.get("/api/actions")).json()["actions"][0]["fingerprint"]
            assert action_step["action_hash"] == current
            assert current != operation_hash

        # Yeniden deneme, yeni oturum testi ve yayıncı onayından sonra çalışır; her aşamada tek not.
        def notes() -> list[str]:
            return [c["text"] for c in lab.control("GET", "/__lab/state").json()["commits"]]

        before = len(notes())
        async with async_playwright() as p:
            browser = await ui_engine(p).launch()
            ui = await browser.new_page(viewport={"width": 1440, "height": 1000})
            await ui.goto(f"{base}/prototype/designer")
            await ui.get_by_role("button", name="Kayıtlı taslakları göster").click()
            await ui.get_by_role("button", name="“Dosya notu” taslağını aç").click()
            await ui.get_by_role("button", name="Gerçek oturum", exact=True).click()
            # Yeni tarayıcıda hatırlanan seçim yoktur (localStorage boş): mevcut oturum açıkça seçilir.
            await ui.get_by_label("Tarayıcı oturumu").select_option(sid)
            await expect(ui.get_by_label("Tarayıcı oturumu")).to_have_value(sid, timeout=10000)
            handle = server.app.state.container.sessions.peek(OWNER, sid)
            flow = Flow(ui, server, lab, sid, handle, "Dosya notu")
            await flow.goto(PATH)

            async def prepare_note() -> None:
                # Yalnız aksiyon adımı yeniden denenir; ön koşulu (Not = parametre) analist
                # pencerede hazırlar. Hazırlanmazsa ürün gönderimi reddeder (2026-11-13 teşhisi).
                await flow.in_server(flow.handle.page.get_by_role("textbox", name="Not").fill(NOTE))

            await flow.confirm_and_try(1, before=prepare_note)
            assert len(notes()) == before + 1
            await flow.publish(PATH)
            assert flow.release != operation["release_id"]
            assert len(notes()) == before + 2
            await flow.assistant_open("Dosya notu", PATH)
            await flow.assistant_start(ack=True)
            assert notes()[before:] == [NOTE] * 3
            await browser.close()
    finally:
        server.stop()
