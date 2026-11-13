"""Onay ve tutarlı yayımlama (docs/02 Tutarlı yayımlama).

Sıra: (1) değişmez operasyon revizyonu idempotent yazılır, (2) bütün referanslar doğrulanmış tam manifest
yazılır,
(3) aktif pointer en son compare-and-set ile değişir. Eksik yayın runtime tarafından okunamaz çünkü
runtime yalnız
aktif pointer'ın gösterdiği manifesti okur. CAS kaybında manifest pasif kalır (PublishConflict).

R3: işlemin ekran tanımı ayrı, değişmez bir ekran revizyonu olarak catalog_screens'e (işlem revizyonundan
önce) yazılır. İşlem tanımındaki screen_ref (ekran içerik hash'i) onay hash'inin kapsamındadır; manifest
kullanılan ekran revizyonlarını listeler ve hash'ine katar. Eski (ekransız) revizyon/manifestolar yerinde
değiştirilmez; çalıştırılmaları MigrationRequired ile reddedilir.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from agentask.application.errors import (
    DraftNotFound,
    DraftNotReady,
    IdempotencyConflict,
    MigrationRequired,
    PlanInvalid,
    PublishConflict,
    StaleApproval,
)
from agentask.application.observability import log_event
from agentask.application.ports.catalog import CatalogStore
from agentask.application.ports.drafts import DraftRepository
from agentask.domain.actions import ActionSet
from agentask.domain.catalog import (
    MAX_COMPONENT_DEPTH,
    ComponentLookup,
    OperationDraft,
    component_inputs,
    definition_schema,
    requires_migration,
    screen_refs,
)
from agentask.domain.release import (
    ActivationRecord,
    ApprovalRecord,
    ManifestEntry,
    OperationRevision,
    ReleaseManifest,
    ScreenEntry,
    ScreenRevision,
    canonical_hash,
)
from agentask.domain.screens import ScreenDef

# v4: pinli bileşen çağrısı (E); v5: seçim adımı alanları (ADR 0021)
SUPPORTED_SCHEMAS = frozenset({"catalog-v2", "catalog-v3", "catalog-v4", "catalog-v5", "catalog-v6"})
SCREEN_LOOKUP_LIMIT = 200  # hash ile ekran revizyonu aranırken geriye bakılacak en fazla revizyon

logger = logging.getLogger(__name__)
MIN_ACTIVATION_REASON = 10


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
        log_event(
            logger,
            "draft_approved",
            audit=True,
            outcome="success",
            actor=approver,
            resource_type="draft",
            resource_id=draft.draft_id,
            application_id=draft.application_id,
            operation_id=draft.operation_id,
            revision=draft.revision,
        )
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
        assert draft.screen is not None  # validation_issues screen_missing'i zaten reddeder
        new_screens: list[ScreenEntry] = []
        for (
            screen
        ) in draft.all_screens().values():  # R4: başlangıç + diğer ekranlar, her biri değişmez revizyon
            screen_hash = screen.content_hash()
            latest_screen = await self._store.latest_screen(app, screen.screen_id)
            screen_number = (
                latest_screen.revision
                if latest_screen and latest_screen.content_hash == screen_hash
                else (latest_screen.revision + 1 if latest_screen else 1)
            )
            await self._store.put_screen(
                ScreenRevision(
                    application_id=app,
                    screen_id=screen.screen_id,
                    revision=screen_number,
                    content_hash=screen_hash,
                    definition=screen.model_dump(mode="json"),
                    approved_by=approval.approver,
                    approval_hash=approval.approval_hash,
                )
            )
            new_screens.append(
                ScreenEntry(screen_id=screen.screen_id, revision=screen_number, content_hash=screen_hash)
            )

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
                schema_version=definition_schema(draft.definition()),
            )
        )

        active = await self._store.get_active(app, env)
        base = await self._store.get_release(active.release_id) if active else None
        entries = [e for e in (base.operations if base else []) if e.operation_id != op]
        entries.append(ManifestEntry(operation_id=op, revision=number, content_hash=content_hash))
        referenced: set[tuple[str, str]] = set()
        for entry in entries:  # eksik referanslı manifest yazılmaz
            rev = await self._store.get_revision(app, entry.operation_id, entry.revision)
            if rev is None or rev.content_hash != entry.content_hash:
                raise PublishConflict("Manifest referansı doğrulanamadı; yayın yapılmadı.")
            referenced |= screen_refs(rev.definition)
            # E: pinli bileşenler (ve onların bileşenleri) değişmez revizyon olarak var olmalı; ekranları
            # manifeste girer (çağıran yayında bileşenin ekranı da pinlidir).
            referenced |= await self._component_screen_refs(app, rev.definition, 1)
        screens = [
            s
            for s in (base.screens if base else [])
            if (s.screen_id, s.content_hash) in referenced and s not in new_screens
        ] + new_screens
        for screen_id, screen_hash in sorted(referenced - {(s.screen_id, s.content_hash) for s in screens}):
            found = await self._screen_by_hash(
                app, screen_id, screen_hash
            )  # bileşenin önceki yayındaki ekranı
            if found is not None:
                screens.append(
                    ScreenEntry(screen_id=screen_id, revision=found.revision, content_hash=screen_hash)
                )
        for s in screens:  # ekran referansları da doğrulanır
            stored = await self._store.get_screen(app, s.screen_id, s.revision)
            if stored is None or stored.content_hash != s.content_hash:
                raise PublishConflict("Ekran referansı doğrulanamadı; yayın yapılmadı.")
        missing = referenced - {(s.screen_id, s.content_hash) for s in screens}
        if missing:
            raise PublishConflict("Bir işlemin ekran revizyonu manifestte yok; yayın yapılmadı.")
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
            screens=sorted(screens, key=lambda s: (s.screen_id, s.revision)),
            manifest_hash=ReleaseManifest.compute_hash(app, env, entries, screens),
            created_by=publisher,
        )
        await self._store.insert_release(manifest)
        if not await self._store.compare_and_set_active(
            app, env, active.release_id if active else None, manifest.release_id, publisher
        ):
            logger.warning("publish_cas_lost release=%s", manifest.release_id)
            raise PublishConflict()
        log_event(
            logger,
            "release_published",
            audit=True,
            outcome="success",
            actor=publisher,
            resource_type="release",
            resource_id=manifest.release_id,
            release_id=manifest.release_id,
            application_id=draft.application_id,
            operation_id=draft.operation_id,
            count=len(entries),
        )
        return manifest

    # ---- etkin yayın değişikliği (geri/ileri alma) -----------------------------------------

    async def _incompatibilities(self, app: str, draft: OperationDraft, depth: int = 0) -> list[str]:
        """Yayın mevcut aksiyonlarla çalışabilir mi? Bileşenlerin içi dahil; değişmiş aksiyon engeldir."""
        problems: list[str] = []
        for step in draft.steps:
            if step.op == "invoke_approved_action":
                problem = self._actions.problem(step.action_id, step.action_hash, draft.application_id)
                if problem is not None:
                    problems.append(f"{draft.operation_id}:{problem}:{step.action_id}")
            if step.call is not None and depth < 5:
                component = await self.component(app, step.call.operation_id, step.call.revision)
                if component is None:
                    problems.append(f"{draft.operation_id}:component_missing:{step.call.operation_id}")
                else:
                    problems += await self._incompatibilities(app, component, depth + 1)
        return problems

    async def activate_release(
        self, publisher: str, release_id: str, expected_active: str | None, reason: str
    ) -> ReleaseManifest:
        """Var olan yayını etkin yapar (geri/ileri alma). Yeni kayıt silinmez, yayınlar değişmez; süren
        çalışmalar kendi derlenmiş planlarında kalır. Yalnız mevcut aksiyonlarla uyumlu yayın etkinleşir."""
        text = reason.strip()
        if len(text) < MIN_ACTIVATION_REASON:
            raise PlanInvalid(
                f"Gerekçe en az {MIN_ACTIVATION_REASON} karakter olmalı.",
                details={"reason": "reason_required"},
            )
        manifest = await self._store.get_release(release_id)
        if manifest is None or manifest.environment != self.environment:
            raise PublishConflict("Yayın bulunamadı.", details={"reason": "release_not_found"})
        app, env = manifest.application_id, manifest.environment
        current = await self._store.get_active(app, env)
        active_id = current.release_id if current else None
        if active_id == release_id:
            raise PublishConflict("Bu yayın zaten etkin.", details={"reason": "already_active"})
        if active_id != expected_active:
            raise PublishConflict(
                "Etkin yayın değişti; listeyi yenileyin.", details={"reason": "stale_active"}
            )
        problems: list[str] = []
        for entry in manifest.operations:
            revision = await self._store.get_revision(app, entry.operation_id, entry.revision)
            if revision is None or definition_schema(revision.definition) not in SUPPORTED_SCHEMAS:
                problems.append(f"{entry.operation_id}:unsupported_schema")
                continue
            problems += await self._incompatibilities(app, await self.published_draft(manifest, revision))
        if problems:
            raise PublishConflict(
                "Bu yayın mevcut onaylı işlemlerle uyumlu değil; etkinleştirilmedi.",
                details={"reason": "incompatible_actions", "problems": problems[:10]},
            )
        if not await self._store.compare_and_set_active(app, env, active_id, release_id, publisher):
            raise PublishConflict(
                "Etkin yayın değişti; listeyi yenileyin.", details={"reason": "stale_active"}
            )
        await self._store.add_activation(
            ActivationRecord(
                application_id=app,
                environment=env,
                from_release_id=active_id,
                to_release_id=release_id,
                by=publisher,
                reason=text,
            )
        )
        log_event(
            logger,
            "release_activated",
            audit=True,
            outcome="success",
            actor=publisher,
            resource_type="release",
            resource_id=release_id,
            release_id=release_id,
            application_id=app,
        )
        return manifest

    async def activations(self, app: str) -> list[ActivationRecord]:
        return await self._store.list_activations(app, self.environment)

    # ---- E: sürümlü bileşenler -----------------------------------------------------------

    async def _screen_by_hash(self, app: str, screen_id: str, content_hash: str) -> ScreenRevision | None:
        latest = await self._store.latest_screen(app, screen_id)
        if latest is None:
            return None
        for number in range(latest.revision, max(0, latest.revision - SCREEN_LOOKUP_LIMIT), -1):
            rev = (
                latest if number == latest.revision else await self._store.get_screen(app, screen_id, number)
            )
            if rev is not None and rev.content_hash == content_hash:
                return rev
        return None

    async def _component_screen_refs(
        self, app: str, definition: dict[str, Any], depth: int
    ) -> set[tuple[str, str]]:
        refs: set[tuple[str, str]] = set()
        for step in definition.get("steps", []):
            call = step.get("call")
            if not isinstance(call, dict):
                continue
            if depth > MAX_COMPONENT_DEPTH:
                raise PlanInvalid(details={"reason": "component_too_deep"})
            rev = await self._store.get_revision(app, call["operation_id"], call["revision"])
            if rev is None or rev.content_hash != call["content_hash"]:
                raise PublishConflict("Pinli bileşen revizyonu doğrulanamadı; yayın yapılmadı.")
            refs |= screen_refs(rev.definition) | await self._component_screen_refs(
                app, rev.definition, depth + 1
            )
        return refs

    async def component(self, app: str, operation_id: str, revision: int) -> OperationDraft | None:
        """Pinli bileşen: değişmez revizyon + ekranları (hash ile). Aktif yayında olması gerekmez; böylece
        eski yayınlar bileşenin yeni revizyonundan etkilenmez."""
        rev = await self._store.get_revision(app, operation_id, revision)
        if rev is None or requires_migration(rev.definition):
            return None
        if definition_schema(rev.definition) not in SUPPORTED_SCHEMAS:
            return None
        screens: list[ScreenDef] = []
        for ref in [rev.definition["screen_ref"], *rev.definition.get("screens_ref", [])]:
            stored = await self._screen_by_hash(app, ref["screen_id"], ref["content_hash"])
            if stored is None:
                return None
            screen = ScreenDef.model_validate(stored.definition)
            if screen.content_hash() != stored.content_hash:
                return None
            screens.append(screen)
        draft = OperationDraft.from_definition(
            rev.definition, created_by="catalog", screen=screens[0], extra_screens=screens[1:]
        )
        return draft if draft.content_hash() == rev.content_hash else None

    async def component_lookup(self, app: str, draft: OperationDraft) -> ComponentLookup:
        """Derleme için pinli bileşenleri (iç içe, sınırlı derinlik) önceden yükler; derleme eşzamanlıdır."""
        table: dict[tuple[str, int], OperationDraft] = {}

        async def load(op: OperationDraft, depth: int) -> None:
            for step in op.steps:
                if step.call is None or depth > MAX_COMPONENT_DEPTH:
                    continue
                key = (step.call.operation_id, step.call.revision)
                if key in table:
                    continue
                found = await self.component(app, *key)
                if found is not None:
                    table[key] = found
                    await load(found, depth + 1)

        await load(draft, 1)
        return lambda operation_id, revision: table.get((operation_id, revision))

    async def available_components(self, app: str, exclude: str | None = None) -> list[dict[str, Any]]:
        """Etkin yayındaki çağrılabilir işlemler (bileşen adayları), son revizyonları ve sözleşme özetleri."""
        release = await self.active_release(app)
        out: list[dict[str, Any]] = []
        for entry in release.operations if release else []:
            if entry.operation_id == exclude:
                continue
            comp = await self.component(app, entry.operation_id, entry.revision)
            if comp is None or comp.screen is None:
                continue
            effects = {s.effect(self._actions) for s in comp.steps}
            out.append(
                {
                    "operation_id": entry.operation_id,
                    "revision": entry.revision,
                    "content_hash": entry.content_hash,
                    "title": comp.title,
                    "inputs": [
                        {"name": p.name, "title": p.title, "max_length": p.max_length}
                        for p in comp.parameters
                        if p.name in component_inputs(comp)
                    ],
                    "outputs": [
                        {"name": s.element_id, "title": comp.elements[s.element_id].meaning}
                        for s in comp.steps
                        if s.op == "read" and s.element_id in comp.elements
                    ],
                    "start_screen": comp.screen.screen_id,
                    "end_screen": comp.route_end(),
                    "effect": "mutating" if "mutating" in effects else "ui_local",
                    "steps": len(comp.steps),
                }
            )
        return out

    async def active_release(self, app: str) -> ReleaseManifest | None:
        pointer = await self._store.get_active(app, self.environment)
        return await self._store.get_release(pointer.release_id) if pointer else None

    async def release(self, release_id: str) -> ReleaseManifest | None:
        return await self._store.get_release(release_id)

    async def releases(self, app: str) -> list[ReleaseManifest]:
        return await self._store.list_releases(app, self.environment)

    async def operation(self, app: str, entry: ManifestEntry) -> OperationRevision | None:
        return await self._store.get_revision(app, entry.operation_id, entry.revision)

    async def screen_for(self, manifest: ReleaseManifest, rev: OperationRevision) -> ScreenDef:
        return await self.screen_of(manifest, rev.operation_id, rev.revision, rev.definition)

    async def screen_of(
        self, manifest: ReleaseManifest, operation_id: str, revision: int, definition: dict[str, Any]
    ) -> ScreenDef:
        """Başlangıç ekranı (bkz. screens_of)."""
        start, _ = await self.screens_of(manifest, operation_id, revision, definition)
        return start

    async def _pinned(self, manifest: ReleaseManifest, operation_id: str, ref: dict[str, Any]) -> ScreenDef:
        entry = next(
            (
                s
                for s in manifest.screens
                if s.screen_id == ref.get("screen_id") and s.content_hash == ref.get("content_hash")
            ),
            None,
        )
        stored = (
            await self._store.get_screen(manifest.application_id, entry.screen_id, entry.revision)
            if entry
            else None
        )
        if stored is None or stored.content_hash != ref.get("content_hash"):
            raise PlanInvalid(details={"reason": "screen_revision_missing", "operation_id": operation_id})
        screen = ScreenDef.model_validate(stored.definition)
        if screen.content_hash() != stored.content_hash:
            raise PlanInvalid(details={"reason": "screen_hash_mismatch", "operation_id": operation_id})
        return screen

    async def screens_of(
        self, manifest: ReleaseManifest, operation_id: str, revision: int, definition: dict[str, Any]
    ) -> tuple[ScreenDef, list[ScreenDef]]:
        """Yayındaki işlemin pinlenmiş ekranları (başlangıç, diğerleri). Eski (ekransız) tanım →
        MigrationRequired; bilinmeyen şema veya bozuk manifest/ekran bütünlüğü → PlanInvalid. Ekran kontrolü
        hiçbir durumda sessizce atlanmaz."""
        if requires_migration(definition):
            raise MigrationRequired(
                details={"reason": "migration_required", "operation_id": operation_id, "revision": revision}
            )
        if definition_schema(definition) not in SUPPORTED_SCHEMAS:
            raise PlanInvalid(details={"reason": "unsupported_schema", "operation_id": operation_id})
        start = await self._pinned(manifest, operation_id, definition["screen_ref"])
        extra = [await self._pinned(manifest, operation_id, r) for r in definition.get("screens_ref", [])]
        return start, extra

    async def published_draft(self, manifest: ReleaseManifest, rev: OperationRevision) -> OperationDraft:
        """Yayımlanmış revizyondan pinlenmiş ekranıyla derlenebilir model (eski tanım: MigrationRequired)."""
        start, extra = await self.screens_of(manifest, rev.operation_id, rev.revision, rev.definition)
        return OperationDraft.from_definition(
            rev.definition, created_by="catalog", screen=start, extra_screens=extra
        )
