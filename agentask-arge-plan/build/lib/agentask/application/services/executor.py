"""Sınırlı komut motoru. Bir run'ı, oturum kilidi çağıran tarafından tutulurken adım adım yürütür.

İlkeler (docs/03):
- Her adımda hedef P2 ile yeniden çözülür; ambiguous → dispatch yok (paused_ambiguous).
- Her adımdan önce engelleyici ve oturum kontrolü: native/bilinmeyen dialog → paused_blocked (kapatılmaz);
  bilinen engelleyici → yalnız tanımlı düğme; oturum kaybı → paused_session.
- Hazır olmayan hedef: DOM/frame değişimine bağlı, READINESS_TIMEOUT_MS ile sınırlı bekleme (sabit sleep yok).
- Retry yalnız dış etki oluşmamışsa (veya adım retry-safe ise) ve RECOVERY_MAX_ATTEMPTS içinde.
- Veri değiştiren onaylı aksiyon: niyet + taban checkpoint → dispatched checkpoint → tıklama → verifying →
  sonuç kanıtı; belirsizse yalnız onaylı uzlaştırma okuması. Non-idempotent aksiyon asla yeniden gönderilmez.
  UI tıklamasıyla exactly-once garantisi verilmez.
- İptal: yeni adım ve yeni dispatch başlatılmaz; başlamış adım tamamlanır/uzlaştırılır, geri alma yapılmaz.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import TypeAdapter

from agentask.application.controls import (
    AdapterError,
    AdapterRegistry,
    ChoiceNotAvailable,
    ControlUnsupported,
    RecordOutcome,
    StaleTarget,
    TableLimits,
    TargetNotReady,
    VerificationFailed,
)
from agentask.application.ports.controls import PageDriver
from agentask.application.ports.observation import PageObserverPort
from agentask.application.ports.runs import RunRepository
from agentask.application.services.observation import resolve_target
from agentask.config.settings import Settings
from agentask.domain.actions import ActionSet, ApprovedAction, ErrorClass, TextMatch
from agentask.domain.commands import (
    ActivateTabCommand,
    AssertConditionCommand,
    ChoiceEquals,
    Command,
    EnsureChoiceCommand,
    EnsureValueCommand,
    EvaluateConditionCommand,
    FindRecordCommand,
    InvokeApprovedActionCommand,
    ReadCommand,
    TabActive,
    TextPresent,
    ValueEquals,
)
from agentask.domain.observation import ObservedControl
from agentask.domain.runtime import RESUMABLE_RUN, Run, RunStatus, StepRecord, StepState
from agentask.domain.targeting import Outcome, TargetSpec, normalize_name

logger = logging.getLogger(__name__)
COMMAND: TypeAdapter[Command] = TypeAdapter(Command)
_CONTEXT_OPS = {"ensure_value", "ensure_choice", "activate_tab", "find_record"}


class ExecHandle(Protocol):
    @property
    def observer(self) -> PageObserverPort: ...

    @property
    def driver(self) -> PageDriver: ...


@dataclass(frozen=True, slots=True)
class ExecutorConfig:
    readiness_timeout_ms: int
    outcome_timeout_ms: int
    reconcile_timeout_ms: int
    recovery_max_attempts: int
    run_max_duration_s: int
    table: TableLimits

    @classmethod
    def from_settings(cls, s: Settings) -> ExecutorConfig:
        return cls(
            readiness_timeout_ms=s.readiness_timeout_ms,
            outcome_timeout_ms=s.outcome_timeout_ms,
            reconcile_timeout_ms=s.reconcile_timeout_ms,
            recovery_max_attempts=s.recovery_max_attempts,
            run_max_duration_s=s.run_max_duration_seconds,
            table=TableLimits(s.table_max_pages, s.table_max_rows, s.table_no_progress_limit),
        )


class _Stop(Exception):
    """Run'ı durdurur. Adım durumu fırlatılmadan önce ayarlanmıştır."""

    def __init__(self, status: RunStatus, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


class _Retry(Exception):
    def __init__(self, error_class: str) -> None:
        super().__init__(error_class)
        self.error_class = error_class


@dataclass
class _Ctx:
    run: Run
    observer: PageObserverPort
    driver: PageDriver
    deadline: float
    records: dict[str, str] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Executor:
    def __init__(
        self,
        repository: RunRepository,
        actions: ActionSet,
        registry: AdapterRegistry,
        config: ExecutorConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = repository
        self._actions = actions
        self._registry = registry
        self._config = config
        self._clock = clock
        self.shutting_down = False

    # ---- run düzeyi --------------------------------------------------------------

    def _save(self, run: Run) -> None:
        self._repo.save(run)

    async def execute(self, run: Run, handle: ExecHandle) -> Run:
        ctx = _Ctx(run, handle.observer, handle.driver, self._clock() + self._config.run_max_duration_s)
        resuming = run.status in RESUMABLE_RUN
        if run.status is not RunStatus.CANCEL_REQUESTED:
            run.set_status(RunStatus.RUNNING)
        self._save(run)
        logger.info("run_started run=%s steps=%d resume=%s", run.run_id, len(run.steps), resuming)
        try:
            if resuming:
                await self._revalidate(ctx)
            for step in run.steps:
                if step.state in {StepState.SUCCEEDED, StepState.SKIPPED}:
                    continue
                if run.cancel_requested:
                    break
                if self.shutting_down:
                    raise _Stop(RunStatus.PAUSED_SESSION, "shutdown")
                if self._clock() > ctx.deadline:
                    step.error_class = ErrorClass.BUDGET_EXCEEDED.value
                    raise _Stop(RunStatus.FAILED, "run_duration_exceeded")
                if step.when is not None and step.state is StepState.PENDING:
                    ref = run.steps[int(step.when["step"])]
                    satisfied = ref.state is StepState.SUCCEEDED and ref.result.get("satisfied") is True
                    if satisfied != bool(step.when["is"]):
                        step.to(StepState.SKIPPED)
                        step.message = "Koşul sağlanmadı; adım atlandı."
                        self._save(run)
                        continue
                if step.state is StepState.KNOWN_FAILED and step.retry_allowed:
                    step.to(StepState.PENDING)
                    step.retry_allowed = False
                if step.state is not StepState.PENDING:
                    raise _Stop(RunStatus.FAILED, f"step_not_runnable:{step.state.value}")
                await self._run_step(ctx, step)
        except _Stop as stop:
            if stop.status is RunStatus.CANCELLED:
                self._skip_pending(run)
            run.set_status(stop.status, stop.reason)
            self._save(run)
            logger.info("run_stopped run=%s status=%s reason=%s", run.run_id, run.status.value, stop.reason)
            return run
        if run.cancel_requested and any(s.state is StepState.PENDING for s in run.steps):
            self._skip_pending(run)
            run.set_status(RunStatus.CANCELLED, "cancel_requested")
        else:
            run.set_status(
                RunStatus.COMPLETED, "cancel_arrived_after_last_step" if run.cancel_requested else None
            )
        self._save(run)
        logger.info("run_finished run=%s status=%s", run.run_id, run.status.value)
        return run

    @staticmethod
    def _skip_pending(run: Run) -> None:
        for step in run.steps:
            if step.state is StepState.PENDING:
                step.to(StepState.SKIPPED)

    async def _revalidate(self, ctx: _Ctx) -> None:
        """Devam: belirsiz adımları onaylı okumayla uzlaştır, sonra önceki bağlam adımlarını (güvenli
        ensure ve
        find_record) yeni oturumda yeniden kur. Onaylı aksiyonlar asla yeniden gönderilmez."""
        await self._gate(ctx, None)
        for step in ctx.run.steps:
            if step.state is not StepState.OUTCOME_UNKNOWN:
                continue
            command = COMMAND.validate_python(step.command)
            assert isinstance(command, InvokeApprovedActionCommand)
            action = self._actions.actions[command.action_id]
            baseline = int((step.intent or {}).get("baseline", -1))
            if (
                action.reconcile is None
                or baseline < 0
                or not await self._reconcile(ctx, action, command.params, baseline)
            ):
                step.message = "Sonuç hâlâ doğrulanamadı; insan incelemesi gerekli."
                raise _Stop(RunStatus.OUTCOME_UNKNOWN, "reconciliation_inconclusive")
            step.to(StepState.SUCCEEDED)
            step.error_class = None
            step.result = {**step.result, "verified_by": "reconciliation", "reconciled_at": _now_iso()}
            self._save(ctx.run)
        first_open = next((s.index for s in ctx.run.steps if s.state is not StepState.SUCCEEDED), None)
        if first_open is None:
            return
        for step in ctx.run.steps[:first_open]:
            if step.command.get("op") not in _CONTEXT_OPS:
                continue
            scratch = step.model_copy(deep=True)
            scratch.state = (
                StepState.PREPARED
            )  # başarılı adımın kaydı değişmez; yalnız bağlam yeniden kurulur
            try:
                await self._apply(ctx, scratch, COMMAND.validate_python(step.command))
            except (AdapterError, _Stop) as exc:
                step.message = "Devam için bağlam yeniden kurulamadı."
                raise _Stop(RunStatus.PAUSED_SESSION, "context_revalidation_failed") from exc
            step.recoveries.append("CONTEXT_REESTABLISHED")
        self._save(ctx.run)

    # ---- adım düzeyi --------------------------------------------------------------

    def _fail(self, step: StepRecord, error_class: ErrorClass, message: str, status: RunStatus) -> _Stop:
        if step.state is not StepState.KNOWN_FAILED:
            step.to(StepState.KNOWN_FAILED)
        step.error_class = error_class.value
        step.message = message
        return _Stop(status, error_class.value)

    async def _run_step(self, ctx: _Ctx, step: StepRecord) -> None:
        command = COMMAND.validate_python(step.command)
        while True:
            step.to(StepState.PREPARED)
            step.attempts += 1
            self._save(ctx.run)
            try:
                await self._gate(ctx, step)
                if isinstance(command, InvokeApprovedActionCommand):
                    await self._invoke(ctx, step, command)
                else:
                    changed, result = await self._apply(ctx, step, command)
                    if changed:
                        step.to(StepState.DISPATCHED)
                        step.to(StepState.VERIFYING)
                    step.to(StepState.SUCCEEDED)
                    step.result = result
                step.error_class, step.message = None, None
                self._save(ctx.run)
                logger.info(
                    "step_done run=%s step=%d op=%s state=%s",
                    ctx.run.run_id,
                    step.index,
                    command.op,
                    step.state.value,
                )
                return
            except _Retry as retry:
                step.recoveries.append(retry.error_class)
                if step.attempts > self._config.recovery_max_attempts:
                    raise self._fail(
                        step,
                        ErrorClass.BUDGET_EXCEEDED,
                        f"Toparlanma deneme sınırı aşıldı ({retry.error_class}).",
                        RunStatus.FAILED,
                    ) from None
                if step.state is StepState.PREPARED:
                    step.to(StepState.PENDING)
                elif step.state is StepState.VERIFYING:
                    step.to(StepState.PREPARED)
                    step.to(StepState.PENDING)
                continue
            except _Stop:
                if step.state is StepState.PREPARED:
                    step.to(StepState.PENDING)
                raise
            except (StaleTarget, TargetNotReady, VerificationFailed) as exc:
                if step.state is StepState.PREPARED or (step.state is StepState.VERIFYING and exc.retry_safe):
                    step.recoveries.append(exc.error_class.value)
                    if step.attempts > self._config.recovery_max_attempts:
                        raise self._fail(step, exc.error_class, exc.message, RunStatus.FAILED) from None
                    if step.state is StepState.VERIFYING:
                        step.to(StepState.PREPARED)
                    step.to(StepState.PENDING)
                    continue
                raise self._fail(step, exc.error_class, exc.message, RunStatus.FAILED) from None
            except (ControlUnsupported, ChoiceNotAvailable) as exc:
                raise self._fail(step, exc.error_class, exc.message, RunStatus.FAILED) from None
            except AdapterError as exc:
                status = (
                    RunStatus.PAUSED_AMBIGUOUS
                    if exc.error_class is ErrorClass.TARGET_AMBIGUOUS
                    else RunStatus.FAILED
                )
                raise self._fail(step, exc.error_class, exc.message, status) from None

    async def _gate(self, ctx: _Ctx, step: StepRecord | None) -> None:
        """Engelleyici pencere ve oturum kontrolü. Yalnız onaylı engelleyicide tanımlı düğmeye basılır."""
        for _ in range(3):
            dialogs = await ctx.driver.open_dialogs()
            if not dialogs:
                break
            dialog = dialogs[0]
            blocker = (
                None
                if dialog.native
                else next(
                    (
                        b
                        for b in self._actions.blockers
                        if dialog.name
                        and normalize_name(dialog.name) == normalize_name(b.dialog_name)
                        and b.text.matches(dialog.text, {})
                    ),
                    None,
                )
            )
            if blocker is None or len(dialogs) > 1:
                if step is not None:
                    step.error_class = ErrorClass.UNKNOWN_DIALOG.value
                    step.message = "Tanımlı olmayan bir pencere açık; kapatılmadı, insan müdahalesi gerekli."
                raise _Stop(RunStatus.PAUSED_BLOCKED, ErrorClass.UNKNOWN_DIALOG.value)
            if not await ctx.driver.click_dialog_button(blocker.dialog_name, blocker.button_label):
                raise _Stop(RunStatus.PAUSED_BLOCKED, ErrorClass.KNOWN_OVERLAY.value)
            if step is not None:
                step.recoveries.append(f"KNOWN_OVERLAY:{blocker.blocker_id}")
            await ctx.driver.wait_for_change(1000)
        else:
            raise _Stop(RunStatus.PAUSED_BLOCKED, ErrorClass.KNOWN_OVERLAY.value)
        if await self._session_lost(ctx):
            if step is not None:
                step.error_class = ErrorClass.SESSION_EXPIRED.value
                step.message = "Uygulama oturumu sona ermiş; yeni oturumla devam edilmeli."
            raise _Stop(RunStatus.PAUSED_SESSION, ErrorClass.SESSION_EXPIRED.value)

    async def _session_lost(self, ctx: _Ctx) -> bool:
        path = await ctx.driver.current_path()
        return any(path.startswith(prefix) for prefix in self._actions.profile.session_lost_path_prefixes)

    async def _resolve(self, ctx: _Ctx, step: StepRecord, spec: TargetSpec) -> ObservedControl:
        deadline = self._clock() + self._config.readiness_timeout_ms / 1000
        while True:
            resolution = await resolve_target(ctx.observer, spec)
            snapshot = ctx.observer.current_snapshot
            if resolution.outcome is Outcome.RESOLVED and snapshot and resolution.candidate_id:
                control = snapshot.control(resolution.candidate_id)
                if control is not None:
                    return control
            if resolution.outcome is Outcome.AMBIGUOUS:
                raise self._fail(
                    step,
                    ErrorClass.TARGET_AMBIGUOUS,
                    f"Hedef belirsiz: {len(resolution.candidates)} aday; işlem yapılmadı.",
                    RunStatus.PAUSED_AMBIGUOUS,
                )
            await self._gate(ctx, step)
            remaining = deadline - self._clock()
            if remaining <= 0:
                error = (
                    ErrorClass.TARGET_NOT_FOUND
                    if resolution.reason == "not_found"
                    else ErrorClass.TARGET_NOT_READY
                )
                raise self._fail(step, error, f"Hedef çözülemedi ({resolution.reason}).", RunStatus.FAILED)
            if ErrorClass.TARGET_NOT_READY.value not in step.recoveries:
                step.recoveries.append(ErrorClass.TARGET_NOT_READY.value)
            await ctx.driver.wait_for_change(int(min(remaining, 1.5) * 1000))

    async def _apply(self, ctx: _Ctx, step: StepRecord, command: Command) -> tuple[bool, dict[str, Any]]:
        """Onaylı aksiyon dışındaki komutlar. (değişti mi, sonuç) döner; doğrulama adapter içindedir."""
        driver = ctx.driver
        if isinstance(command, ReadCommand):
            control = await self._resolve(ctx, step, command.target)
            adapter = self._registry.for_control(control)
            return False, {"adapter": adapter.name, "value": await adapter.read(driver, control)}
        if isinstance(command, EnsureValueCommand):
            control = await self._resolve(ctx, step, command.target)
            adapter = self._registry.for_control(control)
            r = await adapter.ensure_value(driver, control, command.value)
            return r.changed, {"adapter": adapter.name, "changed": r.changed, "verified": r.verified}
        if isinstance(command, EnsureChoiceCommand):
            control = await self._resolve(ctx, step, command.target)
            adapter = self._registry.for_control(control)
            r = await adapter.ensure_choice(driver, control, command.choice)
            return r.changed, {"adapter": adapter.name, "changed": r.changed, "observed": r.observed}
        if isinstance(command, ActivateTabCommand):
            control = await self._resolve(ctx, step, command.target)
            adapter = self._registry.for_control(control)
            r = await adapter.activate_tab(driver, control)
            return r.changed, {"adapter": adapter.name, "changed": r.changed}
        if isinstance(command, FindRecordCommand):
            return await self._find_record(ctx, step, command)
        if isinstance(command, AssertConditionCommand):
            return False, await self._assert(ctx, step, command)
        if isinstance(command, EvaluateConditionCommand):
            return False, await self._evaluate(ctx, command)
        raise ControlUnsupported(f"unsupported_command:{command.op}")

    async def _find_record(
        self, ctx: _Ctx, step: StepRecord, command: FindRecordCommand
    ) -> tuple[bool, dict[str, Any]]:
        control = await self._resolve(ctx, step, command.table)
        adapter = self._registry.for_control(control)

        async def relocate(_: ObservedControl) -> ObservedControl:
            await self._gate(ctx, step)
            return await self._resolve(ctx, step, command.table)

        search = await adapter.find_record(
            ctx.driver,
            control,
            command.key,
            command.navigation,
            command.next_labels,
            command.end_text,
            self._config.table,
            relocate,
        )
        result = {
            "adapter": adapter.name,
            "outcome": search.outcome.value,
            "pages_visited": search.pages_visited,
            "rows_seen": search.rows_seen,
        }
        if search.outcome is RecordOutcome.FOUND:
            ctx.records[control.accessible_name or "table"] = command.key
            return search.pages_visited > 1, result
        step.result = result
        messages = {
            RecordOutcome.NOT_FOUND_AT_END: "Kayıt tablonun sonuna kadar bulunamadı.",
            RecordOutcome.LIMIT_REACHED: "Tarama sınırına ulaşıldı; kaydın olmadığı kesin değil.",
            RecordOutcome.NO_PROGRESS: "Liste ilerlemedi; kaydın olmadığı kesin değil.",
            RecordOutcome.DUPLICATE_KEY: "Aynı iş anahtarı birden fazla satırda; kayıt seçilmedi.",
        }
        error = (
            ErrorClass.BUSINESS_VALIDATION
            if search.outcome is RecordOutcome.NOT_FOUND_AT_END
            else (
                ErrorClass.TARGET_AMBIGUOUS
                if search.outcome is RecordOutcome.DUPLICATE_KEY
                else ErrorClass.RECORD_NOT_LOADED
            )
        )
        status = RunStatus.PAUSED_AMBIGUOUS if error is ErrorClass.TARGET_AMBIGUOUS else RunStatus.FAILED
        raise self._fail(step, error, messages[search.outcome], status)

    async def _assert(self, ctx: _Ctx, step: StepRecord, command: AssertConditionCommand) -> dict[str, Any]:
        condition = command.condition
        deadline = self._clock() + self._config.readiness_timeout_ms / 1000
        while True:
            observed: str | None
            if isinstance(condition, TextPresent):
                texts = await ctx.driver.evidence(condition.evidence, None)
                ok = any(condition.match.matches(t, {}) for t in texts)
                observed = None
            else:
                control = await self._resolve(ctx, step, condition.target)
                adapter = self._registry.for_control(control)
                observed = await adapter.read(ctx.driver, control)
                if isinstance(condition, ValueEquals):
                    ok = observed == condition.value
                elif isinstance(condition, ChoiceEquals):
                    ok = observed is not None and normalize_name(observed) == normalize_name(condition.choice)
                else:
                    assert isinstance(condition, TabActive)
                    ok = observed == "active"
            if ok:
                return {"condition": condition.type, "satisfied": True}
            remaining = deadline - self._clock()
            if remaining <= 0:
                step.result = {"condition": condition.type, "satisfied": False}
                raise self._fail(
                    step, ErrorClass.VERIFICATION_FAILED, "Koşul süre içinde sağlanmadı.", RunStatus.FAILED
                )
            await ctx.driver.wait_for_change(int(min(remaining, 1.5) * 1000))

    async def _evaluate(self, ctx: _Ctx, command: EvaluateConditionCommand) -> dict[str, Any]:
        """Guard koşulu: tek değerlendirme, beklemez, başarısız olmaz. Hedef tekil çözülemezse koşul sağlanmamıştır."""
        condition = command.condition
        if isinstance(condition, TextPresent):
            texts = await ctx.driver.evidence(condition.evidence, None)
            return {
                "condition": condition.type,
                "satisfied": any(condition.match.matches(t, {}) for t in texts),
            }
        resolution = await resolve_target(ctx.observer, condition.target)
        snapshot = ctx.observer.current_snapshot
        control = snapshot.control(resolution.candidate_id) if snapshot and resolution.candidate_id else None
        if resolution.outcome is not Outcome.RESOLVED or control is None:
            return {"condition": condition.type, "satisfied": False, "reason": resolution.reason}
        observed = await self._registry.for_control(control).read(ctx.driver, control)
        if isinstance(condition, ValueEquals):
            ok = observed == condition.value
        elif isinstance(condition, ChoiceEquals):
            ok = observed is not None and normalize_name(observed) == normalize_name(condition.choice)
        else:
            ok = observed == "active"
        return {"condition": condition.type, "satisfied": ok}

    # ---- onaylı aksiyon: dispatch sınırı ve uzlaştırma -------------------------------

    async def _invoke(self, ctx: _Ctx, step: StepRecord, command: InvokeApprovedActionCommand) -> None:
        action = self._actions.actions.get(command.action_id)
        if action is None:
            raise self._fail(step, ErrorClass.POLICY_DENIED, "Onaylı aksiyon bulunamadı.", RunStatus.FAILED)
        params = command.params
        for binding in action.requires_fields:
            field_control = await self._resolve(ctx, step, binding.target)
            current = await self._registry.for_control(field_control).read(ctx.driver, field_control)
            if current != params[binding.param]:
                raise self._fail(
                    step,
                    ErrorClass.VERIFICATION_FAILED,
                    "Gönderim ön koşulu sağlanmadı: alan değeri parametreyle aynı değil.",
                    RunStatus.FAILED,
                )
        control = await self._resolve(ctx, step, action.target)
        baseline = None
        if action.reconcile is not None:
            items = await ctx.driver.evidence(action.reconcile.evidence, control.candidate_id)
            baseline = sum(1 for i in items if action.reconcile.match.matches(i, params))
        before = await ctx.driver.evidence(action.outcome.evidence, control.candidate_id)
        await ctx.driver.click_trial(
            control.candidate_id
        )  # tıklamadan actionability; başarısızsa güvenli tekrar
        stale = await ctx.observer.check_candidate(control.candidate_id)
        if stale is not None:
            raise _Retry(ErrorClass.FRAME_CHANGED.value)
        step.intent = {
            "action_id": action.action_id,
            "effect": action.effect,
            "retry_safe": action.retry_safe,
            "baseline": baseline,
            "records": dict(ctx.records),
            "prepared_at": _now_iso(),
        }
        self._save(ctx.run)
        if ctx.run.cancel_requested or self.shutting_down:
            step.to(StepState.PENDING)
            raise _Stop(
                RunStatus.CANCELLED if ctx.run.cancel_requested else RunStatus.PAUSED_SESSION,
                "cancelled_before_dispatch" if ctx.run.cancel_requested else "shutdown",
            )
        step.to(StepState.DISPATCHED)
        self._save(ctx.run)  # bu noktadan sonra dış etki oluşmuş olabilir
        click_error: str | None = None
        try:
            await ctx.driver.click(control.candidate_id)
        except AdapterError as exc:
            click_error = exc.error_class.value
        step.to(StepState.VERIFYING)
        self._save(ctx.run)
        verdict, detail = "unknown", f"click_error:{click_error}"
        if click_error is None:
            try:
                verdict, detail = await self._await_outcome(ctx, action, params, control.candidate_id, before)
            except Exception as exc:  # gönderilmiş adımda hiçbir hata 'bilinen başarısızlık' sayılmaz
                verdict, detail = "unknown", f"verification_error:{type(exc).__name__}"
        if verdict == "success":
            step.to(StepState.SUCCEEDED)
            step.result = {"action_id": action.action_id, "verified_by": "outcome", "evidence": detail}
            return
        if verdict == "failure":
            rule = next(f for f in action.outcome.failures if f.error_class.value == detail)
            step.retry_allowed = rule.applied is False
            status = (
                RunStatus.PAUSED_SESSION
                if rule.error_class is ErrorClass.SESSION_EXPIRED
                else RunStatus.FAILED
            )
            raise self._fail(
                step, rule.error_class, "Uygulama işlemi reddetti (uygulanmadığı biliniyor).", status
            )
        step.recoveries.append(ErrorClass.WRITE_RESULT_UNKNOWN.value)
        if action.effect == "non_mutating" and action.retry_safe:
            raise _Retry(ErrorClass.WRITE_RESULT_UNKNOWN.value)
        assert action.reconcile is not None and baseline is not None
        if await self._reconcile(ctx, action, params, baseline):
            step.to(StepState.SUCCEEDED)
            step.result = {"action_id": action.action_id, "verified_by": "reconciliation", "reason": detail}
            return
        step.to(StepState.OUTCOME_UNKNOWN)
        step.error_class = ErrorClass.WRITE_RESULT_UNKNOWN.value
        step.message = "İşlem gönderildi ancak sonucu doğrulanamadı; yeniden gönderilmedi."
        step.result = {"action_id": action.action_id, "verified_by": None, "reason": detail}
        raise _Stop(RunStatus.OUTCOME_UNKNOWN, ErrorClass.WRITE_RESULT_UNKNOWN.value)

    async def _await_outcome(
        self, ctx: _Ctx, action: ApprovedAction, params: dict[str, str], anchor: str, before: list[str]
    ) -> tuple[str, str]:
        deadline = self._clock() + self._config.outcome_timeout_ms / 1000
        outcome = action.outcome
        while True:
            if ctx.observer.native_dialog is not None:
                return "unknown", "native_dialog"
            try:
                texts = await ctx.driver.evidence(outcome.evidence, anchor)
            except (StaleTarget, TargetNotReady):
                texts = []
            fresh = [t for t in texts if t not in before] if texts != before else []
            for text in fresh:
                if outcome.success.matches(text, params):
                    return "success", text
                for rule in outcome.failures:
                    if rule.match.matches(text, params):
                        return "failure", rule.error_class.value
                if any(m.matches(text, params) for m in outcome.unknown):
                    return "unknown", "unknown_outcome_text"
            if (
                action.effect == "non_mutating"
                and texts
                and texts == before
                and any(outcome.success.matches(t, params) for t in texts)
            ):
                return "success", texts[0]
            if await self._session_lost(ctx):
                return "unknown", "session_lost_after_dispatch"
            remaining = deadline - self._clock()
            if remaining <= 0:
                return "unknown", "outcome_timeout"
            await ctx.driver.wait_for_change(int(min(remaining, 1.5) * 1000))

    async def _reconcile(
        self, ctx: _Ctx, action: ApprovedAction, params: dict[str, str], baseline: int
    ) -> bool:
        """Onaylı okuma: listede eşleşen öğe sayısı tabana göre tam 1 artmışsa uygulanmış sayılır.
        'Henüz görünmüyor' uygulanmadığını kanıtlamaz → False (outcome_unknown)."""
        spec = action.reconcile
        assert spec is not None
        try:
            if spec.reload:
                await ctx.driver.reload()
        except Exception as exc:  # uzlaştırma okuması başarısızsa sonuç belirsiz kalır
            logger.warning("reconcile_reload_failed type=%s", type(exc).__name__)
            return False
        deadline = self._clock() + self._config.reconcile_timeout_ms / 1000
        matcher: TextMatch = spec.match
        while True:
            if ctx.observer.native_dialog is not None or await self._session_lost(ctx):
                return False
            anchor = None
            resolution = await resolve_target(ctx.observer, action.target)
            if resolution.outcome is Outcome.RESOLVED:
                anchor = resolution.candidate_id
            try:
                items = await ctx.driver.evidence(spec.evidence, anchor)
            except AdapterError:
                return False
            delta = sum(1 for i in items if matcher.matches(i, params)) - baseline
            if delta == spec.expected_increase:
                return True
            if delta > spec.expected_increase:
                logger.warning("reconcile_unexpected_increase delta=%d", delta)
                return False
            remaining = deadline - self._clock()
            if remaining <= 0:
                return False
            await ctx.driver.wait_for_change(int(min(remaining, 1.5) * 1000))
