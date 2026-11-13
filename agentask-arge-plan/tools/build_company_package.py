"""Tek şirket test paketini üretir ve içeriğini denetler. `.env`, `var/`, oturum ve sırlar pakete girmez.

Kullanım: `.venv/bin/python -m tools.build_company_package [--version-tag YYYYMMDD]`
Windows wheel'leri burada indirilir (paket şirkette internet istemez); indirilemezse araç başarısız olur.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "packaging" / "company"
FORBIDDEN_NAMES = {".env", "mongod.lock"}
FORBIDDEN_PARTS = {"var", ".venv", "__pycache__", "drafts", "runs", "verification"}
COPIED = (
    "install.ps1",
    "start.ps1",
    "doctor.ps1",
    "hash-admin.ps1",
    "approved-actions.example.json",
    "INSTALL.md",
    "MANUAL_ACCEPTANCE.md",
    "KNOWN_LIMITS.md",
    "ROLLBACK.md",
)
COMPANY_VALUES = {
    "APP_ENV": "test",
    "AUTH_MODE": "local_admin",
    "DEV_AUTH_ENABLED": "false",
    "SESSION_SIGNING_KEY": "",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD_HASH": "",
    "MONGO_URI": "mongodb://127.0.0.1:27017",
    "MONGO_DATABASE": "agentask_company_test",
    "LOCAL_MONGO_AUTOSTART": "false",
    "CATALOG_BACKEND": "mongo",
    "CATALOG_ENVIRONMENT": "sirket_test",
    "CATALOG_APPLICATION_ID": "pega_test",
    "TARGET_ALLOWED_ORIGINS": '["https://pega-test.kurum.example"]',
    "TARGET_BASE_URL": "https://pega-test.kurum.example/",
    "AUTOMATION_APPLICATIONS_JSON": (
        '[{"id":"pega_test","name":"Pega test","base_url":"https://pega-test.kurum.example/"}]'
    ),
    "LAB_PRIMARY_ORIGIN": "",
    "LAB_SECONDARY_ORIGIN": "",
    "APPROVED_ACTION_SET": "none",
    "BROWSER_HEADLESS": "false",
    "LLM_ENABLED": "false",
    "LOG_FORMAT": "json",
}


def run(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)  # noqa: S603 - sabit komutlar


def company_env() -> str:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        match = re.match(r"^([A-Z0-9_]+)=", line)
        if match and match[1] in COMPANY_VALUES:
            out.append(f"{match[1]}={COMPANY_VALUES[match[1]]}")
            seen.add(match[1])
        else:
            out.append(line)
    missing = set(COMPANY_VALUES) - seen
    if missing:
        raise SystemExit(f".env.example içinde yok: {sorted(missing)}")
    return "\n".join(out) + "\n"


def build_wheel(destination: Path) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "src-tree"
        tree.mkdir()
        shutil.copy(ROOT / "pyproject.toml", tree)
        shutil.copy(ROOT / "README.md", tree)
        ignore = shutil.ignore_patterns("__pycache__", "*.egg-info", "*.pyc")
        shutil.copytree(ROOT / "src", tree / "src", ignore=ignore)
        run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(destination), str(tree)])
    return next(destination.glob("agentask-*.whl"))


def _windows_only_requirements(destination: Path) -> set[str]:
    found: set[str] = set()
    for wheel in destination.glob("*.whl"):
        with zipfile.ZipFile(wheel) as archive:
            metadata = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
            for line in archive.read(metadata).decode("utf-8").splitlines():
                if not line.startswith("Requires-Dist:") or "extra ==" in line:
                    continue
                if re.search(r"(platform_system|sys_platform|os_name)\s*==\s*['\"](Windows|win32|nt)", line):
                    found.add(re.split(r"[ ;(<>=!~\[]", line.removeprefix("Requires-Dist:").strip())[0])
    return found


def windows_wheels(destination: Path) -> str:
    """Windows/Python 3.12 için çözümlenen tam küme; sürümler requirements.lock ile sınırlıdır."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    with tempfile.TemporaryDirectory() as tmp:
        direct = Path(tmp) / "direct.txt"
        direct.write_text("\n".join(project["dependencies"]) + "\n", encoding="utf-8")
        run(
            [
                sys.executable, "-m", "pip", "download", "-q", "-d", str(destination),
                "--platform", "win_amd64", "--python-version", "3.12", "--implementation", "cp",
                "--abi", "cp312", "--abi", "abi3", "--abi", "none", "--only-binary=:all:",
                "-c", str(ROOT / "requirements.lock"), "-r", str(direct),
            ]
        )  # fmt: skip
    # pip, platform işaretlerini bu makineye göre değerlendirir: Windows'a özgü bağımlılıklar ayrıca alınır.
    extras = {"tzdata", *_windows_only_requirements(destination)}  # zoneinfo Windows'ta tzdata ister
    run(
        [
            sys.executable, "-m", "pip", "download", "-q", "-d", str(destination),
            "--platform", "win_amd64", "--python-version", "3.12", "--implementation", "cp",
            "--abi", "cp312", "--abi", "abi3", "--abi", "none", "--only-binary=:all:",
            "-c", str(ROOT / "requirements.lock"), *sorted(extras),
        ]
    )  # fmt: skip
    lines = []
    for wheel in sorted(destination.glob("*.whl")):
        name, version = wheel.name.split("-")[:2]
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        lines.append(f"{name.replace('_', '-').lower()}=={version} --hash=sha256:{digest}")
    return "\n".join(lines) + "\n"


def audit(package: Path) -> None:
    problems: list[str] = []
    real_env = ROOT / ".env"
    secret_values: set[str] = set()
    if real_env.is_file():  # gerçek değerler yalnız karşılaştırma için bellekte kalır; yazdırılmaz
        for line in real_env.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            sensitive = re.search("KEY|PASSWORD|SECRET|TOKEN", key) or (key.endswith("URI") and "@" in value)
            if sep and sensitive and len(value.strip()) >= 12:
                secret_values.add(value.strip())
    for path in package.rglob("*"):
        relative = path.relative_to(package)
        if path.name in FORBIDDEN_NAMES or FORBIDDEN_PARTS & set(relative.parts):
            problems.append(f"yasak yol: {relative}")
        if path.is_file() and path.suffix in {".md", ".ps1", ".json", ".lock", ".example", ".txt"}:
            text = path.read_text(encoding="utf-8")
            if any(value in text for value in secret_values):
                problems.append(f"gerçek ayar değeri içeriyor: {relative}")
    wheel = next((package / "app").glob("agentask-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    if not any(n.endswith("presentation/static/auth.js") for n in names):
        problems.append("wheel: static dosyalar eksik")
    if any(n.endswith(".env") or "/var/" in n for n in names):
        problems.append("wheel: yasak dosya")
    if problems:
        raise SystemExit("Paket denetimi başarısız:\n" + "\n".join(problems))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-tag", required=True)
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    name = f"agentask-company-test-{version}-{args.version_tag}"
    dist = ROOT / "dist"
    package = dist / name
    if package.exists():
        shutil.rmtree(package)
    (package / "wheels").mkdir(parents=True)
    (package / "app").mkdir()
    build_wheel(package / "app")
    (package / "requirements-windows.lock").write_text(windows_wheels(package / "wheels"), encoding="utf-8")
    (package / ".env.company.example").write_text(company_env(), encoding="utf-8")
    for item in COPIED:
        shutil.copy(TEMPLATES / item, package / item)
    audit(package)
    sums = []
    for path in sorted(p for p in package.rglob("*") if p.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sums.append(f"{digest}  {path.relative_to(package).as_posix()}")
    (package / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    archive = shutil.make_archive(str(dist / name), "zip", dist, name)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
