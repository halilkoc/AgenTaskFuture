"""R3 gerçek MongoDB roundtrip'i (geçici mongod, testlere özel rastgele veritabanı; kullanıcı verisine
dokunmaz).

- catalog_screens şema doğrulaması, unique ve aynı revizyon/farklı hash reddi
- yayın → yeni bağlantıyla geri okuma (ekran revizyonu manifestte pinli)
- R3 öncesi ham belgeler (screen_ref/screens yok): ensure_schema sonrası BAYT BAYT aynı kalır, çalıştırma
  migration_required ile reddedilir, geçiş akışı r2 yayımlar, r1 ve eski manifest yerinde kalır
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from pymongo.errors import WriteError

from agentask.application.errors import ContentConflict, MigrationRequired
from agentask.application.services.assistant import AssistantService
from agentask.application.services.designer import DesignerService
from agentask.application.services.publishing import PublishService
from agentask.domain.release import ScreenRevision
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from agentask.infrastructure.mongo.catalog_store import MongoCatalogStore
from tests.legacy_catalog import legacy_definition
from tests.screens import PARTIES_SCREEN
from tests.unit.test_publishing import ready_draft

pytestmark = pytest.mark.mongo


def services(store: MongoCatalogStore, tmp: Path) -> tuple[PublishService, LocalFileDraftRepository]:
    repo = LocalFileDraftRepository(tmp / "drafts")
    return PublishService(store, repo, LAB_ACTION_SET, "arge"), repo


def assistant(pub: PublishService) -> AssistantService:
    return AssistantService(
        pub,
        None,
        LAB_ACTION_SET,
        UnavailableLLM("kapalı"),
        2000,
        200,
        1,
        "lab",  # type: ignore[arg-type]
    )


async def raw(store: MongoCatalogStore, collection: str) -> list[dict[str, Any]]:
    return [d async for d in store._db[collection].find({}, sort=[("_id", 1)])]


async def test_screen_revision_roundtrip_and_restart(
    store: MongoCatalogStore, mongo_uri: str, tmp_path: Path
) -> None:
    pub, repo = services(store, tmp_path)
    d = ready_draft(repo)
    d = pub.approve("pub", d.draft_id, d.revision)
    release = await pub.publish("pub", d.draft_id, "r1")
    docs = await raw(store, "catalog_screens")
    assert len(docs) == 1 and docs[0]["screen_id"] == "basvuru_taraflar" and docs[0]["revision"] == 1
    blob = str(docs[0]["definition"])
    assert "candidate" not in blob and "url" not in blob and "#" not in blob

    # Yeni bağlantı (uygulama yeniden başlatma benzetimi): manifest ve ekran aynı okunur.
    again = MongoCatalogStore(mongo_uri, store._db.name, 3000)
    try:
        pub2 = PublishService(again, repo, LAB_ACTION_SET, "arge")
        active = await pub2.active_release("lab")
        assert active == release and [s.revision for s in active.screens] == [1]
        rev = await pub2.operation("lab", active.operations[0])
        assert rev is not None
        assert await pub2.screen_for(active, rev) == PARTIES_SCREEN
        preview = await assistant(pub2).preview("ayse", active.release_id, "kefil_no", {"no": "00456"})
        assert preview["commands"][0]["screen"] == PARTIES_SCREEN.model_dump(mode="json")
    finally:
        await again.close()


async def test_catalog_screens_schema_and_immutability(store: MongoCatalogStore) -> None:
    with pytest.raises(WriteError):
        await store._db["catalog_screens"].insert_one(
            {"application_id": "lab", "screen_id": "x", "revision": 0}
        )
    rev = ScreenRevision(
        application_id="lab",
        screen_id="basvuru_taraflar",
        revision=1,
        content_hash=PARTIES_SCREEN.content_hash(),
        definition=PARTIES_SCREEN.model_dump(mode="json"),
        approved_by="pub",
        approval_hash="a" * 64,
    )
    assert await store.put_screen(rev) == "inserted"
    assert await store.put_screen(rev) == "exists"  # idempotent
    other = rev.model_copy(update={"content_hash": "f" * 64})
    with pytest.raises(ContentConflict):  # aynı ekran+revizyon farklı içerikle yazılamaz
        await store.put_screen(other)
    assert await store.get_screen("lab", "basvuru_taraflar", 1) == rev


async def test_pre_r3_documents_preserved_rejected_and_migrated(
    store: MongoCatalogStore, tmp_path: Path
) -> None:
    pub, repo = services(store, tmp_path)
    source = ready_draft(repo, "kefil_musteri_no", "Kefil müşteri numarasını gir")
    definition = legacy_definition(source)
    from agentask.domain.release import canonical_hash

    content_hash = canonical_hash(definition)
    # R3 öncesi kodun yazdığı ham belgeler (screens / screen_ref alanı yok).
    await store._db["catalog_operations"].insert_one(
        {
            "application_id": "lab",
            "operation_id": "kefil_musteri_no",
            "revision": 1,
            "content_hash": content_hash,
            "definition": copy.deepcopy(definition),
            "approved_by": "eski",
            "approval_hash": "0" * 64,
            "schema_version": "catalog-v1",
        }
    )
    await store._db["catalog_releases"].insert_one(
        {
            "release_id": "rel-v1",
            "request_id": "req-v1",
            "application_id": "lab",
            "environment": "arge",
            "operations": [{"operation_id": "kefil_musteri_no", "revision": 1, "content_hash": content_hash}],
            "base_release_id": None,
            "approvals": [],
            "adapter_version": "controls-p3.1",
            "schema_version": "catalog-v1",
            "manifest_hash": "1" * 64,
            "created_by": "eski",
            "created_at": source.created_at,
        }
    )
    assert await store.compare_and_set_active("lab", "arge", None, "rel-v1", "eski")
    before = {c: await raw(store, c) for c in ("catalog_operations", "catalog_releases")}

    await store.ensure_schema()  # sürüm yükseltmesi: şema eklenir, mevcut belge değişmez
    assert {c: await raw(store, c) for c in before} == before

    with pytest.raises(MigrationRequired):
        await assistant(pub).preview("ayse", "rel-v1", "kefil_musteri_no", {"no": "00456"})

    designer = DesignerService(repo, None, None, None, LAB_ACTION_SET, 1, publishing=pub)  # type: ignore[arg-type]
    draft = await designer.start_migration("ayse", "lab", "kefil_musteri_no")
    assert {c: await raw(store, c) for c in before} == before  # taslak açmak yayına yazmaz
    draft.screen = PARTIES_SCREEN
    draft.record_fresh_test(run_id="run-migr0001", passed=True)
    repo.update(draft, draft.revision)
    draft = pub.approve("pub", draft.draft_id, draft.revision)
    release = await pub.publish("pub", draft.draft_id, "migr-1")

    ops = await raw(store, "catalog_operations")
    assert [o["revision"] for o in ops] == [1, 2]
    assert ops[0] == before["catalog_operations"][0]  # r1 yerinde, değişmedi
    releases = await raw(store, "catalog_releases")
    assert releases[0] == before["catalog_releases"][0] and len(releases) == 2
    assert release.base_release_id == "rel-v1" and release.screens[0].screen_id == "basvuru_taraflar"
    active = await pub.active_release("lab")
    assert active is not None and active.release_id == release.release_id
    preview = await assistant(pub).preview("ayse", release.release_id, "kefil_musteri_no", {"no": "00456"})
    assert preview["revision"] == 2 and preview["steps"][0].startswith("Ekranı doğrula")
