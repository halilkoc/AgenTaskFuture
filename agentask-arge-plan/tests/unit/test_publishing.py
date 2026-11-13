"""Hash-bağlı onay ve tutarlı yayımlama kuralları (sahte depo; gerçek Mongo testleri integration/mongo)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agentask.application.errors import (
    ContentConflict,
    DraftNotReady,
    IdempotencyConflict,
    PublishConflict,
    StaleApproval,
)
from agentask.application.services.publishing import PublishService
from agentask.domain.catalog import Confirmation, OperationDraft, ParameterDef, StepStatus
from agentask.domain.release import OperationRevision
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from tests.fake_catalog_store import FakeCatalogStore
from tests.screens import PARTIES_SCREEN


def ready_draft(
    repo: LocalFileDraftRepository, op_id: str = "kefil_no", title: str = "Kefil no"
) -> OperationDraft:
    d = OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id=op_id, title=title, description=""
    )
    d.parameters.append(ParameterDef(name="no", title="No", max_length=20, source="user_input"))
    d.add_element(
        "kefil_no", "Kefil no", {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"}, "observed"
    )
    s = d.add_step("yaz")
    s.op, s.element_id, s.value_template = "ensure_value", "kefil_no", "{no}"
    d.screen = PARTIES_SCREEN
    for status in (StepStatus.TARGET_SELECTED,):
        s.move(status)
    s.confirmation = Confirmation(meaning=True, target=True, effect=True, params=True, by="ayse")
    for status in (
        StepStatus.MEANING_AND_TARGET_CONFIRMED,
        StepStatus.TRIAL_REQUESTED,
        StepStatus.OBSERVED,
        StepStatus.OUTCOME_CONFIRMED,
        StepStatus.READY_FOR_REVIEW,
    ):
        s.move(status)
    d.record_fresh_test(run_id="run-fresh0001", passed=True)
    repo.create(d)
    return d


@pytest.fixture
def env(tmp_path: Path) -> tuple[PublishService, FakeCatalogStore, LocalFileDraftRepository]:
    store, repo = FakeCatalogStore(), LocalFileDraftRepository(tmp_path / "drafts")
    return PublishService(store, repo, LAB_ACTION_SET, environment="arge"), store, repo


async def test_approve_then_publish_activates_complete_release(env) -> None:  # type: ignore[no-untyped-def]
    service, store, repo = env
    d = ready_draft(repo)
    approved = service.approve("pub", d.draft_id, d.revision)
    assert approved.approval is not None and approved.approval.content_hash == d.content_hash()
    release = await service.publish("pub", d.draft_id, "req-1")
    active = await store.get_active("lab", "arge")
    assert active is not None and active.release_id == release.release_id
    assert [(o.operation_id, o.revision) for o in release.operations] == [("kefil_no", 1)]
    assert release.approvals[0].approver == "pub" and release.manifest_hash


async def test_unready_draft_cannot_be_approved(env, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    service, _, repo = env
    d = OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id="bos", title="Boş", description=""
    )
    repo.create(d)
    with pytest.raises(DraftNotReady):
        service.approve("pub", d.draft_id, d.revision)


async def test_publish_without_approval_rejected(env) -> None:  # type: ignore[no-untyped-def]
    service, store, repo = env
    d = ready_draft(repo)
    with pytest.raises(StaleApproval):
        await service.publish("pub", d.draft_id, "req-1")
    assert store.revisions == {} and store.active == {}


async def test_stale_approval_rejected(env) -> None:  # type: ignore[no-untyped-def]
    service, store, repo = env
    d = ready_draft(repo)
    d = service.approve("pub", d.draft_id, d.revision)
    d.title = "Onaydan sonra değişti"
    repo.update(d, d.revision)
    with pytest.raises(StaleApproval):
        await service.publish("pub", d.draft_id, "req-1")
    assert store.revisions == {} and store.active == {}


@pytest.mark.parametrize("stage", ["put_revision", "insert_release"])
async def test_failure_mid_publish_never_activates(env, stage: str) -> None:  # type: ignore[no-untyped-def]
    service, store, repo = env
    d = ready_draft(repo)
    service.approve("pub", d.draft_id, d.revision)
    store.fail_after = stage
    with pytest.raises(RuntimeError):
        await service.publish("pub", d.draft_id, "req-1")
    assert store.active == {}
    assert await service.active_release("lab") is None


async def test_concurrent_publish_one_wins(env) -> None:  # type: ignore[no-untyped-def]
    service, store, repo = env
    a = ready_draft(repo, "op_a", "A")
    b = ready_draft(repo, "op_b", "B")
    service.approve("pub", a.draft_id, a.revision)
    service.approve("pub", b.draft_id, b.revision)
    store.cas_delay = 0.05
    results = await asyncio.gather(
        service.publish("pub", a.draft_id, "ra"),
        service.publish("pub", b.draft_id, "rb"),
        return_exceptions=True,
    )
    assert sum(isinstance(r, PublishConflict) for r in results) == 1
    active = await service.active_release("lab")
    assert active is not None and len(active.operations) == 1
    # kaybeden yeniden denerse aktif manifest ikisini birlikte içerir
    loser = a if isinstance(results[0], PublishConflict) else b
    again = await service.publish("pub", loser.draft_id, "retry")
    assert {o.operation_id for o in again.operations} == {"op_a", "op_b"}


async def test_old_release_pinned_and_immutable(env) -> None:  # type: ignore[no-untyped-def]
    service, _, repo = env
    d = ready_draft(repo)
    d = service.approve("pub", d.draft_id, d.revision)
    first = await service.publish("pub", d.draft_id, "r1")
    pinned = await service.release(first.release_id)
    d = repo.get(d.draft_id)
    assert d is not None
    d.steps[0].value_template = "{no} "
    d.record_fresh_test(run_id="run-fresh0002", passed=True)
    repo.update(d, d.revision)
    d = service.approve("pub", d.draft_id, d.revision)
    second = await service.publish("pub", d.draft_id, "r2")
    assert [o.revision for o in second.operations] == [2]
    assert await service.release(first.release_id) == pinned
    assert (await service.active_release("lab")).release_id == second.release_id  # type: ignore[union-attr]


async def test_publish_idempotency(env) -> None:  # type: ignore[no-untyped-def]
    service, store, repo = env
    d = ready_draft(repo)
    service.approve("pub", d.draft_id, d.revision)
    first = await service.publish("pub", d.draft_id, "same")
    again = await service.publish("pub", d.draft_id, "same")
    assert again.release_id == first.release_id and len(store.releases) == 1
    other = ready_draft(repo, "op_x", "X")
    service.approve("pub", other.draft_id, other.revision)
    with pytest.raises(IdempotencyConflict):
        await service.publish("pub", other.draft_id, "same")


async def test_same_revision_different_hash_conflicts() -> None:
    store = FakeCatalogStore()
    base = dict(
        application_id="lab", operation_id="x", revision=1, definition={}, approved_by="p", approval_hash="a"
    )
    await store.put_revision(OperationRevision(content_hash="h1", **base))
    with pytest.raises(ContentConflict):
        await store.put_revision(OperationRevision(content_hash="h2", **base))
