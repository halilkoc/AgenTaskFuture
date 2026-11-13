"""Yayın modeli: hash-bağlı onay, değişmez operasyon revizyonu, tam release manifestosu, aktif pointer."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ADAPTER_VERSION = "controls-p3.1"
SCHEMA_VERSION = "catalog-v1"


def _now() -> datetime:
    # MongoDB milisaniye saklar; değişmez kayıt geri okunduğunda birebir aynı olmalı.
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def canonical_hash(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovalRecord(_Frozen):
    """Sunucu tarafı onay: kim, hangi içerik hash'i, hangi test kanıtı, hangi adapter/şema sürümü."""

    draft_id: str
    approver: str
    content_hash: str
    test_run_id: str
    test_evidence_hash: str
    adapter_version: str = ADAPTER_VERSION
    schema_version: str = SCHEMA_VERSION
    at: datetime = Field(default_factory=_now)

    @property
    def approval_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json", exclude={"at"}))


class OperationRevision(_Frozen):
    application_id: str
    operation_id: str
    revision: int = Field(ge=1)
    content_hash: str
    definition: dict[str, Any]
    approved_by: str
    approval_hash: str
    schema_version: str = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=_now)


class ManifestEntry(_Frozen):
    operation_id: str
    revision: int
    content_hash: str


class ReleaseManifest(_Frozen):
    release_id: str
    request_id: str
    application_id: str
    environment: str
    operations: list[ManifestEntry]
    base_release_id: str | None
    approvals: list[ApprovalRecord]
    adapter_version: str = ADAPTER_VERSION
    schema_version: str = SCHEMA_VERSION
    manifest_hash: str
    created_by: str
    created_at: datetime = Field(default_factory=_now)

    @staticmethod
    def compute_hash(application_id: str, environment: str, operations: list[ManifestEntry]) -> str:
        return canonical_hash(
            {
                "application_id": application_id,
                "environment": environment,
                "operations": [o.model_dump() for o in sorted(operations, key=lambda o: o.operation_id)],
                "adapter_version": ADAPTER_VERSION,
                "schema_version": SCHEMA_VERSION,
            }
        )


class ActivePointer(_Frozen):
    application_id: str
    environment: str
    release_id: str
    version: int
    updated_by: str
    updated_at: datetime = Field(default_factory=_now)
