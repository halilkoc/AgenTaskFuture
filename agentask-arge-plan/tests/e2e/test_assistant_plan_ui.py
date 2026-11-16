"""Ana plan F (arayüz, geçici MongoDB): model test ikamesiyle yayımlanmış işlemlerden sıralı plan önerisi →
eksik bilgi → sunucuda doğrulanan özet → açık başlatma. Gerçek model hizmeti kullanılmaz (BLOCKED)."""

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
from tests.integration.browser.test_assistant import APPLICANT, ScriptedLLM
from tests.screens import PARTIES_SCREEN
from tests.support_browser import ui_engine
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod
from tests.unit.test_component_publishing import make_ready

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
OWNER = "dev.user"
GUARANTOR = {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"}


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
            MONGO_DATABASE="agentask_plan_ui",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()


async def test_model_plan_proposal_to_run(app_server: AppServer, lab: LabServer) -> None:
    from agentask.domain.catalog import OperationDraft, ParameterDef

    container = app_server.app.state.container
    pub, repo = container.publishing, container.designer._drafts
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    async def publish(op_id: str, title: str, target: dict[str, Any], req: str) -> None:
        d = OperationDraft.new(
            created_by=OWNER, application_id="lab", operation_id=op_id, title=title, description=""
        )
        d.parameters.append(ParameterDef(name="no", title="Müşteri No", max_length=20, source="user_input"))
        d.add_element("hedef", title, target, "observed")
        s = d.add_step("yaz")
        s.op, s.element_id, s.value_template = "ensure_value", "hedef", "{no}"
        s.standard_text = f"'{title}' alanına {{no}} değerini yaz"
        d.screen = PARTIES_SCREEN
        make_ready(d)
        repo.create(d)
        pub.approve("pub", d.draft_id, repo.get(d.draft_id).revision)
        await pub.publish("pub", d.draft_id, req)

    await in_server(publish("kefil_no", "Kefil numarasını gir", GUARANTOR, "r1"))
    await in_server(publish("basvuran_no", "Başvuran numarasını gir", APPLICANT, "r2"))
    llm = ScriptedLLM(
        {
            "steps": [
                {"operation_id": "kefil_no", "arguments": {"no": "00123"}},
                {"operation_id": "basvuran_no", "arguments": {}},
            ]
        }
    )
    object.__setattr__(container, "llm", llm)  # test ikamesi; gerçek model yok
    container.assistant._llm = llm

    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page(viewport={"width": 1280, "height": 1000})
        await ui.goto(f"http://127.0.0.1:{app_server.port}/assistant")
        await expect(ui.locator(".as-llm")).to_contain_text("model: kullanılabilir")
        await ui.locator("[name=prompt]").fill("Kefil için 00123 gir, sonra başvuranı da gir")
        await ui.get_by_role("button", name="Birden çok işlem öner (model)").click()
        await expect(ui.locator(".as-result")).to_contain_text("Plan önerildi")
        await expect(ui.locator(".as-result")).to_contain_text("[model önerisi]")
        assert llm.calls == 1
        args = ui.locator(".as-args")
        await expect(args).to_contain_text("1. Kefil numarasını gir")
        await expect(args.locator("fieldset").nth(1)).to_contain_text("Müşteri No (eksik)")
        await args.locator("fieldset").nth(1).locator("input").fill("00456")
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-plan")).to_contain_text("2 işlem sırayla")
        await expect(ui.locator(".as-bindings")).to_contain_text("2. işlem · Müşteri No: 00456")
        await expect(ui.locator(".as-plan")).to_contain_text("alanına 00123 değerini yaz")

        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator(".sp-current")).to_contain_text("Seçili oturum:", timeout=10000)
        await ui.locator("[name=lab_page]").select_option("/pages/duplicates")
        await ui.get_by_role("button", name="Ekranı aç").click()
        await expect(ui.locator(".as-session")).to_contain_text("/pages/duplicates")
        await ui.get_by_role("button", name="Başlat").click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=20_000)
        await expect(ui.locator(".rl-run")).to_contain_text("Tamamlandı")
        await browser.close()
