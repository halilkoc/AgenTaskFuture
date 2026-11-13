from __future__ import annotations

import pytest

from agentask.__main__ import main
from tests.conftest import EnvFileFactory


def test_check_config_succeeds_with_valid_env_file(make_env_file: EnvFileFactory) -> None:
    assert main(["--env-file", str(make_env_file()), "--check-config"]) == 0


def test_invalid_config_exits_with_redacted_error(
    make_env_file: EnvFileFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--env-file", str(make_env_file(SESSION_SIGNING_KEY="leaky-short")), "--check-config"])
    err = capsys.readouterr().err
    assert code == 2
    assert "SESSION_SIGNING_KEY" in err
    assert "leaky-short" not in err
