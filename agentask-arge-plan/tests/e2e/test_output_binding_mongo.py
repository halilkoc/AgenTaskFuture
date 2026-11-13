"""Önceki okuma çıktısı → onaylı işlem parametresi ve bileşen girdisi: tasarımdan Asistan'a (lab + Mongo)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright, expect

from tests.conftest import EnvFileFactory
from tests.e2e.flow_helpers import OWNER, mongo_app, open_flow
from tests.e2e.support import AppServer
from tests.support_lab import LabServer
from tests.unit.test_component_publishing import component_draft, make_ready

pytestmark = [pytest.mark.browser, pytest.mark.mongo]


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    yield from mongo_app(make_env_file, lab, tmp_path, "agentask_outputs")


def commits(lab: LabServer) -> list[str]:
    return [c["text"] for c in lab.control("GET", "/__lab/state").json()["commits"]]


async def test_read_value_is_action_parameter(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        flow = await open_flow(browser, app_server, lab, "Okunan notu kaydet", "/pages/note-form")
        editor = await flow.pick("Alan doldur", "Not alanını seç")
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill("Okunacak metin")
        await flow.pick("Bilgi oku", "Not alanını seç")
        editor = await flow.add("Onaylı işlem")
        await editor.get_by_label("Hangi onaylı işlem?").select_option(
            label="Vakaya not ekle (deney, veri değiştirir)"
        )
        await editor.get_by_label("Önceki adımın çıktısı").check()
        await editor.get_by_label("Hangi adımın değeri?").select_option(index=1)
        await flow.save()
        cards = await flow.reopen()
        await expect(cards).to_have_count(3)
        await flow.introduce_screen()
        for i in range(3):
            await flow.confirm_and_try(i)
        assert commits(lab) == ["Okunacak metin"]
        await flow.publish("/pages/note-form")
        await flow.assistant_open("Okunan notu kaydet", "/pages/note-form")
        await flow.assistant_start(ack=True)
        assert commits(lab) == ["Okunacak metin"] * 3
        await browser.close()


async def test_read_value_is_component_input(app_server: AppServer, lab: LabServer) -> None:
    container = app_server.app.state.container
    pub, repo = container.publishing, container.designer._drafts
    comp = component_draft()
    comp.created_by = OWNER
    make_ready(comp)
    repo.create(comp)

    async def publish_component() -> None:
        latest = repo.get(comp.draft_id)
        pub.approve("pub", comp.draft_id, latest.revision)
        await pub.publish("pub", comp.draft_id, "req-comp")

    app_server.run(publish_component())
    path = "/wizard/C-2001"

    async def field(flow: Any, section: str, label: str) -> str:
        async def read() -> str:
            return str(
                await flow.handle.page.get_by_role("region", name=section).get_by_label(label).input_value()
            )

        return str(await flow.in_server(read()))

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        flow = await open_flow(browser, app_server, lab, "Vakayı bileşene aktar", path)
        await flow.pick("Bilgi oku", "Vaka bölümündeki Vaka No alanını seç")
        editor = await flow.add("Akış çağır")
        await editor.get_by_role("button", name="Yayımlanmış bileşenleri getir").click()
        await editor.get_by_label("Hangi bileşen?").select_option(label="Müşteri yaz ve vaka oku · sürüm 1")
        await editor.get_by_label("Önceki adımın çıktısı").check()
        await editor.get_by_label("Hangi adımın değeri?").select_option(index=1)
        await flow.save()
        cards = await flow.reopen()
        await expect(cards).to_have_count(2)
        await expect(cards.nth(1)).to_contain_text("bileşeni")
        await flow.introduce_screen()
        for i in range(2):
            await flow.confirm_and_try(i)
        case_no = await field(flow, "Vaka", "Vaka No")
        assert case_no and await field(flow, "Müşteri", "Müşteri No") == case_no
        await flow.publish(path)
        await flow.assistant_open(flow.name, path)
        assert await field(flow, "Müşteri", "Müşteri No") == ""
        await flow.assistant_start(ack=False)
        assert await field(flow, "Müşteri", "Müşteri No") == case_no
        await browser.close()
