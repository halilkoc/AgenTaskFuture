"""Dosya/kanıt depolama (ADR 0016): yerel adaptör, telafi, bütünlük, sahiplik, saklama ve öksüz temizliği.
S3 gerçek bağlantısı yoktur (BLOCKED); port sözleşmesi yerel adaptörle doğrulanır."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agentask.application.errors import DependencyUnavailable
from agentask.application.services.artifacts import (
    ArtifactMissing,
    ArtifactNotFound,
    ArtifactRejected,
    ArtifactService,
)
from agentask.domain.artifacts import ArtifactRef
from agentask.infrastructure.artifacts.local_file import LocalArtifactIndex, LocalObjectStore

NOW = datetime(2026, 11, 7, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def make(
    tmp_path: Path, clock: Clock | None = None
) -> tuple[ArtifactService, LocalObjectStore, LocalArtifactIndex]:
    store, index = LocalObjectStore(tmp_path), LocalArtifactIndex(tmp_path)
    return (
        ArtifactService(store, index, max_bytes=1000, retention_days=7, clock=clock or Clock()),
        store,
        index,
    )


async def test_store_and_fetch_with_integrity_and_owner_check(tmp_path: Path) -> None:
    service, _, _ = make(tmp_path)
    ref = await service.store("ayse", "evidence", "text/plain", b"sonuc: basarili", run_id="run-1")
    assert ref.size_bytes == 15 and len(ref.sha256) == 64 and ref.retain_until == NOW + timedelta(days=7)
    got, data = await service.fetch("ayse", ref.artifact_id)
    assert data == b"sonuc: basarili" and got == ref
    with pytest.raises(ArtifactNotFound):  # başka kullanıcıya varlığı sızdırılmaz
        await service.fetch("mehmet", ref.artifact_id)
    # Metadata içinde içerik yok; yalnız referans.
    assert "basarili" not in ref.model_dump_json()


@pytest.mark.parametrize(
    ("content_type", "data", "masked", "reason"),
    [
        ("application/x-sh", b"x", False, "content_type"),
        ("text/plain", b"", False, "size"),
        ("text/plain", b"x" * 1001, False, "size"),
        ("image/png", b"png", False, "masking_unverified"),
    ],
)
async def test_rejections(tmp_path: Path, content_type: str, data: bytes, masked: bool, reason: str) -> None:
    service, store, index = make(tmp_path)
    with pytest.raises(ArtifactRejected) as exc:
        await service.store("ayse", "evidence", content_type, data, masking_verified=masked)
    assert exc.value.details["reason"] == reason
    assert await store.list_keys() == [] and await index.all() == []


async def test_masked_screenshot_is_accepted(tmp_path: Path) -> None:
    service, _, _ = make(tmp_path)
    ref = await service.store("ayse", "evidence", "image/png", b"png", masking_verified=True)
    assert ref.content_type == "image/png"


async def test_index_failure_compensates_object(tmp_path: Path) -> None:
    service, store, index = make(tmp_path)

    async def broken(ref: ArtifactRef) -> None:
        raise OSError("disk dolu")

    index.save = broken  # type: ignore[method-assign]
    with pytest.raises(DependencyUnavailable):
        await service.store("ayse", "evidence", "text/plain", b"veri")
    assert await store.list_keys() == []  # yarım kayıt bırakılmadı


async def test_object_write_failure_creates_no_metadata(tmp_path: Path) -> None:
    service, store, index = make(tmp_path)

    async def broken(key: str, data: bytes, content_type: str) -> None:
        raise OSError("bağlantı yok")

    store.put = broken  # type: ignore[method-assign]
    with pytest.raises(DependencyUnavailable):
        await service.store("ayse", "evidence", "text/plain", b"veri")
    assert await index.all() == []


async def test_missing_or_corrupted_object_is_not_presented(tmp_path: Path) -> None:
    service, store, _ = make(tmp_path)
    ref = await service.store("ayse", "evidence", "text/plain", b"veri")
    (tmp_path / "objects" / ref.artifact_id).write_bytes(b"bozuk")
    with pytest.raises(ArtifactMissing):
        await service.fetch("ayse", ref.artifact_id)
    await store.delete(ref.artifact_id)
    with pytest.raises(ArtifactMissing):
        await service.fetch("ayse", ref.artifact_id)


async def test_retention_and_orphan_cleanup(tmp_path: Path) -> None:
    clock = Clock()
    service, store, index = make(tmp_path, clock)
    old = await service.store("ayse", "evidence", "text/plain", b"eski")
    clock.now = NOW + timedelta(days=3)
    keep = await service.store("ayse", "evidence", "text/plain", b"yeni")
    await store.put("art_" + "a" * 20, b"oksuz", "text/plain")  # metadata'sız (çöken süreçten kalma)
    clock.now = NOW + timedelta(days=8)
    assert await service.purge_expired() == 1
    assert await index.get(old.artifact_id) is None and await index.get(keep.artifact_id) is not None
    assert await service.cleanup_orphans() == 1
    assert await store.list_keys() == [keep.artifact_id]


async def test_keys_cannot_escape_storage_root(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    for bad in ("../x", "art_../../etc", "art_" + "A" * 20):
        with pytest.raises(ValueError):
            await store.put(bad, b"x", "text/plain")
    assert await LocalArtifactIndex(tmp_path).get("../../x") is None


PDF_BYTES = b"%PDF-1.4 x"


async def test_upload_type_must_match_content(tmp_path: Path) -> None:
    service, _, _ = make(tmp_path)
    with pytest.raises(ArtifactRejected):
        await service.store_upload("u", "application/pdf", b"not a pdf", "a.pdf")


@pytest.mark.parametrize("name", ["../a.pdf", "c:\\a.pdf", "a/b.pdf", "", "a\nb.pdf"])
async def test_upload_rejects_path_like_names(tmp_path: Path, name: str) -> None:
    service, _, _ = make(tmp_path)
    with pytest.raises(ArtifactRejected):
        await service.store_upload("u", "application/pdf", PDF_BYTES, name)


async def test_read_upload_checks_owner_kind_type_and_expiry(tmp_path: Path) -> None:
    clock = Clock()
    service, _, _ = make(tmp_path, clock)
    ref = await service.store_upload("u", "application/pdf", PDF_BYTES, "a.pdf")
    got, data = await service.read_upload("u", ref.artifact_id, ["application/pdf"])
    assert (got.file_name, data) == ("a.pdf", PDF_BYTES)
    with pytest.raises(ArtifactNotFound):
        await service.read_upload("other", ref.artifact_id, None)
    with pytest.raises(ArtifactRejected):
        await service.read_upload("u", ref.artifact_id, ["text/plain"])
    evidence = await service.store("u", "attachment", "text/plain", b"x")
    with pytest.raises(ArtifactNotFound):  # adsız kayıt (kullanıcı yüklemesi değil) gönderilemez
        await service.read_upload("u", evidence.artifact_id, None)
    clock.now += timedelta(days=8)
    with pytest.raises(ArtifactNotFound):
        await service.read_upload("u", ref.artifact_id, None)
