"""Run checkpoint deposu. Ar-Ge'de yerel dosya; ileride MongoDB adapteri aynı sözleşmeyi uygular."""

from __future__ import annotations

from typing import Protocol

from agentask.domain.runtime import Run


class RunRepository(Protocol):
    def save(self, run: Run) -> None:
        """Atomik yazar ve run.revision'ı artırır."""
        ...

    def get(self, run_id: str) -> Run | None: ...

    def list_for(self, owner_id: str) -> list[Run]: ...

    def list_all(self) -> list[Run]: ...

    def find_by_request(self, owner_id: str, request_id: str) -> Run | None: ...
