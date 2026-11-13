"""Uygulama kapsamı (AUTOMATION_APPLICATIONS_JSON): katalog/plan/run seçilen uygulamayla sınırlı.

- Bilinmeyen uygulama reddedilir; başka uygulamaya sessizce düşülmez.
- Bir uygulamanın planı (release) başka uygulama seçiliyken kullanılamaz.
- Run, oturum seçilen uygulamanın origin'inde değilse başlamaz ve oturum kilidi bırakılır.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from agentask.application.errors import (
    ApplicationNotConfigured,
    ReleaseSuperseded,
    SessionApplicationMismatch,
)
from agentask.application.services.assistant import AssistantService
from agentask.application.services.publishing import PublishService
from agentask.application.services.runs import RunService
from agentask.domain.applications import ApplicationRegistry, AutomationApplication
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.fake_catalog_store import FakeCatalogStore
from tests.unit.test_publishing import ready_draft

LAB = AutomationApplication(id="lab", name="Deney", base_url="http://127.0.0.1:8100/")
OPERA = AutomationApplication(id="opera", name="Opera", base_url="https://opera.example.internal/giris")
REGISTRY = ApplicationRegistry([LAB, OPERA])


class FakeHandle:
    def __init__(self, url: str) -> None:
        self.current_url = url


class FakeSessions:
    def __init__(self, url: str) -> None:
        self.handle = FakeHandle(url)
        self.busy = False

    @asynccontextmanager
    async def operation(
        self, owner: str, sid: str, name: str, allow_verification: bool = False
    ) -> AsyncIterator[Any]:
        assert not self.busy, "oturum kilidi bırakılmamış"
        self.busy = True
        try:
            yield self.handle
        finally:
            self.busy = False


class RecordingRuns:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return "run"


async def _published(tmp: Path) -> tuple[PublishService, str]:
    drafts = LocalFileDraftRepository(tmp / "drafts")
    pub = PublishService(FakeCatalogStore(), drafts, LAB_ACTION_SET, "arge")
    d = ready_draft(drafts, "kefil_no", "Kefil no")
    d.record_fresh_test(run_id="run-fresh0001", passed=True)
    drafts.update(d, d.revision)
    d = pub.approve("pub", d.draft_id, d.revision)
    release = await pub.publish("pub", d.draft_id, "r1")
    return pub, release.release_id


def _assistant(pub: PublishService, runs: Any) -> AssistantService:
    return AssistantService(
        pub, runs, LAB_ACTION_SET, UnavailableLLM("kapalı"), 2000, 100, 1, "lab", applications=REGISTRY
    )


async def test_catalog_is_scoped_to_selected_application(tmp_path: Path) -> None:
    pub, _ = await _published(tmp_path)
    assistant = _assistant(pub, RecordingRuns())
    assert [o.operation_id for o in await assistant.catalog("lab")] == ["kefil_no"]
    # Yapılandırılmış ama yayını olmayan uygulama: boş katalog (lab yayınları ona bağlanmaz).
    assert await assistant.catalog("opera") == []
    with pytest.raises(ApplicationNotConfigured):
        await assistant.catalog("bilinmeyen")
    interp = await assistant.interpret("u", "Kefil no gir", application_id="opera")
    assert interp.status == "no_match" and interp.operation_id is None


async def test_plan_from_one_application_cannot_be_used_in_another(tmp_path: Path) -> None:
    pub, release_id = await _published(tmp_path)
    runs = RecordingRuns()
    assistant = _assistant(pub, runs)
    preview = await assistant.preview("u", release_id, "kefil_no", {"no": "1"}, application_id="lab")
    assert preview["application_id"] == "lab"
    with pytest.raises(ReleaseSuperseded):
        await assistant.preview("u", release_id, "kefil_no", {"no": "1"}, application_id="opera")
    with pytest.raises(ReleaseSuperseded):
        await assistant.execute(
            "u", "sid", release_id, "kefil_no", {"no": "1"}, "req-1", application_id="opera"
        )
    with pytest.raises(ApplicationNotConfigured):
        await assistant.execute(
            "u", "sid", release_id, "kefil_no", {"no": "1"}, "req-2", application_id="yok"
        )
    assert runs.calls == []


async def test_execute_pins_application_and_requires_its_origin(tmp_path: Path) -> None:
    pub, release_id = await _published(tmp_path)
    runs = RecordingRuns()
    assistant = _assistant(pub, runs)
    await assistant.execute("u", "sid", release_id, "kefil_no", {"no": "1"}, "req-1", application_id="lab")
    call = runs.calls[0]
    assert call["required_origin"] == "http://127.0.0.1:8100"
    assert call["binding"]["application_id"] == "lab"
    # İç kullanım (kimlik verilmeden) eski davranışı korur: origin şartı eklenmez.
    await assistant.execute("u", "sid", release_id, "kefil_no", {"no": "1"}, "req-2")
    assert runs.calls[1]["required_origin"] is None


@pytest.mark.parametrize(
    "url", ["https://opera.example.internal/giris", "about:blank", "http://127.0.0.1:8101/pages/x"]
)
async def test_run_refuses_session_outside_application_origin(tmp_path: Path, url: str) -> None:
    sessions = FakeSessions(url)
    repo = LocalFileRunRepository(tmp_path / "runs")
    runs = RunService(repo, sessions, None, LAB_ACTION_SET, 100)  # type: ignore[arg-type]  # reddedilen yol çalıştırmaz
    steps = [{"op": "read", "target": {"kind": "textbox", "labels": ["Müşteri No"]}}]
    with pytest.raises(SessionApplicationMismatch):
        await runs.create("u", "sid", "req-1", steps, required_origin=LAB.origin)
    assert not sessions.busy  # kilit bırakıldı
    assert repo.find_by_request("u", "req-1") is None  # run kaydı oluşmadı
