"""Katalog Tasarımcısı use case'leri (modelsiz, yönlendirilmiş). Taslaklar yalnız DraftRepository'ye yazılır.

Akış: niyet → kural tabanlı komut önerisi → (gözlem) hedef adayları → seçim (tekillik doğrulaması) →
anlam/hedef/etki/parametre ayrı onayları → deneme (gerçek etki olabilir; mutating için açık onay) →
sistem doğrulaması (P3 sonuç kontrolü) → kullanıcı sonucu onaylar → yeni oturum testi → incelemeye hazır.

R3 ekran tanımı: tasarımcı güncel gözlemden tanıma işaretleri seçer (kalıcı locator değil, anlamsal hedef),
mantıksal bölgeler işaretlerle kanıtlanır, tanım kaydedilmeden önce aynı çekirdekle (assess_screen) canlı
doğrulanır. Geçiş: eski (ekransız) yayımlanmış işlemden taslak açılır; yayın yerinde değişmez.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from agentask.application.errors import (
    CandidateStale,
    DependencyUnavailable,
    DraftNotFound,
    DraftNotReady,
    EffectNotAcknowledged,
    PlanInvalid,
    ScreenNotRecognized,
    SessionBusy,
    TargetNotUnique,
)
from agentask.application.observability import log_event
from agentask.application.ports.drafts import DraftRepository
from agentask.application.services.browser_sessions import BrowserSessionService
from agentask.application.services.observation import (
    ObservationService,
    assess_screen,
    resolve_target,
)
from agentask.application.services.publishing import PublishService
from agentask.application.services.runs import RunService
from agentask.domain import templating
from agentask.domain.actions import ActionSet, KnownBlocker
from agentask.domain.authoring import propose_op, rank_candidates, spec_from_control, standard_text
from agentask.domain.catalog import (
    CallSpec,
    Confirmation,
    MigrationSource,
    OperationDraft,
    ParameterDef,
    ParamSourceKind,
    Provenance,
    StepCard,
    StepStatus,
    TrialEvidence,
    compile_operation,
    component_inputs,
    requires_migration,
)
from agentask.domain.routes import ContextCheck, TransitionDef
from agentask.domain.runtime import RunStatus
from agentask.domain.screens import RegionDef, ScreenDef, static_issues
from agentask.domain.targeting import Outcome, TargetSpec, normalize_name

logger = logging.getLogger(__name__)
_CONFIGURABLE = {
    "op",
    "value_template",
    "choice_template",
    "key_template",
    "navigation",
    "action_id",
    "action_params",
    "success_check",
    "choice_value",
    "choice_effect",
    "checked",
    "autocomplete",
    "search_text",
    "choice_set",
    "date_format",
    "file_types",
    "next_labels",
    "end_text",
    "in_found_row",
    "result_text",
    "standard_text",
    "screen_id",  # R4: adımın beklenen ekranı
    "transition_id",  # R4: adımın tetiklediği onaylı geçiş
}


@dataclass(slots=True)
class _FreshWait:
    """Elle giriş bekleyen yeni oturum testi. Değerler bellekte kalır; diske veya loga yazılmaz."""

    draft_id: str
    owner: str
    session_id: str
    content_hash: str
    args: dict[str, str]
    expires_at: float
    run_id: str | None = None
    message: str = ""
    busy: bool = False


class DesignerService:
    def __init__(
        self,
        drafts: DraftRepository,
        sessions: BrowserSessionService,
        observation: ObservationService,
        runs: RunService,
        actions: ActionSet,
        run_timeout_s: float,
        publishing: PublishService | None = None,
        fresh_login_timeout_s: int = 600,
    ) -> None:
        self._publishing = publishing
        self._fresh_login_timeout_s = fresh_login_timeout_s
        self._fresh_waits: dict[str, _FreshWait] = {}
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
        self._log_saved(draft)
        return draft

    @staticmethod
    def _log_saved(draft: OperationDraft) -> None:
        log_event(
            logger,
            "draft_saved",
            audit=True,
            outcome="success",
            actor=draft.created_by,
            resource_type="draft",
            resource_id=draft.draft_id,
            application_id=draft.application_id,
            operation_id=draft.operation_id,
            revision=draft.revision,
        )

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
        self._log_saved(draft)
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

    def remove_parameter(self, owner: str, draft_id: str, revision: int, name: str) -> OperationDraft:
        """Kullanılmayan parametreyi kaldırır. Bir adım, geçiş veya bağlam koşulu kullanıyorsa reddedilir."""
        draft = self.get(owner, draft_id)
        templates = (
            [t for s in draft.steps for t in s.templates()]
            + [c.value_template for t in draft.transitions for c in t.completion]
            + [c.value_template for c in draft.start_context]
        )
        if any(name in templating.placeholders(t) for t in templates):
            raise PlanInvalid(
                "Bu değer bir adımda kullanılıyor; önce adımı değiştirin.",
                details={"reason": "parameter_in_use"},
            )
        draft.parameters = [p for p in draft.parameters if p.name != name]
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
        in_found_row: bool = False,
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
            # Satırdaki kontrol tasarımda bulunduğu satırla tekil çözülür; katalogda satır değeri tutulmaz.
            resolution = await resolve_target(observer, _in_row(spec, control, in_found_row))
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
        step.in_found_row = in_found_row
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
        if "action_id" in fields:
            problem = self._actions.problem(
                fields["action_id"], self._actions.fingerprint(fields["action_id"]), draft.application_id
            )
            if problem is not None:
                raise PlanInvalid(details={"reason": problem})
            # Onay, deneme ve yayın bu davranış özetine bağlanır (değişirse yeniden test ve onay gerekir).
            step.action_hash = self._actions.fingerprint(fields["action_id"])
        if fields.get("screen_id") and fields["screen_id"] not in draft.all_screens():
            raise PlanInvalid(
                "Adım için seçilen ekran taslakta tanımlı değil.", details={"reason": "unknown_screen"}
            )
        if fields.get("transition_id") and draft.transition(fields["transition_id"]) is None:
            raise PlanInvalid(
                "Seçilen geçiş taslakta tanımlı değil.", details={"reason": "unknown_transition"}
            )
        has_target = (
            step.element_id is not None
            or (step.op == "invoke_approved_action" and step.action_id)
            or (step.op == "follow_transition" and step.transition_id)
        )
        step.reset()
        if has_target:
            step.status = StepStatus.TARGET_SELECTED
        if "standard_text" not in fields:
            transition = draft.transition(step.transition_id)
            target = draft.all_screens().get(transition.to_screen) if transition else None
            meaning = (
                draft.elements[step.element_id].meaning
                if step.element_id in draft.elements
                else self._actions.actions[step.action_id].title
                if step.action_id in self._actions.actions
                else target.title
                if step.op == "follow_transition" and target is not None
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
        if step.effect(self._actions) in {"mutating", "component", "unknown"} and not acknowledge_effect:
            raise EffectNotAcknowledged()
        if step.changes_screen and not acknowledge_effect:
            # Alan keşfi asla geçiş tetiklemez; deneme tarayıcıda gerçek tıklama yapar → açık onay.
            raise EffectNotAcknowledged(
                "Bu deneme tarayıcıda onaylı ekran geçişini tetikler (ekran değişir); bunu açıkça onaylayın."
            )
        try:
            # Ekran tanımlıysa tek adım denemesi de ekran doğrulamasıyla başlar; henüz tanımlanmadıysa deneme
            # yapılabilir ama taslak ekran tanımı olmadan incelemeye/onaya hazır olamaz (screen_missing).
            commands = compile_operation(
                draft,
                args,
                self._actions,
                steps=_trial_steps(draft, step),
                screen_check="if_present",
                components=await self._lookup(draft),
            )
        except ValueError as exc:
            raise PlanInvalid(details={"reason": str(exc)}) from None
        step.move(StepStatus.TRIAL_REQUESTED)
        self._save(draft, revision)
        run = await self._runs.create(
            owner,
            session_id,
            f"trial-{draft.draft_id}-{step.step_id}-{draft.revision}",
            commands,
            title=f"Deneme: {draft.title}",
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
        if draft.screen is None:
            raise DraftNotReady("Yeni oturum testi için önce ekran tanımı ekleyin.")
        try:
            commands = compile_operation(draft, args, self._actions, components=await self._lookup(draft))
        except ValueError as exc:
            raise PlanInvalid(details={"reason": str(exc)}) from None
        # Eski snapshot/locator taşınmasın diye ayrı bir browser context gerekir. Bu, kullanıcının etkileşimli
        # oturum kotasına sayılmayan, toplam kapasite içindeki geçici doğrulama oturumudur; ana tasarım
        # oturumuna
        # ve başka kullanıcıların oturumlarına dokunulmaz; blok sonunda (hata/iptal/zaman aşımı dahil)
        # kapanır.
        async with self._sessions.verification_session(owner) as view:
            async with self._sessions.operation(
                owner, view.session_id, "navigate", allow_verification=True
            ) as handle:
                await handle.navigate(entry_url)
            run = await self._runs.create(
                owner,
                view.session_id,
                f"fresh-{draft.draft_id}-{secrets.token_hex(6)}",
                commands,
                allow_verification=True,
                title=f"Yeni oturum testi: {draft.title}",
            )
            run = await self._runs.wait(run.run_id, self._run_timeout_s)
            if not run.is_terminal and run.status is not RunStatus.OUTCOME_UNKNOWN:
                # Zaman aşımı: yeni adım başlatılmasın, run durumunu yazsın; ardından oturum kapanır.
                await self._runs.cancel(owner, run.run_id, by="system_timeout")
                run = await self._runs.wait(run.run_id, 10)
        draft = self.get(owner, draft_id)
        draft.record_fresh_test(run_id=run.run_id, passed=run.status is RunStatus.COMPLETED)
        return self._save(draft, draft.revision)

    # ---- yeni oturum testi: hedef uygulamaya elle giriş ---------------------------------------

    def _fresh_plan(self, draft: OperationDraft) -> None:
        if any(s.status is not StepStatus.READY_FOR_REVIEW for s in draft.steps) or not draft.steps:
            raise DraftNotReady("Bütün adımlar incelemeye hazır olmalı.")
        if draft.screen is None:
            raise DraftNotReady("Yeni oturum testi için önce ekran tanımı ekleyin.")

    async def _compiled(self, draft: OperationDraft, args: dict[str, str]) -> list[dict[str, Any]]:
        try:
            return compile_operation(draft, args, self._actions, components=await self._lookup(draft))
        except ValueError as exc:
            raise PlanInvalid(details={"reason": str(exc)}) from None

    def _start_screen(self, draft: OperationDraft) -> ScreenDef:
        screens = draft.all_screens()
        first = draft.step_screen_id(draft.steps[0]) or (draft.screen.screen_id if draft.screen else "")
        return screens[first]

    async def _screen_recognized(self, wait: _FreshWait, draft: OperationDraft) -> bool:
        async with self._sessions.operation(
            wait.owner, wait.session_id, "observe", allow_verification=True
        ) as handle:
            return (await assess_screen(handle.observer, self._start_screen(draft))).recognized

    async def _login_page_open(self, wait: _FreshWait) -> bool:
        async with self._sessions.operation(
            wait.owner, wait.session_id, "observe", allow_verification=True
        ) as handle:
            path = await handle.driver.current_path()
        return any(path.startswith(p) for p in self._actions.profile.session_lost_path_prefixes)

    async def _drop_wait(self, wait: _FreshWait) -> None:
        self._fresh_waits.pop(wait.draft_id, None)
        await self._sessions.close_verification(wait.owner, wait.session_id)

    async def reap_fresh_waits(self) -> int:
        """Süresi dolan elle giriş beklemeleri kapatılır; test sonucu yazılmaz."""
        now = time.monotonic()
        expired = [w for w in self._fresh_waits.values() if w.expires_at <= now and not w.busy]
        for wait in expired:
            await self._drop_wait(wait)
        return len(expired)

    def fresh_wait(self, draft: OperationDraft) -> dict[str, Any] | None:
        wait = self._fresh_waits.get(draft.draft_id)
        if wait is None or wait.owner != draft.created_by:
            return None
        return {
            "message": wait.message,
            "expires_in_s": max(0, int(wait.expires_at - time.monotonic())),
            "resuming": wait.run_id is not None,
            "busy": wait.busy,
        }

    async def begin_fresh_test(
        self, owner: str, draft_id: str, args: dict[str, str], entry_url: str
    ) -> OperationDraft:
        """Yeni oturumu açar ve başlangıç adresine gider. Beklenen ekran açılmışsa test hemen koşar; değilse
        kullanıcı açılan pencerede elle giriş yapana kadar bekler. Kimlik bilgisi bu kodun içinden geçmez."""
        draft = self.get(owner, draft_id)
        self._fresh_plan(draft)
        await self._compiled(draft, args)  # eksik argüman oturum açılmadan bildirilsin
        previous = self._fresh_waits.get(draft_id)
        if previous is not None:
            if previous.busy:
                raise SessionBusy()
            await self._drop_wait(previous)
        view = await self._sessions.open(owner, purpose="verification")
        wait = _FreshWait(
            draft_id=draft_id,
            owner=owner,
            session_id=view.session_id,
            content_hash=draft.content_hash(),
            args=dict(args),
            expires_at=time.monotonic() + self._fresh_login_timeout_s,
        )
        self._fresh_waits[draft_id] = wait
        try:
            async with self._sessions.operation(
                owner, view.session_id, "navigate", allow_verification=True
            ) as handle:
                await handle.navigate(entry_url)
            if await self._screen_recognized(wait, draft):
                return await self._run_waited(wait, draft)
        except Exception:
            await self._drop_wait(wait)
            raise
        wait.message = (
            "Açılan tarayıcı penceresinde uygulamaya giriş yapın ve başlangıç ekranını açın; sonra "
            "“Giriş yaptım, devam et” düğmesine basın."
        )
        return self.get(owner, draft_id)

    async def _run_waited(self, wait: _FreshWait, draft: OperationDraft) -> OperationDraft:
        commands = await self._compiled(draft, wait.args)
        wait.busy = True
        try:
            run = await self._runs.create(
                wait.owner,
                wait.session_id,
                f"fresh-{draft.draft_id}-{secrets.token_hex(6)}",
                commands,
                allow_verification=True,
                title=f"Yeni oturum testi: {draft.title}",
            )
            wait.run_id = run.run_id
            return await self._settle_wait(wait, run.run_id)
        finally:
            wait.busy = False

    async def _settle_wait(self, wait: _FreshWait, run_id: str) -> OperationDraft:
        run = await self._runs.wait(run_id, self._run_timeout_s)
        if run.status is RunStatus.PAUSED_SESSION and run.status_reason == "SESSION_EXPIRED":
            # Giriş işlem sırasında düştü: sonuç yazılmaz; devamda yapılmış adımlar yeniden oynatılmaz.
            wait.expires_at = time.monotonic() + self._fresh_login_timeout_s
            wait.message = (
                "Uygulama oturumu işlem sırasında sona erdi. Pencerede yeniden giriş yapıp açık kalan ekrana "
                "dönün; devam edince tamamlanmış adımlar tekrar yapılmaz."
            )
            return self.get(wait.owner, wait.draft_id)
        if not run.is_terminal and run.status is not RunStatus.OUTCOME_UNKNOWN:
            await self._runs.cancel(wait.owner, run.run_id, by="system_timeout")
            run = await self._runs.wait(run.run_id, 10)
        await self._drop_wait(wait)
        draft = self.get(wait.owner, wait.draft_id)
        if draft.content_hash() != wait.content_hash:
            return draft  # test sırasında tanım değişti; bu sonuç yeni tanım için geçerli değil
        draft.record_fresh_test(run_id=run.run_id, passed=run.status is RunStatus.COMPLETED)
        return self._save(draft, draft.revision)

    async def continue_fresh_test(self, owner: str, draft_id: str) -> OperationDraft:
        draft = self.get(owner, draft_id)
        wait = self._fresh_waits.get(draft_id)
        if wait is None or wait.owner != owner:
            raise DraftNotReady("Bekleyen yeni oturum testi yok veya süresi doldu; testi yeniden başlatın.")
        if wait.busy:
            raise SessionBusy()
        if wait.expires_at <= time.monotonic() or not self._sessions.is_open(owner, wait.session_id):
            await self._drop_wait(wait)
            raise DraftNotReady("Giriş bekleme süresi doldu veya pencere kapandı; testi yeniden başlatın.")
        if draft.content_hash() != wait.content_hash:
            await self._drop_wait(wait)
            raise DraftNotReady("Taslak değişti; yeni oturum testini yeniden başlatın.")
        wait.busy = True
        try:
            if await self._login_page_open(wait):
                wait.message = "Uygulama hâlâ giriş ekranında. Girişi tamamlayıp yeniden deneyin."
                return draft
            if wait.run_id is None:
                if not await self._screen_recognized(wait, draft):
                    wait.message = (
                        "Beklenen başlangıç ekranı görünmüyor; işlem başlatılmadı. Pencerede doğru ekranı "
                        "açıp yeniden deneyin."
                    )
                    return draft
            else:
                await self._runs.resume(owner, wait.run_id, wait.session_id, allow_verification=True)
                return await self._settle_wait(wait, wait.run_id)
        finally:
            wait.busy = False
        return await self._run_waited(wait, draft)

    async def cancel_fresh_test(self, owner: str, draft_id: str) -> OperationDraft:
        draft = self.get(owner, draft_id)
        wait = self._fresh_waits.get(draft_id)
        if wait is None or wait.owner != owner:
            return draft
        if wait.busy:
            raise SessionBusy()
        if wait.run_id is not None:
            await self._runs.cancel(owner, wait.run_id, by="user")
        await self._drop_wait(wait)
        return self.get(owner, draft_id)

    def fresh_test_failure(self, draft: OperationDraft) -> dict[str, Any] | None:
        """Başarısız yeni oturum testinin nedeni: run kaydındaki ilk hatalı adımdan (giriş, başlangıç
        ekranı, hedef çözümü, değer doğrulaması). Yalnız hata sınıfı ve adım türü kullanılır; değer ve oturum
        bilgisi döndürülmez."""
        test = draft.fresh_test
        if test is None or test.passed:
            return None
        try:
            run = self._runs.get(draft.created_by, test.run_id)
        except Exception:
            return {
                "code": "run_missing",
                "step": None,
                "run_id": test.run_id,
                **_FRESH_REASONS["run_missing"],
            }
        failed = next((s for s in run.steps if s.error_class), None)
        code = (
            failed.error_class
            if failed and failed.error_class in _FRESH_REASONS
            else ("timeout" if failed is None and run.status is RunStatus.CANCELLED else "other")
        )
        return {
            "code": code,
            "error_class": failed.error_class if failed else None,
            "step": failed.index + 1 if failed else None,
            "op": failed.command.get("op") if failed else None,
            "run_status": run.status.value,
            "run_id": run.run_id,
            **_FRESH_REASONS[code],
        }

    def validate(self, owner: str, draft_id: str) -> list[str]:
        return self.get(owner, draft_id).validation_issues(self._actions)

    # ---- ekran tanımı (R3) -------------------------------------------------------------

    async def define_screen(
        self,
        owner: str,
        draft_id: str,
        revision: int,
        session_id: str,
        *,
        screen_id: str,
        title: str,
        marker_candidate_ids: list[str],
        regions: list[dict[str, str]] | None = None,
        absent_markers: list[dict[str, Any]] | None = None,
    ) -> tuple[OperationDraft, dict[str, Any]]:
        """Güncel gözlemdeki adaylardan anlamsal tanıma işaretleri kurar ve tanımı kaydetmeden önce aynı
        ekran çekirdeğiyle canlı doğrular. Aday kimlikleri yalnız bu istekte kullanılır, saklanmaz."""
        draft = self.get(owner, draft_id)
        if not marker_candidate_ids:
            raise PlanInvalid(details={"reason": "markers_required"})
        async with self._sessions.operation(owner, session_id, "designer") as handle:
            observer = handle.observer
            markers: list[TargetSpec] = []
            for candidate_id in marker_candidate_ids:
                reason = await observer.check_candidate(candidate_id)
                snapshot = observer.current_snapshot
                control = snapshot.control(candidate_id) if snapshot else None
                if reason is not None or control is None:
                    raise CandidateStale(details={"reason": reason or "unknown_candidate"})
                markers.append(spec_from_control(control))
            region_defs = _regions(regions, markers)
            screen = ScreenDef(
                screen_id=screen_id,
                title=title,
                regions=region_defs,
                markers=markers,
                absent_markers=[TargetSpec.model_validate(a) for a in absent_markers or []],
            )
            verdict = await assess_screen(observer, screen)
        on_screen = [
            s.element_id
            for s in draft.steps
            if s.element_id and (not draft.is_multi_screen or draft.step_screen_id(s) in {None, screen_id})
        ]
        issues = [
            i
            for i in static_issues(
                screen, {e: draft.elements[e].target for e in on_screen if e in draft.elements}, on_screen
            )
            if i == "screen_markers_only_targets"
        ]
        if issues:
            raise PlanInvalid(
                "Ekran tanıma işlemin kendi hedefine dayanamaz; adımlarda kullanılmayan en az bir "
                "işaret seçin.",
                details={"reason": issues[0]},
            )
        if not verdict.recognized:
            raise ScreenNotRecognized(verdict.explanation, details={"screen": verdict.to_dict()})
        existing = draft.all_screens().get(screen_id)
        # Ana pencereye dönüşün hedefi başlangıç ekranı olabilir; yalnız ileri geçişler "hedef" sayılır.
        is_target = any(
            t.to_screen == screen_id and t.trigger.kind != "window_return" for t in draft.transitions
        )
        if (draft.screen is None and not is_target) or (
            draft.screen is not None and draft.screen.screen_id == screen_id
        ):
            draft.screen = screen  # ilk tanımlanan ekran başlangıç ekranıdır
        elif existing is not None:
            draft.extra_screens = [screen if s.screen_id == screen_id else s for s in draft.extra_screens]
        else:
            draft.extra_screens = [*draft.extra_screens, screen]
        if existing is not None and existing != screen:
            _invalidate(
                draft, lambda s: draft.step_screen_id(s) == screen_id or _uses_screen(draft, s, screen_id)
            )
        return self._save(draft, revision), verdict.to_dict()

    async def verify_screen(
        self, owner: str, draft_id: str, session_id: str, screen_id: str | None = None
    ) -> dict[str, Any]:
        """İnceleme: seçilen ekran tanımını güncel ekranda aynı çekirdekle doğrular; kaydetmez."""
        draft = self.get(owner, draft_id)
        screen = draft.all_screens().get(screen_id) if screen_id else draft.screen
        if screen is None:
            raise DraftNotReady("Taslakta bu ekran tanımı yok.")
        async with self._sessions.operation(owner, session_id, "designer") as handle:
            verdict = await assess_screen(handle.observer, screen)
        return verdict.to_dict()

    def remove_screen(
        self, owner: str, draft_id: str, revision: int, screen_id: str | None = None
    ) -> OperationDraft:
        draft = self.get(owner, draft_id)
        if screen_id is None or (draft.screen is not None and draft.screen.screen_id == screen_id):
            if draft.extra_screens:
                raise PlanInvalid(
                    "Başlangıç ekranı kaldırılmadan önce diğer ekranları kaldırın.",
                    details={"reason": "start_screen_in_use"},
                )
            draft.screen = None
        else:
            draft.extra_screens = [s for s in draft.extra_screens if s.screen_id != screen_id]
        return self._save(draft, revision)

    # ---- onaylı ekran geçişleri (R4) -----------------------------------------------------

    async def define_transition(
        self,
        owner: str,
        draft_id: str,
        revision: int,
        *,
        transition_id: str,
        from_screen: str,
        to_screen: str,
        trigger_kind: str,
        session_id: str | None = None,
        trigger_candidate_id: str | None = None,
        timeout_ms: int = 10_000,
        completion: list[dict[str, Any]] | None = None,
        trigger_in_found_row: bool = False,
        window: str | None = None,
        window_origin: str | None = None,
        close: bool = True,
    ) -> OperationDraft:
        """Geçiş tanımı. Kontrol tetikleyicisi güncel gözlemden anlamsal hedefe çevrilir ve tekil çözülmesi
        doğrulanır; HİÇBİR tıklama yapılmaz (deneme ayrı ve açık onaylıdır)."""
        draft = self.get(owner, draft_id)
        # Ekranlar henüz tanıtılmamış olabilir (yeni tasarımcı: geçiş, hedef ekrana gidilmeden kaydedilir).
        # Tanıtılmamış uç `transition_unknown_screen` eksikliği olarak kalır; taslak bu durumda denenemez,
        # incelemeye/onaya hazır olamaz ve derlenemez. Tetikleyici yine şimdi tekil çözülmelidir.
        trigger: dict[str, Any] = {"kind": trigger_kind}
        if trigger_kind == "window_return":
            trigger["close"] = close
        if trigger_kind == "control":
            if not session_id or not trigger_candidate_id:
                raise PlanInvalid(details={"reason": "trigger_candidate_required"})
            async with self._sessions.operation(owner, session_id, "designer") as handle:
                observer = handle.observer
                reason = await observer.check_candidate(trigger_candidate_id)
                snapshot = observer.current_snapshot
                control = snapshot.control(trigger_candidate_id) if snapshot else None
                if reason is not None or control is None:
                    raise CandidateStale(details={"reason": reason or "unknown_candidate"})
                spec = spec_from_control(control)
                resolution = await resolve_target(observer, _in_row(spec, control, trigger_in_found_row))
            if resolution.outcome is not Outcome.RESOLVED:
                raise TargetNotUnique(
                    details={"outcome": resolution.outcome.value, "reason": resolution.reason}
                )
            trigger["target"] = spec.model_dump(mode="json", exclude_none=True)
        transition = TransitionDef.model_validate(
            {
                "transition_id": transition_id,
                "from_screen": from_screen,
                "to_screen": to_screen,
                "trigger": trigger,
                "timeout_ms": timeout_ms,
                "completion": completion or [],
                "window": window,
                "window_origin": window_origin,
            }
        )
        previous = draft.transition(transition_id)
        draft.transitions = [t for t in draft.transitions if t.transition_id != transition_id] + [transition]
        if previous is not None and previous != transition:
            _invalidate(draft, lambda s: s.transition_id == transition_id)
        return self._save(draft, revision)

    def remove_transition(
        self, owner: str, draft_id: str, revision: int, transition_id: str
    ) -> OperationDraft:
        draft = self.get(owner, draft_id)
        draft.transitions = [t for t in draft.transitions if t.transition_id != transition_id]
        _invalidate(draft, lambda s: s.transition_id == transition_id)
        return self._save(draft, revision)

    def set_start_context(
        self, owner: str, draft_id: str, revision: int, checks: list[dict[str, Any]]
    ) -> OperationDraft:
        draft = self.get(owner, draft_id)
        draft.start_context = [ContextCheck.model_validate(c) for c in checks]
        return self._save(draft, revision)

    def set_optional_dialogs(
        self, owner: str, draft_id: str, revision: int, dialogs: list[dict[str, Any]]
    ) -> OperationDraft:
        """Yalnız veri değiştirmediği beyan edilen pencereler; tanım değişince adımlar yeniden denenir."""
        draft = self.get(owner, draft_id)
        parsed = [KnownBlocker.model_validate(d) for d in dialogs]
        if parsed != draft.optional_dialogs:
            draft.optional_dialogs = parsed
            _invalidate(draft, lambda _: True)
        return self._save(draft, revision)

    # ---- E: sürümlü bileşenler ------------------------------------------------------------

    async def _lookup(self, draft: OperationDraft) -> Any:
        if not any(s.call for s in draft.steps):
            return None
        return await self._pub().component_lookup(draft.application_id, draft)

    async def available_components(self, owner: str, draft_id: str) -> list[dict[str, Any]]:
        draft = self.get(owner, draft_id)
        return await self._pub().available_components(draft.application_id, exclude=draft.operation_id)

    async def set_call(
        self,
        owner: str,
        draft_id: str,
        revision: int,
        step_id: str,
        *,
        operation_id: str,
        component_revision: int,
        arguments: dict[str, str],
    ) -> OperationDraft:
        """Adımı yayımlanmış bir işlemin belirli revizyonuna pinli çağrı yapar. Sözleşme özeti (girdi, çıktı,
        ekranlar) sunucuda değişmez revizyondan çıkarılır; istemci hash veya ekran bildiremez."""
        draft = self.get(owner, draft_id)
        step = draft.step(step_id)
        if operation_id == draft.operation_id:
            raise PlanInvalid(
                "Bir işlem kendini bileşen olarak çağıramaz.", details={"reason": "component_cycle"}
            )
        component = await self._pub().component(draft.application_id, operation_id, component_revision)
        if component is None:
            raise PlanInvalid(
                "Bu bileşen revizyonu yayımlanmış katalogda bulunamadı.",
                details={"reason": "component_missing"},
            )
        lookup = await self._pub().component_lookup(draft.application_id, component)
        try:  # döngü/derinlik ve iç bileşen bütünlüğü şimdi denetlenir (çalıştırmadan)
            compile_operation(
                component,
                {n: "x" for n in component_inputs(component)},
                self._actions,
                components=lookup,
            )
        except ValueError as exc:
            reason = str(exc).split(":")[0]
            if reason.startswith("component_") or reason == "prior_output_unavailable":
                raise PlanInvalid(details={"reason": reason}) from None
        if any(s.call is not None and s.call.operation_id == draft.operation_id for s in component.steps):
            raise PlanInvalid(details={"reason": "component_cycle"})
        try:
            spec = CallSpec.of(component, component_revision, arguments)
        except ValueError as exc:
            raise PlanInvalid(details={"reason": str(exc)}) from None
        step.op = "call_operation"
        step.call = spec
        step.element_id, step.value_template, step.transition_id = None, None, None
        step.provenance["call"] = Provenance.HUMAN_VERIFIED
        step.reset()
        step.status = StepStatus.TARGET_SELECTED
        step.standard_text = f"'{component.title}' bileşenini çalıştır (sürüm {component_revision})"[:500]
        draft.steps = list(draft.steps)
        return self._save(draft, revision)

    async def component_updates(self, owner: str, draft_id: str) -> list[dict[str, Any]]:
        """Pinli bileşenlerin etkin yayındaki daha yeni revizyonları ve yükseltme etkisi. Salt okunur."""
        draft = self.get(owner, draft_id)
        pub = self._pub()
        release = await pub.active_release(draft.application_id)
        latest = {e.operation_id: e for e in (release.operations if release else [])}
        out: list[dict[str, Any]] = []
        for index, step in enumerate(draft.steps):
            used = {p.prior_output for p in draft.parameters if p.prior_step == index and p.prior_output}
            call = step.call
            entry = latest.get(call.operation_id) if call else None
            if call is None or entry is None or entry.revision == call.revision:
                continue
            new = await pub.component(draft.application_id, call.operation_id, entry.revision)
            if new is None:
                continue
            spec = CallSpec.of(new, entry.revision, call.arguments)
            needs = [n for n in spec.inputs if n not in call.arguments]
            lost = sorted(o for o in used if o in call.outputs and o not in spec.outputs)
            screen = (spec.start_screen, spec.end_screen) != (call.start_screen, call.end_screen)
            out.append(
                {
                    "step_id": step.step_id,
                    "step": index + 1,
                    "operation_id": call.operation_id,
                    "pinned_revision": call.revision,
                    "latest_revision": entry.revision,
                    "new_inputs": needs,
                    "removed_inputs": sorted(set(call.inputs) - set(spec.inputs)),
                    "lost_outputs": lost,
                    "screen_changed": screen,
                    "compatible": not needs and not lost and not screen,
                    # yükseltme adım onayını, denemeyi ve yeni oturum testini sıfırlar
                    "retest_required": True,
                }
            )
        return out

    # ---- eski yayın geçişi (R3) ----------------------------------------------------------

    def _pub(self) -> PublishService:
        if self._publishing is None:
            raise DependencyUnavailable("Yayımlanmış katalog yok (CATALOG_BACKEND=disabled).")
        return self._publishing

    async def migration_candidates(self, application_id: str) -> dict[str, Any]:
        """Etkin yayında ekran tanımı olmayan (geçiş gerektiren) işlemler. Salt okunur."""
        pub = self._pub()
        release = await pub.active_release(application_id)
        if release is None:
            return {"release_id": None, "operations": []}
        out = []
        for entry in release.operations:
            rev = await pub.operation(application_id, entry)
            if rev is not None and requires_migration(rev.definition):
                out.append(
                    {
                        "operation_id": entry.operation_id,
                        "revision": entry.revision,
                        "content_hash": entry.content_hash,
                        "title": rev.definition.get("title"),
                        "schema_version": rev.schema_version,
                    }
                )
        return {"release_id": release.release_id, "operations": out}

    async def start_migration(self, owner: str, application_id: str, operation_id: str) -> OperationDraft:
        """Eski yayımlanmış revizyondan geçiş taslağı açar. Yayın, revizyon ve aktif pointer DEĞİŞMEZ;
        taslak ekran tanımı, yeni oturum testi ve hash-bağlı yeniden onay olmadan yayımlanamaz."""
        pub = self._pub()
        release = await pub.active_release(application_id)
        entry = (
            next((e for e in release.operations if e.operation_id == operation_id), None) if release else None
        )
        if release is None or entry is None:
            raise PlanInvalid(details={"reason": "operation_not_in_release"})
        rev = await pub.operation(application_id, entry)
        if rev is None:
            raise PlanInvalid(details={"reason": "revision_missing"})
        if not requires_migration(rev.definition):
            raise PlanInvalid(
                "Bu işlemin yayında zaten ekran tanımı var; geçiş gerekmiyor.",
                details={"reason": "migration_not_required"},
            )
        draft = OperationDraft.from_definition(rev.definition, created_by=owner)
        draft.migrated_from = MigrationSource(
            release_id=release.release_id,
            operation_id=operation_id,
            revision=rev.revision,
            content_hash=rev.content_hash,
        )
        for step in draft.steps:
            step.intent_text = (step.standard_text or step.op or "")[:500]
        draft.steps = list(draft.steps)
        self._drafts.create(draft)
        return draft


_FRESH_REASONS: dict[str, dict[str, str]] = {
    "SESSION_EXPIRED": {
        "stage": "giriş",
        "reason": "Yeni test oturumu uygulamaya giriş yapılmamış olarak açıldı; başlangıç adresi giriş "
        "ekranını gösterdi. Bu test eski ekran/oturum bilgisi taşınmasın diye sizin tarayıcı oturumunuzu ve "
        "girişinizi kullanmaz.",
        "next": "Başlangıç adresini, yeni oturumda girişi de yapan bir adres olarak verip testi yeniden "
        "çalıştırın.",
    },
    "SCREEN_NOT_RECOGNIZED": {
        "stage": "başlangıç ekranı",
        "reason": "Başlangıç adresi beklenen ekranı açmadı; ekran tanıma işaretleri bulunamadı.",
        "next": "Başlangıç adresini alanların bulunduğu ekrana ayarlayıp testi yeniden çalıştırın.",
    },
    "RECORD_CONTEXT_MISMATCH": {
        "stage": "başlangıç ekranı",
        "reason": "Ekran türü doğru ancak açılan kayıt beklenen kayıt değil.",
        "next": "Başlangıç adresinin doğru kaydı açtığını kontrol edin.",
    },
    "TARGET_NOT_FOUND": {
        "stage": "hedef çözümü",
        "reason": "Alan yeni oturumda bulunamadı.",
        "next": "Ekranı ve alan seçimini kontrol edin; gerekirse alanı yeniden seçip taslağı kaydedin.",
    },
    "TARGET_AMBIGUOUS": {
        "stage": "hedef çözümü",
        "reason": "Alan yeni oturumda birden fazla adayla eşleşti; yanlış alana yazmamak için durduruldu.",
        "next": "Bölümü belli olan bir alan seçip taslağı yeniden kaydedin.",
    },
    "TARGET_BLOCKED": {
        "stage": "hedef çözümü",
        "reason": "Alan bir pencere veya katmanın arkasında kaldı.",
        "next": "Başlangıç ekranında açık pencere olmadığından emin olup yeniden deneyin.",
    },
    "TARGET_NOT_READY": {
        "stage": "hedef çözümü",
        "reason": "Alan süre içinde kullanılabilir olmadı.",
        "next": "Ekranın tam yüklendiğini kontrol edip yeniden deneyin.",
    },
    "VERIFICATION_FAILED": {
        "stage": "değer doğrulaması",
        "reason": "Değer yazıldı ancak alanda beklenen değer doğrulanamadı.",
        "next": "Alanın biçim kurallarını (uzunluk, rakam) ve deneme değerini kontrol edin.",
    },
    "UNKNOWN_DIALOG": {
        "stage": "başlangıç ekranı",
        "reason": "Beklenmeyen bir tarayıcı/sayfa penceresi açıldı; kapatılmadı.",
        "next": "Uygulamadaki pencerenin nedenini giderip yeniden deneyin.",
    },
    "NEW_WINDOW": {
        "stage": "başlangıç ekranı",
        "reason": "Yeni pencere/sekme açıldı; otomatik geçilmedi.",
        "next": "Başlangıç adresinin yeni pencere açmadığını kontrol edin.",
    },
    "timeout": {
        "stage": "süre",
        "reason": "Test süre sınırı içinde tamamlanmadı ve durduruldu.",
        "next": "Uygulamanın yanıt verdiğini kontrol edip testi yeniden çalıştırın.",
    },
    "run_missing": {
        "stage": "kayıt",
        "reason": "Testin çalışma kaydı bulunamadı.",
        "next": "Yeni oturum testini yeniden çalıştırın.",
    },
    "other": {
        "stage": "yürütme",
        "reason": "Test tamamlanamadı.",
        "next": "Teknik ayrıntıdaki hata sınıfını kontrol edip testi yeniden çalıştırın.",
    },
}


def _in_row(spec: TargetSpec, control: Any, enabled: bool) -> TargetSpec:
    if not enabled:
        return spec
    key = next((c.key for c in control.contexts if c.kind == "table_row" and c.key), None)
    if key is None:
        raise PlanInvalid(
            "Seçilen kontrol bir tablo satırında değil.", details={"reason": "not_in_table_row"}
        )
    return spec.model_copy(update={"row_key": key})


def _trial_steps(draft: OperationDraft, step: StepCard) -> list[StepCard]:
    """Tek adım denemesi. Adım önceki bir okuma çıktısına bağlıysa kaynak okuma adımı da (etkisiz) önce
    çalışır; değer tahmin edilmez, gerçek okumadan gelir."""
    names = {n for t in step.templates() for n in templating.placeholders(t)}
    sources = sorted(
        {
            p.prior_step
            for p in draft.parameters
            if p.name in names and p.source is ParamSourceKind.PRIOR_OUTPUT and p.prior_step is not None
        }
    )
    index = draft.steps.index(step)
    reads = [draft.steps[i] for i in sources if i < index and draft.steps[i].op == "read"]
    # Bulunan satırda çalışan adım, kaydı bulan adım olmadan denenemez (bulma etkisizdir).
    finder = (
        [next(s for s in reversed(draft.steps[:index]) if s.op == "find_record")]
        if step.in_found_row and any(s.op == "find_record" for s in draft.steps[:index])
        else []
    )
    return [*reads, *finder, step]


def _uses_screen(draft: OperationDraft, step: StepCard, screen_id: str) -> bool:
    transition = draft.transition(step.transition_id)
    return transition is not None and screen_id in {transition.from_screen, transition.to_screen}


def _invalidate(draft: OperationDraft, affected: Any) -> None:
    """Ekran/geçiş tanımı değişince ilgili adımların onay ve denemesi geçersizdir (hedef seçimi korunur)."""
    for step in draft.steps:
        if affected(step) and step.status is not StepStatus.INTENT_ENTERED:
            step.confirmation, step.trial = None, None
            step.status = StepStatus.TARGET_SELECTED
    draft.steps = list(draft.steps)


def _slug(name: str) -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in normalize_name(name)).strip("_")
    text = "_".join(part for part in text.split("_") if part)
    return (text if text[:1].isalpha() else f"b_{text}")[:60] or "bolge"


def _regions(given: list[dict[str, str]] | None, markers: list[TargetSpec]) -> list[RegionDef]:
    """Bölgeler: verilenler (ad zorunlu) + işaretlerin bölgeleri. Her bölge ScreenDef'te bir işaretle
    kanıtlanmalıdır; kanıtsız bölge doğrulama hatası verir."""
    out: list[RegionDef] = []
    seen: set[str] = set()
    for item in given or []:
        name = item.get("name", "")
        key = normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(RegionDef(region_id=item.get("region_id") or _slug(name), name=name))
    for marker in markers:
        if marker.region and normalize_name(marker.region) not in seen:
            seen.add(normalize_name(marker.region))
            out.append(RegionDef(region_id=_slug(marker.region), name=marker.region))
    return out


def _value_of(step: StepCard) -> str | None:
    return step.value_template or step.choice_template or step.key_template
