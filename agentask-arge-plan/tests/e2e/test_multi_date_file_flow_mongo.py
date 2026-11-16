"""Çoklu seçim + tarih + dosya: tasarımdan İşlem Asistanı'na (lab + MongoDB)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright, expect

from tests.conftest import EnvFileFactory
from tests.e2e.flow_helpers import Flow, changed_fields, mongo_app, open_flow
from tests.e2e.support import AppServer
from tests.support_browser import ui_engine
from tests.support_lab import LabServer

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
PAGE = "/pages/controls"
PAYLOAD = {"name": "rapor.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4 deneme"}


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    yield from mongo_app(make_env_file, lab, tmp_path, "agentask_multi")


async def state(flow: Flow) -> tuple[list[str], str, str | None]:
    async def read() -> tuple[list[str], str, str | None]:
        page = flow.handle.page
        tags = page.get_by_role("region", name="Çoklu").get_by_label("Etiketler")
        chosen = await tags.evaluate("e => Array.from(e.selectedOptions).map(o => o.text)")
        date = await page.get_by_role("region", name="Tarih").get_by_label("Başlangıç").input_value()
        got = (
            await page.get_by_role("region", name="Yükleme")
            .get_by_label("Belge", exact=True)
            .get_attribute("data-received")
        )
        return sorted(chosen), date, got

    result: tuple[list[str], str, str | None] = await flow.in_server(read())
    return result


async def test_multi_date_file_from_design_to_assistant(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        flow = await open_flow(browser, app_server, lab, "Belge ve seçimler", PAGE)

        editor = await flow.pick("Çoklu seçim", "Çoklu bölümündeki Etiketler alanını seç")
        await expect(editor.locator("[id$='-options']").first).to_contain_text("Gama")
        await editor.get_by_label("Her çalıştırmada sor").check()
        await editor.get_by_label("Kullanıcıya sorulacak metin").fill("Hangi etiketler?")
        await editor.get_by_label("Yalnız bu alanın seçimini değiştirir").check()

        editor = await flow.pick("Alan doldur", "Tarih bölümündeki Başlangıç alanını seç")
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Bu bir tarih alanı").check()
        await expect(editor.get_by_label("Tarih biçimi")).to_have_value("DD.MM.YYYY")
        await editor.get_by_label("Yazılacak değer").fill("31.02.2026")
        await expect(editor).to_contain_text("Geçerli bir tarih yazın")  # geçersiz tarih tanımlanamaz
        await editor.get_by_label("Yazılacak değer").fill("09.11.2026")
        await expect(editor).not_to_contain_text("Geçerli bir tarih yazın")

        editor = await flow.pick("Dosya yükle", "Yükleme bölümündeki Belge alanını seç")
        await editor.get_by_label("Kullanıcıya sorulacak metin").fill("Hangi belge?")
        await editor.get_by_label("PDF").check()
        await editor.get_by_label("Ekranda görünmesi gereken durum mesajı (zorunlu)").fill("Belge alındı")

        await flow.save()
        cards = await flow.reopen()
        await expect(cards).to_have_count(3)
        await cards.nth(1).click()
        await expect(flow.editor.get_by_label("Bu bir tarih alanı")).to_be_checked()
        await cards.nth(2).click()
        await expect(flow.editor.get_by_label("Kullanıcıya sorulacak metin")).to_have_value("Hangi belge?")

        await flow.introduce_screen()
        panel = flow.panel
        await panel.locator("textarea[id^='pd-arg-']").fill("Gama\nAlfa")
        await panel.locator("input[type=file][id^='pd-arg-']").set_input_files(PAYLOAD)
        await expect(panel.locator("[id$='-note']")).to_have_text("Dosya yüklendi.", timeout=10000)
        for i in range(3):
            await flow.confirm_and_try(i)
        chosen, date, got = await state(flow)
        assert (chosen, date) == (["Alfa", "Gama"], "2026-11-09")
        assert got is not None and got.startswith("rapor.pdf|application/pdf|")

        await flow.publish(PAGE)
        await flow.assistant_open(flow.name, PAGE)
        form = flow.ui.locator(".as-args")
        await form.locator(".as-multi").get_by_label("Beta").check()
        # PDF olarak beyan edilip içeriği PDF olmayan dosya depoya alınmaz; işlem de başlatılamaz.
        await form.locator(".as-file").set_input_files(
            {"name": "sahte.pdf", "mimeType": "application/pdf", "buffer": b"bu pdf degil"}
        )
        await expect(form).to_contain_text("Dosya kabul edilmedi", timeout=10000)
        await form.locator(".as-file").set_input_files(PAYLOAD)
        await expect(form).to_contain_text("Dosya yüklendi.", timeout=10000)
        fresh = await flow.fields()
        await flow.assistant_start(ack=True)
        chosen, date, got = await state(flow)
        assert chosen == ["Beta"]
        assert got is not None and got.startswith("rapor.pdf|")
        assert changed_fields(fresh, await flow.fields()).keys() <= {"Tarih › Başlangıç", "Yükleme › Belge"}

        async def uploads() -> Any:
            page = flow.handle.page
            return (
                await page.get_by_role("region", name="Yükleme")
                .get_by_label("Belge", exact=True)
                .get_attribute("data-uploads")
            )

        assert await flow.in_server(uploads()) == "1"
        await browser.close()
