"""Bellek içi deney durumu: senaryo parametreleri, lab oturumları ve commit kayıtları."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    delay_ms: int = Field(default=0, ge=0, le=30_000)
    reveal_delay_ms: int = Field(default=1_000, ge=0, le=30_000)
    late_frame_delay_ms: int = Field(default=1_500, ge=0, le=30_000)
    combobox_delay_ms: int = Field(default=300, ge=0, le=10_000)
    dialog: Literal["none", "modal", "unknown_modal", "native"] = "none"
    lose_next_commit_response: bool = False
    lost_response_hang_ms: int = Field(default=5_000, ge=100, le=60_000)
    client_timeout_ms: int = Field(default=2_000, ge=100, le=60_000)
    table_rows: int = Field(default=57, ge=0, le=5_000)
    page_size: int = Field(default=10, ge=1, le=200)
    scroll_batch: int = Field(default=15, ge=1, le=200)
    heavy_fields: int = Field(default=500, ge=1, le=10_000)
    guarantor_customer_label: str = Field(default="Müşteri No", min_length=1, max_length=50)


class ScenarioUpdate(BaseModel):
    """Kısmi güncelleme; bilinmeyen alan reddedilir."""

    model_config = ConfigDict(extra="forbid")

    delay_ms: int | None = Field(default=None, ge=0, le=30_000)
    reveal_delay_ms: int | None = Field(default=None, ge=0, le=30_000)
    late_frame_delay_ms: int | None = Field(default=None, ge=0, le=30_000)
    combobox_delay_ms: int | None = Field(default=None, ge=0, le=10_000)
    dialog: Literal["none", "modal", "unknown_modal", "native"] | None = None
    lose_next_commit_response: bool | None = None
    lost_response_hang_ms: int | None = Field(default=None, ge=100, le=60_000)
    client_timeout_ms: int | None = Field(default=None, ge=100, le=60_000)
    table_rows: int | None = Field(default=None, ge=0, le=5_000)
    page_size: int | None = Field(default=None, ge=1, le=200)
    scroll_batch: int | None = Field(default=None, ge=1, le=200)
    heavy_fields: int | None = Field(default=None, ge=1, le=10_000)
    guarantor_customer_label: str | None = Field(default=None, min_length=1, max_length=50)


class NoteCommit(BaseModel):
    note_no: int
    case_id: str
    text: str
    client_request_id: str
    user: str
    committed_at: datetime


@dataclass
class LabState:
    scenario: Scenario = field(default_factory=Scenario)
    commits: list[NoteCommit] = field(default_factory=list)
    _sessions: dict[str, str] = field(default_factory=dict)

    def apply(self, update: ScenarioUpdate) -> Scenario:
        merged = self.scenario.model_dump() | update.model_dump(exclude_none=True)
        self.scenario = Scenario.model_validate(merged)
        return self.scenario

    def login(self, user: str) -> str:
        token = secrets.token_urlsafe(24)
        self._sessions[token] = user
        return token

    def user_for(self, token: str | None) -> str | None:
        return self._sessions.get(token) if token else None

    def expire_sessions(self) -> int:
        count = len(self._sessions)
        self._sessions.clear()
        return count

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)

    def commit_note(self, case_id: str, text: str, client_request_id: str, user: str) -> NoteCommit:
        commit = NoteCommit(
            note_no=len([c for c in self.commits if c.case_id == case_id]) + 1,
            case_id=case_id,
            text=text,
            client_request_id=client_request_id,
            user=user,
            committed_at=datetime.now(UTC),
        )
        self.commits.append(commit)
        return commit

    def reset(self) -> None:
        self.scenario = Scenario()
        self.commits.clear()
        self._sessions.clear()
