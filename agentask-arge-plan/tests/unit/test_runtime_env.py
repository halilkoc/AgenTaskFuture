from __future__ import annotations

import os

import pytest

from agentask.config import load_settings
from agentask.config.runtime_env import apply_playwright_environment
from tests.conftest import EnvFileFactory


def test_playwright_browsers_path_exported_only_when_set(
    make_env_file: EnvFileFactory, monkeypatch: pytest.MonkeyPatch, tmp_path: os.PathLike[str]
) -> None:
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    apply_playwright_environment(load_settings(make_env_file()))
    assert "PLAYWRIGHT_BROWSERS_PATH" not in os.environ  # noqa: TID251
    apply_playwright_environment(load_settings(make_env_file(PLAYWRIGHT_BROWSERS_PATH="/opt/pw")))
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "/opt/pw"  # noqa: TID251
