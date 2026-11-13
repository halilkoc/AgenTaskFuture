"""Yeni oturum testinde elle giriş: yeniden doğrulama, devam, süre aşımı, vazgeçme, tekrar oynatmama."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentask.application.errors import DraftNotReady, SessionBusy
from agentask.application.services import designer as designer_module
from agentask.application.services.designer import DesignerService
from agentask.domain.actions import ActionSet, AppProfile
from agentask.domain.runtime import RunStatus
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from tests.unit.test_component_publishing import component_draft, make_ready

OWNER = "ayse"


@dataclass
class Sessions:
    path: str = "/login"
    opened: list[str] = field(default_factory=list)
    closed: list[str] = field(default_factory=list)
    alive: bool = True

    async def open(self, owner: str, purpose: str) -> Any:
        assert purpose == "verification"
        self.opened.append(owner)
        return SimpleNamespace(session_id=f"v{len(self.opened)}")

    async def close_verification(self, owner: str, sid: str) -> None:
        self.closed.append(sid)

    def is_open(self, owner: str, sid: str) -> bool:
        return self.alive

    @asynccontextmanager
    async def operation(self, *_: Any, **__: Any) -> AsyncIterator[Any]:
        async def current_path() -> str:
            return self.path

        async def navigate(_: str) -> None:
            return None

        yield SimpleNamespace(
            navigate=navigate, observer=None, driver=SimpleNamespace(current_path=current_path)
        )


@dataclass
class Runs:
    results: list[Any] = field(default_factory=list)
    created: list[Any] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)
    cancelled: list[tuple[str, str]] = field(default_factory=list)

    async def create(self, owner: str, sid: str, request_id: str, commands: Any, **_: Any) -> Any:
        self.created.append(commands)
        return SimpleNamespace(run_id="run-1")

    async def wait(self, run_id: str, timeout: float) -> Any:
        return self.results.pop(0)

    async def resume(self, owner: str, run_id: str, sid: str, allow_verification: bool = False) -> Any:
        assert allow_verification
        self.resumed.append(run_id)

    async def cancel(self, owner: str, run_id: str, by: str = "user") -> Any:
        self.cancelled.append((run_id, by))


def finished(status: RunStatus, reason: str | None = None) -> Any:
    return SimpleNamespace(
        run_id="run-1",
        status=status,
        status_reason=reason,
        is_terminal=status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED},
    )


@dataclass
class Env:
    service: DesignerService
    sessions: Sessions
    runs: Runs
    draft_id: str
    screen: dict[str, bool]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    repo = LocalFileDraftRepository(tmp_path / "d")
    draft = component_draft()
    draft.parameters = []
    draft.steps[0].value_template = "sabit"
    draft.created_by = OWNER
    make_ready(draft)
    draft.fresh_test = None
    repo.create(draft)
    sessions, runs = Sessions(), Runs()
    actions = ActionSet(profile=AppProfile(session_lost_path_prefixes=["/login"]))
    service = DesignerService(repo, sessions, None, runs, actions, 5.0, fresh_login_timeout_s=100)  # type: ignore[arg-type]
    screen = {"recognized": False}

    async def assess(_: Any, __: Any) -> Any:
        return SimpleNamespace(recognized=screen["recognized"])

    monkeypatch.setattr(designer_module, "assess_screen", assess)
    return Env(service, sessions, runs, draft.draft_id, screen)


async def begin(env: Env) -> Any:
    return await env.service.begin_fresh_test(OWNER, env.draft_id, {}, "https://uygulama/")


async def test_waits_when_login_needed_and_runs_after_revalidation(env: Env) -> None:
    draft = await begin(env)
    assert env.service.fresh_wait(draft)["message"] and not env.runs.created and draft.fresh_test is None
    # Giriş yapılmadan devam: işlem başlamaz.
    draft = await env.service.continue_fresh_test(OWNER, env.draft_id)
    assert "giriş ekranında" in env.service.fresh_wait(draft)["message"] and not env.runs.created
    # Giriş yapıldı ama ekran yanlış: yine başlamaz.
    env.sessions.path = "/ana"
    draft = await env.service.continue_fresh_test(OWNER, env.draft_id)
    assert "görünmüyor" in env.service.fresh_wait(draft)["message"] and not env.runs.created
    env.screen["recognized"] = True
    env.runs.results = [finished(RunStatus.COMPLETED)]
    draft = await env.service.continue_fresh_test(OWNER, env.draft_id)
    assert draft.fresh_test.passed and len(env.runs.created) == 1
    assert env.service.fresh_wait(draft) is None and env.sessions.closed == ["v1"]


async def test_no_wait_when_screen_already_open(env: Env) -> None:
    env.sessions.path, env.screen["recognized"] = "/ana", True
    env.runs.results = [finished(RunStatus.COMPLETED)]
    draft = await begin(env)
    assert draft.fresh_test.passed and env.service.fresh_wait(draft) is None


async def test_login_lost_midway_resumes_without_new_run(env: Env) -> None:
    env.sessions.path, env.screen["recognized"] = "/ana", True
    env.runs.results = [finished(RunStatus.PAUSED_SESSION, "SESSION_EXPIRED")]
    draft = await begin(env)
    wait = env.service.fresh_wait(draft)
    assert wait["resuming"] and "tekrar yapılmaz" in wait["message"] and draft.fresh_test is None
    env.runs.results = [finished(RunStatus.COMPLETED)]
    draft = await env.service.continue_fresh_test(OWNER, env.draft_id)
    assert env.runs.resumed == ["run-1"] and len(env.runs.created) == 1 and draft.fresh_test.passed


async def test_timeout_and_cancel_write_no_result(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    await begin(env)
    wait = env.service._fresh_waits[env.draft_id]
    wait.expires_at = 0
    with pytest.raises(DraftNotReady, match="süresi doldu"):
        await env.service.continue_fresh_test(OWNER, env.draft_id)
    assert env.sessions.closed == ["v1"]
    await begin(env)
    env.service._fresh_waits[env.draft_id].expires_at = 0
    assert await env.service.reap_fresh_waits() == 1
    draft = await begin(env)
    draft = await env.service.cancel_fresh_test(OWNER, env.draft_id)
    assert draft.fresh_test is None and env.service.fresh_wait(draft) is None and not env.runs.created


async def test_cancel_after_midway_loss_is_user_cancel(env: Env) -> None:
    env.sessions.path, env.screen["recognized"] = "/ana", True
    env.runs.results = [finished(RunStatus.PAUSED_SESSION, "SESSION_EXPIRED")]
    await begin(env)
    await env.service.cancel_fresh_test(OWNER, env.draft_id)
    assert env.runs.cancelled == [("run-1", "user")]


async def test_changed_draft_invalidates_wait(env: Env) -> None:
    draft = await begin(env)
    env.service.update_meta(OWNER, env.draft_id, draft.revision, title="Değişti")
    with pytest.raises(DraftNotReady, match="değişti"):
        await env.service.continue_fresh_test(OWNER, env.draft_id)
    assert not env.runs.created


async def test_other_owner_and_double_continue_refused(env: Env) -> None:
    await begin(env)
    env.service._fresh_waits[env.draft_id].busy = True
    with pytest.raises(SessionBusy):
        await env.service.continue_fresh_test(OWNER, env.draft_id)
    from agentask.application.errors import DraftNotFound

    with pytest.raises(DraftNotFound):
        await env.service.continue_fresh_test("baskasi", env.draft_id)
