"""Yerel dosya taslak adapteri (Ar-Ge). Revizyon kontrollü (optimistic concurrency), atomik yazma."""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from agentask.application.errors import DraftConflict
from agentask.domain.catalog import OperationDraft

logger = logging.getLogger(__name__)
_ID = re.compile(r"^draft-[A-Za-z0-9_-]{6,40}$")


class LocalFileDraftRepository:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, draft_id: str) -> Path | None:
        return self._dir / f"{draft_id}.json" if _ID.fullmatch(draft_id) else None

    def _write(self, draft: OperationDraft, path: Path) -> None:
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "wb") as handle:
            handle.write(draft.model_dump_json().encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)

    def _load(self, path: Path) -> OperationDraft | None:
        try:
            return OperationDraft.model_validate_json(path.read_bytes())
        except (OSError, ValidationError, ValueError):
            logger.warning("draft_unreadable file=%s", path.name)
            return None

    def create(self, draft: OperationDraft) -> None:
        path = self._path(draft.draft_id)
        if path is None or path.exists():
            raise ValueError("geçersiz veya mevcut taslak kimliği")
        with self._lock:
            draft.revision = 1
            self._write(draft, path)

    def get(self, draft_id: str) -> OperationDraft | None:
        path = self._path(draft_id)
        return self._load(path) if path is not None and path.is_file() else None

    def update(self, draft: OperationDraft, expected_revision: int) -> None:
        path = self._path(draft.draft_id)
        if path is None:
            raise ValueError("geçersiz taslak kimliği")
        with self._lock:
            current = self._load(path) if path.is_file() else None
            if current is None or current.revision != expected_revision:
                raise DraftConflict()
            draft.revision = expected_revision + 1
            draft.updated_at = datetime.now(UTC)
            self._write(draft, path)

    def list_all(self) -> list[OperationDraft]:
        drafts = [d for p in sorted(self._dir.glob("draft-*.json")) if (d := self._load(p)) is not None]
        return sorted(drafts, key=lambda d: d.updated_at, reverse=True)

    def list_for(self, owner_id: str) -> list[OperationDraft]:
        return [d for d in self.list_all() if d.created_by == owner_id]
