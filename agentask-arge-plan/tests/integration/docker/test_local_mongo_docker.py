"""Gerçek Docker ile yerel Mongo (yalnız teste özel proje/volume/port). Daemon yoksa BLOCKED olarak atlanır.

Geliştiricinin gerçek katalog volume'u (LOCAL_MONGO_VOLUME varsayılanı) asla kullanılmaz; test sonunda yalnız
teste özel kaynaklar silinir.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from agentask.application.services.publishing import PublishService
from agentask.config import load_settings
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.mongo.catalog_store import MongoCatalogStore
from tests.conftest import EnvFileFactory, parse_env_example
from tests.unit.test_publishing import ready_draft

pytestmark = pytest.mark.docker
COMPOSE = Path(__file__).resolve().parents[3] / "compose.local-mongo.yml"


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0  # noqa: S607
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
def test_env(make_env_file: EnvFileFactory) -> Iterator[Path]:
    if not _docker_available():
        pytest.skip("BLOCKED: Docker daemon erişilemiyor; gerçek Compose kalıcılık testi çalıştırılamadı")
    tag = secrets.token_hex(4)
    port = _free_port()
    project, volume = f"agentask-test-{tag}", f"agentask-test-{tag}-data"
    assert volume != parse_env_example()["LOCAL_MONGO_VOLUME"]
    env = make_env_file(
        LOCAL_MONGO_AUTOSTART="true",
        LOCAL_MONGO_PROJECT=project,
        LOCAL_MONGO_VOLUME=volume,
        LOCAL_MONGO_PORT=str(port),
        MONGO_URI=f"mongodb://127.0.0.1:{port}",
        MONGO_DATABASE=f"agentask_test_{tag}",
        CATALOG_BACKEND="mongo",
    )
    try:
        yield env
    finally:  # yalnız teste özel proje ve volume temizlenir
        subprocess.run(
            ["docker", "compose", "-p", project, "-f", str(COMPOSE), "down", "-v"],  # noqa: S607
            capture_output=True,
            timeout=120,
            env={
                **os.environ,
                "LOCAL_MONGO_IMAGE": "mongo:8.0",
                "LOCAL_MONGO_PORT": str(port),
                "LOCAL_MONGO_VOLUME": volume,
            },
        )
        subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True, timeout=60)  # noqa: S607


async def test_release_survives_mongo_restart_and_container_recreate(test_env: Path, tmp_path: Path) -> None:
    from tools.local_mongo.manager import ensure_running
    from tools.local_mongo.settings import load_tool_settings

    settings, tool = load_settings(test_env), load_tool_settings(test_env)
    project = ensure_running(settings, tool)
    store = MongoCatalogStore(settings.mongo_uri.get_secret_value(), settings.mongo_database, 5000)
    await store.ensure_schema()
    drafts = LocalFileDraftRepository(tmp_path / "drafts")
    pub = PublishService(store, drafts, LAB_ACTION_SET, settings.catalog_environment)
    d = ready_draft(drafts)
    d = pub.approve("pub", d.draft_id, d.revision)
    release = await pub.publish("pub", d.draft_id, "r1")
    await store.close()

    project.stop()  # veri korunur
    ensure_running(settings, tool)
    store = MongoCatalogStore(settings.mongo_uri.get_secret_value(), settings.mongo_database, 5000)
    await store.ensure_schema()  # yeniden şema kurulumu mevcut veriyi ezmez
    assert (
        await PublishService(store, drafts, LAB_ACTION_SET, settings.catalog_environment).active_release(
            "lab"
        )
        == release
    )
    await store.close()

    subprocess.run(
        ["docker", "compose", "-p", tool.project, "-f", str(COMPOSE), "rm", "-sf", "mongo"],  # noqa: S607
        capture_output=True,
        timeout=120,
        check=True,
        env=project._env(),
    )
    ensure_running(settings, tool)  # container yeniden oluşturulur, named volume aynı
    store = MongoCatalogStore(settings.mongo_uri.get_secret_value(), settings.mongo_database, 5000)
    active = await PublishService(store, drafts, LAB_ACTION_SET, settings.catalog_environment).active_release(
        "lab"
    )
    assert active is not None and active.manifest_hash == release.manifest_hash
    await store.close()


def _start_launcher(env_file: Path, port: int) -> subprocess.Popen[str]:
    import sys

    return subprocess.Popen(
        [sys.executable, "-m", "tools.local_mongo", "dev", "--env-file", str(env_file)],
        cwd=COMPOSE.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _wait_ready(port: int, proc: subprocess.Popen[str]) -> dict:  # type: ignore[type-arg]
    import time

    import httpx

    for _ in range(240):
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=2)
            if r.status_code == 200:
                return dict(r.json())
        except httpx.HTTPError:
            pass
        if proc.poll() is not None:
            raise AssertionError(proc.stdout.read() if proc.stdout else "launcher çıktı")
        time.sleep(0.5)
    raise AssertionError("uygulama hazır olmadı")


async def test_launcher_prepares_mongo_starts_app_and_release_survives_restarts(
    test_env: Path, tmp_path: Path, make_env_file: EnvFileFactory
) -> None:
    import httpx
    from tools.local_mongo.compose import ComposeProject
    from tools.local_mongo.settings import load_tool_settings

    values = {
        k: v for k, v in (line.split("=", 1) for line in test_env.read_text().splitlines() if "=" in line)
    }
    app_port = _free_port()
    env = make_env_file(
        name="launch.env",
        **{k: values[k] for k in values if k.startswith(("LOCAL_MONGO_", "MONGO_"))},
        CATALOG_BACKEND="mongo",
        APP_PORT=str(app_port),
        APP_BASE_URL=f"http://127.0.0.1:{app_port}",
        BROWSER_HEADLESS="true",
        DRAFT_DIRECTORY=str(tmp_path / "drafts"),
        RUN_DIRECTORY=str(tmp_path / "runs"),
    )
    settings, tool = load_settings(env), load_tool_settings(env)
    proc = _start_launcher(env, app_port)
    try:
        ready = _wait_ready(app_port, proc)
        assert {"name": "catalog_mongo", "required": True, "status": "available"} in ready["components"]
        store = MongoCatalogStore(settings.mongo_uri.get_secret_value(), settings.mongo_database, 5000)
        drafts = LocalFileDraftRepository(tmp_path / "drafts")
        pub = PublishService(store, drafts, LAB_ACTION_SET, settings.catalog_environment)
        d = ready_draft(drafts)
        d = pub.approve("pub", d.draft_id, d.revision)
        release = await pub.publish("pub", d.draft_id, "launch-r1")
        await store.close()
    finally:
        proc.terminate()
        proc.communicate(timeout=30)
    ComposeProject(tool).stop()  # Mongo da durdurulur; veri silinmez
    proc = _start_launcher(env, app_port)  # açılışta Mongo yeniden hazır edilir
    try:
        _wait_ready(app_port, proc)
        data = httpx.get(f"http://127.0.0.1:{app_port}/api/catalogs/releases", timeout=10).json()
        assert data["active_release_id"] == release.release_id
        assert data["releases"][0]["manifest_hash"] == release.manifest_hash
    finally:
        proc.terminate()
        proc.communicate(timeout=30)


def test_real_port_conflict_leaves_other_service_untouched(test_env: Path) -> None:
    import sys

    from tools.local_mongo.compose import ComposeProject
    from tools.local_mongo.settings import load_tool_settings

    tool = load_tool_settings(test_env)
    with socket.socket() as other:
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        other.bind(("127.0.0.1", tool.port))
        other.listen()
        out = subprocess.run(
            [sys.executable, "-m", "tools.local_mongo", "up", "--env-file", str(test_env)],
            cwd=COMPOSE.parent,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert out.returncode != 0 and "başka bir servis" in (out.stdout + out.stderr)
        assert other.fileno() != -1  # diğer servis açık kaldı
    assert not ComposeProject(tool).is_running()
