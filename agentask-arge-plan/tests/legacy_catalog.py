"""YALNIZ TEST: R3 öncesi (catalog-v1, ekransız) yayımlanmış kaydı TEST deposuna yazar.

Kullanıcının veritabanına asla bağlanmaz; yalnız verilen (sahte veya geçici mongod) depoyu kullanır. Eski
kodun
yazdığı biçimi taklit eder: işlem tanımında screen_ref yok, manifestoda screens yok, şema catalog-v1."""

from __future__ import annotations

from typing import Any

from agentask.application.ports.catalog import CatalogStore
from agentask.domain.catalog import OperationDraft
from agentask.domain.release import ManifestEntry, OperationRevision, ReleaseManifest, canonical_hash

LEGACY = "catalog-v1"


def legacy_definition(draft: OperationDraft) -> dict[str, Any]:
    copy = draft.model_copy(deep=True)
    copy.screen = None
    definition = copy.definition()
    assert "screen_ref" not in definition
    return definition


async def seed_legacy_release(
    store: CatalogStore, draft: OperationDraft, *, environment: str = "arge", release_id: str = "rel-legacy1"
) -> ReleaseManifest:
    definition = legacy_definition(draft)
    content_hash = canonical_hash(definition)
    app, op = draft.application_id, draft.operation_id
    await store.put_revision(
        OperationRevision(
            application_id=app,
            operation_id=op,
            revision=1,
            content_hash=content_hash,
            definition=definition,
            approved_by="eski-onayci",
            approval_hash="0" * 64,
            schema_version=LEGACY,
        )
    )
    entries = [ManifestEntry(operation_id=op, revision=1, content_hash=content_hash)]
    manifest = ReleaseManifest(
        release_id=release_id,
        request_id=f"req-{release_id}",
        application_id=app,
        environment=environment,
        operations=entries,
        base_release_id=None,
        approvals=[],
        adapter_version="controls-p3.1",
        schema_version=LEGACY,
        manifest_hash="1" * 64,
        created_by="eski-yayinci",
    )
    await store.insert_release(manifest)
    assert await store.compare_and_set_active(app, environment, None, release_id, "eski-yayinci")
    return manifest
