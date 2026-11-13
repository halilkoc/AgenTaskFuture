"""Run yaşam döngüsü: oluşturma (request_id idempotency), iptal, devam ve süreç yeniden başlatma
kurtarması."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from agentask.application.errors import (
    IdempotencyConflict,
    PlanInvalid,
    RunNotFound,
    RunNotResumable,
    SessionApplicationMismatch,
)
from agentask.application.observability import (
    SOFTWARE,
    current_correlation_id,
    log_context,
    log_event,
)
from agentask.application.ports.runs import RunRepository
from agentask.application.services.browser_sessions import BrowserSessionService
from agentask.application.services.executor import COMMAND, Executor
from agentask.domain.actions import ActionSet
from agentask.domain.commands import PlanRejected, validate_plan
from agentask.domain.origins import origin_of
from agentask.domain.run_summary import outcome_of, run_log_fields
from agentask.domain.runtime import RESUMABLE_RUN, Run, RunStatus, StepState

logger = logging.getLogger(__name__)
EVIDENCE_STATUSES = {
    RunStatus.FAILED,
    RunStatus.OUTCOME_UNKNOWN,
    RunStatus.PAUSED_AMBIGUOUS,
    RunStatus.PAUSED_BLOCKED,
}


def recover_interrupted(repository: RunRepository) -> list[Run]:
    """Süreç kesildiğinde yarım kalan run'ları güvenli duruma çeker. Eski browser nesneleri geri yüklenmez.

    - Gönderilmiş ama doğrulanmamış adım → outcome_unknown (sonuç bilinmiyor; yeniden gönderilmez).
    - Gönderim yoksa run paused_session (devam için yeni oturum ve bağlam doğrulaması gerekir).
    - İptal talebi varsa ve gönderim yoksa iptal tamamlanır.
    """
    recovered: list[Run] = []
    for run in repository.list_all():
        if run.status not in {RunStatus.RUNNING, RunStatus.CANCEL_REQUESTED, RunStatus.CREATED}:
            continue
        in_flight = [s for s in run.steps if s.state in {StepState.DISPATCHED, StepState.VERIFYING}]
        for step in in_flight:
            step.to(StepState.OUTCOME_UNKNOWN)
            step.error_class = "WRITE_RESULT_UNKNOWN"
            step.message = "Süreç, işlem gönderildikten sonra kesildi; sonuç doğrulanmadı."
        for step in run.steps:
            if step.state is StepState.PREPARED:
                step.to(StepState.PENDING)
        if in_flight:
            run.set_status(RunStatus.OUTCOME_UNKNOWN, "process_restart")
        elif run.status is RunStatus.CANCEL_REQUESTED or run.cancel_requested:
            for step in run.steps:
                if step.state is StepState.PENDING:
                    step.to(StepState.SKIPPED)
            run.set_status(RunStatus.CANCELLED, "cancelled_during_restart")
        elif run.status is RunStatus.CREATED:
            run.set_status(RunStatus.FAILED, "process_restart_before_start")
        else:
            run.set_status(RunStatus.PAUSED_SESSION, "process_restart")
        repository.save(run)
        recovered.append(run)
        log_event(
            logger,
            "run_recovered",
            level=logging.WARNING,
            audit=True,
            outcome=outcome_of(run.status),
            status=run.status.value,
            reason=run.status_reason,
            correlation_id=run.correlation_id,
            **run_log_fields(run),
        )
    return recovered


def _payload_hash(session_id: str, steps: list[dict[str, Any]]) -> str:
    canonical = json.dumps({"session_id": session_id, "steps": steps}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RunService:
    """Run'ları oluşturur ve arka planda yürütür. Run, oturum kilidini ('run' işlemi) baştan sona tutar;
    aynı oturumda başka çalıştırma veya gözlem 409 alır. Kilit bellek içidir (tek worker)."""

    def __init__(
        self,
        repository: RunRepository,
        sessions: BrowserSessionService,
        executor: Executor,
        actions: ActionSet,
        max_steps: int,
        allow_composition: bool = False,
    ) -> None:
        self._allow_composition = allow_composition
        self._repo = repository
        self._sessions = sessions
        self._executor = executor
        self._actions = actions
        self._max_steps = max_steps
        self._active: dict[str, Run] = {}
        # (run, oturum tutamacı) → artifact_id | None. Yalnız EVIDENCE_SCREENSHOTS_ENABLED iken bağlanır.
        self.evidence: Callable[[Run, Any], Awaitable[str | None]] | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def actions(self) -> ActionSet:
        return self._actions

    def start_recovery(self) -> list[Run]:
        return recover_interrupted(self._repo)

    def _parse(self, raw_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            steps = [COMMAND.validate_python(s) for s in raw_steps]
        except ValidationError as exc:
            fields = [".".join(str(p) for p in e["loc"]) for e in exc.errors(include_input=False)]
            raise PlanInvalid(details={"reason": "schema", "fields": fields[:20]}) from None
        try:
            validate_plan(steps, self._actions, self._max_steps, self._allow_composition)
        except PlanRejected as exc:
            raise PlanInvalid(details={"reason": exc.reason, "step": exc.step}) from None
        return [s.model_dump(mode="json", exclude_none=True) for s in steps]

    async def create(
        self,
        owner_id: str,
        session_id: str,
        request_id: str,
        raw_steps: list[dict[str, Any]],
        binding: dict[str, Any] | None = None,
        guards: list[dict[str, Any] | None] | None = None,
        allow_verification: bool = False,
        required_origin: str | None = None,
        title: str | None = None,
    ) -> Run:
        steps = self._parse(raw_steps)
        digest = _payload_hash(session_id, steps)
        existing = self._repo.find_by_request(owner_id, request_id)
        if existing is not None:
            if existing.payload_hash != digest:
                raise IdempotencyConflict()
            return self._active.get(existing.run_id, existing)
        stack = contextlib.AsyncExitStack()
        handle = await stack.enter_async_context(
            self._sessions.operation(owner_id, session_id, "run", allow_verification=allow_verification)
        )
        if required_origin is not None and origin_of(handle.current_url) != required_origin:
            # Uygulama kapsamı: başka uygulamanın sayfasında (veya boş oturumda) run başlatılmaz.
            await stack.aclose()
            raise SessionApplicationMismatch()
        run = Run.new(
            owner_id=owner_id,
            session_id=session_id,
            request_id=request_id,
            payload_hash=digest,
            commands=steps,
        )
        run.binding = binding
        run.title = title[:200] if title else None
        run.correlation_id = current_correlation_id()
        for step, guard in zip(run.steps, guards or [], strict=False):
            if guard is not None and not 0 <= int(guard["step"]) < step.index:
                raise PlanInvalid(details={"reason": "invalid_guard"})
            step.when = guard
        self._repo.save(run)
        self._start(run, handle, stack)
        return run

    async def resume(
        self, owner_id: str, run_id: str, session_id: str, allow_verification: bool = False
    ) -> Run:
        if run_id in self._active:
            raise RunNotResumable("Çalıştırma zaten sürüyor.")
        run = self._repo.get(run_id)
        if run is None or run.owner_id != owner_id:
            raise RunNotFound()
        if run.status not in RESUMABLE_RUN:
            raise RunNotResumable()
        stack = contextlib.AsyncExitStack()
        handle = await stack.enter_async_context(
            self._sessions.operation(owner_id, session_id, "run", allow_verification=allow_verification)
        )
        run.session_id = session_id  # eski browser nesneleri yok; yeni oturumda bağlam yeniden doğrulanır
        log_event(logger, "run_resume_requested", audit=True, status=run.status.value, **run_log_fields(run))
        self._start(run, handle, stack)
        return run

    def _start(self, run: Run, handle: Any, stack: contextlib.AsyncExitStack) -> None:
        self._active[run.run_id] = run

        async def drive() -> None:
            # Görev, başlatan isteğin bağlamını devralır; yeniden başlatma sonrası korelasyon kayıttan gelir.
            context: dict[str, Any] = {"run_id": run.run_id, "actor": run.owner_id}
            if current_correlation_id() is None:
                context["correlation_id"] = run.correlation_id
            with log_context(**context):
                try:
                    await self._executor.execute(run, handle)
                    if self.evidence is not None and run.status in EVIDENCE_STATUSES:
                        await self._record_evidence(run, handle)
                except asyncio.CancelledError:
                    raise  # süreç kesintisi: son durum yazılmaz; checkpoint yeniden başlatmada kurtarılır
                except Exception as exc:
                    self._mark_crashed(run)
                    log_event(
                        logger,
                        "run_finished",
                        level=logging.ERROR,
                        audit=True,
                        exc_info=exc,
                        outcome=outcome_of(run.status),
                        status=run.status.value,
                        reason=run.status_reason,
                        error_code="internal_error",
                        error_kind=SOFTWARE,
                        **run_log_fields(run),
                    )
                finally:
                    self._active.pop(run.run_id, None)
                    self._tasks.pop(run.run_id, None)
                    await stack.aclose()

        self._tasks[run.run_id] = asyncio.create_task(drive(), name=f"run:{run.run_id}")

    def attach_file_reader(self, reader: Callable[..., Awaitable[tuple[Any, bytes]]]) -> None:
        self._executor.file_reader = reader

    async def _record_evidence(self, run: Run, handle: Any) -> None:
        """Başarısız/belirsiz/duran run için tek maskeli kanıt. Kanıt alınamaması run sonucunu değiştirmez."""
        assert self.evidence is not None
        try:
            artifact_id = await self.evidence(run, handle)
        except Exception as exc:
            logger.warning("evidence_failed run=%s type=%s", run.run_id, type(exc).__name__)
            return
        if artifact_id:
            run.evidence = [*run.evidence, artifact_id]
            self._repo.save(run)

    def _mark_crashed(self, run: Run) -> None:
        in_flight = False
        for step in run.steps:
            if step.state in {StepState.DISPATCHED, StepState.VERIFYING}:
                step.to(StepState.OUTCOME_UNKNOWN)
                step.error_class = "WRITE_RESULT_UNKNOWN"
                in_flight = True
            elif step.state is StepState.PREPARED:
                step.to(StepState.PENDING)
        with contextlib.suppress(Exception):
            run.set_status(RunStatus.OUTCOME_UNKNOWN if in_flight else RunStatus.FAILED, "internal_error")
        self._repo.save(run)

    def get(self, owner_id: str, run_id: str) -> Run:
        run = self._active.get(run_id) or self._repo.get(run_id)
        if run is None or run.owner_id != owner_id:
            raise RunNotFound()
        return run

    def list_runs(self, owner_id: str) -> list[Run]:
        stored = {r.run_id: r for r in self._repo.list_for(owner_id)}
        stored.update({k: v for k, v in self._active.items() if v.owner_id == owner_id})
        return sorted(stored.values(), key=lambda r: r.created_at, reverse=True)

    async def cancel(self, owner_id: str, run_id: str, by: str = "user") -> Run:
        """by: "user" (kullanıcı kararı) veya "system_timeout" (süre aşımı); geçmişte ayrı gösterilir."""
        run = self.get(owner_id, run_id)
        if run.is_terminal:
            return run
        run.cancel_requested = True
        run.cancelled_by = by
        if run_id in self._active:
            if run.status is RunStatus.RUNNING:
                run.set_status(RunStatus.CANCEL_REQUESTED, "cancel_requested")
            self._repo.save(run)
            # Durdurma talebi sonuç değildir; run_finished yürütücü durunca yazılır.
            log_event(
                logger,
                "run_cancel_requested",
                audit=True,
                status=run.status.value,
                action=by,
                **run_log_fields(run),
            )
            return run
        # Duraklamış/belirsiz run: yeni adım başlamaz. Belirsiz adım durumunu korur (geri alındı sanılmaz).
        for step in run.steps:
            if step.state is StepState.PENDING:
                step.to(StepState.SKIPPED)
        run.set_status(RunStatus.CANCELLED, "cancelled_while_paused")
        self._repo.save(run)
        log_event(
            logger,
            "run_finished",
            audit=True,
            outcome=outcome_of(run.status),
            status=run.status.value,
            reason=run.status_reason,
            **run_log_fields(run),
        )
        return run

    def task_for(self, run_id: str) -> asyncio.Task[None] | None:
        return self._tasks.get(run_id)

    async def wait(self, run_id: str, timeout: float) -> Run:
        task = self._tasks.get(run_id)
        if task is not None:
            await asyncio.wait({task}, timeout=timeout)
        run = self._active.get(run_id) or self._repo.get(run_id)
        assert run is not None
        return run

    async def shutdown(self, grace_s: float = 5.0) -> None:
        """Yeni adım/dispatch başlatılmaz; süren adımlar kısa süre beklenir, sonra görev kesilir
        (checkpoint'teki gönderilmiş adımlar bir sonraki açılışta outcome_unknown olur)."""
        self._executor.shutting_down = True
        tasks = list(self._tasks.values())
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=grace_s)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
