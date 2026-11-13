"""Gerçek MongoDB (geçici mongod) ile yayın tutarlılığı: şema doğrulama, unique, CAS, eksik yayın,
eşzamanlılık."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pymongo.errors import WriteError

from agentask.application.errors import ContentConflict, PublishConflict, StaleApproval
from agentask.application.services.publishing import PublishService
from agentask.domain.release import OperationRevision
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.mongo.catalog_store import MongoCatalogStore
from tests.unit.test_publishing import ready_draft

pytestmark = pytest.mark.mongo


class FailingStore:
    """Gerçek Mongo deposunu sarar; belirli adımdan sonra hata enjekte eder (süreç çökmesi benzetimi)."""

    def __init__(self, real: MongoCatalogStore, fail_after: str) -> None:
        self._real, self._fail_after = real, fail_after

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        attr = getattr(self._real, name)
        if name != self._fail_after:
            return attr

        async def wrapped(*args, **kwargs):  # type: ignore[no-untyped-def]
            await attr(*args, **kwargs)
            raise RuntimeError(f"enjekte hata: {name} sonrası")

        return wrapped


def service(store: object, tmp: Path) -> tuple[PublishService, LocalFileDraftRepository]:
    repo = LocalFileDraftRepository(tmp / "drafts")
    return PublishService(store, repo, LAB_ACTION_SET, "arge"), repo  # type: ignore[arg-type]


async def test_publish_and_read_back(store: MongoCatalogStore, tmp_path: Path) -> None:
    svc, repo = service(store, tmp_path)
    d = ready_draft(repo)
    svc.approve("pub", d.draft_id, d.revision)
    release = await svc.publish("pub", d.draft_id, "r1")
    active = await svc.active_release("lab")
    assert active == release
    rev = await svc.operation("lab", release.operations[0])
    assert rev is not None and rev.definition["operation_id"] == "kefil_no"
    assert "candidate" not in str(rev.definition) and "#" not in str(rev.definition["elements"])


async def test_schema_validation_rejects_malformed_documents(store: MongoCatalogStore) -> None:
    with pytest.raises(WriteError):
        await store._db["catalog_operations"].insert_one({"application_id": "lab", "revision": 0})
    with pytest.raises(WriteError):
        await store._db["catalog_releases"].insert_one({"release_id": "x", "operations": []})


async def test_same_revision_different_hash_conflicts(store: MongoCatalogStore) -> None:
    base = dict(
        application_id="lab",
        operation_id="x",
        revision=1,
        definition={"a": 1},
        approved_by="p",
        approval_hash="a",
    )
    assert await store.put_revision(OperationRevision(content_hash="1" * 64, **base)) == "inserted"
    assert await store.put_revision(OperationRevision(content_hash="1" * 64, **base)) == "exists"
    with pytest.raises(ContentConflict):
        await store.put_revision(OperationRevision(content_hash="2" * 64, **base))


@pytest.mark.parametrize("stage", ["put_revision", "insert_release"])
async def test_failure_mid_publish_never_activates(
    store: MongoCatalogStore, tmp_path: Path, stage: str
) -> None:
    svc, repo = service(FailingStore(store, stage), tmp_path)
    d = ready_draft(repo)
    svc.approve("pub", d.draft_id, d.revision)
    with pytest.raises(RuntimeError):
        await svc.publish("pub", d.draft_id, "r1")
    assert await store.get_active("lab", "arge") is None


async def test_concurrent_publish_one_wins(store: MongoCatalogStore, tmp_path: Path) -> None:
    svc, repo = service(store, tmp_path)
    a, b = ready_draft(repo, "op_a", "A"), ready_draft(repo, "op_b", "B")
    svc.approve("pub", a.draft_id, a.revision)
    svc.approve("pub", b.draft_id, b.revision)
    results = await asyncio.gather(
        *(svc.publish("pub", x.draft_id, f"r-{x.operation_id}") for x in (a, b)), return_exceptions=True
    )
    wins = [r for r in results if not isinstance(r, Exception)]
    assert len(wins) >= 1
    assert all(isinstance(r, PublishConflict) for r in results if isinstance(r, Exception))
    active = await svc.active_release("lab")
    assert active is not None
    for entry in active.operations:  # aktif manifest her zaman tam
        assert await store.get_revision("lab", entry.operation_id, entry.revision) is not None


async def test_cas_rejects_stale_expected(store: MongoCatalogStore) -> None:
    assert await store.compare_and_set_active("lab", "arge", None, "rel-a", "p")
    assert not await store.compare_and_set_active("lab", "arge", None, "rel-b", "p")
    assert not await store.compare_and_set_active("lab", "arge", "rel-x", "rel-b", "p")
    assert await store.compare_and_set_active("lab", "arge", "rel-a", "rel-b", "p")
    active = await store.get_active("lab", "arge")
    assert active is not None and active.release_id == "rel-b" and active.version == 2


async def test_stale_approval_never_writes(store: MongoCatalogStore, tmp_path: Path) -> None:
    svc, repo = service(store, tmp_path)
    d = ready_draft(repo)
    d = svc.approve("pub", d.draft_id, d.revision)
    d.description = "değişti"
    repo.update(d, d.revision)
    with pytest.raises(StaleApproval):
        await svc.publish("pub", d.draft_id, "r1")
    assert await store._db["catalog_operations"].count_documents({}) == 0


async def test_unavailable_mongo_is_dependency_error() -> None:
    from agentask.application.errors import DependencyUnavailable

    dead = MongoCatalogStore("mongodb://127.0.0.1:1", "x", 300)
    assert await dead.ping() is False
    with pytest.raises(DependencyUnavailable):
        await dead.get_active("lab", "arge")
    await dead.close()
