"""Onay öncesi taslak deposu. Yayımlanmış katalogdan ayrıdır; taslaklar yayın koleksiyonlarına yazılmaz."""

from __future__ import annotations

from typing import Protocol

from agentask.domain.catalog import OperationDraft


class DraftRepository(Protocol):
    def create(self, draft: OperationDraft) -> None: ...

    def get(self, draft_id: str) -> OperationDraft | None: ...

    def update(self, draft: OperationDraft, expected_revision: int) -> None:
        """Saklanan revizyon expected_revision değilse DraftConflict."""
        ...

    def list_for(self, owner_id: str) -> list[OperationDraft]: ...

    def list_all(self) -> list[OperationDraft]: ...
