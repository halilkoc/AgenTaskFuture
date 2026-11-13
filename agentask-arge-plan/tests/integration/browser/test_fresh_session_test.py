"""R2: Yeni oturum testi varsayılan sınırlarla, geçici doğrulama oturumunda; ana oturum ve diğer
kullanıcılar korunur."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from agentask.application.controls import AdapterRegistry
from agentask.application.errors import NavigationNotAllowed
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.designer import DesignerService
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.observation import ObservationService
from agentask.application.services.runs import RunService
from agentask.config import Settings
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer
from tests.unit.test_publishing import ready_draft

pytestmark = pytest.mark.browser


def limits_from(settings: Settings) -> SessionLimits:
    return SessionLimits(
        settings.browser_max_sessions,
        settings.browser_max_sessions_per_user,
        settings.browser_session_idle_seconds,
        settings.browser_max_verification_sessions_per_user,
    )


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[dict[str, Any]]:
    settings = lab_settings(
        make_env_file, lab, READINESS_TIMEOUT_MS="2000"
    )  # oturum sınırları .env.example varsayılanı
    assert settings.browser_max_sessions_per_user == 1
    sessions = BrowserSessionService(PlaywrightContextFactory(settings), limits_from(settings))
    run_repo = LocalFileRunRepository(tmp_path / "runs")
    runs = RunService(
        run_repo,
        sessions,
        Executor(run_repo, LAB_ACTION_SET, AdapterRegistry.default(), ExecutorConfig.from_settings(settings)),
        LAB_ACTION_SET,
        100,
    )
    drafts = LocalFileDraftRepository(tmp_path / "drafts")
    designer = DesignerService(drafts, sessions, ObservationService(sessions, 2000), runs, LAB_ACTION_SET, 30)
    d = ready_draft(drafts, "kefil_musteri_no", "Kefil")
    d.fresh_test = None
    drafts.update(d, d.revision)
    main = await sessions.open("ayse")
    other = await sessions.open("mehmet")
    lab.reset()
    yield {
        "designer": designer,
        "sessions": sessions,
        "draft": drafts.get(d.draft_id),
        "main": main,
        "other": other,
        "lab": lab,
        "drafts": drafts,
    }
    await runs.shutdown()
    await sessions.shutdown()


def entry(lab: LabServer, path: str) -> str:
    return f"{lab.primary}/__lab/autologin?user=ayse&next={path}"


async def test_fresh_test_with_default_limits_keeps_main_and_other_sessions(env: dict[str, Any]) -> None:
    designer, sessions, d, lab = env["designer"], env["sessions"], env["draft"], env["lab"]
    main_handle = sessions.peek("ayse", env["main"].session_id)
    await main_handle.navigate(entry(lab, "/pages/dropdowns"))
    result = await designer.fresh_session_test(
        "ayse", d.draft_id, d.revision, {"no": "00777"}, entry(lab, "/pages/duplicates")
    )
    assert result.fresh_test is not None and result.fresh_test.passed
    assert [v.session_id for v in sessions.list("ayse")] == [env["main"].session_id]  # geçici oturum kapandı
    assert [v.session_id for v in sessions.list("mehmet")] == [env["other"].session_id]
    assert main_handle.current_url.endswith("/pages/dropdowns")  # ana tasarım oturumu dokunulmadı
    await main_handle.navigate(entry(lab, "/pages/duplicates"))
    region = main_handle.page.get_by_role("region", name="Kefil")  # type: ignore[attr-defined]
    assert await region.get_by_label("Müşteri No").input_value() == ""  # test ana oturumda çalışmadı


async def test_failed_navigation_closes_temporary_session(env: dict[str, Any]) -> None:
    designer, sessions, d = env["designer"], env["sessions"], env["draft"]
    with pytest.raises(NavigationNotAllowed):
        await designer.fresh_session_test("ayse", d.draft_id, d.revision, {"no": "1"}, "http://127.0.0.1:1/")
    assert [v.purpose for v in sessions.list("ayse")] == ["interactive"]
    stored = env["drafts"].get(d.draft_id)
    assert stored is not None and stored.fresh_test is None


async def test_failing_operation_records_failure_and_cleans_up(env: dict[str, Any]) -> None:
    designer, sessions, d, lab = env["designer"], env["sessions"], env["draft"], env["lab"]
    result = await designer.fresh_session_test(
        "ayse", d.draft_id, d.revision, {"no": "1"}, entry(lab, "/pages/note-form")
    )  # hedef bu ekranda yok
    assert result.fresh_test is not None and result.fresh_test.passed is False
    assert [v.purpose for v in sessions.list("ayse")] == ["interactive"]


async def test_timeout_cancels_run_and_cleans_up(env: dict[str, Any]) -> None:
    sessions, d, lab, old = env["sessions"], env["draft"], env["lab"], env["designer"]
    # Run bekleme süresi (0.3 sn) hazır olma beklemesinden (2 sn) kısa: süre dolduğunda run hâlâ sürüyor.
    designer = DesignerService(env["drafts"], sessions, old.observation, old._runs, LAB_ACTION_SET, 0.3)
    result = await designer.fresh_session_test(
        "ayse", d.draft_id, d.revision, {"no": "1"}, entry(lab, "/pages/note-form")
    )  # hedef bu ekranda yok
    assert result.fresh_test is not None and result.fresh_test.passed is False
    assert [v.purpose for v in sessions.list("ayse")] == ["interactive"]
