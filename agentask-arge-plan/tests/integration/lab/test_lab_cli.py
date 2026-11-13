from __future__ import annotations

import pytest

from agentask_lab.__main__ import main
from tests.conftest import EnvFileFactory


def test_lab_cli_requires_lab_origins(
    make_env_file: EnvFileFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    env = make_env_file(LAB_PRIMARY_ORIGIN=None, LAB_SECONDARY_ORIGIN=None)
    assert main(["--env-file", str(env), "--check-config"]) == 2
    assert "LAB_PRIMARY_ORIGIN" in capsys.readouterr().err


def test_lab_cli_check_config_ok(make_env_file: EnvFileFactory, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--env-file", str(make_env_file()), "--check-config"]) == 0
    assert "http://127.0.0.1:8100" in capsys.readouterr().out
