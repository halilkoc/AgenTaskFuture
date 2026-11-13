"""YALNIZ TEST: bellek içi CatalogStore. Gerçek MongoDB yerine geçmiş gibi sunulmaz; hata enjeksiyonu için."""

from __future__ import annotations

import asyncio
import copy

from agentask.application.errors import ContentConflict
from agentask.domain.release import (
    ActivationRecord,
    ActivePointer,
    OperationRevision,
    ReleaseManifest,
    ScreenRevision,
)


class FakeCatalogStore:
    def __init__(self) -> None:
        self.activations: list[ActivationRecord] = []
        self.revisions: dict[tuple[str, str, int], OperationRevision] = {}
        self.screens: dict[tuple[str, str, int], ScreenRevision] = {}
        self.releases: dict[str, ReleaseManifest] = {}
        self.active: dict[tuple[str, str], ActivePointer] = {}
        self.fail_after: str | None = None  # "put_revision" | "insert_release"
        self.cas_delay = 0.0
        self._lock = asyncio.Lock()

    async def ensure_schema(self) -> None:
        return None

    async def ping(self) -> bool:
        return True

    async def put_revision(self, rev: OperationRevision) -> str:
        key = (rev.application_id, rev.operation_id, rev.revision)
        existing = self.revisions.get(key)
        if existing is not None:
            if existing.content_hash != rev.content_hash:
                raise ContentConflict()
            result = "exists"
        else:
            self.revisions[key] = copy.deepcopy(rev)
            result = "inserted"
        if self.fail_after == "put_revision":
            raise RuntimeError("enjekte hata: revizyondan sonra")
        return result

    async def latest_revision(self, app: str, op: str) -> OperationRevision | None:
        found = [r for (a, o, _), r in self.revisions.items() if a == app and o == op]
        return max(found, key=lambda r: r.revision) if found else None

    async def get_revision(self, app: str, op: str, revision: int) -> OperationRevision | None:
        return self.revisions.get((app, op, revision))

    async def put_screen(self, rev: ScreenRevision) -> str:
        key = (rev.application_id, rev.screen_id, rev.revision)
        existing = self.screens.get(key)
        if existing is not None:
            if existing.content_hash != rev.content_hash:
                raise ContentConflict()
            return "exists"
        self.screens[key] = copy.deepcopy(rev)
        if self.fail_after == "put_screen":
            raise RuntimeError("enjekte hata: ekran revizyonundan sonra")
        return "inserted"

    async def latest_screen(self, app: str, screen_id: str) -> ScreenRevision | None:
        found = [r for (a, s, _), r in self.screens.items() if a == app and s == screen_id]
        return max(found, key=lambda r: r.revision) if found else None

    async def get_screen(self, app: str, screen_id: str, revision: int) -> ScreenRevision | None:
        return self.screens.get((app, screen_id, revision))

    async def insert_release(self, manifest: ReleaseManifest) -> None:
        self.releases[manifest.release_id] = copy.deepcopy(manifest)
        if self.fail_after == "insert_release":
            raise RuntimeError("enjekte hata: manifestten sonra")

    async def get_release(self, release_id: str) -> ReleaseManifest | None:
        r = self.releases.get(release_id)
        return copy.deepcopy(r) if r else None

    async def find_release_by_request(self, request_id: str) -> ReleaseManifest | None:
        return next((copy.deepcopy(r) for r in self.releases.values() if r.request_id == request_id), None)

    async def list_releases(self, app: str, env: str) -> list[ReleaseManifest]:
        return sorted(
            (r for r in self.releases.values() if r.application_id == app and r.environment == env),
            key=lambda r: r.created_at,
            reverse=True,
        )

    async def get_active(self, app: str, env: str) -> ActivePointer | None:
        return self.active.get((app, env))

    async def add_activation(self, record: ActivationRecord) -> None:
        self.activations.append(record)

    async def list_activations(self, app: str, env: str) -> list[ActivationRecord]:
        return [a for a in reversed(self.activations) if (a.application_id, a.environment) == (app, env)]

    async def compare_and_set_active(
        self, app: str, env: str, expected: str | None, new: str, by: str
    ) -> bool:
        await asyncio.sleep(self.cas_delay)
        async with self._lock:
            current = self.active.get((app, env))
            if (current.release_id if current else None) != expected:
                return False
            self.active[(app, env)] = ActivePointer(
                application_id=app,
                environment=env,
                release_id=new,
                version=(current.version + 1) if current else 1,
                updated_by=by,
            )
            return True
