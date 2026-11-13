"""Yerel Mongo geliştirme aracı (Docker gerektirmeyen birim testleri; Docker çağrıları sahte
çalıştırıcıyla)."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tools.local_mongo.settings import LocalMongoSettings, ToolConfigurationError, load_tool_settings

from agentask.config import load_settings
from tests.conftest import EnvFileFactory, parse_env_example


class RecordingRunner:
    """Komutları kaydeder; 'ps' için konteyner durumunu taklit eder. shell kullanılmaz (list argüman)."""

    def __init__(self, running: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.running = running

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert isinstance(args, list) and kwargs.get("shell") in (None, False)
        self.calls.append(args)
        out = ""
        if "ps" in args:
            out = '{"Service":"mongo","State":"running"}' if self.running else ""
        return subprocess.CompletedProcess(args, 0, out, "")


def tool(make_env_file: EnvFileFactory, **kw: str | None) -> tuple[Any, LocalMongoSettings, Path]:
    env = make_env_file(**kw)
    return load_settings(env), load_tool_settings(env), env


def test_env_example_documents_exactly_the_tool_fields() -> None:
    tool_keys = sorted(
        k for k in parse_env_example() if k.startswith("LOCAL_MONGO_") and k != "LOCAL_MONGO_AUTOSTART"
    )
    assert tool_keys == sorted(f"LOCAL_MONGO_{f.upper()}" for f in LocalMongoSettings.model_fields)


def test_tool_settings_reject_their_own_typos(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ToolConfigurationError, match="LOCAL_MONGO_PROT"):
        load_tool_settings(make_env_file(LOCAL_MONGO_PROT="1"))
    with pytest.raises(ToolConfigurationError, match="LOCAL_MONGO_PORT"):
        load_tool_settings(make_env_file(LOCAL_MONGO_PORT="abc"))


def test_tool_settings_not_required_when_autostart_false(make_env_file: EnvFileFactory) -> None:
    from tools.local_mongo.launcher import prepare

    env = make_env_file(LOCAL_MONGO_IMAGE=None, LOCAL_MONGO_PORT=None, LOCAL_MONGO_PROJECT=None)
    runner = RecordingRunner()
    assert prepare(env, runner=runner) is None  # autostart=false: araç ayarı okunmaz, Docker çağrılmaz
    assert runner.calls == []


@pytest.mark.parametrize(
    ("uri", "fragment"),
    [
        ("mongodb://db.kurum.internal:27017", "yerel"),
        ("mongodb://127.0.0.1:27018", "port"),
        ("mongodb+srv://cluster.example.net", "yerel"),
        ("mongodb://u:p@127.0.0.1:{port}", "kimlik"),
        ("mongodb://127.0.0.1:{port},127.0.0.1:27030", "tek"),
    ],
)
def test_managed_uri_must_match_local_service(make_env_file: EnvFileFactory, uri: str, fragment: str) -> None:
    from tools.local_mongo.manager import ManagedMongoError, ensure_running

    settings, tsettings, _ = tool(make_env_file, LOCAL_MONGO_AUTOSTART="true", LOCAL_MONGO_PORT="27991")
    settings = settings.model_copy(update={"mongo_uri": type(settings.mongo_uri)(uri.format(port=27991))})
    runner = RecordingRunner()
    with pytest.raises(ManagedMongoError, match=fragment):
        ensure_running(settings, tsettings, runner=runner)
    assert runner.calls == []  # uzak/uyumsuz bağlantıda Docker'a dokunulmaz


def test_port_conflict_does_not_touch_other_service(make_env_file: EnvFileFactory) -> None:
    from tools.local_mongo.manager import ManagedMongoError, ensure_running

    with socket.socket() as other:  # başka bir servis bu portu kullanıyor
        other.bind(("127.0.0.1", 0))
        other.listen()
        port = other.getsockname()[1]
        settings, tsettings, _ = tool(
            make_env_file,
            LOCAL_MONGO_AUTOSTART="true",
            LOCAL_MONGO_PORT=str(port),
            MONGO_URI=f"mongodb://127.0.0.1:{port}",
        )
        runner = RecordingRunner(running=False)
        with pytest.raises(ManagedMongoError, match="port"):
            ensure_running(settings, tsettings, runner=runner)
    assert all(not ({"up", "stop", "down", "rm", "kill"} & set(c)) for c in runner.calls)


def test_commands_never_remove_data(make_env_file: EnvFileFactory) -> None:
    from tools.local_mongo.compose import ComposeProject

    _, tsettings, _ = tool(make_env_file, LOCAL_MONGO_AUTOSTART="true")
    runner = RecordingRunner()
    project = ComposeProject(tsettings, runner=runner)
    project.up()
    project.stop()
    flat = [" ".join(c) for c in runner.calls]
    assert any(" up -d" in c for c in flat) and any(c.endswith(" stop") for c in flat)
    assert not any(x in c for c in flat for x in (" down", " -v", "--volumes", " rm"))
    assert all(c[:2] == ["docker", "compose"] and "-p" in c and "-f" in c for c in runner.calls)


def test_compose_file_is_loopback_named_volume_and_fixed_project() -> None:
    text = (Path(__file__).resolve().parents[2] / "compose.local-mongo.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:${LOCAL_MONGO_PORT' in text
    assert "/data/db" in text and "name: ${LOCAL_MONGO_VOLUME" in text
    assert "0.0.0.0" not in text  # noqa: S104


def test_restore_refuses_main_database(make_env_file: EnvFileFactory) -> None:
    from tools.local_mongo.compose import ComposeProject
    from tools.local_mongo.manager import ManagedMongoError, restore

    settings, tsettings, _ = tool(make_env_file, LOCAL_MONGO_AUTOSTART="true")
    with pytest.raises(ManagedMongoError, match="ayrı"):
        restore(
            settings,
            ComposeProject(tsettings, runner=RecordingRunner()),
            Path("x.archive.gz"),
            settings.mongo_database,
        )


def test_app_does_not_import_tools() -> None:
    import ast

    src = Path(__file__).resolve().parents[2] / "src"
    for path in src.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            )
            assert not any(n.startswith("tools") for n in names), path


def test_launcher_false_path_never_loads_docker_module(make_env_file: EnvFileFactory) -> None:
    for name in [
        m
        for m in sys.modules
        if m.startswith("tools.local_mongo.compose") or m.startswith("tools.local_mongo.manager")
    ]:
        del sys.modules[name]
    from tools.local_mongo.launcher import prepare

    assert prepare(make_env_file(), runner=RecordingRunner()) is None
    assert "tools.local_mongo.compose" not in sys.modules and "tools.local_mongo.manager" not in sys.modules
