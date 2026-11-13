"""Run ve step durum makineleri. Geçersiz geçiş IllegalTransition üretir; durumlar checkpoint olarak JSON'a
yazılır."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IllegalTransition(RuntimeError):
    pass


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    PAUSED_SESSION = "paused_session"
    PAUSED_AMBIGUOUS = "paused_ambiguous"
    PAUSED_BLOCKED = "paused_blocked"
    CANCELLED = "cancelled"


class StepState(StrEnum):
    PENDING = "pending"
    PREPARED = "prepared"
    DISPATCHED = "dispatched"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    KNOWN_FAILED = "known_failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    SKIPPED = "skipped"


_PAUSED = {RunStatus.PAUSED_SESSION, RunStatus.PAUSED_AMBIGUOUS, RunStatus.PAUSED_BLOCKED}
_STOPPING = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.OUTCOME_UNKNOWN, RunStatus.CANCELLED, *_PAUSED}

RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED},
    RunStatus.RUNNING: {RunStatus.CANCEL_REQUESTED, *_STOPPING},
    RunStatus.CANCEL_REQUESTED: {
        RunStatus.CANCELLED,
        RunStatus.COMPLETED,
        RunStatus.OUTCOME_UNKNOWN,
        RunStatus.FAILED,
        *_PAUSED,
    },
    **{p: {RunStatus.RUNNING, RunStatus.CANCELLED} for p in _PAUSED},
    RunStatus.OUTCOME_UNKNOWN: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}

STEP_TRANSITIONS: dict[StepState, set[StepState]] = {
    StepState.PENDING: {StepState.PREPARED, StepState.SKIPPED, StepState.KNOWN_FAILED},
    StepState.PREPARED: {
        StepState.DISPATCHED,
        StepState.SUCCEEDED,
        StepState.KNOWN_FAILED,
        StepState.PENDING,
        StepState.SKIPPED,
    },
    StepState.DISPATCHED: {StepState.VERIFYING, StepState.OUTCOME_UNKNOWN, StepState.KNOWN_FAILED},
    # VERIFYING → PREPARED yalnız retry_safe adımlar için executor tarafından kullanılır.
    StepState.VERIFYING: {
        StepState.SUCCEEDED,
        StepState.KNOWN_FAILED,
        StepState.OUTCOME_UNKNOWN,
        StepState.PREPARED,
    },
    # Belirsiz sonuç yalnız uzlaştırma kanıtıyla kapanır; yeniden gönderim yoktur.
    StepState.OUTCOME_UNKNOWN: {StepState.SUCCEEDED},
    # Uygulanmadığı onaylı bilinen hata (ör. oturum düşmüş, 401) devamda yeniden denenebilir.
    StepState.KNOWN_FAILED: {StepState.PENDING},
    StepState.SUCCEEDED: set(),
    StepState.SKIPPED: set(),
}

TERMINAL_RUN = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
RESUMABLE_RUN = {*_PAUSED, RunStatus.OUTCOME_UNKNOWN}


def _now() -> datetime:
    return datetime.now(UTC)


class StepRecord(BaseModel):
    index: int
    command: dict[str, Any]
    state: StepState = StepState.PENDING
    attempts: int = 0
    error_class: str | None = None
    message: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    intent: dict[str, Any] | None = None
    recoveries: list[str] = Field(default_factory=list)
    retry_allowed: bool = False
    # Birleştirme guard'ı: {"step": i, "is": True} → i. adım koşulu sağlanmazsa bu adım atlanır.
    when: dict[str, Any] | None = None
    updated_at: datetime = Field(default_factory=_now)

    def to(self, state: StepState) -> None:
        if state not in STEP_TRANSITIONS[self.state]:
            raise IllegalTransition(f"step {self.state} → {state}")
        self.state = state
        self.updated_at = _now()


class Run(BaseModel):
    run_id: str
    owner_id: str
    session_id: str
    request_id: str
    payload_hash: str
    status: RunStatus = RunStatus.CREATED
    status_reason: str | None = None
    cancel_requested: bool = False
    steps: list[StepRecord]
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    revision: int = 0
    # Asistan run'ları: release_id, operation_id, revision, content_hash (run boyunca değişmez; pin).
    binding: dict[str, Any] | None = None
    # G: maskelemesi doğrulanmış kanıt referansları (artifact_id); içerik ayrı depodadır.
    evidence: list[str] = Field(default_factory=list)
    # Geçmiş ekranı ve destek: işlem adı ve başlatan isteğin korelasyon numarası (eski kayıtlarda yok).
    title: str | None = None
    correlation_id: str | None = None
    # Kim durdurdu: "user" | "system_timeout" (eski kayıtlarda yok; bilinmiyor sayılır).
    cancelled_by: str | None = None

    @classmethod
    def new(
        cls,
        *,
        owner_id: str,
        session_id: str,
        request_id: str,
        payload_hash: str,
        commands: list[dict[str, Any]],
    ) -> Run:
        return cls(
            run_id=f"run-{secrets.token_urlsafe(10)}",
            owner_id=owner_id,
            session_id=session_id,
            request_id=request_id,
            payload_hash=payload_hash,
            steps=[StepRecord(index=i, command=c) for i, c in enumerate(commands)],
        )

    def set_status(self, status: RunStatus, reason: str | None = None) -> None:
        if status not in RUN_TRANSITIONS[self.status]:
            raise IllegalTransition(f"run {self.status} → {status}")
        self.status = status
        self.status_reason = reason
        self.updated_at = _now()

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_RUN
