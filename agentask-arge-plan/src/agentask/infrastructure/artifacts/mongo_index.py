"""Dosya/kanıt metadatası için MongoDB adaptörü (ADR 0013/0018). İçerik değil yalnız referans tutulur.

Koleksiyon: `artifact_index` (artifact_id tekil). Saklama sonu (`retain_until`) dizinlidir; silme yine servis
(`purge_expired`) üzerinden yapılır, böylece nesne ve metadata birlikte kaldırılır (TTL ile metadata'nın tek
başına silinip öksüz nesne kalması önlenir)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import PyMongoError

from agentask.application.errors import DependencyUnavailable
from agentask.domain.artifacts import ARTIFACT_ID_PATTERN, ArtifactRef

logger = logging.getLogger(__name__)
COLLECTION = "artifact_index"
_KEY = re.compile(ARTIFACT_ID_PATTERN)


class MongoArtifactIndex:
    def __init__(
        self,
        uri: str,
        database: str,
        timeout_ms: int,
        tls_ca_file: Path | None = None,
        client: AsyncMongoClient[dict[str, Any]] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "serverSelectionTimeoutMS": timeout_ms,
            "tz_aware": True,
            "appname": "agentask",
        }
        if tls_ca_file is not None:
            kwargs["tlsCAFile"] = str(tls_ca_file)
        self._client = client or AsyncMongoClient(uri, **kwargs)
        self._col = self._client[database][COLLECTION]
        self._ready = False

    async def close(self) -> None:
        await self._client.close()

    async def _ensure(self) -> None:
        if self._ready:
            return
        await self._col.create_index("artifact_id", unique=True)
        await self._col.create_index([("retain_until", ASCENDING)])
        await self._col.create_index([("owner_id", ASCENDING), ("created_at", ASCENDING)])
        self._ready = True

    async def _guard(self, op: Any) -> Any:
        try:
            await self._ensure()
            return await op()
        except PyMongoError as exc:
            logger.warning("artifact_index_unavailable type=%s", type(exc).__name__)
            raise DependencyUnavailable("Dosya metadatasına erişilemiyor.") from None

    async def save(self, ref: ArtifactRef) -> None:
        doc = ref.model_dump(mode="python")
        await self._guard(lambda: self._col.replace_one({"artifact_id": ref.artifact_id}, doc, upsert=True))

    async def get(self, artifact_id: str) -> ArtifactRef | None:
        if not _KEY.fullmatch(artifact_id):
            return None
        doc = await self._guard(lambda: self._col.find_one({"artifact_id": artifact_id}, {"_id": 0}))
        return ArtifactRef.model_validate(doc) if doc else None

    async def delete(self, artifact_id: str) -> None:
        if _KEY.fullmatch(artifact_id):
            await self._guard(lambda: self._col.delete_one({"artifact_id": artifact_id}))

    async def all(self) -> list[ArtifactRef]:
        async def load() -> list[dict[str, Any]]:
            return [d async for d in self._col.find({}, {"_id": 0}).sort("artifact_id", ASCENDING)]

        return [ArtifactRef.model_validate(d) for d in await self._guard(load)]
