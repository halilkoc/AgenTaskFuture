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
    # R3 ekran senaryoları: benzer yanlış ekran, yinelenen Kefil bölgesi, işlem sırasında ekran değişimi.
    party_layout: Literal["standard", "similar", "duplicate_guarantor", "with_change_note"] = "standard"
    party_switch: Literal["none", "dom", "navigate"] = "none"
    # R4 çok ekranlı başvuru sihirbazı senaryoları.
    wizard_delay_ms: int = Field(default=0, ge=0, le=30_000)  # "Devam" sonrası hedef ekran gecikmesi
    wizard_target: Literal["collateral", "unexpected", "duplicate", "other_case", "none"] = "collateral"
    wizard_dialog: bool = False  # teminat ekranında tanımsız pencere (devam/resume senaryosu)
    lose_next_submit_response: bool = False  # gönderim kaydedilir, yanıt istemciye ulaşmaz
    # Seçim senaryoları (/pages/selections).
    selection_options_delay_ms: int = Field(default=0, ge=0, le=10_000)  # seçeneklerin geç yüklenmesi
    selection_catalog: Literal["standard", "changed"] = "standard"  # kayda göre değişen seçenekler
    selection_redraw: bool = False  # liste açılınca seçenekler bir kez yeniden çizilir
    selection_outcome: Literal["ok", "reject", "revert", "late"] = "ok"  # veri etkili seçimin sonucu
    selection_modal: bool = False  # açık pencere (arkadaki alanlar kullanılamaz)
    selection_value_trap: bool = False  # özel liste doğru etiketi gösterip başka değer yayımlar


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
    party_layout: Literal["standard", "similar", "duplicate_guarantor", "with_change_note"] | None = None
    party_switch: Literal["none", "dom", "navigate"] | None = None
    wizard_delay_ms: int | None = Field(default=None, ge=0, le=30_000)
    wizard_target: Literal["collateral", "unexpected", "duplicate", "other_case", "none"] | None = None
    wizard_dialog: bool | None = None
    lose_next_submit_response: bool | None = None
    selection_options_delay_ms: int | None = Field(default=None, ge=0, le=10_000)
    selection_catalog: Literal["standard", "changed"] | None = None
    selection_redraw: bool | None = None
    selection_outcome: Literal["ok", "reject", "revert", "late"] | None = None
    selection_modal: bool | None = None
    selection_value_trap: bool | None = None


class Application(BaseModel):
    application_no: int
    case_id: str
    customer_no: str
    amount: str
    document_no: str
    user: str


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
    applications: list[Application] = field(default_factory=list)
    wizard_advances: dict[str, int] = field(default_factory=dict)
    selection_commits: list[str] = field(default_factory=list)  # veri etkili seçimin kaç kez gönderildiği
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

    def submit_application(
        self, case_id: str, customer_no: str, amount: str, document_no: str, user: str
    ) -> Application:
        app = Application(
            application_no=len(self.applications) + 1,
            case_id=case_id,
            customer_no=customer_no,
            amount=amount,
            document_no=document_no,
            user=user,
        )
        self.applications.append(app)
        return app

    def reset(self) -> None:
        self.scenario = Scenario()
        self.commits.clear()
        self.applications.clear()
        self.wizard_advances.clear()
        self.selection_commits.clear()
        self._sessions.clear()
