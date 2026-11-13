from __future__ import annotations

from pathlib import Path

import pytest

from agentask.application.errors import DraftConflict
from agentask.domain.catalog import OperationDraft
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository


def new() -> OperationDraft:
    return OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id="op_a", title="A", description=""
    )


def test_create_and_reload(tmp_path: Path) -> None:
    repo = LocalFileDraftRepository(tmp_path)
    d = new()
    repo.create(d)
    assert d.revision == 1
    again = LocalFileDraftRepository(tmp_path).get(d.draft_id)
    assert again == d
    assert [x.draft_id for x in repo.list_for("ayse")] == [d.draft_id]
    assert repo.list_for("mehmet") == []


def test_revision_conflict(tmp_path: Path) -> None:
    repo = LocalFileDraftRepository(tmp_path)
    d = new()
    repo.create(d)
    first = repo.get(d.draft_id)
    second = repo.get(d.draft_id)
    assert first is not None and second is not None
    first.title = "Birinci"
    repo.update(first, expected_revision=1)
    second.title = "İkinci"
    with pytest.raises(DraftConflict):
        repo.update(second, expected_revision=1)
    stored = repo.get(d.draft_id)
    assert stored is not None and stored.title == "Birinci" and stored.revision == 2


def test_invalid_id_and_traversal(tmp_path: Path) -> None:
    assert LocalFileDraftRepository(tmp_path).get("../../x") is None
