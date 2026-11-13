"""Yerel geliştirme adaptörleri: ARTIFACT_DIRECTORY altında nesne deposu ve JSON metadata dizini.

Üretimde nesne deposu kurum içi S3 uyumlu adaptörle, metadata MongoDB ile değiştirilir (ADR 0016). Anahtarlar
yalnız kod üretimli kimliklerdir; yol geçişi (../) reddedilir."""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from pathlib import Path

from agentask.domain.artifacts import ARTIFACT_ID_PATTERN, ArtifactRef

_KEY = re.compile(ARTIFACT_ID_PATTERN)


def _checked(key: str) -> str:
    if not _KEY.fullmatch(key):
        raise ValueError("geçersiz nesne anahtarı")
    return key


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self._root = root / "objects"
        self._root.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        target = self._root / _checked(key)
        fd, tmp = tempfile.mkstemp(dir=self._root, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)  # tamamı yazılmadan nesne görünmez
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise

    async def get(self, key: str) -> bytes | None:
        path = self._root / _checked(key)
        return path.read_bytes() if path.is_file() else None

    async def delete(self, key: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            (self._root / _checked(key)).unlink()

    async def list_keys(self) -> list[str]:
        return sorted(p.name for p in self._root.iterdir() if p.is_file() and _KEY.fullmatch(p.name))


class LocalArtifactIndex:
    def __init__(self, root: Path) -> None:
        self._root = root / "index"
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, artifact_id: str) -> Path:
        return self._root / f"{_checked(artifact_id)}.json"

    async def save(self, ref: ArtifactRef) -> None:
        fd, tmp = tempfile.mkstemp(dir=self._root, prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(ref.model_dump_json())
        os.replace(tmp, self._path(ref.artifact_id))

    async def get(self, artifact_id: str) -> ArtifactRef | None:
        try:
            path = self._path(artifact_id)
        except ValueError:
            return None
        return ArtifactRef.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None

    async def delete(self, artifact_id: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path(artifact_id).unlink()

    async def all(self) -> list[ArtifactRef]:
        return [
            ArtifactRef.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self._root.glob("art_*.json"))
        ]
