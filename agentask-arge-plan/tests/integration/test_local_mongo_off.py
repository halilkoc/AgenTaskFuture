"""LOCAL_MONGO_AUTOSTART=false: Docker çağrılmaz/gerekmez; uygulama MONGO_URI ile çalışır; araç
kaldırılabilir."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.conftest import EnvFileFactory
from tests.support_mongo import ephemeral_mongod

REPO = Path(__file__).resolve().parents[2]
VENV_BIN = Path(sys.executable).parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def no_docker_env(tmp_path: Path) -> dict[str, str]:
    """PATH'te docker olmayan ortam: herhangi bir Docker çağrısı başarısız olurdu."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    mongod = shutil.which("mongod")
    if mongod and not (bin_dir / "mongod").exists():
        (bin_dir / "mongod").symlink_to(mongod)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LOCAL_MONGO_", "DOCKER"))}  # noqa: TID251
    env["PATH"] = os.pathsep.join([str(VENV_BIN), str(bin_dir), "/usr/bin", "/bin"])
    assert shutil.which("docker", path=env["PATH"]) is None
    return env


@pytest.mark.mongo
def test_launcher_off_mode_starts_app_without_docker(make_env_file: EnvFileFactory, tmp_path: Path) -> None:
    with ephemeral_mongod() as uri:
        if uri is None:
            pytest.skip("BLOCKED: mongod bulunamadı")
        port = _free_port()
        env_file = make_env_file(
            APP_PORT=str(port),
            APP_BASE_URL=f"http://127.0.0.1:{port}",
            MONGO_URI=uri,
            CATALOG_BACKEND="mongo",
            BROWSER_HEADLESS="true",
            LOCAL_MONGO_AUTOSTART="false",
            RUN_DIRECTORY=str(tmp_path / "runs"),
            DRAFT_DIRECTORY=str(tmp_path / "drafts"),
        )
        proc = subprocess.Popen(
            [sys.executable, "-m", "tools.local_mongo", "dev", "--env-file", str(env_file)],
            cwd=REPO,
            env=no_docker_env(tmp_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            ready = None
            for _ in range(60):
                try:
                    ready = httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=2)
                    break
                except httpx.HTTPError:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.3)
            assert ready is not None, proc.stdout.read() if proc.stdout else ""
            assert ready.status_code == 200
            assert {"name": "catalog_mongo", "required": True, "status": "available"} in ready.json()[
                "components"
            ]
        finally:
            proc.terminate()
            out = proc.communicate(timeout=20)[0]
        assert "docker" not in out.lower()


def test_off_mode_with_unreachable_mongo_fails_explicitly(
    make_env_file: EnvFileFactory, tmp_path: Path
) -> None:
    env_file = make_env_file(
        MONGO_URI="mongodb://127.0.0.1:1",
        MONGO_SERVER_SELECTION_TIMEOUT_MS="300",
        CATALOG_BACKEND="mongo",
        LOCAL_MONGO_AUTOSTART="false",
    )
    code = (
        "import asyncio; from pathlib import Path; from agentask.config import load_settings;"
        "from agentask.presentation.app import create_app; from fastapi.testclient import TestClient;"
        f"s = load_settings(Path(r'{env_file}'));"
        "c = TestClient(create_app(s), client=('127.0.0.1', 1)).__enter__();"
        "r = c.get('/health/ready'); print(r.status_code, r.json()['status'])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=no_docker_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.stdout.strip().endswith("503 not_ready"), out.stderr[-500:]


def test_app_imports_and_starts_without_tool_modules(make_env_file: EnvFileFactory, tmp_path: Path) -> None:
    """Araç dosyaları yokmuş gibi: repo kökü sys.path'te değil (cwd=tmp), 'tools' bulunamaz; uygulama
    yine çalışır."""
    env_file = make_env_file(
        CATALOG_BACKEND="disabled", LOCAL_MONGO_PORT="27999", LOCAL_MONGO_IMAGE="mongo:8.0"
    )
    code = (
        "import importlib.util, sys; from pathlib import Path;"
        "assert importlib.util.find_spec('tools') is None, 'tools import edilebilir';"
        "from agentask.config import load_settings; from agentask.presentation.app import create_app;"
        f"app = create_app(load_settings(Path(r'{env_file}')));"
        "assert not any(m.startswith('tools') for m in sys.modules); print('ok')"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        env=no_docker_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.stdout.strip() == "ok", out.stderr[-800:]
    check = subprocess.run(
        [str(VENV_BIN / "agentask"), "--env-file", str(env_file), "--check-config"],
        cwd=tmp_path,
        env=no_docker_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert check.returncode == 0 and "Yapılandırma geçerli" in check.stdout
