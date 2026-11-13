"""Madde 28: paket içeriği ve geçici sanal ortamda kurulum. Ağda yalnız pip; hedef adresler yereldir."""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from tests.support_mongo import ephemeral_mongod

from tools.local_acceptance.process import run_limited
from tools.local_acceptance.safety import redact

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_NAMES = {".env", "mongod.lock"}
FORBIDDEN_PARTS = {"var", ".venv", "__pycache__", "drafts", "runs", "verification"}
PASSED, FAILED, UNVERIFIED = "GEÇTİ", "KALDI", "OTOMATİK DOĞRULANAMADI"


@dataclass
class PackageResult:
    status: str
    name: str = ""
    sha256: str = ""
    checks: dict[str, str] = field(default_factory=dict)


def candidate_zip(root: Path = ROOT) -> Path | None:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    found = sorted((root / "dist").glob(f"agentask-company-test-{version}-*.zip"))
    return found[-1] if found else None


def forbidden_entries(names: list[str]) -> list[str]:
    return [n for n in names if Path(n).name in FORBIDDEN_NAMES or set(Path(n).parts) & FORBIDDEN_PARTS]


def _step(command: list[str], cwd: Path, log_dir: Path, name: str) -> int | str:
    log = log_dir / f"paket-{name}.log"
    code = run_limited(command, cwd, None, log, 900)
    log.write_text(redact(log.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    return code


def _local_env(source: Path, target: Path, uri: str) -> None:
    """Paketin örnek ayarları: adresler yerel, sırlar bu koşu için üretilir ve iş bitince silinir."""
    from agentask.domain.passwords import hash_password

    local = "http://127.0.0.1:9"
    apps = json.dumps([{"id": "pega_test", "name": "Kabul", "base_url": f"{local}/"}])
    replace = {
        "SESSION_SIGNING_KEY": secrets.token_urlsafe(48),
        "ADMIN_PASSWORD_HASH": f"'{hash_password(secrets.token_urlsafe(24))}'",
        "MONGO_URI": uri,
        "MONGO_DATABASE": "agentask_package_check",
        "TARGET_BASE_URL": f"{local}/",
        "TARGET_ALLOWED_ORIGINS": f"'{json.dumps([local])}'",
        "AUTOMATION_APPLICATIONS_JSON": f"'{apps}'",
    }
    lines = []
    for line in source.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        lines.append(f"{key}={replace[key]}" if key in replace and "=" in line else line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_package(output: Path, work: Path) -> PackageResult:
    package = candidate_zip()
    if package is None:
        return PackageResult(UNVERIFIED, checks={"paket": "pyproject sürümünde paket yok"})
    result = PackageResult(PASSED, package.name, hashlib.sha256(package.read_bytes()).hexdigest())
    extract = work / "package"
    with zipfile.ZipFile(package) as archive:
        bad = forbidden_entries(archive.namelist())
        archive.extractall(extract)
    root = extract / package.stem
    mismatched = 0
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        mismatched += hashlib.sha256((root / name).read_bytes()).hexdigest() != expected
    wheel = next((root / "app").glob("agentask-*.whl"))
    different = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if ".dist-info/" in name or name.endswith("/"):
                continue
            source = ROOT / "src" / name
            different += not source.is_file() or source.read_bytes() != archive.read(name)
    result.checks.update(
        yasak_yol=str(len(bad)), ozet_uyusmayan=str(mismatched), wheel_kaynak_farki=str(different)
    )
    venv, run_dir = work / "venv", work / "run"
    run_dir.mkdir()
    codes: dict[str, int | str] = {
        "venv": _step([sys.executable, "-m", "venv", str(venv)], work, output, "venv")
    }
    pip = [str(venv / "bin/pip"), "install", "-q", "-c", str(ROOT / "requirements.lock"), str(wheel)]
    codes["kurulum"] = _step(pip, work, output, "kurulum")
    with ephemeral_mongod() as uri:
        if uri is None:
            result.status = UNVERIFIED
            result.checks["mongod"] = "bulunamadı"
            return result
        _local_env(root / ".env.company.example", run_dir / ".env", uri)
        codes["check_config"] = _step(
            [str(venv / "bin/agentask"), "--check-config"], run_dir, output, "config"
        )
        codes["doctor"] = _step([str(venv / "bin/agentask"), "--doctor"], run_dir, output, "doctor")
    (run_dir / ".env").unlink(missing_ok=True)
    result.checks.update({k: f"çıkış {v}" for k, v in codes.items()})
    doctor = (output / "paket-doctor.log").read_text(encoding="utf-8")
    if bad or mismatched or different or any(v != 0 for v in codes.values()) or "[HATA]" in doctor:
        result.status = FAILED
    return result
