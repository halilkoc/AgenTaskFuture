"""Dosya ve kanıt depolama use case'leri (ADR 0016).

- Önce nesne yazılır, sonra metadata. Metadata yazılamazsa nesne silinir (telafi). Nesne yazılamazsa metadata
  hiç oluşmaz. Ortak transaction varmış gibi davranılmaz; arada çöken süreçten kalan öksüz nesneler
  `cleanup_orphans` ile temizlenir.
- Okuma sahip kontrollüdür; başka kullanıcıya "bulunamadı" denir (varlık sızdırılmaz). Metadata olup nesne
  yoksa "eksik" hatası verilir; var gibi gösterilmez. Bütünlük sha256 ile doğrulanır.
- Ekran görüntüsü yalnız maskelemesi doğrulanmışsa kaydedilir; aksi halde reddedilir (otomatik kayıt yok).
- İmzalı bağlantı üretilmez; içerik yetkili uçtan akıtılır. Değerler ve içerik loglanmaz.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from agentask.application.errors import ApplicationError, DependencyUnavailable
from agentask.application.ports.artifacts import ArtifactIndex, ObjectStore
from agentask.domain.artifacts import ALLOWED_CONTENT_TYPES, IMAGE_TYPES, ArtifactRef

logger = logging.getLogger(__name__)


class ArtifactRejected(ApplicationError):
    code = "artifact_rejected"
    safe_message = "Dosya kabul edilmedi."


class ArtifactNotFound(ApplicationError):
    code = "artifact_not_found"
    safe_message = "Dosya bulunamadı."


class ArtifactMissing(ApplicationError):
    code = "artifact_missing"
    safe_message = "Dosyanın kaydı var ancak içeriği depoda bulunamadı veya bozuk; dosya kullanılamaz."


_MAGIC = {"application/pdf": b"%PDF-", "image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}


def content_matches(content_type: str, data: bytes) -> bool:
    """Beyan edilen tür ile içeriğin başlangıcı uyuşmalı (uzantıya veya istemcinin beyanına güvenilmez)."""
    if content_type == "text/plain":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return b"\x00" not in data
    magic = _MAGIC.get(content_type)
    return magic is not None and data.startswith(magic)


def safe_file_name(name: str) -> str | None:
    """Yol parçası veya denetim karakteri taşıyan ad reddedilir; ad dosya yolu olarak hiç kullanılmaz."""
    clean = name.strip()
    if not clean or len(clean) > 120 or clean in {".", ".."}:
        return None
    if any(c in clean for c in "/\\") or any(ord(c) < 32 for c in clean):
        return None
    return clean


class ArtifactService:
    def __init__(
        self,
        store: ObjectStore,
        index: ArtifactIndex,
        max_bytes: int,
        retention_days: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store, self._index = store, index
        self._max_bytes, self._retention = max_bytes, timedelta(days=retention_days)
        self._clock = clock

    async def store(
        self,
        owner: str,
        kind: str,
        content_type: str,
        data: bytes,
        *,
        run_id: str | None = None,
        masking_verified: bool = False,
    ) -> ArtifactRef:
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ArtifactRejected(details={"reason": "content_type"})
        if not data or len(data) > self._max_bytes:
            raise ArtifactRejected(details={"reason": "size", "max_bytes": self._max_bytes})
        if content_type in IMAGE_TYPES and not masking_verified:
            # Hassas alan maskelemesi güvenilir değilse ekran görüntüsü kaydedilmez.
            raise ArtifactRejected(details={"reason": "masking_unverified"})
        now = self._clock()
        ref = ArtifactRef(
            artifact_id="art_" + secrets.token_hex(10),
            owner_id=owner,
            kind=kind,
            content_type=content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            created_at=now,
            retain_until=now + self._retention,
            run_id=run_id,
        )
        try:
            await self._store.put(ref.artifact_id, data, content_type)
        except Exception as exc:
            logger.warning("artifact_put_failed type=%s", type(exc).__name__)
            raise DependencyUnavailable("Dosya depoya yazılamadı; kayıt oluşturulmadı.") from None
        try:
            await self._index.save(ref)
        except Exception as exc:
            logger.warning("artifact_index_failed type=%s", type(exc).__name__)
            try:
                await self._store.delete(ref.artifact_id)  # telafi: metadata'sız nesne bırakılmaz
            except Exception:
                logger.warning("artifact_compensation_failed id=%s", ref.artifact_id)
            raise DependencyUnavailable("Dosya kaydı tamamlanamadı; yüklenen içerik geri alındı.") from None
        return ref

    async def fetch(self, owner: str, artifact_id: str) -> tuple[ArtifactRef, bytes]:
        ref = await self._index.get(artifact_id)
        if ref is None or ref.owner_id != owner:
            raise ArtifactNotFound()
        data = await self._store.get(ref.artifact_id)
        if data is None or hashlib.sha256(data).hexdigest() != ref.sha256:
            raise ArtifactMissing()
        return ref, data

    async def store_upload(self, owner: str, content_type: str, data: bytes, file_name: str) -> ArtifactRef:
        """Kullanıcının kendi dosyası (ekran görüntüsü değil): içerik beyan edilen türle uyuşmalıdır."""
        name = safe_file_name(file_name)
        if name is None:
            raise ArtifactRejected(details={"reason": "file_name"})
        if not content_matches(content_type, data):
            raise ArtifactRejected(details={"reason": "content_mismatch"})
        ref = await self.store(owner, "attachment", content_type, data, masking_verified=True)
        named = ref.model_copy(update={"file_name": name})
        await self._index.save(named)
        return named

    async def read_upload(
        self, owner: str, artifact_id: str, allowed_types: list[str] | None
    ) -> tuple[ArtifactRef, bytes]:
        """Gönderimden hemen önce: sahiplik, tür, boyut, süre ve bütünlük yeniden doğrulanır."""
        ref, data = await self.fetch(owner, artifact_id)
        if ref.kind != "attachment" or ref.file_name is None or ref.retain_until <= self._clock():
            raise ArtifactNotFound()
        if allowed_types is not None and ref.content_type not in allowed_types:
            raise ArtifactRejected(details={"reason": "content_type"})
        if len(data) > self._max_bytes or not content_matches(ref.content_type, data):
            raise ArtifactRejected(details={"reason": "size_or_content"})
        return ref, data

    async def purge_expired(self) -> int:
        now = self._clock()
        expired = [r for r in await self._index.all() if r.retain_until <= now]
        for ref in expired:
            await self._store.delete(ref.artifact_id)
            await self._index.delete(ref.artifact_id)
        return len(expired)

    async def cleanup_orphans(self) -> int:
        """Metadata'sı olmayan nesneler (ör. nesne yazıldıktan sonra çöken süreç) silinir."""
        known = {r.artifact_id for r in await self._index.all()}
        orphans = [k for k in await self._store.list_keys() if k not in known]
        for key in orphans:
            await self._store.delete(key)
        return len(orphans)
