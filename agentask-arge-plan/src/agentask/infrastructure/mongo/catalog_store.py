"""MongoDB yayımlanmış katalog adapteri (pymongo async).

Koleksiyonlar (docs/02): catalog_operations (application_id+operation_id+revision unique), catalog_screens
(application_id+screen_id+revision unique; R3), catalog_releases
(release_id unique, request_id unique), catalog_active_releases (application_id+environment unique).
$jsonSchema validator + Pydantic doğrulaması birlikte. Standalone Mongo'da da güvenli: pointer en son CAS
ile değişir. ensure_schema yalnız ekler/günceller: mevcut belgeler silinmez veya yeniden yazılmaz; v1
(ekransız) revizyon ve manifestolar olduğu gibi okunur.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.errors import CollectionInvalid, DuplicateKeyError, PyMongoError

from agentask.application.errors import ContentConflict, DependencyUnavailable
from agentask.domain.release import (
    ActivationRecord,
    ActivePointer,
    OperationRevision,
    ReleaseManifest,
    ScreenRevision,
)

logger = logging.getLogger(__name__)

OPERATIONS, RELEASES, ACTIVE = "catalog_operations", "catalog_releases", "catalog_active_releases"
SCREENS = "catalog_screens"
ACTIVATIONS = "catalog_activations"

_VALIDATORS: dict[str, dict[str, Any]] = {
    OPERATIONS: {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "application_id",
                "operation_id",
                "revision",
                "content_hash",
                "definition",
                "approved_by",
                "approval_hash",
                "schema_version",
            ],
            "properties": {
                "application_id": {"bsonType": "string"},
                "operation_id": {"bsonType": "string"},
                "revision": {"bsonType": ["int", "long"], "minimum": 1},
                "content_hash": {"bsonType": "string", "minLength": 64, "maxLength": 64},
                "definition": {"bsonType": "object"},
            },
        }
    },
    SCREENS: {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "application_id",
                "screen_id",
                "revision",
                "content_hash",
                "definition",
                "approved_by",
                "approval_hash",
                "schema_version",
            ],
            "properties": {
                "application_id": {"bsonType": "string"},
                "screen_id": {"bsonType": "string"},
                "revision": {"bsonType": ["int", "long"], "minimum": 1},
                "content_hash": {"bsonType": "string", "minLength": 64, "maxLength": 64},
                "definition": {"bsonType": "object", "required": ["screen_id", "title", "markers"]},
            },
        }
    },
    RELEASES: {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "release_id",
                "request_id",
                "application_id",
                "environment",
                "operations",
                "manifest_hash",
                "approvals",
                "created_by",
            ],
            "properties": {
                "release_id": {"bsonType": "string"},
                "operations": {"bsonType": "array", "minItems": 1, "maxItems": 500},
                "manifest_hash": {"bsonType": "string", "minLength": 64, "maxLength": 64},
            },
        }
    },
    ACTIVE: {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["application_id", "environment", "release_id", "version"],
            "properties": {"version": {"bsonType": ["int", "long"], "minimum": 1}},
        }
    },
}


def _strip(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


class MongoCatalogStore:
    def __init__(self, uri: str, database: str, timeout_ms: int, tls_ca_file: Path | None = None) -> None:
        kwargs: dict[str, Any] = {
            "serverSelectionTimeoutMS": timeout_ms,
            "tz_aware": True,
            "appname": "agentask",
        }
        if tls_ca_file is not None:
            kwargs["tlsCAFile"] = str(tls_ca_file)
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(uri, **kwargs)
        self._db = self._client[database]

    async def close(self) -> None:
        await self._client.close()

    async def ping(self) -> bool:
        try:
            await self._db.command("ping")
            return True
        except PyMongoError:
            return False

    async def _guard(self, coro: Any) -> Any:
        try:
            return await coro
        except (DuplicateKeyError, ContentConflict):
            raise
        except PyMongoError as exc:
            logger.warning("mongo_unavailable type=%s", type(exc).__name__)
            raise DependencyUnavailable("Katalog veritabanına erişilemiyor.") from None

    async def ensure_schema(self) -> None:
        existing = set(await self._guard(self._db.list_collection_names()))
        for name, validator in _VALIDATORS.items():
            if name in existing:
                await self._guard(
                    self._db.command({"collMod": name, "validator": validator, "validationLevel": "strict"})
                )
            else:
                with contextlib.suppress(CollectionInvalid):  # eşzamanlı oluşturma
                    await self._db.create_collection(name, validator=validator, validationLevel="strict")
        await self._guard(
            self._db[OPERATIONS].create_index(
                [("application_id", ASCENDING), ("operation_id", ASCENDING), ("revision", ASCENDING)],
                unique=True,
            )
        )
        await self._guard(
            self._db[SCREENS].create_index(
                [("application_id", ASCENDING), ("screen_id", ASCENDING), ("revision", ASCENDING)],
                unique=True,
            )
        )
        await self._guard(
            self._db[ACTIVATIONS].create_index(
                [("application_id", ASCENDING), ("environment", ASCENDING), ("at", DESCENDING)]
            )
        )
        await self._guard(self._db[RELEASES].create_index("release_id", unique=True))
        await self._guard(self._db[RELEASES].create_index("request_id", unique=True))
        await self._guard(
            self._db[RELEASES].create_index(
                [("application_id", ASCENDING), ("environment", ASCENDING), ("created_at", DESCENDING)]
            )
        )
        await self._guard(
            self._db[ACTIVE].create_index(
                [("application_id", ASCENDING), ("environment", ASCENDING)], unique=True
            )
        )

    async def put_revision(self, rev: OperationRevision) -> str:
        try:
            await self._guard(self._db[OPERATIONS].insert_one(rev.model_dump(mode="python")))
            return "inserted"
        except DuplicateKeyError:
            existing = await self.get_revision(rev.application_id, rev.operation_id, rev.revision)
            if existing is None or existing.content_hash != rev.content_hash:
                raise ContentConflict() from None
            return "exists"

    async def latest_revision(self, app: str, op: str) -> OperationRevision | None:
        doc = await self._guard(
            self._db[OPERATIONS].find_one(
                {"application_id": app, "operation_id": op}, sort=[("revision", DESCENDING)]
            )
        )
        return OperationRevision.model_validate(_strip(doc)) if doc else None

    async def get_revision(self, app: str, op: str, revision: int) -> OperationRevision | None:
        doc = await self._guard(
            self._db[OPERATIONS].find_one({"application_id": app, "operation_id": op, "revision": revision})
        )
        return OperationRevision.model_validate(_strip(doc)) if doc else None

    async def put_screen(self, rev: ScreenRevision) -> str:
        try:
            await self._guard(self._db[SCREENS].insert_one(rev.model_dump(mode="python")))
            return "inserted"
        except DuplicateKeyError:
            existing = await self.get_screen(rev.application_id, rev.screen_id, rev.revision)
            if existing is None or existing.content_hash != rev.content_hash:
                raise ContentConflict() from None
            return "exists"

    async def latest_screen(self, app: str, screen_id: str) -> ScreenRevision | None:
        doc = await self._guard(
            self._db[SCREENS].find_one(
                {"application_id": app, "screen_id": screen_id}, sort=[("revision", DESCENDING)]
            )
        )
        return ScreenRevision.model_validate(_strip(doc)) if doc else None

    async def get_screen(self, app: str, screen_id: str, revision: int) -> ScreenRevision | None:
        doc = await self._guard(
            self._db[SCREENS].find_one({"application_id": app, "screen_id": screen_id, "revision": revision})
        )
        return ScreenRevision.model_validate(_strip(doc)) if doc else None

    async def insert_release(self, manifest: ReleaseManifest) -> None:
        await self._guard(self._db[RELEASES].insert_one(manifest.model_dump(mode="python")))

    async def get_release(self, release_id: str) -> ReleaseManifest | None:
        doc = await self._guard(self._db[RELEASES].find_one({"release_id": release_id}))
        return ReleaseManifest.model_validate(_strip(doc)) if doc else None

    async def find_release_by_request(self, request_id: str) -> ReleaseManifest | None:
        doc = await self._guard(self._db[RELEASES].find_one({"request_id": request_id}))
        return ReleaseManifest.model_validate(_strip(doc)) if doc else None

    async def list_releases(self, app: str, env: str) -> list[ReleaseManifest]:
        cursor = (
            self._db[RELEASES]
            .find({"application_id": app, "environment": env})
            .sort("created_at", DESCENDING)
        )
        docs = await self._guard(cursor.to_list(length=100))
        return [ReleaseManifest.model_validate(_strip(d)) for d in docs]

    async def get_active(self, app: str, env: str) -> ActivePointer | None:
        doc = await self._guard(self._db[ACTIVE].find_one({"application_id": app, "environment": env}))
        return ActivePointer.model_validate(_strip(doc)) if doc else None

    async def add_activation(self, record: ActivationRecord) -> None:
        await self._guard(self._db[ACTIVATIONS].insert_one(record.model_dump(mode="python")))

    async def list_activations(self, app: str, env: str) -> list[ActivationRecord]:
        cursor = (
            self._db[ACTIVATIONS].find({"application_id": app, "environment": env}).sort("at", DESCENDING)
        )
        docs = await self._guard(cursor.to_list(length=50))
        return [ActivationRecord.model_validate(_strip(d)) for d in docs]

    async def compare_and_set_active(
        self, app: str, env: str, expected: str | None, new: str, by: str
    ) -> bool:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        if expected is None:
            try:
                await self._guard(
                    self._db[ACTIVE].insert_one(
                        {
                            "application_id": app,
                            "environment": env,
                            "release_id": new,
                            "version": 1,
                            "updated_by": by,
                            "updated_at": now,
                        }
                    )
                )
                return True
            except DuplicateKeyError:
                return False
        result = await self._guard(
            self._db[ACTIVE].update_one(
                {"application_id": app, "environment": env, "release_id": expected},
                {"$set": {"release_id": new, "updated_by": by, "updated_at": now}, "$inc": {"version": 1}},
            )
        )
        return bool(result.modified_count == 1)
