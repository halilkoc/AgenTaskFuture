"""Kayıt bul → bulunan satırda bağlantı → kayıt bağlamı: tasarımdan Asistan'a (lab + MongoDB)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from tests.conftest import EnvFileFactory
from tests.e2e.flow_helpers import Flow, mongo_app, open_flow
from tests.e2e.support import AppServer
from tests.support_lab import LabServer

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
LIST = "/pages/records"
KEY = "R-1005"


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    yield from mongo_app(make_env_file, lab, tmp_path, "agentask_records")


async def detail_note(flow: Flow) -> str:
    async def read() -> str:
        return str(
            await flow.handle.page.get_by_role("region", name="Kayıt")
            .get_by_label("Detay Notu")
            .input_value()
        )

    return str(await flow.in_server(read()))


async def test_find_open_row_and_verify_record(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        flow = await open_flow(browser, app_server, lab, "Kaydı bul ve aç", LIST)
        editor = await flow.pick("Kayıt bul", "Kayıtlar tablosunu seç")
        await editor.get_by_label("Her çalıştırmada sor").check()
        await editor.get_by_label("Sayfalı tablo").check()
        await expect(editor.get_by_label("Sonraki sayfa düğmesinin adı")).to_have_value("Sonraki")

        editor = await flow.add("Ekrana geç")
        await editor.get_by_role("button", name="Ekrandaki düğmeleri listele").click()
        await editor.get_by_role("button", name="R-1001 satırındaki Aç düğmesini seç").click()
        await expect(editor.get_by_label("Bulunan kaydın satırında çalışsın")).to_be_checked()
        await editor.get_by_label("Düğmeye basınca açılacak ekranın adı").fill("Kayıt ayrıntısı")
        await editor.get_by_label("Bu düğmenin yalnız ekran değiştirdiğini biliyorum").check()
        await editor.get_by_label("Beklenen değer").select_option(label="Bulunan kaydın anahtarı")
        await editor.get_by_label("Alanın etiketi").fill("Kayıt No")
        await editor.get_by_label("Bölüm (varsa)").fill("Kayıt")

        editor = await flow.add("Alan doldur")
        await flow.goto(f"{LIST}/{KEY}")
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Kayıt bölümündeki Detay Notu alanını seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(
            "Ekranda tek olarak bulundu.", timeout=10000
        )
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill("İşlendi")

        await flow.goto(LIST)
        await flow.ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(flow.ui.locator("#pd-draft-status")).to_contain_text(
            "Kaydetme tamamlanmadı", timeout=30000
        )
        await flow.goto(f"{LIST}/{KEY}")
        await flow.save()
        cards = await flow.reopen()
        await expect(cards).to_have_count(3)
        await expect(cards.nth(0)).to_contain_text("Kayıtlar” tablosu")

        await flow.goto(LIST)
        panel = flow.panel
        await flow.introduce_screen()
        await flow.goto(f"{LIST}/{KEY}")
        await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)

        await flow.goto(LIST)
        arg = panel.locator("input[id^='pd-arg-']")
        await arg.fill(KEY)
        for i in range(3):
            await flow.confirm_and_try(i)
        assert await detail_note(flow) == "İşlendi"
        await arg.fill(KEY)
        await flow.publish(LIST)
        await flow.assistant_open(flow.name, LIST)
        await flow.ui.locator(".as-args input").first.fill(KEY)
        await flow.assistant_start(ack=False)
        assert await detail_note(flow) == "İşlendi"
        await browser.close()
