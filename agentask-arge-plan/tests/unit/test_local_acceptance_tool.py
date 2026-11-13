"""Yerel kabul aracı: yalıtım kuralları, sonuç değerlendirmesi, süre sınırı ve çıkış kodu."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from tools.local_acceptance import coverage
from tools.local_acceptance.__main__ import decide_exit, judge, parse_cases
from tools.local_acceptance.package_check import FAILED, PASSED, UNVERIFIED, PackageResult, forbidden_entries
from tools.local_acceptance.process import TIMEOUT, run_limited
from tools.local_acceptance.safety import env_violations, is_loopback_url, redact, settings_violations

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("url", "local"),
    [
        ("http://127.0.0.1:8100", True),
        ("http://localhost:8000/x", True),
        ("http://[::1]:9", True),
        ("https://pega-test.kurum.example/", False),
        ("http://10.0.0.5", False),
    ],
)
def test_loopback(url: str, local: bool) -> None:
    assert is_loopback_url(url) is local


def test_non_local_environment_is_refused_without_printing_value() -> None:
    env = {"TARGET_BASE_URL": "https://pega.kurum.example", "MONGO_URI": "mongodb://127.0.0.1:27017"}
    assert env_violations(env) == ["TARGET_BASE_URL"]


def test_settings_outside_temp_or_remote_are_violations(tmp_path: Path) -> None:
    inside = tmp_path / "runs"
    ok = settings_violations(
        ["http://127.0.0.1:1"], "http://127.0.0.1:1/", "mongodb://127.0.0.1:2", [inside], tmp_path
    )
    assert ok == []
    bad = settings_violations(
        ["https://pega.kurum.example"],
        None,
        "mongodb://db.kurum.example:27017",
        [ROOT / "var" / "runs"],
        tmp_path,
    )
    assert len(bad) == 3


def test_redaction() -> None:
    text = (
        "ADMIN_PASSWORD_HASH=scrypt$16384$8$1$abc$def Cookie: agentask_admin_session=xyz "
        "kabul-test-parolasi-12345"
    )
    cleaned = redact(text)
    assert "abc$def" not in cleaned and "xyz" not in cleaned and "12345" not in cleaned


def test_judge_never_passes_missing_or_skipped() -> None:
    item = coverage.Item(99, "x", "tam", ("tests/a.py", "tests/b.py::test_x"), "v")
    assert judge(item, {"tests/a.py::t1": "passed", "tests/b.py::test_x": "passed"}, None)[0] == PASSED
    assert judge(item, {"tests/a.py::t1": "passed"}, None)[0] == UNVERIFIED
    assert judge(item, {"tests/a.py::t1": "failed", "tests/b.py::test_x": "passed"}, None)[0] == FAILED
    assert (
        judge(item, {"tests/a.py::t1[p]": "skipped", "tests/b.py::test_x": "passed"}, None)[0] == UNVERIFIED
    )
    package_item = coverage.Item(98, "p", "kismi", (coverage.PACKAGE,), "v")
    assert judge(package_item, {}, None)[0] == UNVERIFIED
    assert judge(package_item, {}, PackageResult(PASSED))[0] == PASSED


def test_parse_cases_and_interrupted_run(tmp_path: Path) -> None:
    assert parse_cases(tmp_path / "yok.xml") == {}  # koşu kesildi: hiçbir madde geçmez
    junit = tmp_path / "j.xml"
    junit.write_text(
        '<testsuites><testsuite><testcase classname="tests.e2e.test_a" name="test_ok"/>'
        '<testcase classname="tests.e2e.test_a" name="test_bad"><failure/></testcase>'
        '<testcase classname="tests.e2e.test_a" name="test_skip"><skipped/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    assert parse_cases(junit) == {
        "tests/e2e/test_a.py::test_ok": "passed",
        "tests/e2e/test_a.py::test_bad": "failed",
        "tests/e2e/test_a.py::test_skip": "skipped",
    }


def test_exit_codes() -> None:
    assert decide_exit(True, 0, {PASSED}) == 0
    assert decide_exit(True, 0, {PASSED, UNVERIFIED}) == 2
    assert decide_exit(True, 1, {PASSED}) == 1
    assert decide_exit(True, 0, {FAILED}) == 1
    assert decide_exit(True, TIMEOUT, {UNVERIFIED}) == 5
    assert decide_exit(False, 0, {PASSED}) == 4


def test_timeout_kills_own_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    script = (
        "import subprocess, sys, time\n"
        f"c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(c.pid))\ntime.sleep(60)\n"
    )
    started = time.monotonic()
    assert run_limited([sys.executable, "-c", script], tmp_path, None, tmp_path / "log", 2) == TIMEOUT
    assert time.monotonic() - started < 20
    child = int(pid_file.read_text())
    time.sleep(0.5)
    alive = subprocess.run(  # noqa: S603 - sabit komut
        ["ps", "-o", "stat=", "-p", str(child)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert alive.stdout.strip() in {"", "Z"}  # torun süreç de sonlandı


def test_cli_refuses_non_local_target_before_running(tmp_path: Path) -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "AGENTASK_ACCEPTANCE_AWAKE": "1",
        "AGENTASK_ACCEPTANCE_REPORTS": str(tmp_path),
        "TARGET_BASE_URL": "https://pega.kurum.example",
    }
    done = subprocess.run(
        [sys.executable, "-m", "tools.local_acceptance"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 3
    assert "TARGET_BASE_URL" in done.stderr and "kurum.example" not in done.stderr
    assert not list(tmp_path.glob("*/junit.xml"))  # hiçbir test başlamadı


def test_coverage_lists_28_items_with_existing_tests() -> None:
    assert [i.number for i in coverage.ITEMS] == list(range(1, 29))
    for item in coverage.ITEMS:
        for test in item.tests:
            if test != coverage.PACKAGE:
                assert (ROOT / test.split("::")[0]).is_file(), test


def test_forbidden_package_entries() -> None:
    assert forbidden_entries(["a/.env", "a/var/x", "a/app/x.whl"]) == ["a/.env", "a/var/x"]
