"""Değişiklik/etki use case'leri. Okuma + yeni taslak açma; etkin yayın değişmez."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agentask.application.errors import DependencyUnavailable, PlanInvalid
from agentask.application.ports.drafts import DraftRepository
from agentask.application.services.observation import ObservationService, assess_screen_on
from agentask.application.services.publishing import PublishService
from agentask.domain.catalog import OperationDraft, requires_migration
from agentask.domain.impact import PublishedOperation, classify_elements, impact_of, repair_draft
from agentask.domain.release import ReleaseManifest
from agentask.domain.screens import ScreenDef


class ImpactService:
    def __init__(
        self,
        publishing: PublishService | None,
        observation: ObservationService,
        drafts: DraftRepository,
        application_id: str,
    ) -> None:
        self._publishing = publishing
        self._observation = observation
        self._drafts = drafts
        self.application_id = application_id

    async def _published(self) -> tuple[ReleaseManifest, list[PublishedOperation]]:
        if self._publishing is None:
            raise DependencyUnavailable("Yayımlanmış katalog yok (CATALOG_BACKEND=disabled).")
        release = await self._publishing.active_release(self.application_id)
        if release is None:
            raise PlanInvalid(details={"reason": "no_active_release"})
        ops = []
        for entry in release.operations:
            rev = await self._publishing.operation(self.application_id, entry)
            if rev is not None:
                ops.append(
                    PublishedOperation(
                        operation_id=entry.operation_id,
                        revision=entry.revision,
                        content_hash=entry.content_hash,
                        definition=rev.definition,
                    )
                )
        return release, ops

    async def _screens(
        self, release: ReleaseManifest, op: PublishedOperation
    ) -> tuple[ScreenDef | None, list[ScreenDef]]:
        """Yayının pinlenmiş ekranları; eski tanımda (None, []) (Changes yalnız 'geçiş gerekli' gösterir)."""
        if requires_migration(op.definition) or self._publishing is None:
            return None, []
        return await self._publishing.screens_of(release, op.operation_id, op.revision, op.definition)

    async def operations(self) -> dict[str, Any]:
        release, ops = await self._published()
        return {
            "release_id": release.release_id,
            "operations": [
                {
                    "operation_id": o.operation_id,
                    "revision": o.revision,
                    "title": o.definition["title"],
                    "elements": list(o.definition["elements"]),
                    "migration_required": requires_migration(o.definition),
                }
                for o in ops
            ],
        }

    async def analyze(self, owner: str, session_id: str, operation_id: str) -> dict[str, Any]:
        release, ops = await self._published()
        op = next((o for o in ops if o.operation_id == operation_id), None)
        if op is None:
            raise PlanInvalid(details={"reason": "operation_not_in_release"})
        snapshot = await self._observation.observe(owner, session_id)
        start, extra = await self._screens(release, op)
        # Aynı ekran çekirdeği: ekran tanınmadan eleman sonuçları "bu ekranda değişti" diye yorumlanmaz.
        verdicts = [assess_screen_on(snapshot, s).to_dict() for s in ([start] if start else []) + extra]
        screen_result = (
            next((v for v in verdicts if v["recognized"]), verdicts[0])
            if verdicts
            else {"status": "migration_required", "recognized": False}
        )
        checks = classify_elements(op, snapshot)
        changed = {
            (op.operation_id, c.element_id) for c in checks if c.status.value in {"not_found", "ambiguous"}
        }
        impacted = impact_of(ops, elements=changed) if changed else []
        return {
            "release_id": release.release_id,
            "operation_id": operation_id,
            "snapshot_revision": snapshot.revision,
            "screen": screen_result,
            "screens": verdicts,
            "elements": [{**asdict(c), "status": c.status.value} for c in checks],
            "impacted": [asdict(i) for i in impacted],
        }

    async def dependency_impact(
        self, adapter_kinds: list[str], action_ids: list[str], screen_ids: list[str] | None = None
    ) -> dict[str, Any]:
        release, ops = await self._published()
        impacted = impact_of(
            ops,
            adapter_kinds=set(adapter_kinds),
            action_ids=set(action_ids),
            screen_ids=set(screen_ids or []),
        )
        return {"release_id": release.release_id, "impacted": [asdict(i) for i in impacted]}

    async def repair(self, owner: str, operation_id: str, element_ids: list[str]) -> OperationDraft:
        release, ops = await self._published()
        op = next((o for o in ops if o.operation_id == operation_id), None)
        if op is None:
            raise PlanInvalid(details={"reason": "operation_not_in_release"})
        draft = repair_draft(
            op,
            set(element_ids),
            created_by=owner,
            base_release_id=release.release_id,
            screen=(screens := await self._screens(release, op))[0],
            extra_screens=screens[1],
        )
        self._drafts.create(draft)
        return draft
