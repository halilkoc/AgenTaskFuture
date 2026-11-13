"""Dosya/kanıt referansı (ADR 0013, 0016). Katalog içine binary/base64 gömülmez; yalnız referans tutulur."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ARTIFACT_ID_PATTERN = r"^art_[a-z0-9]{20}$"
ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "application/pdf", "text/plain"})
IMAGE_TYPES = frozenset({"image/png", "image/jpeg"})


class ArtifactRef(BaseModel):
    """Metadata: erişim (sahip), içerik türü/boyutu, bütünlük (sha256) ve saklama süresi."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(pattern=ARTIFACT_ID_PATTERN)
    owner_id: str = Field(min_length=1, max_length=200)
    kind: Literal["evidence", "attachment"]
    content_type: str
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    retain_until: datetime
    run_id: str | None = Field(default=None, max_length=64)
    file_name: str | None = Field(default=None, max_length=120)  # yalnız kullanıcı yüklemesi; loglanmaz
