"""Kullanıcı olayları: taslak, onay, yayın, müdahale. Başarısız işlem başarı kaydı üretmez."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentask.application.errors import InterruptionChanged, PublishConflict
from agentask.application.services.observation import ObservationService
from agentask.application.services.publishing import PublishService
from agentask.domain.catalog import OperationDraft
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from tests.fake_catalog_store import FakeCatalogStore
from tests.unit.test_component_publishing import component_draft, make_ready

Logs = Callable[[], list[dict[str, Any]]]


def events(logs: Logs, name: str) -> list[dict[str, Any]]:
    return [x for x in logs() if x["event"] == name]


@pytest.fixture
def setup(
    tmp_path: Path,
) -> tuple[PublishService, LocalFileDraftRepository, FakeCatalogStore, OperationDraft]:
    store, repo = FakeCatalogStore(), LocalFileDraftRepository(tmp_path / "drafts")
    draft = component_draft()
    make_ready(draft)
    repo.create(draft)
    return PublishService(store, repo, LAB_ACTION_SET, environment="arge"), repo, store, draft


async def test_approve_and_publish_events_name_actor_and_resource(setup: Any, json_logs: Logs) -> None:
    pub, repo, _, draft = setup
    pub.approve("yayinci", draft.draft_id, repo.get(draft.draft_id).revision)
    manifest = await pub.publish("yayinci", draft.draft_id, "req-1")
    approved, published = events(json_logs, "draft_approved")[0], events(json_logs, "release_published")[0]
    assert approved["actor"] == published["actor"] == "yayinci"
    assert approved["resource_id"] == draft.draft_id and approved["category"] == "audit"
    assert published["resource_id"] == manifest.release_id and published["outcome"] == "success"
    assert published["operation_id"] == draft.operation_id


async def test_lost_publish_produces_no_success_event(
    setup: Any, json_logs: Logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    pub, repo, store, draft = setup
    pub.approve("yayinci", draft.draft_id, repo.get(draft.draft_id).revision)

    async def lost(*_: Any) -> bool:
        return False

    monkeypatch.setattr(store, "compare_and_set_active", lost)
    with pytest.raises(PublishConflict):
        await pub.publish("yayinci", draft.draft_id, "req-2")
    assert not events(json_logs, "release_published")


def test_draft_save_event_written_only_after_save(tmp_path: Path, json_logs: Logs) -> None:
    from agentask.application.errors import DraftConflict
    from agentask.application.services.designer import DesignerService

    repo = LocalFileDraftRepository(tmp_path / "drafts")
    service = DesignerService(repo, None, None, None, LAB_ACTION_SET, 1.0)  # type: ignore[arg-type]
    draft = service.create_draft("ayse", application_id="lab", operation_id="op", title="T", description="")
    updated = service.update_meta("ayse", draft.draft_id, draft.revision, title="Yeni")
    saved = events(json_logs, "draft_saved")
    assert len(saved) == 2 and saved[-1]["actor"] == "ayse" and saved[-1]["revision"] == updated.revision
    with pytest.raises(DraftConflict):
        service.update_meta("ayse", draft.draft_id, 999, title="Çakışma")
    assert len(events(json_logs, "draft_saved")) == 2


class _Observer:
    def __init__(self, result: bool) -> None:
        self.result = result

    async def dismiss_native_dialog(self, _: str) -> bool:
        return self.result

    def interruption_state(self) -> dict[str, Any]:
        return {}


class _Sessions:
    def __init__(self, observer: _Observer) -> None:
        self.observer = observer

    def peek(self, *_: Any) -> Any:
        return self


async def test_intervention_decision_is_recorded_only_when_applied(json_logs: Logs) -> None:
    service = ObservationService(_Sessions(_Observer(True)), 1000)  # type: ignore[arg-type]
    await service.resolve_interruption("ayse", "s1", "dismiss_browser_dialog", ["d1"])
    line = events(json_logs, "interruption_resolved")[0]
    assert (
        line["actor"] == "ayse"
        and line["action"] == "dismiss_browser_dialog"
        and line["outcome"] == "applied"
    )
    stale = ObservationService(_Sessions(_Observer(False)), 1000)  # type: ignore[arg-type]
    with pytest.raises(InterruptionChanged):
        await stale.resolve_interruption("ayse", "s1", "dismiss_browser_dialog", ["d2"])
    assert len(events(json_logs, "interruption_resolved")) == 1
