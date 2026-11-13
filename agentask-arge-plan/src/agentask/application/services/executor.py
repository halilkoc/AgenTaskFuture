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
- Pencere bağlamı (ADR 0014): etkin ekran tanımında bölge olarak bulunan sayfa içi pencere beklenen
  penceredir ve yürütmeyi durdurmaz; diğer görünür pencereler eskisi gibi engelleyicidir. Yeni pencere/sekme
  açılırsa otomatik geçilmez ve kapatılmaz; sonraki adım başlatılmaz (paused_blocked). Açık pencerenin
  arkasındaki veya kaplayan katmanın altındaki hedefe işlem yapılmaz; süre içinde açılmazsa müdahale istenir.
- Ekran (R3): assert_screen ekranı güncel gözlemle doğrular ve etkin ekran olur. Sonraki her sayfa adımından
  (okuma/yazma/seçim/sekme/kayıt/onaylı aksiyon) önce aynı ekran YENİDEN doğrulanır; gezinme/frame değişimi
  sonrası eski gözlem ve aday kimliğine güvenilmez. Tanınmayan/belirsiz/eksik kanıtlı ekranda adım hiçbir
  sürücü eylemi yapmadan başarısız olur. Karar model değil, kod kuralıdır (domain/screens.judge).
- Geçiş (R4): yalnız katalogdaki onaylı geçiş. Kaynak ekran + bağlam doğrulanır, tetikleyici BİR KEZ
  gönderilir (niyet ve DISPATCHED önceden kaydedilir), etkin ekran boşaltılır (eski ekran kuralı meşru geçişi
  engellemez),
  hedef ekran ve bağlam koşulları timeout_ms içinde DOM/frame değişimine bağlı beklenir. Tekrar tıklama yok.
  Zaman aşımı (kaynak hâlâ görünür) ile beklenmeyen ekran ayrı raporlanır. Yazma etkili geçişte iş sonucu
  ayrıca
  doğrulanır; hedef ekranın görünmesi başarı kanıtı değildir.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
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
    SuggestionNotFound,
    TableLimits,
    TargetNotReady,
    VerificationFailed,
)
from agentask.application.errors import ApplicationError
from agentask.application.observability import BUSINESS, log_context, log_event
from agentask.application.ports.controls import OpenDialog, PageDriver
from agentask.application.ports.observation import PageObserverPort
from agentask.application.ports.runs import RunRepository
from agentask.application.services.observation import assess_screen, resolve_target
from agentask.config.settings import Settings
from agentask.domain.actions import (
    ActionSet,
    ApprovedAction,
    ErrorClass,
    EvidenceSpec,
    KnownBlocker,
    TextMatch,
)
from agentask.domain.choices import choice_key
from agentask.domain.commands import (
    ActivateTabCommand,
    AssertConditionCommand,
    AssertScreenCommand,
    CheckedEquals,
    ChoiceEquals,
    ChoicesEqual,
    Command,
    EnsureCheckedCommand,
    EnsureChoiceCommand,
    EnsureChoicesCommand,
    EnsureDateCommand,
    EnsureValueCommand,
    EvaluateConditionCommand,
    FindRecordCommand,
    FollowTransitionCommand,
    InvokeApprovedActionCommand,
    OutputRef,
    ReadCommand,
    RegisterOptionalDialogsCommand,
    ReturnWindowCommand,
    TabActive,
    TextPresent,
    TransitionSpec,
    UploadFileCommand,
    ValueEquals,
    bind_output,
    bind_params,
    output_refs,
)
from agentask.domain.observation import ObservedControl
from agentask.domain.run_summary import failed_step, outcome_of, run_log_fields
from agentask.domain.runtime import RESUMABLE_RUN, Run, RunStatus, StepRecord, StepState
from agentask.domain.screens import ScreenDef, ScreenStatus
from agentask.domain.targeting import Outcome, TargetSpec, normalize_name

logger = logging.getLogger(__name__)
COMMAND: TypeAdapter[Command] = TypeAdapter(Command)
_CONTEXT_OPS = {
    "assert_screen",
    "ensure_value",
    "ensure_choice",
    "ensure_checked",
    "ensure_choices",
    "ensure_date",
    "activate_tab",
    "find_record",
}
# Etkin ekranın yeniden doğrulanmasını gerektirmeyen komutlar (doğrulamanın kendisi veya guard).
_NO_SCREEN_RECHECK = {
    "assert_screen",
    "evaluate_condition",
    "return_window",
    "register_optional_dialogs",
}


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
    screen: ScreenDef | None = None
    context: list[ValueEquals] = field(default_factory=list)
    found_key: str | None = None  # son Kayıt bul adımının bulduğu iş anahtarı
    handle: Any = None
    adopted: bool = False  # etkin sayfa beklenen yeni pencere
    optional: list[KnownBlocker] = field(default_factory=list)  # planda tanımlı isteğe bağlı pencereler


class _TransitionFailed(Exception):
    def __init__(
        self, error_class: ErrorClass, message: str, status: RunStatus, detail: dict[str, Any]
    ) -> None:
        super().__init__(message)
        self.error_class, self.message, self.status, self.detail = error_class, message, status, detail


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
        # (sahip, artifact_id, izinli türler) → (ref, içerik). Yalnız yetkili dosya deposu bağlanır.
        self.file_reader: Callable[[str, str, list[str] | None], Awaitable[tuple[Any, bytes]]] | None = None

    # ---- run düzeyi --------------------------------------------------------------

    def _save(self, run: Run) -> None:
        self._repo.save(run)

    async def execute(self, run: Run, handle: ExecHandle) -> Run:
        ctx = _Ctx(run, handle.observer, handle.driver, self._clock() + self._config.run_max_duration_s)
        ctx.handle, ctx.adopted = handle, bool(getattr(handle, "adopted", False))
        # Devam etme dahil her çalıştırmada plandan okunur; ilk sayfa adımından önce geçerlidir.
        ctx.optional = [
            KnownBlocker.model_validate(d)
            for s in run.steps
            if s.command.get("op") == "register_optional_dialogs"
            for d in s.command["dialogs"]
        ]
        resuming = run.status in RESUMABLE_RUN
        if run.status is not RunStatus.CANCEL_REQUESTED:
            run.set_status(RunStatus.RUNNING)
        self._save(run)
        started = time.monotonic()
        log_event(
            logger, "run_started", audit=True, steps=len(run.steps), resume=resuming, **run_log_fields(run)
        )
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
                with log_context(step_id=step.index):
                    await self._run_step(ctx, step)
        except _Stop as stop:
            if stop.status is RunStatus.CANCELLED:
                self._skip_pending(run)
            run.set_status(stop.status, stop.reason)
            self._save(run)
            self._release_windows(ctx)
            self._log_finished(run, started)
            return run
        if run.cancel_requested and any(s.state is StepState.PENDING for s in run.steps):
            self._skip_pending(run)
            run.set_status(RunStatus.CANCELLED, "cancel_requested")
            self._release_windows(ctx)
        else:
            run.set_status(
                RunStatus.COMPLETED, "cancel_arrived_after_last_step" if run.cancel_requested else None
            )
        self._save(run)
        self._log_finished(run, started)
        return run

    @staticmethod
    def _release_windows(ctx: _Ctx) -> None:
        """Yarıda kalan çalışma: açık pencere insan kararına bırakılır, tutamaç ana sayfaya döner."""
        if ctx.adopted:
            ctx.handle.release_windows()
            ctx.adopted = False

    @staticmethod
    def _log_finished(run: Run, started: float) -> None:
        """Run başına tek sonuç olayı; durum kalıcı yazıldıktan sonra üretilir. Adım hatası burada yazılır."""
        step = failed_step(run) if run.status is not RunStatus.COMPLETED else None
        outcome = outcome_of(run.status)
        log_event(
            logger,
            "run_finished",
            level=logging.INFO if outcome in {"success", "cancelled"} else logging.WARNING,
            audit=True,
            outcome=outcome,
            status=run.status.value,
            reason=run.status_reason,
            step_id=step.index if step else None,
            op=step.command.get("op") if step else None,
            error_code=step.error_class if step else None,
            error_kind=BUSINESS if step and step.error_class else None,
            duration_ms=int((time.monotonic() - started) * 1000),
            **run_log_fields(run),
        )

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
            command = COMMAND.validate_python(self._bound(ctx.run, step)[0])
            if isinstance(
                command, EnsureChoiceCommand | EnsureCheckedCommand | EnsureChoicesCommand | UploadFileCommand
            ):
                if not await self._applied(ctx, command):
                    step.message = "Seçimin sonucu hâlâ doğrulanamadı; insan incelemesi gerekli."
                    raise _Stop(RunStatus.OUTCOME_UNKNOWN, "reconciliation_inconclusive")
                step.to(StepState.SUCCEEDED)
                step.error_class, step.message = None, None
                step.result = {**step.result, "verified_by": "reconciliation", "reconciled_at": _now_iso()}
                self._save(ctx.run)
                continue
            assert isinstance(command, InvokeApprovedActionCommand)
            action = self._actions.actions.get(command.action_id)
            if action is None or self._action_changed(command):
                step.message = (
                    "Onaylı işlem tanımı değişti veya kaldırıldı; sonuç uygulamada elle kontrol edilmeli."
                )
                raise _Stop(RunStatus.OUTCOME_UNKNOWN, "action_definition_changed")
            baseline = int((step.intent or {}).get("baseline", -1))
            if (
                action.reconcile is None
                or baseline < 0
                or not await self._reconcile(ctx, action, command.params, baseline)
            ):
                step.message = "Sonuç hâlâ doğrulanamadı; insan incelemesi gerekli."
                raise _Stop(RunStatus.OUTCOME_UNKNOWN, "reconciliation_inconclusive")
            step.to(StepState.SUCCEEDED)
            step.error_class, step.message = None, None
            step.result = {**step.result, "verified_by": "reconciliation", "reconciled_at": _now_iso()}
            self._save(ctx.run)
        first_open = next((s.index for s in ctx.run.steps if s.state is not StepState.SUCCEEDED), None)
        if first_open is None:
            return
        # R4: yalnız son doğrulanmış ekran segmenti yeniden kurulur. Segment başı: son başarılı assert_screen,
        # follow_transition veya geçişli onaylı aksiyon. Geçiş ve aksiyonlar ASLA yeniden oynatılmaz;
        # segmentin
        # ekranı ve kayıt bağlamı güncel gözlemle doğrulanamazsa durulur.
        anchor_index, screen, context = self._segment(ctx.run.steps[:first_open])
        if screen is not None:
            scratch = ctx.run.steps[anchor_index].model_copy(deep=True)
            scratch.state = StepState.PREPARED
            try:
                await self._verify_screen(ctx, scratch, screen, recheck=False, context=context)
            except _Stop as exc:
                step = ctx.run.steps[first_open]
                step.message = "Devam için beklenen ekran veya kayıt bağlamı doğrulanamadı; işlem yapılmadı."
                step.result = {**step.result, "resume_check": scratch.result}
                raise _Stop(RunStatus.PAUSED_SESSION, "context_revalidation_failed") from exc
            ctx.screen, ctx.context = screen, context
        for step in ctx.run.steps[anchor_index + 1 if screen is not None else 0 : first_open]:
            if step.command.get("op") not in _CONTEXT_OPS or step.command.get("op") == "assert_screen":
                continue
            scratch = step.model_copy(deep=True)
            scratch.state = (
                StepState.PREPARED
            )  # başarılı adımın kaydı değişmez; yalnız bağlam yeniden kurulur
            raw, problem = self._bound(ctx.run, step)
            try:
                if problem is not None:
                    raise _Stop(RunStatus.PAUSED_SESSION, "context_revalidation_failed")
                replay = COMMAND.validate_python(raw)
                if isinstance(replay, EnsureChoiceCommand | EnsureCheckedCommand | EnsureChoicesCommand) and (
                    replay.effect == "unknown"
                    or (isinstance(replay, EnsureChoiceCommand) and replay.autocomplete)
                ):
                    # Etkisi bilinmeyen seçim bağlam kurmak için yeniden gönderilmez; yalnız okunur.
                    if not await self._applied(ctx, replay):
                        raise _Stop(RunStatus.PAUSED_SESSION, "context_revalidation_failed")
                else:
                    await self._apply(ctx, scratch, replay)
            except (AdapterError, _Stop) as exc:
                step.message = "Devam için bağlam yeniden kurulamadı."
                raise _Stop(RunStatus.PAUSED_SESSION, "context_revalidation_failed") from exc
            step.recoveries.append("CONTEXT_REESTABLISHED")
        self._save(ctx.run)

    @staticmethod
    def _segment(done: list[StepRecord]) -> tuple[int, ScreenDef | None, list[ValueEquals]]:
        """Tamamlanmış adımlardan etkin ekranı çıkarır (komutlardan; yeniden çalıştırmadan)."""
        for step in reversed(done):
            command = COMMAND.validate_python(step.command)
            if isinstance(command, AssertScreenCommand):
                return step.index, command.screen, list(command.context)
            if isinstance(command, FollowTransitionCommand):
                return step.index, command.to_screen, list(command.context)
            if isinstance(command, InvokeApprovedActionCommand | EnsureChoiceCommand) and command.transition:
                return step.index, command.transition.to_screen, list(command.transition.context)
        return -1, None, []

    # ---- adım düzeyi --------------------------------------------------------------

    def _fail(self, step: StepRecord, error_class: ErrorClass, message: str, status: RunStatus) -> _Stop:
        if step.state is not StepState.KNOWN_FAILED:
            step.to(StepState.KNOWN_FAILED)
        step.error_class = error_class.value
        step.message = message
        return _Stop(status, error_class.value)

    @staticmethod
    @staticmethod
    def _ref_value(run: Run, step: StepRecord, ref: OutputRef) -> tuple[str | None, str | None]:
        """(değer, sorun). Yalnız kaynak okuma başarıyla bittiyse; boş, hassas veya uzun değer sorundur."""
        source = run.steps[ref.step] if ref.step < step.index else None
        value = source.result.get("value") if source is not None else None
        problem = (
            "kaynak okuma adımı yok"
            if source is None
            else "kaynak okuma adımı başarıyla tamamlanmadı"
            if source.state is not StepState.SUCCEEDED
            else "hassas alandan okunan değer başka alana aktarılmaz"
            if source.result.get("sensitive")
            else "okunan değer boş"
            if not isinstance(value, str) or not value.strip()
            else f"okunan değer {ref.max_length} karakter sınırını aşıyor"
            if len(value) > ref.max_length
            else None
        )
        return (value if problem is None and isinstance(value, str) else None), problem

    @classmethod
    def _bound(cls, run: Run, step: StepRecord) -> tuple[dict[str, Any], str | None]:
        """(çıktısı yerleştirilmiş ham komut, sorun). Sorun varsa komut eylem yapılmadan durdurulur."""
        command = COMMAND.validate_python(step.command)
        refs = output_refs(command)
        if not refs:
            return step.command, None
        if isinstance(command, InvokeApprovedActionCommand):
            values: dict[str, str] = {}
            for name, ref in command.params_from.items():
                value, problem = cls._ref_value(run, step, ref)
                if value is None:
                    return step.command, problem
                values[name] = value
            return bind_params(step.command, values), None
        value, problem = cls._ref_value(run, step, refs[0])
        if value is None:
            return step.command, problem
        return bind_output(step.command, value), None

    def _bind_outputs(self, ctx: _Ctx, step: StepRecord) -> Command:
        """Sürücü eyleminden önce çıktı bağlaması; sorun varsa adım başarısız olur (tahmin yok)."""
        raw, problem = self._bound(ctx.run, step)
        if problem is not None:
            step.to(StepState.PREPARED)
            step.to(StepState.KNOWN_FAILED)
            step.error_class = ErrorClass.PRIOR_OUTPUT_UNAVAILABLE.value
            step.message = f"Önceki adımın çıktısı kullanılamadı: {problem}. İşlem yapılmadı."
            self._save(ctx.run)
            raise _Stop(RunStatus.FAILED, ErrorClass.PRIOR_OUTPUT_UNAVAILABLE.value)
        return COMMAND.validate_python(raw)

    async def _run_step(self, ctx: _Ctx, step: StepRecord) -> None:
        started = time.monotonic()
        command = self._bind_outputs(ctx, step)
        while True:
            step.to(StepState.PREPARED)
            step.attempts += 1
            self._save(ctx.run)
            try:
                # assert_screen doğrulanmakta olan ekranın kendi penceresini engelleyici saymaz.
                if not isinstance(
                    command, ReturnWindowCommand
                ):  # pencere kapanmış olabilir; kendisi doğrular
                    await self._gate(
                        ctx, step, command.screen if isinstance(command, AssertScreenCommand) else None
                    )
                screen_check = None
                if ctx.screen is not None and command.op not in _NO_SCREEN_RECHECK:
                    screen_check = await self._verify_screen(
                        ctx, step, ctx.screen, recheck=True, context=ctx.context
                    )
                if isinstance(command, InvokeApprovedActionCommand):
                    await self._invoke(ctx, step, command)
                elif isinstance(command, FollowTransitionCommand):
                    await self._follow(ctx, step, command)
                else:
                    changed, result = await self._apply(ctx, step, command)
                    if changed and step.state is StepState.PREPARED:
                        step.to(StepState.DISPATCHED)
                        step.to(StepState.VERIFYING)
                    step.to(StepState.SUCCEEDED)
                    step.result = result
                if screen_check is not None:
                    step.result = {**step.result, "screen_reverified": screen_check["screen_id"]}
                refs = output_refs(COMMAND.validate_python(step.command))
                if refs:  # izlenebilirlik: değerin hangi okuma adımından geldiği
                    step.result = {**step.result, "value_from_step": refs[0].step}
                step.error_class, step.message = None, None
                self._save(ctx.run)
                log_event(
                    logger,
                    "step_done",
                    run_id=ctx.run.run_id,
                    op=command.op,
                    status=step.state.value,
                    outcome="success",
                    attempts=step.attempts,
                    duration_ms=int((time.monotonic() - started) * 1000),
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

    async def _gate(self, ctx: _Ctx, step: StepRecord | None, pending: ScreenDef | None = None) -> None:
        if ctx.adopted and ctx.handle.window_closed:
            if step is not None:
                step.error_class = ErrorClass.NEW_WINDOW.value
                step.message = (
                    "Beklenen pencere adım tamamlanmadan kapandı; sonuç bilinmiyor, tekrar edilmedi."
                )
            raise _Stop(RunStatus.OUTCOME_UNKNOWN, ErrorClass.NEW_WINDOW.value)
        """Engelleyici pencere ve oturum kontrolü. Yalnız onaylı engelleyicide tanımlı düğmeye basılır."""
        if ctx.observer.new_windows:
            if step is not None:
                step.error_class = ErrorClass.NEW_WINDOW.value
                step.message = "Yeni bir pencere veya sekme açıldı; otomatik geçilmedi, müdahale gerekli."
            raise _Stop(RunStatus.PAUSED_BLOCKED, ErrorClass.NEW_WINDOW.value)
        for _ in range(3):
            opened = await ctx.driver.open_dialogs()
            dialogs = [d for d in opened if not await self._expected_dialog(ctx, d, pending)]
            if not dialogs:
                break
            dialog = dialogs[0]
            blocker = (
                None
                if dialog.native
                else next(
                    (
                        b
                        for b in [*self._actions.blockers, *ctx.optional]
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

    async def _expected_dialog(self, ctx: _Ctx, dialog: OpenDialog, pending: ScreenDef | None = None) -> bool:
        """Beklenen pencere, mevcut sözleşmeyle AÇIKÇA doğrulanır; bölge adının eşleşmesi tek başına
        yetmez: (1) adımın beklenen ekranı (doğrulanmış etkin ekran veya o anda doğrulanan ekran) pencereyi
        bölge olarak tanımlar ve (2) o bölgenin tanıma işareti GÜNCEL gözlemde bu pencerenin içinde ve
        etkileşime açık (en üstteki pencere) bulunur. Aksi halde pencere tanımsızdır (kapatılmaz, yürütme
        durur)."""
        if dialog.native or dialog.name is None:
            return False
        for screen in (ctx.screen, pending):
            region = screen.region_for(dialog.name) if screen is not None else None
            if screen is None or region is None:
                continue
            for spec in screen.markers:
                if not spec.region or normalize_name(spec.region) != region.key:
                    continue
                resolution = await resolve_target(ctx.observer, spec, presence=True)
                snapshot = ctx.observer.current_snapshot
                control = (
                    snapshot.control(resolution.candidate_id)
                    if resolution.outcome is Outcome.RESOLVED and snapshot and resolution.candidate_id
                    else None
                )
                if (
                    control is not None
                    and control.interaction == "open"
                    and any(
                        c.kind == "dialog" and c.name and normalize_name(c.name) == region.key
                        for c in control.contexts
                    )
                ):
                    return True
        return False

    def _action_changed(self, command: InvokeApprovedActionCommand) -> bool:
        """Plan onaylandıktan sonra aksiyon tanımı veya uygulama bağı değiştiyse (ör. yeniden başlatma)."""
        problem = self._actions.problem(command.action_id, command.action_hash, command.application_id)
        return problem is not None and (command.action_hash is not None or problem != "action_unpinned")

    async def _session_lost(self, ctx: _Ctx) -> bool:
        profile = self._actions.profile
        path = await ctx.driver.current_path()
        if any(path.startswith(prefix) for prefix in profile.session_lost_path_prefixes):
            return True
        if not profile.session_lost_texts:
            return False
        try:
            texts = await ctx.driver.evidence(EvidenceSpec(kind="status_text"), None)
        except AdapterError:
            return False  # sayfa değişiyor olabilir; bu okuma oturum kaybı kanıtı değildir
        return any(match.matches(text, {}) for match in profile.session_lost_texts for text in texts)

    async def _resolve(self, ctx: _Ctx, step: StepRecord, spec: TargetSpec) -> ObservedControl:
        if step.command.get("in_found_row"):
            if ctx.found_key is None:
                raise self._fail(
                    step,
                    ErrorClass.RECORD_NOT_LOADED,
                    "Önce kayıt bulunmalı; satır hedefi çözülmedi, işlem yapılmadı.",
                    RunStatus.FAILED,
                )
            spec = spec.model_copy(update={"row_key": ctx.found_key})
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
                if resolution.reason in {"blocked", "multiple_active_dialogs"}:
                    # Hedef bir pencere/katman arkasında kaldı: hiçbir şey yapılmadı, insan karar verir.
                    raise self._fail(
                        step, ErrorClass.TARGET_BLOCKED, resolution.explanation, RunStatus.PAUSED_BLOCKED
                    )
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
            result: dict[str, Any] = {"adapter": adapter.name, "value": await adapter.read(driver, control)}
            if control.sensitive:
                result["sensitive"] = True  # çıktı bağlamada kullanılamaz
            return False, result
        if isinstance(command, EnsureValueCommand):
            control = await self._resolve(ctx, step, command.target)
            adapter = self._registry.for_control(control)
            r = await adapter.ensure_value(driver, control, command.value)
            return r.changed, {"adapter": adapter.name, "changed": r.changed, "verified": r.verified}
        if isinstance(command, EnsureChoiceCommand):
            return await self._choice(ctx, step, command)
        if isinstance(command, EnsureCheckedCommand):
            return await self._checked(ctx, step, command)
        if isinstance(command, EnsureChoicesCommand):
            return await self._choices(ctx, step, command)
        if isinstance(command, EnsureDateCommand):
            control = await self._resolve(ctx, step, command.target)
            date_adapter = self._registry.for_date(control)
            r = await date_adapter.ensure_date(driver, control, command.value, command.date_format)
            return r.changed, {"adapter": date_adapter.name, "changed": r.changed, "verified": r.verified}
        if isinstance(command, UploadFileCommand):
            return await self._upload(ctx, step, command)
        if isinstance(command, RegisterOptionalDialogsCommand):
            return False, {"optional_dialogs": len(command.dialogs)}
        if isinstance(command, ReturnWindowCommand):
            return await self._return_window(ctx, step, command)
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
        if isinstance(command, AssertScreenCommand):
            result = await self._verify_screen(
                ctx, step, command.screen, recheck=False, context=list(command.context)
            )
            ctx.screen, ctx.context = command.screen, list(command.context)
            return False, result
        raise ControlUnsupported(f"unsupported_command:{command.op}")

    async def _choice(
        self, ctx: _Ctx, step: StepRecord, command: EnsureChoiceCommand
    ) -> tuple[bool, dict[str, Any]]:
        """Seçim. Etkisi bilinmeyen seçim gönderilmeden önce checkpoint yazılır; gönderildikten sonraki hiçbir
        hata otomatik tekrara yol açmaz, sonuç yalnız okumayla uzlaştırılır."""
        control = await self._resolve(ctx, step, command.target)
        adapter: Any = (
            self._registry.for_autocomplete(control)
            if command.autocomplete
            else self._registry.for_control(control)
        )
        dispatched = False
        extra: dict[str, Any] = {"search_text": command.search_text} if command.autocomplete else {}

        async def before_dispatch() -> None:
            nonlocal dispatched
            # Öneri araması yazmak da ekranı değiştirir: gönderim sayılır, hiç tekrarlanmaz.
            if command.effect != "unknown" and command.transition is None and not command.autocomplete:
                return
            step.intent = {"kind": "choice", "effect": "unknown", "prepared_at": _now_iso()}
            self._save(ctx.run)
            if ctx.run.cancel_requested or self.shutting_down:
                step.to(StepState.PENDING)
                raise _Stop(
                    RunStatus.CANCELLED if ctx.run.cancel_requested else RunStatus.PAUSED_SESSION,
                    "cancelled_before_dispatch" if ctx.run.cancel_requested else "shutdown",
                )
            step.to(StepState.DISPATCHED)
            self._save(ctx.run)  # bu noktadan sonra dış etki oluşmuş olabilir
            dispatched = True

        try:
            r = await adapter.ensure_choice(
                ctx.driver,
                control,
                command.choice,
                expected_value=command.expected_value,
                on_dispatch=before_dispatch,
                verify=command.transition is None,
                **extra,
            )
        except SuggestionNotFound as exc:
            # Eşleşme yok ve alan okunarak eski değerine döndü: bilinen başarısızlık (yeniden denenmez).
            step.result = {"adapter": adapter.name, "restored": True}
            raise self._fail(step, exc.error_class, exc.message, RunStatus.FAILED) from None
        except Exception as exc:  # gönderilmiş seçimde hiçbir hata 'güvenle tekrar edilebilir' sayılmaz
            if not dispatched:
                raise
            if command.transition is not None:
                return await self._choice_transition(ctx, step, command, adapter.name)
            return await self._settle_choice(ctx, step, command, adapter.name, type(exc).__name__)
        if command.transition is not None:
            if not r.changed:
                raise self._fail(
                    step,
                    ErrorClass.VERIFICATION_FAILED,
                    "Seçim zaten bu değerde olduğu için ekran geçişi tetiklenmedi; ekranı kontrol edin.",
                    RunStatus.FAILED,
                )
            return await self._choice_transition(ctx, step, command, adapter.name)
        if dispatched:
            step.to(StepState.VERIFYING)
            self._save(ctx.run)
        return r.changed, {"adapter": adapter.name, "changed": r.changed, "observed": r.observed}

    async def _choice_transition(
        self, ctx: _Ctx, step: StepRecord, command: EnsureChoiceCommand, adapter: str
    ) -> tuple[bool, dict[str, Any]]:
        """Seçim ekranı değiştirir: bir kez gönderilmiştir, yalnız hedef ekran beklenir (tekrar seçim yok)."""
        assert command.transition is not None
        source = ctx.screen
        ctx.screen, ctx.context = None, []  # eski ekran ve gözlem artık geçerli değil
        step.to(StepState.VERIFYING)
        self._save(ctx.run)
        try:
            result = await self._await_transition(ctx, command.transition, source)
        except _TransitionFailed as failed:
            step.result = {"adapter": adapter, **failed.detail}
            raise self._fail(step, failed.error_class, failed.message, failed.status) from None
        return True, {"adapter": adapter, "changed": True, **result}

    async def _checked(
        self, ctx: _Ctx, step: StepRecord, command: EnsureCheckedCommand
    ) -> tuple[bool, dict[str, Any]]:
        control = await self._resolve(ctx, step, command.target)
        adapter = self._registry.for_control(control)
        dispatched = False

        async def before_dispatch() -> None:
            nonlocal dispatched
            if command.effect != "unknown":
                return
            await self._mark_dispatched(ctx, step)
            dispatched = True

        try:
            r = await adapter.ensure_checked(
                ctx.driver, control, command.checked, on_dispatch=before_dispatch
            )
        except Exception as exc:
            if not dispatched:
                raise
            return await self._settle_choice(ctx, step, command, adapter.name, type(exc).__name__)
        if dispatched:
            step.to(StepState.VERIFYING)
            self._save(ctx.run)
        return r.changed, {"adapter": adapter.name, "changed": r.changed}

    async def _enter_window(self, ctx: _Ctx, spec: TransitionSpec, deadline: float) -> None:
        """Tek beklenen pencere. Açılmazsa, birden fazlaysa veya adresi uymazsa geçilmez; insan karar verir"""
        while not ctx.observer.new_windows:
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise _TransitionFailed(
                    ErrorClass.NEW_WINDOW, "Beklenen yeni pencere açılmadı.", RunStatus.PAUSED_BLOCKED, {}
                )
            await ctx.driver.wait_for_change(int(min(remaining, 0.25) * 1000))
        outcome = await ctx.handle.adopt_window(spec.window_origin)
        if outcome != "ok":
            raise _TransitionFailed(
                ErrorClass.NEW_WINDOW,
                "Açılan pencere beklenen pencere olarak doğrulanamadı; geçilmedi, müdahale gerekli.",
                RunStatus.PAUSED_BLOCKED,
                {"window": outcome},
            )
        ctx.observer, ctx.driver, ctx.adopted = ctx.handle.observer, ctx.handle.driver, True

    async def _return_window(
        self, ctx: _Ctx, step: StepRecord, command: ReturnWindowCommand
    ) -> tuple[bool, dict[str, Any]]:
        if not ctx.adopted:
            raise self._fail(step, ErrorClass.NEW_WINDOW, "Dönülecek yeni pencere yok.", RunStatus.FAILED)
        if not await ctx.handle.return_main(command.close, command.timeout_ms):
            raise self._fail(
                step, ErrorClass.NEW_WINDOW, "Yeni pencere süresinde kapanmadı.", RunStatus.PAUSED_BLOCKED
            )
        ctx.observer, ctx.driver, ctx.adopted = ctx.handle.observer, ctx.handle.driver, False
        ctx.screen, ctx.context = None, []
        try:
            return False, await self._await_transition(ctx, command, None)
        except _TransitionFailed as failed:
            raise self._fail(step, failed.error_class, failed.message, failed.status) from None

    async def _choices(
        self, ctx: _Ctx, step: StepRecord, command: EnsureChoicesCommand
    ) -> tuple[bool, dict[str, Any]]:
        control = await self._resolve(ctx, step, command.target)
        adapter = self._registry.for_multi(control)
        dispatched = False

        async def before_dispatch() -> None:
            nonlocal dispatched  # kısmi uygulama mümkün: etki beyanından bağımsız her zaman korunur
            await self._mark_dispatched(ctx, step)
            dispatched = True

        try:
            r = await adapter.ensure_choices(
                ctx.driver, control, command.choices, on_dispatch=before_dispatch
            )
        except Exception as exc:
            if not dispatched:
                raise
            return await self._settle_choice(ctx, step, command, adapter.name, type(exc).__name__)
        if dispatched:
            step.to(StepState.VERIFYING)
            self._save(ctx.run)
        return r.changed, {"adapter": adapter.name, "changed": r.changed}

    async def _upload(
        self, ctx: _Ctx, step: StepRecord, command: UploadFileCommand
    ) -> tuple[bool, dict[str, Any]]:
        """Kaynak yalnız yetkili depo. Denetimler gönderimden önce; belirsiz sonuçta yeniden yükleme yok."""
        if self.file_reader is None:
            raise ControlUnsupported("file_store_unavailable")
        control = await self._resolve(ctx, step, command.target)
        try:
            ref, data = await self.file_reader(ctx.run.owner_id, command.artifact_id, command.allowed_types)
        except ApplicationError as exc:
            raise self._fail(
                step, ErrorClass.BUSINESS_VALIDATION, exc.safe_message, RunStatus.FAILED
            ) from None
        await self._mark_dispatched(ctx, step)
        try:
            await ctx.driver.set_file(
                control.candidate_id, ref.file_name or ref.artifact_id, ref.content_type, data
            )
            await ctx.driver.settle()
        except Exception as exc:
            return await self._settle_choice(ctx, step, command, "file", type(exc).__name__)
        step.to(StepState.VERIFYING)
        self._save(ctx.run)
        return True, {"adapter": "file", "changed": True}

    async def _mark_dispatched(self, ctx: _Ctx, step: StepRecord) -> None:
        step.intent = {"kind": "choice", "effect": "unknown", "prepared_at": _now_iso()}
        self._save(ctx.run)
        if ctx.run.cancel_requested or self.shutting_down:
            step.to(StepState.PENDING)
            raise _Stop(
                RunStatus.CANCELLED if ctx.run.cancel_requested else RunStatus.PAUSED_SESSION,
                "cancelled_before_dispatch" if ctx.run.cancel_requested else "shutdown",
            )
        step.to(StepState.DISPATCHED)
        self._save(ctx.run)  # bu noktadan sonra dış etki oluşmuş olabilir

    async def _applied(
        self,
        ctx: _Ctx,
        command: EnsureChoiceCommand | EnsureCheckedCommand | EnsureChoicesCommand | UploadFileCommand,
    ) -> bool:
        """Yalnız okuma: istenen sonuç alanda görülüyor mu? (Hiçbir sürücü eylemi yapılmaz.)"""
        if isinstance(command, UploadFileCommand):
            return False  # yüklemenin hedefte tamamlandığı alan okunarak kanıtlanamaz
        deadline = self._clock() + self._config.reconcile_timeout_ms / 1000
        while True:
            if (
                ctx.observer.native_dialog is not None
                or ctx.observer.new_windows
                or await self._session_lost(ctx)
            ):
                return False
            try:
                resolution = await resolve_target(ctx.observer, command.target)
                if resolution.outcome is Outcome.RESOLVED and resolution.candidate_id:
                    state = await ctx.driver.state(resolution.candidate_id)
                    if isinstance(command, EnsureChoicesCommand):
                        if await self._set_matches(ctx, resolution.candidate_id, command.choices):
                            return True
                    elif isinstance(command, EnsureCheckedCommand):
                        if state.checked is command.checked:
                            return True
                    elif self._choice_matches(
                        state.value if command.autocomplete else state.selected_text,
                        state.selected_value,
                        command.choice,
                        command.expected_value,
                    ):
                        return True
            except AdapterError:
                pass  # ekran yeniden çiziliyor olabilir; süre içinde tekrar okunur
            remaining = deadline - self._clock()
            if remaining <= 0:
                return False
            await ctx.driver.wait_for_change(int(min(remaining, 1.5) * 1000))

    @staticmethod
    async def _set_matches(ctx: _Ctx, cid: str, choices: list[str]) -> bool:
        selected = {choice_key(o.label) for o in await ctx.driver.choice_options(cid) if o.selected}
        return selected == {choice_key(c) for c in choices}

    @staticmethod
    def _choice_matches(text: str | None, value: str | None, choice: str, expected_value: str | None) -> bool:
        if text is None or choice_key(text) != choice_key(choice):
            return False
        return expected_value is None or value is None or value == expected_value

    async def _settle_choice(
        self,
        ctx: _Ctx,
        step: StepRecord,
        command: EnsureChoiceCommand | EnsureCheckedCommand | EnsureChoicesCommand | UploadFileCommand,
        adapter: str,
        reason: str,
    ) -> tuple[bool, dict[str, Any]]:
        step.to(StepState.VERIFYING)
        step.recoveries.append(ErrorClass.WRITE_RESULT_UNKNOWN.value)
        self._save(ctx.run)
        if await self._applied(ctx, command):
            return True, {
                "adapter": adapter,
                "changed": True,
                "verified_by": "reconciliation",
                "reason": reason,
            }
        step.to(StepState.OUTCOME_UNKNOWN)
        step.error_class = ErrorClass.WRITE_RESULT_UNKNOWN.value
        step.message = "İşlem gönderildi ancak sonucu doğrulanamadı; yeniden gönderilmedi."
        step.result = {"adapter": adapter, "verified_by": None, "reason": reason}
        raise _Stop(RunStatus.OUTCOME_UNKNOWN, ErrorClass.WRITE_RESULT_UNKNOWN.value)

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
            ctx.found_key = command.key
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
                anchor = (
                    (await self._resolve(ctx, step, condition.anchor)).candidate_id
                    if condition.anchor is not None
                    else None
                )
                texts = await ctx.driver.evidence(condition.evidence, anchor)
                ok = any(condition.match.matches(t, {}) for t in texts)
                observed = None
            else:
                control = await self._resolve(ctx, step, condition.target)
                if isinstance(condition, ChoicesEqual):
                    self._registry.for_multi(control)
                    if await self._set_matches(ctx, control.candidate_id, condition.choices):
                        return {"condition": condition.type, "satisfied": True}
                    observed, ok = None, False
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        step.result = {"condition": condition.type, "satisfied": False}
                        raise self._fail(
                            step,
                            ErrorClass.VERIFICATION_FAILED,
                            "Koşul süre içinde sağlanmadı.",
                            RunStatus.FAILED,
                        )
                    await ctx.driver.wait_for_change(int(min(remaining, 1.5) * 1000))
                    continue
                adapter: Any = (
                    self._registry.for_autocomplete(control)
                    if isinstance(condition, ChoiceEquals) and condition.autocomplete
                    else self._registry.for_control(control)
                )
                observed = await adapter.read(ctx.driver, control)
                if isinstance(condition, CheckedEquals):
                    ok = observed == ("işaretli" if condition.checked else "işaretli değil")
                elif isinstance(condition, ValueEquals):
                    ok = observed == condition.value
                elif isinstance(condition, ChoiceEquals):
                    state = await ctx.driver.state(control.candidate_id)
                    ok = self._choice_matches(
                        observed, state.selected_value, condition.choice, condition.expected_value
                    )
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

    async def _context_mismatch(self, ctx: _Ctx, context: list[ValueEquals]) -> str | None:
        """Kayıt bağlamı: her koşulun alanı tekil çözülmeli ve değeri beklenene eşit olmalı. Değerler mesaja
        konmaz (iş verisi). Okuma hatası 'doğrulanamadı' sayılır. Bağlam kanıtı ekran kimliği gibi varlık
        kanıtıdır (yalnız okuma): üstünde pencere açık olsa da okunur; pencere politikası engelleyici
        kontrolündedir."""
        for condition in context:
            try:
                resolution = await resolve_target(ctx.observer, condition.target, presence=True)
                snapshot = ctx.observer.current_snapshot
                control = (
                    snapshot.control(resolution.candidate_id)
                    if snapshot and resolution.candidate_id
                    else None
                )
                if resolution.outcome is not Outcome.RESOLVED or control is None:
                    return f"'{condition.target.labels[0]}' bağlam alanı tekil çözülemedi"
                observed = await self._registry.for_control(control).read(ctx.driver, control)
            except AdapterError:
                return f"'{condition.target.labels[0]}' bağlam alanı okunamadı"
            if observed != condition.value:
                return f"'{condition.target.labels[0]}' beklenen kayda ait değil"
        return None

    async def _verify_screen(
        self,
        ctx: _Ctx,
        step: StepRecord,
        screen: ScreenDef,
        *,
        recheck: bool,
        context: list[ValueEquals] | None = None,
    ) -> dict[str, Any]:
        """Ekran (ve kayıt bağlamı) doğrulaması: READINESS_TIMEOUT_MS içinde DOM/frame değişimine bağlı bekler
        (sayfa yükleniyor olabilir). Belirsizlikte beklemeden durur. Başarısızlıkta sürücü eylemi
        yapılmamıştır."""
        deadline = self._clock() + self._config.readiness_timeout_ms / 1000
        while True:
            verdict = await assess_screen(ctx.observer, screen)
            mismatch = await self._context_mismatch(ctx, context or []) if verdict.recognized else None
            if verdict.recognized and mismatch is None:
                return {"screen_id": screen.screen_id, "screen_status": verdict.status.value}
            remaining = deadline - self._clock()
            if mismatch is not None and remaining <= 0:
                step.result = {"screen": verdict.to_dict(), "context": mismatch}
                raise self._fail(
                    step,
                    ErrorClass.RECORD_CONTEXT_MISMATCH,
                    f"Ekran türü doğru ancak kayıt bağlamı farklı: {mismatch}. İşlem yapılmadı.",
                    RunStatus.FAILED,
                )
            if mismatch is not None:
                await ctx.driver.wait_for_change(int(min(remaining, 1.5) * 1000))
                continue
            if verdict.status is ScreenStatus.AMBIGUOUS or remaining <= 0:
                step.result = {"screen": verdict.to_dict()}
                prefix = "Ekran değişti. " if recheck else ""
                raise self._fail(
                    step,
                    ErrorClass.SCREEN_NOT_RECOGNIZED,
                    f"{prefix}{verdict.explanation} İşlem yapılmadı.",
                    RunStatus.PAUSED_AMBIGUOUS
                    if verdict.status is ScreenStatus.AMBIGUOUS
                    else RunStatus.FAILED,
                )
            await self._gate(ctx, step)
            await ctx.driver.wait_for_change(int(min(remaining, 1.5) * 1000))

    # ---- onaylı ekran geçişi (R4) ---------------------------------------------------------

    async def _await_transition(
        self, ctx: _Ctx, spec: TransitionSpec, source: ScreenDef | None, timeout_ms: int | None = None
    ) -> dict[str, Any]:
        """Hedef ekranı ve bağlamını sınırlı süre bekler (sleep yok; DOM/frame değişimi). Başarıda etkin ekran
        hedef olur. Tetikleyici burada ASLA yeniden gönderilmez. Başarısızlık _TransitionFailed fırlatır."""
        deadline = self._clock() + (timeout_ms if timeout_ms is not None else spec.timeout_ms) / 1000
        if spec.window == "new":
            await self._enter_window(ctx, spec, deadline)
        last: dict[str, Any] = {}
        while True:
            try:
                verdict = await assess_screen(ctx.observer, spec.to_screen)
            except Exception as exc:  # gezinme sırasında gözlem kesilebilir: henüz kanıt yok
                logger.info("transition_observe_retry type=%s", type(exc).__name__)
                verdict = None
            if verdict is not None:
                last = verdict.to_dict()
                if verdict.status is ScreenStatus.AMBIGUOUS:
                    raise _TransitionFailed(
                        ErrorClass.SCREEN_NOT_RECOGNIZED,
                        f"Hedef ekran belirsiz: {verdict.explanation} Sonraki adım başlatılmadı.",
                        RunStatus.PAUSED_AMBIGUOUS,
                        {"screen": last},
                    )
                if verdict.recognized:
                    mismatch = await self._context_mismatch(ctx, list(spec.context))
                    if mismatch is None:
                        ctx.screen, ctx.context = spec.to_screen, list(spec.context)
                        return {
                            "transition_id": spec.transition_id,
                            "to_screen": spec.to_screen.screen_id,
                            "transition_completed": True,
                        }
                    last = {**last, "context": mismatch}
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            if ctx.observer.native_dialog is not None or ctx.observer.new_windows:
                break
            await ctx.driver.wait_for_change(int(min(remaining, 1.5) * 1000))
        if "context" in last:
            raise _TransitionFailed(
                ErrorClass.RECORD_CONTEXT_MISMATCH,
                f"'{spec.to_screen.title}' ekranı geldi ancak kayıt bağlamı farklı: {last['context']}. "
                "Sonraki adım başlatılmadı.",
                RunStatus.FAILED,
                last,
            )
        still_source = False
        if source is not None:
            try:
                still_source = (await assess_screen(ctx.observer, source)).recognized
            except Exception:  # kanıt okunamıyorsa kaynak da tanınmamış sayılır
                still_source = False
        if still_source:
            raise _TransitionFailed(
                ErrorClass.TRANSITION_TIMEOUT,
                f"'{spec.to_screen.title}' ekranı {spec.timeout_ms} ms içinde gelmedi; kaynak ekran hâlâ "
                "görünüyor. Geçiş yeniden tetiklenmedi.",
                RunStatus.FAILED,
                last,
            )
        raise _TransitionFailed(
            ErrorClass.UNEXPECTED_SCREEN,
            f"Beklenmeyen ekran: ne kaynak ne '{spec.to_screen.title}' tanındı. Başka rota denenmedi; "
            "geçiş yeniden tetiklenmedi.",
            RunStatus.FAILED,
            last,
        )

    async def _follow(self, ctx: _Ctx, step: StepRecord, command: FollowTransitionCommand) -> None:
        """Yalnız ekran değiştiren onaylı kontrol. Gönderimden önce iptal/kapanış kontrol edilir; gönderimden
        sonra hata 'tekrar dene' değil açık durmadır (çift tetikleme yok)."""
        source = ctx.screen
        control = await self._resolve(ctx, step, command.trigger)
        await ctx.driver.click_trial(control.candidate_id)
        if await ctx.observer.check_candidate(control.candidate_id) is not None:
            raise _Retry(ErrorClass.FRAME_CHANGED.value)
        step.intent = {
            "transition_id": command.transition_id,
            "to_screen": command.to_screen.screen_id,
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
        self._save(ctx.run)  # bu noktadan sonra geçiş tetiklenmiş olabilir: tekrar yok
        ctx.screen, ctx.context = None, []  # eski ekran ve gözlem artık geçerli değil
        click_error: str | None = None
        try:
            await ctx.driver.click(control.candidate_id)
        except AdapterError as exc:
            click_error = exc.error_class.value
        step.to(StepState.VERIFYING)
        self._save(ctx.run)
        try:
            result = await self._await_transition(ctx, command, source)
        except _TransitionFailed as failed:
            step.result = {
                "transition_id": command.transition_id,
                "click_error": click_error,
                **failed.detail,
            }
            raise self._fail(step, failed.error_class, failed.message, failed.status) from None
        step.to(StepState.SUCCEEDED)
        step.result = {**result, "click_error": click_error}

    async def _evaluate(self, ctx: _Ctx, command: EvaluateConditionCommand) -> dict[str, Any]:
        """Guard koşulu: tek değerlendirme, beklemez, başarısız olmaz. Hedef tekil çözülemezse koşul
        sağlanmamıştır."""
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
        if isinstance(condition, ChoicesEqual):
            self._registry.for_multi(control)
            matched = await self._set_matches(ctx, control.candidate_id, condition.choices)
            return {"condition": condition.type, "satisfied": matched}
        autocomplete = isinstance(condition, ChoiceEquals) and condition.autocomplete
        adapter: Any = (
            self._registry.for_autocomplete(control) if autocomplete else self._registry.for_control(control)
        )
        observed = await adapter.read(ctx.driver, control)
        if isinstance(condition, CheckedEquals):
            ok = observed == ("işaretli" if condition.checked else "işaretli değil")
        elif isinstance(condition, ValueEquals):
            ok = observed == condition.value
        elif isinstance(condition, ChoiceEquals):
            ok = self._choice_matches(observed, None, condition.choice, None)
        else:
            ok = observed == "active"
        return {"condition": condition.type, "satisfied": ok}

    # ---- onaylı aksiyon: dispatch sınırı ve uzlaştırma -------------------------------

    async def _invoke(self, ctx: _Ctx, step: StepRecord, command: InvokeApprovedActionCommand) -> None:
        action = self._actions.actions.get(command.action_id)
        if action is None:
            raise self._fail(step, ErrorClass.POLICY_DENIED, "Onaylı aksiyon bulunamadı.", RunStatus.FAILED)
        if self._action_changed(command):
            raise self._fail(
                step,
                ErrorClass.POLICY_DENIED,
                "Onaylı işlemin tanımı değişti; işlem yapılmadı. Yeniden test ve onay gerekir.",
                RunStatus.FAILED,
            )
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
        transition = command.transition
        source = ctx.screen
        # Geçişli aksiyonda kanıt sayfa düzeyinde okunur (tetikleyici hedef ekranda artık yoktur).
        anchor: str | None = None if transition is not None else control.candidate_id
        baseline = None
        if action.reconcile is not None:
            items = await ctx.driver.evidence(action.reconcile.evidence, anchor)
            baseline = sum(1 for i in items if action.reconcile.match.matches(i, params))
        before = await ctx.driver.evidence(action.outcome.evidence, anchor)
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
            **({"transition_id": transition.transition_id} if transition else {}),
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
        if transition is not None:
            ctx.screen, ctx.context = None, []
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
                verdict, detail = await self._await_outcome(ctx, action, params, anchor, before)
            except Exception as exc:  # gönderilmiş adımda hiçbir hata 'bilinen başarısızlık' sayılmaz
                verdict, detail = "unknown", f"verification_error:{type(exc).__name__}"
        if verdict == "success":
            step.to(StepState.SUCCEEDED)
            step.result = {"action_id": action.action_id, "verified_by": "outcome", "evidence": detail}
            await self._complete_action_transition(ctx, step, transition, source)
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
        # Uzlaştırma tanımı olmayan aksiyonda sonuç doğrulanamaz: belirsiz kalır, yeniden gönderilmez.
        if (
            action.reconcile is not None
            and baseline is not None
            and await self._reconcile(ctx, action, params, baseline)
        ):
            step.to(StepState.SUCCEEDED)
            step.result = {"action_id": action.action_id, "verified_by": "reconciliation", "reason": detail}
            await self._complete_action_transition(ctx, step, transition, source, short=True)
            return
        step.to(StepState.OUTCOME_UNKNOWN)
        step.error_class = ErrorClass.WRITE_RESULT_UNKNOWN.value
        step.message = "İşlem gönderildi ancak sonucu doğrulanamadı; yeniden gönderilmedi."
        step.result = {"action_id": action.action_id, "verified_by": None, "reason": detail}
        raise _Stop(RunStatus.OUTCOME_UNKNOWN, ErrorClass.WRITE_RESULT_UNKNOWN.value)

    async def _complete_action_transition(
        self,
        ctx: _Ctx,
        step: StepRecord,
        transition: TransitionSpec | None,
        source: ScreenDef | None,
        short: bool = False,
    ) -> None:
        """İş etkisi doğrulanmış aksiyonun geçişi. Hedefe geçilmezse aksiyon YENİDEN GÖNDERİLMEZ; adım
        başarılı
        (uygulandı) kalır, run açık hatayla durur."""
        if transition is None:
            return
        try:
            result = await self._await_transition(
                ctx, transition, source, self._config.readiness_timeout_ms if short else None
            )
        except _TransitionFailed as failed:
            step.result = {**step.result, "transition_completed": False, **failed.detail}
            step.error_class = ErrorClass.TRANSITION_NOT_COMPLETED.value
            step.message = (
                f"İşlem uygulandı ({step.result.get('verified_by')}) ancak beklenen ekrana geçilmedi: "
                f"{failed.message} Aksiyon yeniden gönderilmedi."
            )
            raise _Stop(RunStatus.FAILED, ErrorClass.TRANSITION_NOT_COMPLETED.value) from None
        step.result = {**step.result, **result}

    async def _await_outcome(
        self,
        ctx: _Ctx,
        action: ApprovedAction,
        params: dict[str, str],
        anchor: str | None,
        before: list[str],
    ) -> tuple[str, str]:
        deadline = self._clock() + self._config.outcome_timeout_ms / 1000
        outcome = action.outcome
        while True:
            if ctx.observer.native_dialog is not None:
                return "unknown", "native_dialog"
            if ctx.observer.new_windows:
                return "unknown", "new_window"
            try:
                texts = await ctx.driver.evidence(outcome.evidence, anchor)
            except AdapterError:  # bayat hedef / gezinme sırasında okunamayan kanıt: henüz sonuç yok
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
            if (
                ctx.observer.native_dialog is not None
                or ctx.observer.new_windows
                or await self._session_lost(ctx)
            ):
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
