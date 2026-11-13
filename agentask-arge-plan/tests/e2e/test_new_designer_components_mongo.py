"""Ana plan E kabulü (geçici MongoDB): yeni tasarımcıda yayımlanmış bileşeni sürümüne pinli çağırma, çıktısını
bağlama ve yeni sürümün etkisini görüp açıkça yükseltme. Lab; Pega uyumluluğu değildir."""

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
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod
from tests.unit.test_component_publishing import component_draft, make_ready

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
OWNER = "dev.user"


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
            MONGO_DATABASE="agentask_components",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()


async def test_call_published_component_bind_output_and_upgrade(
    app_server: AppServer, lab: LabServer
) -> None:
    container = app_server.app.state.container
    sessions, designer, pub = container.sessions, container.designer, container.publishing
    repo = designer._drafts
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    comp = component_draft()
    comp.created_by = OWNER

    async def publish_component(title: str | None, request: str) -> None:
        current = repo.get(comp.draft_id)
        if current is None:
            make_ready(comp)
            repo.create(comp)
        else:
            current.title = title or current.title
            make_ready(current)
            repo.update(current, current.revision)
        latest = repo.get(comp.draft_id)
        pub.approve("pub", comp.draft_id, latest.revision)
        await pub.publish("pub", comp.draft_id, request)

    await in_server(publish_component(None, "req-comp-1"))

    base = f"http://127.0.0.1:{app_server.port}"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ui = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await ui.goto(f"{base}/prototype/designer")
        await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Bileşenli akış")
        await ui.get_by_role("button", name="Gerçek oturum", exact=True).click()
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
        sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
        handle = sessions.peek(OWNER, sid)
        await in_server(handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next=/wizard/C-61"))
        editor = ui.locator("#pd-editor")

        # 1) Akış çağır: yayımlanmış bileşen, sürümüyle
        await ui.locator("#pd-components").get_by_role("button", name="Akış çağır").click()
        await editor.get_by_role("button", name="Yayımlanmış bileşenleri getir").click()
        await editor.get_by_label("Hangi bileşen?").select_option(label="Müşteri yaz ve vaka oku · sürüm 1")
        await expect(editor).to_contain_text("Çıktılar")
        await expect(editor).to_contain_text("yalnız alanlara yazar/okur")

        # 2) Alan doldur: bileşenin okuduğu vaka numarası
        await ui.locator("#pd-components").get_by_role("button", name="Alan doldur").click()
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Müşteri bölümündeki Müşteri No alanını seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(
            "Ekranda tek olarak bulundu.", timeout=10000
        )
        await editor.get_by_label("Önceki adımın çıktısı").check()
        await editor.get_by_label("Hangi adımın değeri?").select_option(index=1)

        await ui.get_by_role("button", name="Taslağı kaydet").click()
        status = ui.locator("#pd-draft-status")
        await expect(status).to_contain_text("Taslak kaydedildi", timeout=20000)
        draft = next(d for d in designer.list_drafts(OWNER) if d.title == "Bileşenli akış")
        call = draft.steps[0].call
        assert call is not None and (call.operation_id, call.revision) == ("musteri_yaz", 1)
        assert call.content_hash == comp.content_hash()
        prior = next(x for x in draft.parameters if str(x.source) == "prior_output")
        assert (prior.prior_step, prior.prior_output) == (0, "vaka_no")
        assert draft.steps[1].value_template == "{" + prior.name + "}"
        issues = designer.validate(OWNER, draft.draft_id)
        assert not [i for i in issues if "call" in i or "component" in i or "prior" in i], issues

        # 3) Bileşenin yeni sürümü yayımlanır: akış kendiliğinden değişmez; etki görünür, yükseltme açıktır.
        await in_server(publish_component("Müşteri yaz ve vaka oku (v2)", "req-comp-2"))
        await ui.get_by_role("button", name="Akışlara dön").click()
        await ui.get_by_role("button", name="Kayıtlı taslakları göster").click()
        await ui.get_by_role("button", name="“Bileşenli akış” taslağını aç").click()
        await expect(ui.locator(".pd-card").first).to_contain_text("Sürüm 1")
        panel = ui.locator("#pd-runpanel")
        await expect(panel).to_contain_text("yayında sürüm 2 var", timeout=10000)
        await expect(panel).to_contain_text("Uyumlu")
        assert designer.get(OWNER, draft.draft_id).steps[0].call.revision == 1  # type: ignore[union-attr]
        await panel.get_by_role("button", name="Sürüm 2'e yükselt").click()
        await expect(ui.locator("#pd-runpanel-status")).to_contain_text("yükseltildi", timeout=10000)
        upgraded = designer.get(OWNER, draft.draft_id)
        assert upgraded.steps[0].call is not None and upgraded.steps[0].call.revision == 2
        assert "step_1_not_ready" in designer.validate(OWNER, draft.draft_id)  # yeniden deneme gerekir
        await expect(ui.locator(".pd-card").first).to_contain_text("Sürüm 2")
        await expect(status).not_to_contain_text("kaydedilmemiş")
        await browser.close()
