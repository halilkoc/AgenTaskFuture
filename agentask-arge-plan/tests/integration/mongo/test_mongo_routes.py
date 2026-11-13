"""R4 gerçek MongoDB roundtrip (geçici mongod, rastgele test veritabanı): çok ekranlı yayın
bütünlüğü ve önceki
(catalog-v2 tek ekranlı) yayın belgelerinin bayt bayt korunması."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentask.application.services.assistant import AssistantService
from agentask.application.services.publishing import PublishService
from agentask.domain.catalog import compile_operation
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from agentask.infrastructure.mongo.catalog_store import MongoCatalogStore
from tests.unit.test_publishing import ready_draft
from tests.wizard import ARGS, wizard_draft

pytestmark = pytest.mark.mongo


async def raw(store: MongoCatalogStore, name: str) -> list[dict[str, Any]]:
    return [d async for d in store._db[name].find({}, sort=[("_id", 1)])]


async def test_multi_screen_publish_roundtrip_keeps_v2_documents(
    store: MongoCatalogStore, mongo_uri: str, tmp_path: Path
) -> None:
    repo = LocalFileDraftRepository(tmp_path / "drafts")
    pub = PublishService(store, repo, LAB_ACTION_SET, "arge")
    v2 = ready_draft(repo, "kefil_musteri_no", "Kefil")
    pub.approve("pub", v2.draft_id, v2.revision)
    first = await pub.publish("pub", v2.draft_id, "r-v2")
    before = {n: await raw(store, n) for n in ("catalog_operations", "catalog_releases", "catalog_screens")}

    w = wizard_draft()
    repo.create(w)
    pub.approve("pub", w.draft_id, w.revision)
    release = await pub.publish("pub", w.draft_id, "r-v3")

    after = {n: await raw(store, n) for n in before}
    for name, docs in before.items():
        assert after[name][: len(docs)] == docs  # önceki belgeler yerinde, değişmedi
    assert [d["schema_version"] for d in after["catalog_operations"]] == ["catalog-v2", "catalog-v3"]
    assert {d["screen_id"] for d in after["catalog_screens"]} == {
        "basvuru_taraflar",
        "basvuru_musteri",
        "basvuru_teminat",
        "basvuru_ozet",
    }
    assert len(release.screens) == 4 and release.base_release_id == first.release_id

    again = MongoCatalogStore(mongo_uri, store._db.name, 3000)  # yeni bağlantı: yeniden başlatma benzetimi
    try:
        pub2 = PublishService(again, repo, LAB_ACTION_SET, "arge")
        active = await pub2.active_release("lab")
        assert active == release
        entry = next(e for e in active.operations if e.operation_id == "basvuru_gonder")
        rev = await pub2.operation("lab", entry)
        assert rev is not None
        model = await pub2.published_draft(active, rev)
        assert model.content_hash() == rev.content_hash == w.content_hash()
        commands = compile_operation(model, ARGS, LAB_ACTION_SET)
        assert [c["op"] for c in commands].count("follow_transition") == 1
        assistant = AssistantService(pub2, None, LAB_ACTION_SET, UnavailableLLM("x"), 2000, 200, 1, "lab")  # type: ignore[arg-type]
        v2_preview = await assistant.preview("ayse", active.release_id, "kefil_musteri_no", {"no": "00456"})
        assert v2_preview["navigation"] is False and v2_preview["revision"] == 1
    finally:
        await again.close()
