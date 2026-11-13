"""ObservationService ile uçtan uca hedef çözümü — gerçek Chromium + deney uygulaması (T01–T05, T23)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import pytest

from agentask.application.errors import CandidateStale, NavigationNotAllowed
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.observation import ObservationService
from agentask.domain.targeting import Outcome, TargetSpec
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings, login
from tests.support_lab import HitCounterServer, LabServer

pytestmark = pytest.mark.browser
OWNER = "ayse"


async def _service(factory: PlaywrightContextFactory, lab: LabServer) -> tuple[ObservationService, str]:
    sessions = BrowserSessionService(factory, SessionLimits(max_sessions=2, max_per_user=1, idle_seconds=600))
    service = ObservationService(sessions, picker_wait_max_ms=5000)
    view = await sessions.open(OWNER)
    handle = sessions.peek(OWNER, view.session_id)
    await login(handle, lab)  # type: ignore[arg-type]
    return service, view.session_id


@pytest.fixture
async def svc(
    factory: PlaywrightContextFactory, lab: LabServer
) -> AsyncIterator[tuple[ObservationService, str]]:
    yield await _service(factory, lab)


def spec(**kw: object) -> TargetSpec:
    return TargetSpec.model_validate(kw)


async def _goto_frames(service: ObservationService, sid: str, lab: LabServer, late_ms: int = 30_000) -> None:
    lab.set_scenario(late_frame_delay_ms=late_ms)
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/frames")
    page = service.sessions.peek(OWNER, sid).page  # type: ignore[attr-defined]
    await (
        page.frame_locator("iframe[title='Vaka Ayrıntıları']")
        .frame_locator("iframe[title='Adres Bilgileri']")
        .get_by_label("Adres")
        .wait_for()
    )
    await (
        page.frame_locator("iframe[title='Müşteri Kaydı (dış sistem)']").get_by_label("Müşteri No").wait_for()
    )


async def test_deep_nested_frame_field_is_resolved(
    svc: tuple[ObservationService, str], lab: LabServer
) -> None:
    service, sid = svc
    await _goto_frames(service, sid, lab)
    result = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Adres"]))
    assert result.outcome is Outcome.RESOLVED, result.to_dict()
    [cand] = result.candidates
    assert cand.frame_titles == ("Vaka Ayrıntıları", "Adres Bilgileri")
    assert result.coverage.overall.value == "complete"
    assert result.snapshot_revision


async def test_frame_title_scopes_cross_origin_duplicate(
    svc: tuple[ObservationService, str], lab: LabServer
) -> None:
    service, sid = svc
    await _goto_frames(service, sid, lab)
    result = await service.resolve(
        OWNER, sid, spec(kind="textbox", labels=["Müşteri No"], frame_title="Müşteri Kaydı (dış sistem)")
    )
    assert result.outcome is Outcome.RESOLVED


async def test_late_frame_not_found_then_resolved(
    svc: tuple[ObservationService, str], lab: LabServer
) -> None:
    service, sid = svc
    await _goto_frames(service, sid, lab, late_ms=1500)
    early = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Belge No"]))
    assert early.outcome is Outcome.UNRESOLVED and early.reason == "not_found"
    page = service.sessions.peek(OWNER, sid).page  # type: ignore[attr-defined]
    await page.frame_locator("iframe[title='Ek Belgeler']").get_by_label("Belge No").wait_for()
    late = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Belge No"]))
    assert late.outcome is Outcome.RESOLVED
    assert late.candidates[0].frame_titles == ("Ek Belgeler",)


async def test_reloaded_frame_candidate_is_stale_and_re_resolves(
    svc: tuple[ObservationService, str], lab: LabServer
) -> None:
    service, sid = svc
    await _goto_frames(service, sid, lab)
    first = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Adres"]))
    assert first.candidate_id is not None
    page = service.sessions.peek(OWNER, sid).page  # type: ignore[attr-defined]
    level1 = next(f for f in page.frames if "/frames/level1" in f.url)
    async with page.expect_event("framenavigated"):
        await level1.evaluate("location.reload()")
    with pytest.raises(CandidateStale) as exc:
        await service.highlight(OWNER, sid, first.candidate_id)
    assert exc.value.details["reason"] == "frame_changed"
    await (
        page.frame_locator("iframe[title='Vaka Ayrıntıları']")
        .frame_locator("iframe[title='Adres Bilgileri']")
        .get_by_label("Adres")
        .wait_for()
    )
    second = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Adres"]))
    assert second.outcome is Outcome.RESOLVED and second.candidate_id != first.candidate_id


async def test_same_named_controls_distinguished_by_context(
    svc: tuple[ObservationService, str], lab: LabServer
) -> None:
    service, sid = svc
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/duplicates")
    guarantor = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Müşteri No"], region="Kefil"))
    applicant = await service.resolve(
        OWNER, sid, spec(kind="textbox", labels=["Müşteri No"], region="Başvuran")
    )
    assert guarantor.outcome is Outcome.RESOLVED and applicant.outcome is Outcome.RESOLVED
    assert guarantor.candidates[0].contexts[0]["name"] == "Kefil"
    assert applicant.candidates[0].contexts[0]["name"] == "Başvuran"
    save = await service.resolve(OWNER, sid, spec(kind="button", labels=["Kaydet"], region="Kefil"))
    assert save.outcome is Outcome.RESOLVED


async def test_insufficient_context_is_ambiguous(svc: tuple[ObservationService, str], lab: LabServer) -> None:
    service, sid = svc
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/duplicates")
    result = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Müşteri No"]))
    assert result.outcome is Outcome.AMBIGUOUS and result.candidate_id is None
    assert sorted(c.contexts[0]["name"] for c in result.candidates) == ["Başvuran", "Kefil"]


async def test_table_row_key_disambiguates(svc: tuple[ObservationService, str], lab: LabServer) -> None:
    service, sid = svc
    lab.set_scenario(table_rows=5, page_size=10)
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/table-paged")
    any_row = await service.resolve(OWNER, sid, spec(kind="button", labels=["Aç"]))
    assert any_row.outcome is Outcome.AMBIGUOUS and len(any_row.candidates) == 5
    row = await service.resolve(OWNER, sid, spec(kind="button", labels=["Aç"], row_key="B-1003"))
    assert row.outcome is Outcome.RESOLVED


async def test_resolved_again_after_ids_change(svc: tuple[ObservationService, str], lab: LabServer) -> None:
    service, sid = svc
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/duplicates")
    target = spec(kind="textbox", labels=["Müşteri No"], region="Kefil")
    before = await service.resolve(OWNER, sid, target)
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/duplicates")
    after = await service.resolve(OWNER, sid, target)
    assert before.outcome is after.outcome is Outcome.RESOLVED
    assert before.candidate_id != after.candidate_id
    with pytest.raises(CandidateStale):
        assert before.candidate_id is not None
        await service.highlight(OWNER, sid, before.candidate_id)
    assert after.candidate_id is not None
    await service.highlight(OWNER, sid, after.candidate_id)


async def test_partial_scan_keeps_coverage(make_env_file: EnvFileFactory, lab: LabServer) -> None:
    factory = PlaywrightContextFactory(lab_settings(make_env_file, lab, FRAME_SCAN_MAX_ELEMENTS="50"))
    try:
        service, sid = await _service(factory, lab)
        lab.set_scenario(heavy_fields=200)
        await service.navigate(OWNER, sid, f"{lab.primary}/pages/heavy")
        beyond = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Alan 150"]))
        assert beyond.outcome is Outcome.UNRESOLVED and beyond.reason == "coverage_incomplete"
        assert beyond.coverage.incomplete[0].reason == "element_limit"
        within = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Alan 10"]))
        assert within.outcome is Outcome.UNRESOLVED and within.reason == "coverage_incomplete"
        assert len(within.candidates) == 1
    finally:
        await factory.shutdown()


async def test_inaccessible_frame_prevents_not_found(
    svc: tuple[ObservationService, str], lab: LabServer, outsider: HitCounterServer
) -> None:
    service, sid = svc
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/duplicates")
    page = service.sessions.peek(OWNER, sid).page  # type: ignore[attr-defined]
    async with page.expect_event("frameattached"):
        await page.evaluate(
            "o => { const f = document.createElement('iframe'); f.src = o; document.body.appendChild(f); }",
            outsider.origin,
        )
    await page.wait_for_timeout(500)
    missing = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Olmayan Alan"]))
    assert missing.outcome is Outcome.UNRESOLVED and missing.reason == "coverage_incomplete"
    assert missing.coverage.incomplete[0].status.value == "inaccessible"


async def test_sensitive_target_resolves_without_values(
    svc: tuple[ObservationService, str], lab: LabServer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    service, sid = svc
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/sensitive")
    page = service.sessions.peek(OWNER, sid).page  # type: ignore[attr-defined]
    await page.get_by_label("Kullanıcı Parolası").fill("Gizli-Parola-123")
    result = await service.resolve(OWNER, sid, spec(kind="textbox", labels=["Kullanıcı Parolası"]))
    assert result.outcome is Outcome.RESOLVED
    assert result.candidate_id is not None
    await service.highlight(OWNER, sid, result.candidate_id)
    snapshot = await service.observe(OWNER, sid)
    assert "Gizli-Parola-123" not in str(result.to_dict()) + str(snapshot) + caplog.text


async def test_navigation_policy_applies(
    svc: tuple[ObservationService, str], outsider: HitCounterServer
) -> None:
    service, sid = svc
    with pytest.raises(NavigationNotAllowed):
        await service.navigate(OWNER, sid, outsider.origin)
