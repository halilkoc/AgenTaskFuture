"""Tek komut: `.venv/bin/python -m tools.local_acceptance` (bkz. docs/18). Otomatik tekrar yoktur.

Çıkış kodu: 0 hepsi GEÇTİ · 1 başarısız madde/test · 2 otomatik doğrulanamayan madde · 3 ön koşul eksik veya
yerel olmayan adres · 4 kalıcı veride değişiklik (yalıtım ihlali) · 5 süre sınırı aşıldı (koşu kesildi).
pytest'in kendi çıkış kodu raporda ve `pytest-exit-code.txt` dosyasında ayrıca saklanır.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.local_acceptance.coverage import HUMAN_CHECKS, ITEMS, PACKAGE, Item
from tools.local_acceptance.package_check import FAILED, PASSED, UNVERIFIED, PackageResult, check_package
from tools.local_acceptance.process import TIMEOUT, run_limited
from tools.local_acceptance.safety import env_violations, redact

ROOT = Path(__file__).resolve().parents[2]
KEEP_ENV = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SHELL")
DEFAULT_TIMEOUT_S = 3600
PER_TEST_STACK_DUMP_S = 600


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def preflight(environ: Mapping[str, str], work: Path) -> tuple[list[str], dict[str, str]]:
    violating = env_violations(environ)
    if violating:  # yerel olmayan hedef verilmişse diğer denetimlere geçilmez
        return ["Kabukta yerel olmayan adres tanımlı; koşu reddedildi: " + ", ".join(violating)], {}
    problems: list[str] = []
    info = {"mongod": "var" if shutil.which("mongod") else "yok"}
    if info["mongod"] == "yok":
        problems.append("mongod bulunamadı (geçici MongoDB için gerekli).")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
    info["gecici_port"] = "bağlanabilir"
    for port in (8000, 8100, 8101, 27017):
        info[f"port_{port}"] = "dolu (kullanılmaz, dokunulmaz)" if _port_open(port) else "boş (kullanılmaz)"
    probe = (
        "import asyncio\nfrom playwright.async_api import async_playwright\n"
        "async def m():\n  async with async_playwright() as p:\n"
        "    b = await p.chromium.launch(); print(b.version); await b.close()\nasyncio.run(m())\n"
    )
    log = work / "chromium-probe.log"
    code = run_limited([sys.executable, "-c", probe], ROOT, None, log, 120)
    if code == 0:
        info["chromium"] = log.read_text(encoding="utf-8").strip()
    else:
        problems.append("Chromium başlatılamadı (playwright install chromium).")
    return problems, info


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        stat = path.stat()
        digest.update(f"{path.relative_to(root)}|{stat.st_size}|{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()


def _real_mongo_counts() -> dict[str, Any]:
    """Yalnız okuma: yerel kalıcı MongoDB'deki veritabanları ve koleksiyon sayıları."""
    if not _port_open(27017):
        return {"durum": "kapalı"}
    from pymongo import MongoClient

    client: MongoClient[dict[str, Any]] = MongoClient(
        "mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=1500
    )
    try:
        out: dict[str, Any] = {}
        for name in sorted(client.list_database_names()):
            if name not in {"admin", "config", "local"}:
                db = client[name]
                out[name] = {c: db[c].estimated_document_count() for c in sorted(db.list_collection_names())}
        return out
    finally:
        client.close()


def snapshot() -> dict[str, Any]:
    env = ROOT / ".env"
    return {
        "env": hashlib.sha256(env.read_bytes()).hexdigest() if env.is_file() else None,
        "var": _tree_digest(ROOT / "var") if (ROOT / "var").is_dir() else None,
        "mongo": _real_mongo_counts(),
    }


def selected_tests() -> list[str]:
    return list(dict.fromkeys(t for item in ITEMS for t in item.tests if t != PACKAGE))


def run_pytest(output: Path, base: Path, environ: Mapping[str, str], timeout_s: float) -> int | str:
    env = {k: environ[k] for k in KEEP_ENV if k in environ}
    env.update(
        AGENTASK_ACCEPTANCE_DIR=str(output),
        AGENTASK_ACCEPTANCE_BASETEMP=str(base),
        PYTHONPATH=str(ROOT),
        PYTHONDONTWRITEBYTECODE="1",
    )
    command = [
        sys.executable, "-m", "pytest", "-q", "-rfEs", "--tb=short", "-p", "no:cacheprovider",
        "-o", f"faulthandler_timeout={PER_TEST_STACK_DUMP_S}", "-p", "tools.local_acceptance.guard",
        f"--basetemp={base}", f"--junitxml={output / 'junit.xml'}", *selected_tests(),
    ]  # fmt: skip
    raw = output / "pytest.raw"
    code = run_limited(command, ROOT, env, raw, timeout_s)
    (output / "pytest.log").write_text(
        redact(raw.read_text(encoding="utf-8", errors="replace")), encoding="utf-8"
    )
    raw.unlink()
    (output / "pytest-exit-code.txt").write_text(str(code), encoding="utf-8")
    return code


def parse_cases(junit: Path) -> dict[str, str]:
    """`dosya::test` → passed/failed/skipped. Dosya yoksa (koşu kesildi) boş döner."""
    if not junit.is_file():
        return {}
    cases: dict[str, str] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):  # noqa: S314 - bu koşunun ürettiği yerel dosya
        path = case.get("classname", "").replace(".", "/") + ".py"
        state = "passed"
        if case.find("failure") is not None or case.find("error") is not None:
            state = "failed"
        elif case.find("skipped") is not None:
            state = "skipped"
        cases[f"{path}::{case.get('name', '')}"] = state
    return cases


def judge(item: Item, cases: Mapping[str, str], package: PackageResult | None) -> tuple[str, int, str]:
    """(sonuç, değerlendirilen test sayısı, not). Sonucu olmayan madde hiçbir zaman GEÇTİ sayılmaz."""
    if PACKAGE in item.tests:
        if package is None:
            return UNVERIFIED, 0, "paket denetimi çalışmadı"
        return package.status, 1, ""
    states: list[str] = []
    for test in item.tests:
        matched = [v for k, v in cases.items() if k == test or k.startswith((f"{test}::", f"{test}["))]
        if not matched:
            return UNVERIFIED, len(states), f"sonuç yok: {test.rsplit('/', 1)[-1]}"
        states += matched
    if "failed" in states:
        return FAILED, len(states), ""
    if "skipped" in states:
        return UNVERIFIED, len(states), "atlanan test var"
    return PASSED, len(states), ""


def decide_exit(isolation_ok: bool, pytest_code: int | str, statuses: set[str]) -> int:
    if not isolation_ok:
        return 4
    if pytest_code == TIMEOUT:
        return 5
    if pytest_code != 0 or FAILED in statuses:
        return 1
    return 2 if UNVERIFIED in statuses else 0


def _evidence(item: Item) -> str:
    return ", ".join("paket denetimi" if t == PACKAGE else t.rsplit("/", 1)[-1] for t in item.tests)


def write_report(output: Path, data: dict[str, Any]) -> None:
    (output / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Yerel kabul raporu (otomatik)", "",
        "**Bu rapor kullanıcı kabulü değildir.** GEÇTİ, maddenin otomatik kanıtla doğrulandığını gösterir; "
        "lab sonucu Pega kabulü değildir.", "",
        f"- Tarih: {data['started']} – {data['finished']}",
        f"- Kod özeti (src, tools, tests): `{data['tree']}`",
        f"- pytest çıkış kodu: **{data['pytest_exit']}**; koşunun çıkış kodu: **{data['exit']}**",
        f"- Yalıtım: {data['isolation']}",
        f"- Paket: `{data['package'].get('name')}` SHA-256 `{data['package'].get('sha256')}`", "",
        "| # | Madde | Sonuç | Test | Kanıt | Doğrulanan sonuç / not |", "|---|---|---|---|---|---|",
    ]  # fmt: skip
    for row in data["items"]:
        note = f" ({row['note']})" if row["note"] else ""
        lines.append(
            f"| {row['number']} | {row['title']} | **{row['status']}** | {row['cases']} | {row['evidence']} "
            f"| {row['verified']}{note} |"
        )
    lines += [
        "",
        "## Paket denetimi",
        "",
        *[f"- {k}: {v}" for k, v in data["package"].get("checks", {}).items()],
    ]
    lines += ["", "## Ön koşullar", "", *[f"- {k}: {v}" for k, v in data["preflight"].items()]]
    lines += ["", "## Size kalan insan kontrolleri", "", *[f"- {c}" for c in HUMAN_CHECKS]]
    lines += [
        "",
        "### Maddeye özel notlar",
        "",
        *[f"- Madde {r['number']}: {r['human']}" for r in data["items"] if r["human"]],
    ]
    if data["failures"]:
        lines += ["", "## Başarısız testler", "", *[f"- `{f}`" for f in data["failures"]]]
        lines += ["", "Teşhis ve ekran görüntüleri: `failures/`."]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="local_acceptance", description=__doc__)
    parser.add_argument("--skip-package", action="store_true", help="Madde 28 OTOMATİK DOĞRULANAMADI olur")
    parser.add_argument(
        "--timeout-s", type=float, default=DEFAULT_TIMEOUT_S, help="pytest toplam süre sınırı"
    )
    args = parser.parse_args(argv)
    environ = dict(os.environ)
    if (
        platform.system() == "Darwin"
        and not environ.get("AGENTASK_ACCEPTANCE_AWAKE")
        and shutil.which("caffeinate")
    ):
        environ["AGENTASK_ACCEPTANCE_AWAKE"] = "1"  # uzun koşu uykuda bozulmasın
        command = ["caffeinate", "-i", sys.executable, "-m", "tools.local_acceptance", *sys.argv[1:]]
        os.execvpe("caffeinate", command, environ)  # noqa: S606, S607 - sabit komut, kabuk yok
    reports = Path(environ.get("AGENTASK_ACCEPTANCE_REPORTS", ROOT / "acceptance-reports"))
    reports.mkdir(parents=True, exist_ok=True)
    lock = reports / ".kosu.lock"
    try:
        lock.touch(exist_ok=False)
    except FileExistsError:
        print(f"Başka bir kabul koşusu sürüyor veya yarım kaldı: {lock}", file=sys.stderr)
        return 3
    output = reports / datetime.now().strftime("%Y%m%d-%H%M%S")
    output.mkdir()
    work = Path(tempfile.mkdtemp(prefix="agentask-acceptance-"))
    try:
        problems, info = preflight(environ, work)
        if problems:
            (output / "preflight-failed.txt").write_text("\n".join(problems) + "\n", encoding="utf-8")
            (output / "exit-code.txt").write_text("3", encoding="utf-8")
            print("\n".join(problems), file=sys.stderr)
            return 3
        before = snapshot()
        started = datetime.now().isoformat(timespec="seconds")
        print(f"Kabul koşusu başladı; rapor: {output}", flush=True)
        pytest_code = run_pytest(output, work / "pytest", environ, args.timeout_s)
        package = None if args.skip_package or pytest_code == TIMEOUT else check_package(output, work)
        after = snapshot()
        cases = parse_cases(output / "junit.xml")
        items = []
        for item in ITEMS:
            status, count, note = judge(item, cases, package)
            items.append(
                {**asdict(item), "status": status, "cases": count, "note": note, "evidence": _evidence(item)}
            )
        code = decide_exit(before == after, pytest_code, {i["status"] for i in items})
        tree = hashlib.sha256()
        for folder in ("src", "tools", "tests"):
            for path in sorted((ROOT / folder).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and ".egg-info" not in str(path):
                    tree.update(path.read_bytes())
        isolation = "değişiklik yok (.env, var/, kalıcı MongoDB sayıları)" if before == after else "İHLAL"
        package_data = (
            asdict(package) if package else {"status": UNVERIFIED, "checks": {"paket": "çalışmadı"}}
        )
        failures = sorted(k for k, v in cases.items() if v == "failed")
        write_report(
            output,
            {
                "started": started, "finished": datetime.now().isoformat(timespec="seconds"),
                "tree": tree.hexdigest(), "pytest_exit": pytest_code, "exit": code, "isolation": isolation,
                "package": package_data, "preflight": info, "items": items, "failures": failures,
            },
        )  # fmt: skip
        (output / "exit-code.txt").write_text(str(code), encoding="utf-8")
        passed = sum(i["status"] == PASSED for i in items)
        print(f"Sonuç: {passed}/{len(items)} GEÇTİ · çıkış {code} · {output / 'report.md'}")
        return code
    finally:
        shutil.rmtree(work, ignore_errors=True)
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
