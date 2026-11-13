"""Çok ekranlı başvuru: tasarımdan Asistan'a, yanlış vakada durma, geçmiş ve çıkış (lab + MongoDB)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright, expect

from tests.conftest import EnvFileFactory
from tests.e2e.flow_helpers import Flow, admin_settings, mongo_app, open_flow
from tests.e2e.support import AppServer
from tests.support_lab import LabServer

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
CASE = "C-2001"
START = f"/wizard/{CASE}"
COLLATERAL = f"{START}/collateral"
AMOUNT = "12500"
STOPPED = re.compile("Müdahale|Başarısız|Tamamlanamadı|Duraklatıldı|Belirsiz|Durdu")


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    yield from mongo_app(make_env_file, lab, tmp_path, "agentask_wizard", **admin_settings())


def advances(lab: LabServer) -> int:
    return int(lab.control("GET", "/__lab/state").json()["wizard_advances"].get(CASE, 0))


async def press_next(flow: Flow) -> None:
    async def press() -> None:
        await flow.handle.page.get_by_role("button", name="Devam").click()
        await flow.handle.page.wait_for_url("**/collateral")

    await flow.in_server(press())


async def amount_field(flow: Flow) -> Any:
    async def read() -> str:
        return str(
            await flow.handle.page.get_by_role("region", name="Teminat")
            .get_by_label("Teminat Tutarı")
            .input_value()
        )

    return await flow.in_server(read())


async def shown_case(flow: Flow) -> str:
    async def read() -> str:
        return str(
            await flow.handle.page.get_by_role("region", name="Vaka").get_by_label("Vaka No").input_value()
        )

    return str(await flow.in_server(read()))


async def customer_field(flow: Flow) -> str:
    async def read() -> str:
        return str(
            await flow.handle.page.get_by_role("region", name="Müşteri")
            .get_by_label("Müşteri No")
            .input_value()
        )

    return str(await flow.in_server(read()))


async def test_wizard_design_publish_wrong_case_history_logout(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        flow = await open_flow(browser, app_server, lab, "Teminat gir", START, admin=True)
        await flow.pick("Bilgi oku", "Vaka bölümündeki Vaka No alanını seç")
        editor = await flow.pick("Alan doldur", "Müşteri bölümündeki Müşteri No alanını seç")
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill("00456")
        editor = await flow.add("Ekrana geç")
        await editor.get_by_role("button", name="Ekrandaki düğmeleri listele").click()
        await editor.get_by_role("button", name="Devam düğmesini seç").click()
        await editor.get_by_label("Düğmeye basınca açılacak ekranın adı").fill("Teminat bilgileri")
        await editor.get_by_label("Bu düğmenin yalnız ekran değiştirdiğini biliyorum").check()
        # Açılan ekranda kayıt doğrulanır: başka vakanın aynı türdeki ekranında işlem durmalı.
        await editor.get_by_label("Beklenen değer").select_option(label="Sabit değer")
        await editor.get_by_label("Alanın etiketi").fill("Vaka No")
        await editor.get_by_label("Bölüm (varsa)").fill("Vaka")
        await editor.locator("[id$='-ctx-fixed']").fill(CASE)
        editor = await flow.add("Alan doldur")
        await flow.goto(COLLATERAL)
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Teminat bölümündeki Teminat Tutarı alanını seç").click()
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill(AMOUNT)

        # Her adım kendi ekranı açıkken doğrulanır; tasarım ve kaydetme düğmeye basmaz.
        await flow.goto(START)
        await flow.ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(flow.ui.locator("#pd-draft-status")).to_contain_text(
            "Kaydetme tamamlanmadı", timeout=30000
        )
        await flow.goto(COLLATERAL)
        await flow.save()
        assert advances(lab) == 0
        drafts = await (await flow.ui.request.get(f"{flow.base}/api/drafts")).json()
        saved = await (await flow.ui.request.get(f"{flow.base}/api/drafts/{drafts[0]['draft_id']}")).json()
        (transition,) = saved["transitions"]
        (check,) = transition["completion"]  # kontrol kaydedilen geçiş tanımında
        assert check["target"]["labels"] == ["Vaka No"] and check["target"]["region"] == "Vaka"
        assert check["value_template"] == CASE
        cards = await flow.reopen()
        await expect(cards).to_have_count(4)

        await flow.goto(START)
        panel = flow.panel
        await flow.introduce_screen()
        await press_next(flow)
        await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)
        design_advances = advances(lab)

        await flow.goto(START)
        for i in range(4):
            await flow.confirm_and_try(i)
        assert await amount_field(flow) == AMOUNT
        assert advances(lab) == design_advances + 1  # gerçek denemede tek geçiş

        await flow.publish(START)
        assert advances(lab) == design_advances + 2

        await flow.assistant_open(flow.name, START)
        await flow.ui.get_by_role("button", name="Planı göster").click()
        await expect(flow.ui.locator(".as-route")).to_contain_text("→")  # rota iki ekran
        await flow.assistant_start(ack=False)
        assert await amount_field(flow) == AMOUNT
        assert advances(lab) == design_advances + 3

        # Başka vakanın ekranı açılırsa tutar yazılmaz; neden ve destek numarası görünür.
        lab.control("PUT", "/__lab/scenario", json={"wizard_target": "other_case"})
        await flow.goto(START)
        await flow.ui.get_by_role("button", name="Planı göster").click()
        await flow.assistant_start(ack=False, expected=STOPPED)
        assert await shown_case(flow) == f"{CASE}-B"  # başka vakanın teminat ekranı açıldı
        assert await amount_field(flow) == ""  # tutar yazılmadı
        stopped_support = flow.support
        detail = await flow.history_detail()
        await expect(detail.locator(".rn-stage")).not_to_be_empty()
        await expect(detail.locator(".rn-reason")).not_to_be_empty()
        await expect(detail.locator(".rn-next")).not_to_be_empty()
        assert await detail.locator("details.rn-tech").get_attribute("open") is None  # teknik ayrıntı kapalı
        assert stopped_support

        # Vaka doğru olunca aynı yayın yeniden çalışır.
        lab.control("PUT", "/__lab/scenario", json={"wizard_target": "collateral"})
        await flow.assistant_open(flow.name, START)
        await flow.assistant_start(ack=False)
        assert await amount_field(flow) == AMOUNT

        await flow.ui.goto(f"{flow.base}/runs")
        await flow.ui.get_by_role("button", name="Çıkış").click()
        await expect(flow.ui).to_have_url(f"{flow.base}/login")
        await flow.ui.goto(f"{flow.base}/runs")
        await expect(flow.ui).to_have_url(f"{flow.base}/login?next=/runs")
        await browser.close()
