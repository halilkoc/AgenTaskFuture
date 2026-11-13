"""Katalog Tasarımcısı use case'leri (modelsiz, yönlendirilmiş). Taslaklar yalnız DraftRepository'ye yazılır.

Akış: niyet → kural tabanlı komut önerisi → (gözlem) hedef adayları → seçim (tekillik doğrulaması) →
anlam/hedef/etki/parametre ayrı onayları → deneme (gerçek etki olabilir; mutating için açık onay) →
sistem doğrulaması (P3 sonuç kontrolü) → kullanıcı sonucu onaylar → yeni oturum testi → incelemeye hazır.
"""

from __future__ import annotations

from typing import Any

from agentask.application.errors import (
    CandidateStale,
    DraftNotFound,
    DraftNotReady,
    EffectNotAcknowledged,
    PlanInvalid,
    TargetNotUnique,
)
from agentask.application.ports.drafts import DraftRepository
from agentask.application.services.browser_sessions import BrowserSessionService
from agentask.application.services.observation import ObservationService, resolve_target
from agentask.application.services.runs import RunService
from agentask.domain.actions import ActionSet
from agentask.domain.authoring import propose_op, rank_candidates, spec_from_control, standard_text
from agentask.domain.catalog import (
    Confirmation,
    OperationDraft,
    ParameterDef,
    Provenance,
    StepCard,
    StepStatus,
    TrialEvidence,
    compile_operation,
)
from agentask.domain.runtime import RunStatus
from agentask.domain.targeting import Outcome

_CONFIGURABLE = {
    "op",
    "value_template",
    "choice_template",
    "key_template",
    "navigation",
    "action_id",
    "action_params",
    "success_check",
    "standard_text",
}


class DesignerService:
    def __init__(
        self,
        drafts: DraftRepository,
        sessions: BrowserSessionService,
        observation: ObservationService,
        runs: RunService,
        actions: ActionSet,
        run_timeout_s: float,
    ) -> None:
        self._drafts = drafts
        self._sessions = sessions
        self.observation = observation
        self._runs = runs
        self._actions = actions
        self._run_timeout_s = run_timeout_s

    @property
    def actions(self) -> ActionSet:
        return self._actions

    # ---- taslak ---------------------------------------------------------------------

    def get(self, owner: str, draft_id: str) -> OperationDraft:
        draft = self._drafts.get(draft_id)
        if draft is None or draft.created_by != owner:
            raise DraftNotFound()
        return draft

    def list_drafts(self, owner: str) -> list[OperationDraft]:
        return self._drafts.list_for(owner)

    def _save(self, draft: OperationDraft, expected_revision: int) -> OperationDraft:
        self._drafts.update(draft, expected_revision)
        return draft

    def create_draft(
        self,
        owner: str,
        *,
        application_id: str,
        operation_id: str,
        title: str,
        description: str,
        intent_phrases: list[str] | None = None,
    ) -> OperationDraft:
        draft = OperationDraft.new(
            created_by=owner,
            application_id=application_id,
            operation_id=operation_id,
            title=title,
            description=description,
        )
        draft.intent_phrases = list(intent_phrases or [])
        self._drafts.create(draft)
        return draft

    def update_meta(self, owner: str, draft_id: str, revision: int, **fields: Any) -> OperationDraft:
        draft = self.get(owner, draft_id)
        for key in ("title", "description", "intent_phrases"):
            if key in fields and fields[key] is not None:
                setattr(draft, key, fields[key])
        return self._save(draft, revision)

    def add_parameter(self, owner: str, draft_id: str, revision: int, **fields: Any) -> OperationDraft:
        draft = self.get(owner, draft_id)
        param = ParameterDef.model_validate(fields)
        draft.parameters = [p for p in draft.parameters if p.name != param.name] + [param]
        return self._save(draft, revision)

    def add_step(
        self, owner: str, draft_id: str, revision: int, intent_text: str
    ) -> tuple[OperationDraft, StepCard]:
        draft = self.get(owner, draft_id)
        step = draft.add_step(intent_text)
        op = propose_op(step.intent_text)
        if op is not None:
            step.op = op  # type: ignore[assignment]
            step.provenance["op"] = Provenance.RULE_GENERATED
        draft.steps = list(draft.steps)
        self._save(draft, revision)
        return draft, draft.step(step.step_id)

    def remove_step(self, owner: str, draft_id: str, revision: int, step_id: str) -> OperationDraft:
        draft = self.get(owner, draft_id)
        draft.steps = [s for s in draft.steps if s.step_id != step_id]
        return self._save(draft, revision)

    # ---- hedef önerisi ve seçimi ------------------------------------------------------

    async def propose_targets(
        self, owner: str, draft_id: str, step_id: str, session_id: str
    ) -> dict[str, Any]:
        draft = self.get(owner, draft_id)
        step = draft.step(step_id)
        snapshot = await self.observation.observe(owner, session_id)
        ranked = rank_candidates(step.intent_text, snapshot.controls, step.op)
        reuse = [
            {
                "draft_id": other.draft_id,
                "element_id": e.element_id,
                "meaning": e.meaning,
                "target": e.target.model_dump(mode="json", exclude_none=True),
            }
            for other in self._drafts.list_all()
            if other.application_id == draft.application_id
            for e in other.elements.values()
            if any(r.control.label in e.target.labels for r in ranked[:3])
        ][:10]
        if step.status in {StepStatus.INTENT_ENTERED, StepStatus.TARGET_PROPOSED}:
            revision = draft.revision
            step.move(StepStatus.TARGET_PROPOSED)
            self._save(draft, revision)
        return {
            "op": step.op,
            "snapshot_revision": snapshot.revision,
            "candidates": [
                {
                    "candidate_id": r.control.candidate_id,
                    "label": r.control.label or r.control.accessible_name,
                    "kind": r.control.kind.value,
                    "score": r.score,
                    "matched": list(r.matched),
                    "contexts": [{"kind": c.kind, "name": c.name, "key": c.key} for c in r.control.contexts],
                    "frame_titles": list(r.control.frame_titles),
                    "visible": r.control.visible,
                }
                for r in ranked[:15]
            ],
            "reuse": reuse,
        }

    async def select_target(
        self,
        owner: str,
        draft_id: str,
        revision: int,
        step_id: str,
        session_id: str,
        candidate_id: str,
        *,
        element_id: str,
        meaning: str,
        provenance: str = "observed",
        include_region: bool = True,
    ) -> OperationDraft:
        draft = self.get(owner, draft_id)
        step = draft.step(step_id)
        async with self._sessions.operation(owner, session_id, "designer") as handle:
            observer = handle.observer
            reason = await observer.check_candidate(candidate_id)
            snapshot = observer.current_snapshot
            control = snapshot.control(candidate_id) if snapshot else None
            if reason is not None or control is None:
                raise CandidateStale(details={"reason": reason or "unknown_candidate"})
            spec = spec_from_control(control)
            if not include_region:
                spec = spec.model_copy(update={"region": None})
            resolution = await resolve_target(observer, spec)
        if resolution.outcome is not Outcome.RESOLVED:
            raise TargetNotUnique(
                details={
                    "outcome": resolution.outcome.value,
                    "reason": resolution.reason,
                    "candidates": len(resolution.candidates),
                }
            )
        existing = next((e for e in draft.elements.values() if e.target == spec), None)
        if existing is None:
            draft.add_element(element_id, meaning, spec, provenance)
            existing = draft.elements[element_id]
        step.element_id = existing.element_id
        step.provenance["target"] = Provenance(provenance)
        step.provenance["meaning"] = Provenance.HUMAN_VERIFIED
        step.confirmation, step.trial = None, None
        step.status = (
            StepStatus.TARGET_PROPOSED if step.status is not StepStatus.INTENT_ENTERED else step.status
        )
        step.move(StepStatus.TARGET_SELECTED)
        step.standard_text = standard_text(step.op or "read", existing.meaning, _value_of(step))
        return self._save(draft, revision)

    def configure_step(
        self, owner: str, draft_id: str, revision: int, step_id: str, **fields: Any
    ) -> OperationDraft:
        draft = self.get(owner, draft_id)
        step = draft.step(step_id)
        unknown = set(fields) - _CONFIGURABLE
        if unknown:
            raise PlanInvalid(details={"reason": "unknown_fields", "fields": sorted(unknown)})
        for key, value in fields.items():
            setattr(step, key, value)
            step.provenance[key] = Provenance.HUMAN_VERIFIED
        if "action_id" in fields and fields["action_id"] not in self._actions.actions:
            raise PlanInvalid(details={"reason": "unknown_action"})
        has_target = step.element_id is not None or (step.op == "invoke_approved_action" and step.action_id)
        step.reset()
        if has_target:
            step.status = StepStatus.TARGET_SELECTED
        if "standard_text" not in fields:
            meaning = (
                draft.elements[step.element_id].meaning
                if step.element_id in draft.elements
                else self._actions.actions[step.action_id].title
                if step.action_id in self._actions.actions
                else step.intent_text
            )
            step.standard_text = standard_text(step.op or "read", meaning, _value_of(step))
        draft.steps = list(draft.steps)
        return self._save(draft, revision)

    def confirm_step(
        self,
        owner: str,
        draft_id: str,
        revision: int,
        step_id: str,
        *,
        meaning: bool,
        target: bool,
        effect: bool,
        params: bool,
    ) -> OperationDraft:
        draft = self.get(owner, draft_id)
        step = draft.step(step_id)
        step.confirmation = Confirmation(
            meaning=meaning, target=target, effect=effect, params=params, by=owner
        )
        step.move(StepStatus.MEANING_AND_TARGET_CONFIRMED)
        draft.steps = list(draft.steps)
        return self._save(draft, revision)

    # ---- deneme ve test ---------------------------------------------------------------

    async def trial_step(
        self,
        owner: str,
        draft_id: str,
        revision: int,
        step_id: str,
        session_id: str,
        args: dict[str, str],
        acknowledge_effect: bool = False,
    ) -> OperationDraft:
        draft = self.get(owner, draft_id)
        step = draft.step(step_id)
        if step.effect(self._actions) == "mutating" and not acknowledge_effect:
            raise EffectNotAcknowledged()
        try:
            commands = compile_operation(draft, args, self._actions, steps=[step])
        except ValueError as exc:
            raise PlanInvalid(details={"reason": str(exc)}) from None
        step.move(StepStatus.TRIAL_REQUESTED)
        self._save(draft, revision)
        run = await self._runs.create(
            owner, session_id, f"trial-{draft.draft_id}-{step.step_id}-{draft.revision}", commands
        )
        run = await self._runs.wait(run.run_id, self._run_timeout_s)
        draft = self.get(owner, draft_id)
        step = draft.step(step_id)
        step.trial = TrialEvidence(
            run_id=run.run_id,
            run_status=run.status.value,
            verified=run.status is RunStatus.COMPLETED,
            detail=next((s.error_class for s in run.steps if s.error_class), None),
        )
        step.move(StepStatus.OBSERVED)
        draft.steps = list(draft.steps)
        return self._save(draft, draft.revision)

    def confirm_outcome(self, owner: str, draft_id: str, revision: int, step_id: str) -> OperationDraft:
        draft = self.get(owner, draft_id)
        step = draft.step(step_id)
        if step.trial is None or not step.trial.verified:
            raise DraftNotReady("Sistem sonucu doğrulamadan sonuç onaylanamaz; denemeyi tekrarlayın.")
        step.move(StepStatus.OUTCOME_CONFIRMED)
        step.move(StepStatus.READY_FOR_REVIEW)
        draft.steps = list(draft.steps)
        return self._save(draft, revision)

    async def fresh_session_test(
        self, owner: str, draft_id: str, revision: int, args: dict[str, str], entry_url: str
    ) -> OperationDraft:
        """Eski snapshot/locator olmadan yeni bir browser oturumunda bütün işlemi çalıştırır."""
        draft = self.get(owner, draft_id)
        if any(s.status is not StepStatus.READY_FOR_REVIEW for s in draft.steps) or not draft.steps:
            raise DraftNotReady("Bütün adımlar incelemeye hazır olmalı.")
        try:
            commands = compile_operation(draft, args, self._actions)
        except ValueError as exc:
            raise PlanInvalid(details={"reason": str(exc)}) from None
        view = await self._sessions.open(owner)
        try:
            async with self._sessions.operation(owner, view.session_id, "navigate") as handle:
                await handle.navigate(entry_url)
            run = await self._runs.create(
                owner,
                view.session_id,
                f"fresh-{draft.draft_id}-{revision}-{draft.content_hash()[:12]}",
                commands,
            )
            run = await self._runs.wait(run.run_id, self._run_timeout_s)
        finally:
            await self._sessions.close(owner, view.session_id)
        draft = self.get(owner, draft_id)
        draft.record_fresh_test(run_id=run.run_id, passed=run.status is RunStatus.COMPLETED)
        return self._save(draft, draft.revision)

    def validate(self, owner: str, draft_id: str) -> list[str]:
        return self.get(owner, draft_id).validation_issues(self._actions)


def _value_of(step: StepCard) -> str | None:
    return step.value_template or step.choice_template or step.key_template
