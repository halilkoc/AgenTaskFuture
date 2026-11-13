"""Tek depolama portu: nesne deposu (yerel dosya / kurum içi S3 uyumlu) + metadata dizini (ADR 0016/0018).

Port asenkrondur (S3/MongoDB ağ G/Ç). Nesne deposu ile metadata arasında ortak transaction yoktur; tutarlılık
servis düzeyinde telafi ve temizlikle sağlanır."""

from __future__ import annotations

from typing import Protocol

from agentask.domain.artifacts import ArtifactRef


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Tamamı yazılmadan nesne görünür olmamalı (atomik yerleştirme)."""
        ...

    async def get(self, key: str) -> bytes | None:
        """Nesne yoksa None (var gibi davranılmaz)."""
        ...

    async def delete(self, key: str) -> None: ...

    async def list_keys(self) -> list[str]: ...


class ArtifactIndex(Protocol):
    async def save(self, ref: ArtifactRef) -> None: ...

    async def get(self, artifact_id: str) -> ArtifactRef | None: ...

    async def delete(self, artifact_id: str) -> None: ...

    async def all(self) -> list[ArtifactRef]: ...
