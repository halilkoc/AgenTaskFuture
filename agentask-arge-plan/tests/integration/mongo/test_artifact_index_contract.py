"""G: dosya metadata dizini sözleşmesi — yerel JSON dizini ve MongoDB adaptörü aynı testlerden geçer (geçici
mongod; yoksa BLOCKED olarak atlanır)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agentask.application.services.artifacts import ArtifactService
from agentask.domain.artifacts import ArtifactRef
from agentask.infrastructure.artifacts.local_file import LocalArtifactIndex, LocalObjectStore
from agentask.infrastructure.artifacts.mongo_index import MongoArtifactIndex
from tests.support_mongo import ephemeral_mongod

NOW = datetime(2026, 11, 7, tzinfo=UTC)


def ref(n: str, owner: str = "ayse") -> ArtifactRef:
    return ArtifactRef(
        artifact_id="art_" + n * 20,
        owner_id=owner,
        kind="evidence",
        content_type="text/plain",
        size_bytes=3,
        sha256="0" * 64,
        created_at=NOW,
        retain_until=NOW + timedelta(days=7),
        run_id="run-1",
    )


@pytest.fixture(scope="module")
def mongo_uri() -> Iterator[str | None]:
    with ephemeral_mongod() as uri:
        yield uri


@pytest.fixture(params=["local", "mongo"])
async def index(request: pytest.FixtureRequest, tmp_path: Path, mongo_uri: str | None) -> AsyncIterator[Any]:
    if request.param == "local":
        yield LocalArtifactIndex(tmp_path)
        return
    if mongo_uri is None:
        pytest.skip("BLOCKED: mongod bulunamadı")
    idx = MongoArtifactIndex(mongo_uri, f"agentask_art_{tmp_path.name[-12:]}", 3000)
    yield idx
    await idx.close()


async def test_save_get_delete_all(index: Any) -> None:
    a, b = ref("a"), ref("b", owner="mehmet")
    await index.save(a)
    await index.save(b)
    await index.save(a)  # aynı kayıt tekrar yazılabilir (tekil kimlik)
    assert await index.get(a.artifact_id) == a  # tarih/saat dilimi korunur
    assert [r.artifact_id for r in await index.all()] == [a.artifact_id, b.artifact_id]
    await index.delete(a.artifact_id)
    await index.delete(a.artifact_id)
    assert await index.get(a.artifact_id) is None
    assert await index.get("../../x") is None


async def test_service_retention_over_index(index: Any, tmp_path: Path) -> None:
    clock = {"now": NOW}
    service = ArtifactService(
        LocalObjectStore(tmp_path / "obj"), index, max_bytes=100, retention_days=1, clock=lambda: clock["now"]
    )
    old = await service.store("ayse", "evidence", "text/plain", b"eski")
    clock["now"] = NOW + timedelta(days=2)
    assert await service.purge_expired() == 1
    assert await index.get(old.artifact_id) is None
