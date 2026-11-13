"""R3 uçtan uca (gerçek Chromium + geçici mongod, testlere özel veritabanı): eski yayın reddi → tasarımcıda
geçiş
taslağı → ekran tanımı → yeni oturum testi → yeniden onay → r2 yayını → asistanda doğru ekranda çalıştırma ve
benzer yanlış ekranda yazmadan durma. Eski r1 kaydı ve eski manifest bayt bayt korunur."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Page, async_playwright, expect

from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.mongo.catalog_store import MongoCatalogStore
from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e import test_designer_ui as flow
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.legacy_catalog import seed_legacy_release
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod
from tests.unit.test_publishing import ready_draft

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
DB = "agentask_e2e_r3"


@pytest.fixture
def mongo_uri() -> Iterator[str]:
    with ephemeral_mongod() as uri:
        if uri is None:
            pytest.skip("BLOCKED: mongod bulunamadı")
        yield uri


@pytest.fixture
def app_server(
    make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path, mongo_uri: str
) -> Iterator[AppServer]:
    lab.reset()
    settings = lab_settings(
        make_env_file,
        lab,
        RUN_DIRECTORY=str(tmp_path / "runs"),
        DRAFT_DIRECTORY=str(tmp_path / "drafts"),
        CATALOG_BACKEND="mongo",
        MONGO_URI=mongo_uri,
        MONGO_DATABASE=DB,
        READINESS_TIMEOUT_MS="2500",
    )
    server = AppServer(create_app(settings))
    server.start()
    yield server
    server.stop()


async def raw(store: MongoCatalogStore) -> dict[str, list[dict[str, Any]]]:
    out = {}
    for name in ("catalog_operations", "catalog_releases"):
        out[name] = [d async for d in store._db[name].find({}, sort=[("_id", 1)])]
    return out


async def interpret(ui: Page, port: int) -> None:
    await ui.goto(f"http://127.0.0.1:{port}/assistant")
    await ui.locator("[name=prompt]").fill("Kefil müşteri numarasını gir")
    await ui.get_by_role("button", name="Yorumla").click()
    await ui.locator(".as-args [name=no]").fill("00456")


async def test_legacy_release_migrated_through_ui(
    app_server: AppServer, lab: LabServer, mongo_uri: str, tmp_path: Path
) -> None:
    port = app_server.port
    store = MongoCatalogStore(mongo_uri, DB, 3000)
    legacy_draft = ready_draft(
        LocalFileDraftRepository(tmp_path / "seed"), "kefil_musteri_no", "Kefil müşteri numarasını gir"
    )
    legacy_draft.intent_phrases = ["kefil müşteri numarasını gir"]
    legacy_draft.steps[0].standard_text = "'Kefil müşteri numarası' alanına {no} değerini yaz"
    legacy = await seed_legacy_release(store, legacy_draft)
    before = await raw(store)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            ui = await browser.new_page()

            # 1) Eski yayın: asistan açıkça reddeder (migration_required), ekran kontrolü atlanmaz.
            await interpret(ui, port)
            await expect(ui.locator(".as-llm")).to_contain_text(
                "1 işlem ekran tanımı olmadığı için geçiş bekliyor"
            )
            await expect(ui.locator(".as-migration")).to_contain_text("migration_required")
            await ui.get_by_role("button", name="Planı göster").click()
            await expect(ui.locator(".tl-error")).to_contain_text("ekran tanımı olmayan eski bir yayından")
            await expect(ui.locator(".as-plan")).to_be_hidden()

            # 2) Tasarımcı: geçiş taslağı → ekran tanımı → yeni oturum testi → onay → yayın (r2).
            await ui.goto(f"http://127.0.0.1:{port}/designer")
            await ui.get_by_role("button", name="Yeni oturum aç").click()
            await expect(ui.locator(".sp-current")).to_contain_text("Seçili oturum:")
            await ui.locator("[name=lab_page]").select_option("/pages/duplicates")
            await ui.get_by_role("button", name="Ekranı aç").click()
            item = ui.locator(".dz-migrations li").filter(has_text="kefil_musteri_no r1")
            await expect(item).to_contain_text("ekran tanımı yok")
            await item.get_by_role("button", name="Geçiş taslağı oluştur").click()
            await expect(ui.locator(".dz-migrated")).to_contain_text("Geçiş taslağı: kefil_musteri_no r1")
            await expect(ui.locator(".dz-drafts li").filter(has_text="geçiş: r1")).to_contain_text("1 adım")
            await expect(ui.get_by_role("button", name="Onayla (yayıncı)")).to_be_visible()
            await ui.get_by_role("button", name="Onayla (yayıncı)").click()
            await expect(ui.locator(".tl-error")).to_contain_text(
                "hazır değil"
            )  # ekran ve test olmadan onay yok
            await flow.define_parties_screen(ui)
            await ui.locator("[name=entry]").select_option("/pages/duplicates")
            await ui.locator("[name=fresh_no]").fill("00999")
            await ui.get_by_role("button", name="Yeni oturum testi").click()
            await expect(ui.locator(".dz-review")).to_contain_text(
                "İncelemeye hazır: bütün adımlar doğrulandı", timeout=30_000
            )
            await ui.get_by_role("button", name="Onayla (yayıncı)").click()
            await expect(ui.locator(".dz-publish")).to_contain_text("Onaylandı")
            await ui.get_by_role("button", name="Yayımla").click()
            await expect(ui.locator(".dz-publish")).to_contain_text("kefil_musteri_no r2")
            await expect(ui.locator(".dz-migrations")).to_contain_text("Geçiş gereken işlem yok.")

            # 3) Asistan: r2 doğru ekranda çalışır; plan bağlanan değeri gösterir.
            await interpret(ui, port)
            await ui.get_by_role("button", name="Planı göster").click()
            await expect(ui.locator(".as-plan")).to_contain_text("revizyon 2")
            await expect(ui.locator(".as-plan")).to_contain_text("alanına 00456 değerini yaz")
            await ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
            await ui.locator("[name=lab_page]").select_option("/pages/duplicates")
            await ui.get_by_role("button", name="Ekranı aç").click()
            await expect(ui.locator(".as-session")).to_contain_text("/pages/duplicates")
            await ui.get_by_role("button", name="Başlat").click()
            await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=20_000)
            await expect(ui.locator(".rl-steps")).to_contain_text("assert_screen")

            # 4) Benzer ama yanlış ekran: hiçbir yazma adımı başlamadan durur.
            lab.set_scenario(party_layout="similar")
            await ui.get_by_role("button", name="Ekranı aç").click()
            await ui.get_by_role("button", name="Planı göster").click()
            await ui.get_by_role("button", name="Başlat").click()
            await expect(ui.locator(".rl-steps")).to_contain_text("SCREEN_NOT_RECOGNIZED", timeout=20_000)
            await expect(ui.locator(".rl-steps tr[data-state=succeeded]")).to_have_count(0)
            await expect(ui.locator(".rl-steps tr[data-state=pending]")).to_have_count(2)
            await browser.close()

        after = await raw(store)
        assert after["catalog_operations"][0] == before["catalog_operations"][0]  # r1 bayt bayt aynı
        assert [o["revision"] for o in after["catalog_operations"]] == [1, 2]
        assert after["catalog_releases"][0] == before["catalog_releases"][0]
        assert after["catalog_releases"][0]["release_id"] == legacy.release_id
    finally:
        await store.close()
