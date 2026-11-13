"""Onay ve tutarlı yayımlama (docs/02 Tutarlı yayımlama).

Sıra: (1) değişmez operasyon revizyonu idempotent yazılır, (2) bütün referanslar doğrulanmış tam manifest
yazılır,
(3) aktif pointer en son compare-and-set ile değişir. Eksik yayın runtime tarafından okunamaz çünkü
runtime yalnız
aktif pointer'ın gösterdiği manifesti okur. CAS kaybında manifest pasif kalır (PublishConflict).
"""

from __future__ import annotations

import logging
import secrets

from agentask.application.errors import (
    DraftNotFound,
    DraftNotReady,
    IdempotencyConflict,
    PublishConflict,
    StaleApproval,
)
from agentask.application.ports.catalog import CatalogStore
from agentask.application.ports.drafts import DraftRepository
from agentask.domain.actions import ActionSet
from agentask.domain.catalog import OperationDraft
from agentask.domain.release import (
    ApprovalRecord,
    ManifestEntry,
    OperationRevision,
    ReleaseManifest,
    canonical_hash,
)

logger = logging.getLogger(__name__)


class PublishService:
    def __init__(
        self, store: CatalogStore, drafts: DraftRepository, actions: ActionSet, environment: str
    ) -> None:
        self._store = store
        self._drafts = drafts
        self._actions = actions
        self.environment = environment

    def _draft(self, draft_id: str) -> OperationDraft:
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise DraftNotFound()
        return draft

    @staticmethod
    def _test_evidence_hash(draft: OperationDraft) -> str:
        assert draft.fresh_test is not None
        return canonical_hash(draft.fresh_test.model_dump(mode="json"))

    def approve(self, approver: str, draft_id: str, expected_revision: int) -> OperationDraft:
        """Yetki kontrolü çağıran katmanda (PUBLISH_CATALOG). Onay içerik ve test kanıtı hash'ine bağlanır."""
        draft = self._draft(draft_id)
        issues = draft.validation_issues(self._actions)
        if issues:
            raise DraftNotReady(details={"issues": issues})
        assert draft.fresh_test is not None
        record = ApprovalRecord(
            draft_id=draft.draft_id,
            approver=approver,
            content_hash=draft.content_hash(),
            test_run_id=draft.fresh_test.run_id,
            test_evidence_hash=self._test_evidence_hash(draft),
        )
        draft.approval = record
        self._drafts.update(draft, expected_revision)
        logger.info("draft_approved draft=%s", draft.draft_id)
        return draft

    def _valid_approval(self, draft: OperationDraft) -> ApprovalRecord:
        if draft.approval is None or draft.fresh_test is None or draft.validation_issues(self._actions):
            raise StaleApproval()
        record = draft.approval
        if (
            record.content_hash != draft.content_hash()
            or record.test_evidence_hash != self._test_evidence_hash(draft)
        ):
            raise StaleApproval()
        return record

    async def publish(self, publisher: str, draft_id: str, request_id: str) -> ReleaseManifest:
        draft = self._draft(draft_id)
        existing = await self._store.find_release_by_request(request_id)
        if existing is not None:
            mine = any(
                a.draft_id == draft_id and a.content_hash == draft.content_hash() for a in existing.approvals
            )
            if not mine:
                raise IdempotencyConflict()
            return existing
        approval = self._valid_approval(draft)
        app, env, op = draft.application_id, self.environment, draft.operation_id
        content_hash = draft.content_hash()

        latest = await self._store.latest_revision(app, op)
        number = (
            latest.revision
            if latest and latest.content_hash == content_hash
            else (latest.revision + 1 if latest else 1)
        )
        await self._store.put_revision(
            OperationRevision(
                application_id=app,
                operation_id=op,
                revision=number,
                content_hash=content_hash,
                definition=draft.definition(),
                approved_by=approval.approver,
                approval_hash=approval.approval_hash,
            )
        )

        active = await self._store.get_active(app, env)
        base = await self._store.get_release(active.release_id) if active else None
        entries = [e for e in (base.operations if base else []) if e.operation_id != op]
        entries.append(ManifestEntry(operation_id=op, revision=number, content_hash=content_hash))
        for entry in entries:  # eksik referanslı manifest yazılmaz
            rev = await self._store.get_revision(app, entry.operation_id, entry.revision)
            if rev is None or rev.content_hash != entry.content_hash:
                raise PublishConflict("Manifest referansı doğrulanamadı; yayın yapılmadı.")
        approvals = [
            a
            for a in (base.approvals if base else [])
            if a.draft_id != draft_id and any(e.content_hash == a.content_hash for e in entries)
        ] + [approval]
        manifest = ReleaseManifest(
            release_id=f"rel-{secrets.token_urlsafe(9)}",
            request_id=request_id,
            application_id=app,
            environment=env,
            operations=sorted(entries, key=lambda e: e.operation_id),
            base_release_id=active.release_id if active else None,
            approvals=approvals,
            manifest_hash=ReleaseManifest.compute_hash(app, env, entries),
            created_by=publisher,
        )
        await self._store.insert_release(manifest)
        if not await self._store.compare_and_set_active(
            app, env, active.release_id if active else None, manifest.release_id, publisher
        ):
            logger.warning("publish_cas_lost release=%s", manifest.release_id)
            raise PublishConflict()
        logger.info("release_activated release=%s ops=%d", manifest.release_id, len(entries))
        return manifest

    async def active_release(self, app: str) -> ReleaseManifest | None:
        pointer = await self._store.get_active(app, self.environment)
        return await self._store.get_release(pointer.release_id) if pointer else None

    async def release(self, release_id: str) -> ReleaseManifest | None:
        return await self._store.get_release(release_id)

    async def releases(self, app: str) -> list[ReleaseManifest]:
        return await self._store.list_releases(app, self.environment)

    async def operation(self, app: str, entry: ManifestEntry) -> OperationRevision | None:
        return await self._store.get_revision(app, entry.operation_id, entry.revision)
