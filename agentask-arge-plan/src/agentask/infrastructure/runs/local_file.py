"""Yerel dosya checkpoint adapteri: run başına bir JSON; tmp + fsync + os.replace ile atomik yazma."""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path

from pydantic import ValidationError

from agentask.domain.runtime import Run

logger = logging.getLogger(__name__)
_RUN_ID = re.compile(r"^run-[A-Za-z0-9_-]{8,40}$")


class LocalFileRunRepository:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, run_id: str) -> Path | None:
        return self._dir / f"{run_id}.json" if _RUN_ID.fullmatch(run_id) else None

    def save(self, run: Run) -> None:
        path = self._path(run.run_id)
        if path is None:
            raise ValueError("geçersiz run_id")
        with self._lock:
            run.revision += 1
            tmp = path.with_suffix(".json.tmp")
            data = run.model_dump_json().encode("utf-8")
            with open(tmp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)

    def _load(self, path: Path) -> Run | None:
        try:
            return Run.model_validate_json(path.read_bytes())
        except (OSError, ValidationError, ValueError):
            logger.warning("run_checkpoint_unreadable file=%s", path.name)
            return None

    def get(self, run_id: str) -> Run | None:
        path = self._path(run_id)
        if path is None or not path.is_file():
            return None
        return self._load(path)

    def list_all(self) -> list[Run]:
        runs = [r for p in sorted(self._dir.glob("run-*.json")) if (r := self._load(p)) is not None]
        return sorted(runs, key=lambda r: r.created_at)

    def list_for(self, owner_id: str) -> list[Run]:
        return [r for r in self.list_all() if r.owner_id == owner_id]

    def find_by_request(self, owner_id: str, request_id: str) -> Run | None:
        return next((r for r in self.list_for(owner_id) if r.request_id == request_id), None)
