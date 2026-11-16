"""Kontrol adapterleri + Playwright sürücüsü, gerçek Chromium ve deney uygulamasıyla."""

from __future__ import annotations

import pytest

from agentask.application.controls import (
    AdapterRegistry,
    ChoiceNotAvailable,
    ControlUnsupported,
    RecordOutcome,
    StaleTarget,
    TableLimits,
)
from agentask.application.services.observation import resolve_target
from agentask.domain.observation import ObservedControl
from agentask.domain.targeting import Outcome, TargetSpec
from agentask.infrastructure.browser.playwright_factory import (
    PlaywrightContextFactory,
    PlaywrightContextHandle,
)
from tests.integration.browser.helpers import login
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
REG = AdapterRegistry.default()
LIMITS = TableLimits(max_pages=20, max_rows=1000, no_progress_limit=3)


@pytest.fixture
async def handle(factory: PlaywrightContextFactory, lab: LabServer) -> PlaywrightContextHandle:
    h = await factory.create_context("ayse")
    await login(h, lab)
    return h


async def target(handle: PlaywrightContextHandle, **spec: object) -> ObservedControl:
    result = await resolve_target(handle.observer, TargetSpec.model_validate(spec))
    assert result.outcome is Outcome.RESOLVED, result.to_dict()
    snapshot = handle.observer.current_snapshot
    assert snapshot is not None and result.candidate_id is not None
    control = snapshot.control(result.candidate_id)
    assert control is not None
    return control


async def test_textbox_write_verify_and_no_change(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    await handle.navigate(f"{lab.primary}/pages/duplicates")
    field = await target(handle, kind="textbox", labels=["Müşteri No"], region="Kefil")
    adapter = REG.for_control(field)
    first = await adapter.ensure_value(handle.driver, field, "00123")
    assert first.changed and first.observed == "00123"
    guarantor = handle.page.get_by_role("region", name="Kefil").get_by_label("Müşteri No")
    assert await guarantor.input_value() == "00123"
    assert (
        await handle.page.get_by_role("region", name="Başvuran").get_by_label("Müşteri No").input_value()
        == ""
    )

    events = await handle.page.evaluate("""() => { window.__inputs = 0;
        document.addEventListener('input', () => window.__inputs++, true); return true; }""")
    assert events
    again = await adapter.ensure_value(handle.driver, field, "00123")
    assert again.changed is False
    assert await handle.page.evaluate("window.__inputs") == 0


async def test_native_and_custom_dropdown(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    await handle.navigate(f"{lab.primary}/pages/dropdowns")
    branch = await target(handle, kind="select", labels=["Şube"])
    assert (await REG.for_control(branch).ensure_choice(handle.driver, branch, "konak")).changed
    assert await handle.page.get_by_label("Şube").input_value() == "konak"
    branch = await target(handle, kind="select", labels=["Şube"])
    assert not (await REG.for_control(branch).ensure_choice(handle.driver, branch, "Konak")).changed
    with pytest.raises(ChoiceNotAvailable):
        await REG.for_control(branch).ensure_choice(handle.driver, branch, "Kon")

    combo = await target(handle, kind="combobox", labels=["Ürün Tipi"])
    adapter = REG.for_control(combo)
    assert adapter.name == "custom_combobox"
    result = await adapter.ensure_choice(handle.driver, combo, "Ticari Kart")
    assert result.changed and result.observed == "Ticari Kart"
    ui = handle.page.get_by_role("combobox", name="Ürün Tipi")
    assert await ui.get_attribute("aria-expanded") == "false"
    assert not (await adapter.ensure_choice(handle.driver, combo, "ticari kart")).changed
    with pytest.raises(ChoiceNotAvailable):
        await adapter.ensure_choice(handle.driver, combo, "Altın Kart")
    assert await ui.get_attribute("aria-expanded") == "false"
    assert "Ticari Kart" in await ui.inner_text()


async def test_tab_activation_verified(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    await handle.navigate(f"{lab.primary}/pages/dropdowns")
    tab = await target(handle, kind="tab", labels=["Teslimat"])
    result = await REG.for_control(tab).activate_tab(handle.driver, tab)
    assert result.changed
    assert await handle.page.get_by_role("tab", name="Teslimat").get_attribute("aria-selected") == "true"
    assert await handle.page.get_by_label("Teslimat Adresi").is_visible()
    tab = await target(handle, kind="tab", labels=["Teslimat"])
    assert not (await REG.for_control(tab).activate_tab(handle.driver, tab)).changed


async def test_find_record_paged_by_business_key(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    lab.set_scenario(table_rows=35, page_size=10)
    await handle.navigate(f"{lab.primary}/pages/table-paged")
    table = await target(handle, kind="table", labels=["Başvurular"])

    async def relocate(_: ObservedControl) -> ObservedControl:
        # Yürütücü yeniden bulmayı hedef hazır olana dek bekler (`_resolve`); bu yardımcı beklemediği için
        # Firefox'ta sayfa yeni yüklenirken tablo "görünür değil" çıkabiliyordu. Aynı bekleme eklendi.
        await handle.page.get_by_role("table", name="Başvurular").wait_for()
        return await target(handle, kind="table", labels=["Başvurular"])

    found = await REG.for_control(table).find_record(
        handle.driver, table, "B-1027", "paged", ["Sonraki"], None, LIMITS, relocate
    )
    assert found.outcome is RecordOutcome.FOUND and found.pages_visited == 3
    assert "Sayfa 3 / 4" in await handle.page.inner_text("body")
    row_button = await target(handle, kind="button", labels=["Aç"], row_key="B-1027")
    assert row_button.contexts[0].key == "B-1027"

    await handle.navigate(f"{lab.primary}/pages/table-paged")
    table = await target(handle, kind="table", labels=["Başvurular"])
    missing = await REG.for_control(table).find_record(
        handle.driver, table, "B-9999", "paged", ["Sonraki"], None, LIMITS, relocate
    )
    assert missing.outcome is RecordOutcome.NOT_FOUND_AT_END and missing.pages_visited == 4
    await handle.navigate(f"{lab.primary}/pages/table-paged")
    table = await target(handle, kind="table", labels=["Başvurular"])
    limited = await REG.for_control(table).find_record(
        handle.driver,
        table,
        "B-1034",
        "paged",
        ["Sonraki"],
        None,
        TableLimits(max_pages=2, max_rows=1000, no_progress_limit=3),
        relocate,
    )
    assert limited.outcome is RecordOutcome.LIMIT_REACHED


async def test_find_record_scroll_by_business_key(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    lab.set_scenario(table_rows=50, scroll_batch=15)
    await handle.navigate(f"{lab.primary}/pages/table-scroll")
    await handle.page.get_by_role("table", name="Hareketler").locator("tbody tr").nth(14).wait_for()
    table = await target(handle, kind="table", labels=["Hareketler"])

    async def same(c: ObservedControl) -> ObservedControl:
        return c

    found = await REG.for_control(table).find_record(
        handle.driver, table, "B-1042", "scroll", [], "Tüm kayıtlar yüklendi", LIMITS, same
    )
    assert found.outcome is RecordOutcome.FOUND
    missing = await REG.for_control(table).find_record(
        handle.driver, table, "B-2000", "scroll", [], "Tüm kayıtlar yüklendi", LIMITS, same
    )
    assert missing.outcome is RecordOutcome.NOT_FOUND_AT_END
    capped = await REG.for_control(table).find_record(
        handle.driver,
        table,
        "B-2000",
        "scroll",
        [],
        "Tüm kayıtlar yüklendi",
        TableLimits(max_pages=1, max_rows=20, no_progress_limit=3),
        same,
    )
    assert capped.outcome is RecordOutcome.LIMIT_REACHED


async def test_unsupported_controls_are_explicit(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    await handle.navigate(f"{lab.primary}/pages/sensitive")
    password = await target(handle, kind="textbox", labels=["Kullanıcı Parolası"])
    with pytest.raises(ControlUnsupported, match="sensitive"):
        REG.for_control(password)
    await handle.page.evaluate("""() => {
        const i = document.createElement('input'); i.setAttribute('role', 'combobox');
        i.setAttribute('aria-label', 'Arama Kutusu'); document.body.appendChild(i); }""")
    combo = await target(handle, kind="combobox", labels=["Arama Kutusu"])
    with pytest.raises(ControlUnsupported, match="input_combobox"):
        REG.for_control(combo)


async def test_driver_refuses_stale_candidate(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    await handle.navigate(f"{lab.primary}/pages/duplicates")
    field = await target(handle, kind="textbox", labels=["Müşteri No"], region="Kefil")
    await handle.page.reload()
    with pytest.raises(StaleTarget):
        await REG.for_control(field).ensure_value(handle.driver, field, "1")
