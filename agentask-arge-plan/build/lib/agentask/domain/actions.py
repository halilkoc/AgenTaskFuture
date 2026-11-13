"""Onaylı aksiyon, bilinen engelleyici ve uygulama profili şemaları.

Serbest kod/selector yoktur: aksiyon hedefi anlamsal TargetSpec, etki türü, sonuç kanıtı ve (veri değiştiren
aksiyonlarda) onaylı uzlaştırma okuması zorunludur. Metin şablonlarında yalnız tanımlı parametre adları
kullanılabilir.
"""

from __future__ import annotations

import re
import string
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentask.domain.observation import ControlKind
from agentask.domain.targeting import TargetSpec

_SPACES = re.compile(r"\s+")


def _collapse(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ErrorClass(StrEnum):
    FRAME_CHANGED = "FRAME_CHANGED"
    TARGET_NOT_READY = "TARGET_NOT_READY"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    CONTROL_UNSUPPORTED = "CONTROL_UNSUPPORTED"
    RECORD_NOT_LOADED = "RECORD_NOT_LOADED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    KNOWN_OVERLAY = "KNOWN_OVERLAY"
    UNKNOWN_DIALOG = "UNKNOWN_DIALOG"
    BUSINESS_VALIDATION = "BUSINESS_VALIDATION"
    WRITE_RESULT_UNKNOWN = "WRITE_RESULT_UNKNOWN"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    POLICY_DENIED = "POLICY_DENIED"


class TextMatch(_Model):
    mode: Literal["equals", "prefix", "contains"]
    text: str = Field(min_length=1, max_length=300)

    def placeholders(self) -> set[str]:
        return {name for _, name, _, _ in string.Formatter().parse(self.text) if name}

    def render(self, params: dict[str, str]) -> str:
        return self.text.format_map({k: params.get(k, "") for k in self.placeholders()})

    def matches(self, actual: str, params: dict[str, str]) -> bool:
        expected = _collapse(self.render(params))
        value = _collapse(actual)
        if self.mode == "equals":
            return value == expected
        if self.mode == "prefix":
            return value.startswith(expected)
        return expected in value


class EvidenceSpec(_Model):
    """status_text: hedefin formundaki/bölgesindeki role=status metni. list_items: adı verilen listenin
    öğeleri."""

    kind: Literal["status_text", "list_items"]
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _name_for_lists(self) -> Self:
        if self.kind == "list_items" and self.name is None:
            raise ValueError("list_items kanıtı liste adı gerektirir")
        return self


class FailureRule(_Model):
    """Bilinen başarısızlık metni. applied=False: işlemin uygulanmadığı onaylı bilgidir (güvenle devam
    edilebilir)."""

    match: TextMatch
    error_class: ErrorClass
    applied: Literal[False] = False


class OutcomeSpec(_Model):
    evidence: EvidenceSpec
    success: TextMatch
    failures: list[FailureRule] = Field(default_factory=list)
    unknown: list[TextMatch] = Field(default_factory=list)


class ReconcileSpec(_Model):
    """Belirsiz sonuçta onaylı okuma: sayfa yenilenir, listede eşleşen öğe sayısı tabana göre tam 1
    artmışsa uygulandı."""

    reload: bool = True
    evidence: EvidenceSpec
    match: TextMatch
    expected_increase: Literal[1] = 1


class ParamSpec(_Model):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")
    title: str = Field(min_length=1, max_length=100)
    max_length: int = Field(ge=1, le=500)


class FieldBinding(_Model):
    """Ön koşul: gönderimden hemen önce bu alanın değeri parametreye eşit olmalı (yanlış içerik
    gönderilmesin)."""

    target: TargetSpec
    param: str = Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")


class ApprovedAction(_Model):
    action_id: str = Field(pattern=r"^[a-z0-9_.]{3,80}$")
    title: str = Field(min_length=1, max_length=200)
    target: TargetSpec
    effect: Literal["mutating", "non_mutating"]
    retry_safe: bool
    params: list[ParamSpec] = Field(default_factory=list)
    outcome: OutcomeSpec
    reconcile: ReconcileSpec | None = None
    requires_fields: list[FieldBinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _contract(self) -> Self:
        if self.target.kind is not ControlKind.BUTTON:
            raise ValueError("onaylı aksiyon hedefi düğme olmalı")
        if self.effect == "mutating" and self.reconcile is None:
            raise ValueError("veri değiştiren aksiyon uzlaştırma okuması tanımlamalı")
        declared = {p.name for p in self.params}
        matches = [self.outcome.success, *self.outcome.unknown, *(f.match for f in self.outcome.failures)]
        if self.reconcile is not None:
            matches.append(self.reconcile.match)
        used = set().union(*(m.placeholders() for m in matches))
        if not used <= declared:
            raise ValueError("metin şablonları yalnız tanımlı parametreleri kullanabilir")
        if not {b.param for b in self.requires_fields} <= declared:
            raise ValueError("ön koşul alanları yalnız tanımlı parametrelere bağlanabilir")
        return self


class KnownBlocker(_Model):
    """Onaylı engelleyici pencere: adı ve metni tam eşleşirse yalnız tanımlı düğmeye basılır."""

    blocker_id: str = Field(pattern=r"^[a-z0-9_.]{3,80}$")
    dialog_name: str = Field(min_length=1, max_length=200)
    text: TextMatch
    button_label: str = Field(min_length=1, max_length=100)


class AppProfile(_Model):
    session_lost_path_prefixes: list[str] = Field(default_factory=list)
    session_lost_texts: list[TextMatch] = Field(default_factory=list)


class ActionSet(_Model):
    actions: dict[str, ApprovedAction] = Field(default_factory=dict)
    blockers: list[KnownBlocker] = Field(default_factory=list)
    profile: AppProfile = Field(default_factory=AppProfile)
