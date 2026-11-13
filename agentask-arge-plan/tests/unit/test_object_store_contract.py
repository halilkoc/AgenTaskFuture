"""G: nesne deposu sözleşmesi — yerel adaptör ve S3 uyumlu adaptör (sahte S3) aynı testlerden
geçer. S3 imzası AWS'nin yayımladığı SigV4 örnek vektörüyle ayrıca doğrulanır. Kurum S3 kabulü BLOCKED."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agentask.application.errors import DependencyUnavailable
from agentask.application.services.artifacts import ArtifactMissing, ArtifactService
from agentask.infrastructure.artifacts.local_file import LocalArtifactIndex, LocalObjectStore
from agentask.infrastructure.artifacts.s3 import EMPTY_SHA256, ObjectStoreError, S3ObjectStore, sign_v4
from tests.fake_s3 import FakeS3

ACCESS, SECRET, REGION = "AKIDTEST0000", "test-secret-not-real", "tr-ankara-1"
KEY_A, KEY_B, KEY_C = "art_" + "a" * 20, "art_" + "b" * 20, "art_" + "c" * 20


def test_sigv4_matches_aws_published_example() -> None:
    """AWS S3 SigV4 belgesindeki 'GET Object' örneği (examplebucket, 20130524, Range: bytes=0-9)."""
    auth = sign_v4(
        method="GET",
        host="examplebucket.s3.amazonaws.com",
        path="/test.txt",
        query={},
        headers={
            "range": "bytes=0-9",
            "x-amz-content-sha256": EMPTY_SHA256,
            "x-amz-date": "20130524T000000Z",
        },
        payload_sha256=EMPTY_SHA256,
        amz_date="20130524T000000Z",
        region="us-east-1",
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    )
    assert "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date" in auth
    assert auth.endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


def make_s3(fake: FakeS3, secret: str = SECRET, prefix: str = "agentask/") -> S3ObjectStore:
    return S3ObjectStore(
        endpoint="http://127.0.0.1:9000",
        bucket=fake.bucket,
        region=REGION,
        access_key=ACCESS,
        secret_key=secret,
        prefix=prefix,
        transport=fake.transport(),
        clock=lambda: datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
    )


@pytest.fixture(params=["local", "s3"])
async def store(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[Any]:
    if request.param == "local":
        yield LocalObjectStore(tmp_path)
        return
    fake = FakeS3("agentask-kanit", ACCESS, SECRET, REGION, page_size=2)
    s3 = make_s3(fake)
    s3.fake = fake  # type: ignore[attr-defined]
    yield s3
    await s3.close()


async def test_round_trip_overwrite_missing_and_delete(store: Any) -> None:
    assert await store.get(KEY_A) is None  # yok: None (var gibi davranılmaz)
    await store.put(KEY_A, b"ilk", "text/plain")
    await store.put(KEY_A, b"ikinci", "text/plain")
    assert await store.get(KEY_A) == b"ikinci"
    await store.delete(KEY_A)
    await store.delete(KEY_A)  # tekrar silmek hata değildir
    assert await store.get(KEY_A) is None


async def test_list_keys_paginates_and_ignores_foreign_objects(store: Any) -> None:
    for key in (KEY_C, KEY_A, KEY_B):
        await store.put(key, b"x", "text/plain")
    if isinstance(store, S3ObjectStore):
        store.fake.objects["baska-uygulama/art_" + "d" * 20] = (b"y", "text/plain")  # type: ignore[attr-defined]
        store.fake.objects["agentask/serbest.txt"] = (b"y", "text/plain")  # type: ignore[attr-defined]
    assert await store.list_keys() == [KEY_A, KEY_B, KEY_C]


async def test_invalid_keys_are_rejected_before_any_request(store: Any) -> None:
    for bad in ("../x", "art_../../etc", "art_" + "A" * 20, "agentask/art_" + "a" * 20):
        with pytest.raises(ValueError):
            await store.put(bad, b"x", "text/plain")
    if isinstance(store, S3ObjectStore):
        assert store.fake.requests == []  # type: ignore[attr-defined]


async def test_s3_rejects_wrong_credentials_and_server_errors(tmp_path: Path) -> None:
    fake = FakeS3("agentask-kanit", ACCESS, SECRET, REGION)
    wrong = make_s3(fake, secret="yanlis")
    with pytest.raises(ObjectStoreError) as exc:
        await wrong.put(KEY_A, b"x", "text/plain")
    assert "yanlis" not in str(exc.value) and SECRET not in str(exc.value)  # sır sızmaz
    assert fake.objects == {}
    good = make_s3(fake)
    fake.fail_next = 500
    with pytest.raises(ObjectStoreError):
        await good.get(KEY_A)
    await wrong.close()
    await good.close()


async def test_service_over_s3_compensates_and_detects_corruption(tmp_path: Path) -> None:
    fake = FakeS3("agentask-kanit", ACCESS, SECRET, REGION)
    s3 = make_s3(fake)
    service = ArtifactService(s3, LocalArtifactIndex(tmp_path), max_bytes=1000, retention_days=7)
    ref = await service.store("ayse", "evidence", "text/plain", b"sonuc")
    assert fake.objects["agentask/" + ref.artifact_id][0] == b"sonuc"
    fake.objects["agentask/" + ref.artifact_id] = (b"bozuk", "text/plain")
    with pytest.raises(ArtifactMissing):
        await service.fetch("ayse", ref.artifact_id)
    fake.fail_next = 503  # depo yazılamazsa metadata oluşmaz
    with pytest.raises(DependencyUnavailable):
        await service.store("ayse", "evidence", "text/plain", b"x")
    assert len(await LocalArtifactIndex(tmp_path).all()) == 1
    await s3.close()


def test_endpoint_with_credentials_is_refused() -> None:
    with pytest.raises(ValueError):
        S3ObjectStore(
            endpoint="https://kullanici:parola@s3.kurum.local",
            bucket="b-kanit",
            region=REGION,
            access_key=ACCESS,
            secret_key=SECRET,
        )
