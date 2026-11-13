"""FrameTracker + bütçeli anlamsal envanter, gerçek Chromium ve deney uygulamasıyla (T01, T03, T04, T23)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

import pytest

from agentask.domain.observation import ControlKind, ScanStatus, Snapshot
from agentask.infrastructure.browser.playwright_factory import (
    PlaywrightContextFactory,
    PlaywrightContextHandle,
)
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings, login
from tests.support_lab import HitCounterServer, LabServer

pytestmark = pytest.mark.browser


@pytest.fixture
async def handle(factory: PlaywrightContextFactory, lab: LabServer) -> PlaywrightContextHandle:
    h = await factory.create_context("ayse")
    await login(h, lab)
    return h


def by_label(snapshot: Snapshot, label: str, kind: ControlKind | None = None) -> list:  # type: ignore[type-arg]
    return [c for c in snapshot.controls if c.label == label and (kind is None or c.kind is kind)]


async def test_deep_nested_and_cross_origin_frames(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    lab.set_scenario(late_frame_delay_ms=30_000)
    await handle.navigate(f"{lab.primary}/pages/frames")
    await (
        handle.page.frame_locator("iframe[title='Vaka Ayrıntıları']")
        .frame_locator("iframe[title='Adres Bilgileri']")
        .get_by_label("Adres")
        .wait_for()
    )
    await (
        handle.page.frame_locator("iframe[title='Müşteri Kaydı (dış sistem)']")
        .get_by_label("Müşteri No")
        .wait_for()
    )
    snapshot = await handle.observer.observe()

    [address] = by_label(snapshot, "Adres")
    assert address.frame_titles == ("Vaka Ayrıntıları", "Adres Bilgileri")
    frame = snapshot.frame(address.frame_ref)
    assert frame is not None and frame.depth == 2 and frame.status is ScanStatus.COMPLETE
    [external] = by_label(snapshot, "Müşteri No")
    ext_frame = snapshot.frame(external.frame_ref)
    assert ext_frame is not None and ext_frame.origin == lab.secondary
    assert all(f.status is ScanStatus.COMPLETE for f in snapshot.frames)
    assert len(snapshot.frames) == 4


async def test_late_frame_is_tracked(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    lab.set_scenario(late_frame_delay_ms=700)
    await handle.navigate(f"{lab.primary}/pages/frames")
    first = await handle.observer.observe()
    revision_before = handle.observer.tree_revision
    assert not by_label(first, "Belge No")
    await handle.page.frame_locator("iframe[title='Ek Belgeler']").get_by_label("Belge No").wait_for()
    assert handle.observer.tree_revision != revision_before
    second = await handle.observer.observe()
    [late] = by_label(second, "Belge No")
    assert late.frame_titles == ("Ek Belgeler",)
    assert second.revision != first.revision


async def test_frame_reload_invalidates_only_subtree(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    lab.set_scenario(late_frame_delay_ms=30_000)
    await handle.navigate(f"{lab.primary}/pages/frames")
    await (
        handle.page.frame_locator("iframe[title='Vaka Ayrıntıları']")
        .frame_locator("iframe[title='Adres Bilgileri']")
        .get_by_label("Adres")
        .wait_for()
    )
    snapshot = await handle.observer.observe()
    [address] = by_label(snapshot, "Adres")  # level2 (level1'in çocuğu)
    [status] = by_label(snapshot, "Vaka Durumu")  # level1
    [external] = by_label(snapshot, "Müşteri No")  # kardeş, dış origin
    for c in (address, status, external):
        assert await handle.observer.check_candidate(c.candidate_id) is None

    level1 = next(f for f in handle.page.frames if "/frames/level1" in f.url)
    async with handle.page.expect_event("framenavigated"):
        await level1.evaluate("location.reload()")
    assert await handle.observer.check_candidate(status.candidate_id) == "frame_changed"
    assert await handle.observer.check_candidate(address.candidate_id) == "frame_changed"
    assert await handle.observer.check_candidate(external.candidate_id) is None


async def test_new_snapshot_supersedes_old_candidates(
    handle: PlaywrightContextHandle, lab: LabServer
) -> None:
    await handle.navigate(f"{lab.primary}/pages/duplicates")
    old = await handle.observer.observe()
    await handle.observer.observe()
    assert await handle.observer.check_candidate(old.controls[0].candidate_id) == "snapshot_superseded"


async def test_rerender_detected_as_detached_or_changed(
    handle: PlaywrightContextHandle, lab: LabServer
) -> None:
    await handle.navigate(f"{lab.primary}/pages/duplicates")
    snapshot = await handle.observer.observe()
    applicant, guarantor = by_label(snapshot, "Müşteri No")
    await handle.page.evaluate("""() => {
        const sections = document.querySelectorAll('section');
        sections[0].replaceWith(sections[0].cloneNode(true));
        sections[1].querySelector('h2').textContent = 'Müşteri';
    }""")
    assert await handle.observer.check_candidate(applicant.candidate_id) == "element_detached"
    assert await handle.observer.check_candidate(guarantor.candidate_id) == "element_changed"


async def test_same_semantics_after_ids_change(handle: PlaywrightContextHandle, lab: LabServer) -> None:
    def semantic(s: Snapshot) -> list[tuple[str, str | None, tuple[str | None, ...]]]:
        return sorted(
            (c.kind.value, c.label or c.accessible_name, tuple(x.name for x in c.contexts))
            for c in s.controls
        )

    await handle.navigate(f"{lab.primary}/pages/duplicates")
    first_ids = await handle.page.locator("[id]").evaluate_all("els => els.map(e => e.id)")
    first = await handle.observer.observe()
    await handle.page.reload()
    second_ids = await handle.page.locator("[id]").evaluate_all("els => els.map(e => e.id)")
    second = await handle.observer.observe()
    assert set(first_ids).isdisjoint(second_ids)
    assert semantic(first) == semantic(second)
    assert {c.candidate_id for c in first.controls}.isdisjoint({c.candidate_id for c in second.controls})


async def test_inventory_records_kind_context_and_state(
    handle: PlaywrightContextHandle, lab: LabServer
) -> None:
    lab.set_scenario(table_rows=3, page_size=10)
    await handle.navigate(f"{lab.primary}/pages/table-paged")
    snapshot = await handle.observer.observe()
    [table] = [c for c in snapshot.controls if c.kind is ControlKind.TABLE]
    assert table.accessible_name == "Başvurular"
    buttons = [c for c in snapshot.controls if c.kind is ControlKind.BUTTON and c.accessible_name == "Aç"]
    assert [next(x.key for x in b.contexts if x.kind == "table_row") for b in buttons] == [
        "B-1000",
        "B-1001",
        "B-1002",
    ]
    assert all(next(x.name for x in b.contexts if x.kind == "table_row") == "Başvurular" for b in buttons)

    await handle.navigate(f"{lab.primary}/pages/dropdowns")
    await handle.page.get_by_label("Şube").select_option(label="Konak")
    snapshot = await handle.observer.observe()
    [branch] = by_label(snapshot, "Şube", ControlKind.SELECT)
    assert branch.selected_text == "Konak" and "Kadıköy" in branch.options
    [combo] = [c for c in snapshot.controls if c.kind is ControlKind.COMBOBOX]
    assert combo.accessible_name == "Ürün Tipi"
    tabs = [c for c in snapshot.controls if c.kind is ControlKind.TAB]
    assert [t.accessible_name for t in tabs] == ["Kart Bilgileri", "Teslimat"]
    [delivery] = by_label(snapshot, "Teslimat Adresi")
    assert delivery.visible is False
    assert any(x.kind == "tabpanel" and x.name == "Teslimat" for x in delivery.contexts)


async def test_sensitive_values_never_enter_snapshot_or_logs(
    handle: PlaywrightContextHandle, lab: LabServer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await handle.navigate(f"{lab.primary}/pages/sensitive")
    page = handle.page
    secrets_ = {
        "Kullanıcı Parolası": "Pa55-gizli-deger",
        "Tek Kullanımlık Kod": "908172",
        "Kart Güvenlik Kodu": "4417",
        "Açıklama": "normal-metin-degeri",
    }
    for label, value in secrets_.items():
        await page.get_by_label(label).fill(value)
    await page.get_by_label("Gizli Soru").select_option(label="İlk okulunuz")
    snapshot = await handle.observer.observe()
    dumped = json.dumps([asdict(c) for c in snapshot.controls], ensure_ascii=False) + caplog.text
    for value in [*secrets_.values(), "İlk okulunuz"]:
        assert value not in dumped
    sensitive = {c.label: c.sensitive for c in snapshot.controls if c.label}
    assert (
        sensitive["Kullanıcı Parolası"]
        and sensitive["Tek Kullanımlık Kod"]
        and sensitive["Kart Güvenlik Kodu"]
    )
    assert sensitive["Gizli Soru"] and not sensitive["Açıklama"]
    assert all(c.has_value for c in snapshot.controls if c.label in secrets_)
    assert "<input" not in caplog.text and "<section" not in caplog.text


async def test_element_limit_reports_partial(make_env_file: EnvFileFactory, lab: LabServer) -> None:
    factory = PlaywrightContextFactory(lab_settings(make_env_file, lab, FRAME_SCAN_MAX_ELEMENTS="20"))
    try:
        h = await factory.create_context("ayse")
        await login(h, lab)
        lab.set_scenario(heavy_fields=100)
        await h.navigate(f"{lab.primary}/pages/heavy")
        snapshot = await h.observer.observe()
        main = snapshot.frames[0]
        assert main.status is ScanStatus.PARTIAL and main.reason == "element_limit"
        assert len(snapshot.controls) == 20
    finally:
        await factory.shutdown()


async def test_frame_timeout_reports_timed_out(make_env_file: EnvFileFactory, lab: LabServer) -> None:
    factory = PlaywrightContextFactory(lab_settings(make_env_file, lab, FRAME_SCAN_TIMEOUT_MS="1"))
    try:
        h = await factory.create_context("ayse")
        await login(h, lab)
        lab.set_scenario(heavy_fields=3000)
        await h.navigate(f"{lab.primary}/pages/heavy")
        snapshot = await h.observer.observe()
        assert snapshot.frames[0].status is ScanStatus.TIMED_OUT
        assert snapshot.controls == ()
    finally:
        await factory.shutdown()


async def test_depth_and_frame_limits_report_not_scanned(
    make_env_file: EnvFileFactory, lab: LabServer
) -> None:
    factory = PlaywrightContextFactory(lab_settings(make_env_file, lab, FRAME_SCAN_MAX_DEPTH="1"))
    try:
        h = await factory.create_context("ayse")
        await login(h, lab)
        lab.set_scenario(late_frame_delay_ms=30_000)
        await h.navigate(f"{lab.primary}/pages/frames")
        await (
            h.page.frame_locator("iframe[title='Vaka Ayrıntıları']")
            .frame_locator("iframe[title='Adres Bilgileri']")
            .get_by_label("Adres")
            .wait_for()
        )
        snapshot = await h.observer.observe()
        deep = next(f for f in snapshot.frames if f.title == "Adres Bilgileri")
        assert deep.status is ScanStatus.NOT_SCANNED and deep.reason == "depth_limit"
        assert not by_label(snapshot, "Adres")
    finally:
        await factory.shutdown()


async def test_blocked_frame_reported_inaccessible(
    handle: PlaywrightContextHandle, lab: LabServer, outsider: HitCounterServer
) -> None:
    await handle.navigate(f"{lab.primary}/pages/duplicates")
    async with handle.page.expect_event("frameattached"):
        await handle.page.evaluate(
            "o => { const f = document.createElement('iframe'); f.title = 'Dış Kaynak'; f.src = o; "
            "document.body.appendChild(f); }",
            outsider.origin,
        )
    await handle.page.wait_for_timeout(500)
    snapshot = await handle.observer.observe()
    blocked = next(f for f in snapshot.frames if f.title == "Dış Kaynak")
    assert blocked.status is ScanStatus.INACCESSIBLE
    assert outsider.hits == []
    assert len(by_label(snapshot, "Müşteri No")) == 2
