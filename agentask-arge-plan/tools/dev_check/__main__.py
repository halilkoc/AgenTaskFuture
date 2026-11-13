"""Tek geliştirme kontrol komutu.

    .venv/bin/python -m tools.dev_check            # lint + format + typecheck + ilgili testler
    .venv/bin/python -m tools.dev_check --full     # ... + bütün testler (Docker hariç)
    .venv/bin/python -m tools.dev_check --docker   # ... + Docker testleri (daemon gerekir)

- Bütün kontroller sırayla çalışır; biri başarısız olsa da diğerleri çalışır, hiçbiri gizlenmez.
- Herhangi biri başarısızsa çıkış kodu 1'dir.
- Atlanan/BLOCKED testler ayrıca listelenir.
- Kullanıcının veritabanına bağlanmaz: MongoDB testleri geçici mongod (rastgele port, geçici dizin) kullanır.
  Çalışan servislere (Homebrew mongod, uygulama, lab) dokunmaz.
- Docker temel kontrolde zorunlu değildir (-m "not docker").
- Tam paket ayrıca `.venv/bin/pytest -q -rs` ile çalıştırılabilir.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = Path(sys.executable).parent

RELEVANT_TESTS = [
    "tests/unit",
    *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests/integration").glob("test_*.py")),
    "tests/integration/mongo",
    "tests/integration/browser/test_screen_runtime.py",
    "tests/integration/browser/test_multi_screen_runtime.py",
    "tests/integration/browser/test_designer.py",
    "tests/integration/browser/test_assistant.py",
    "tests/integration/browser/test_impact.py",
    "tests/e2e/test_designer_ui.py",
    "tests/e2e/test_assistant_ui.py",
    "tests/e2e/test_r3_migration_ui.py",
    "tests/e2e/test_r4_multi_screen_ui.py",
]
_SKIP = re.compile(r"^SKIPPED \[\d+\] (.+)$")


@dataclass
class Result:
    name: str
    code: int
    seconds: float
    skipped: list[str]


def run(name: str, command: list[str]) -> Result:
    print(f"\n=== {name}: {' '.join(command)}", flush=True)
    start = time.monotonic()
    skipped: list[str] = []
    proc = subprocess.Popen(  # sabit argüman listesi, shell yok
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="", flush=True)
        match = _SKIP.match(line.strip())
        if match:
            skipped.append(match.group(1))
    code = proc.wait()
    return Result(name, code, time.monotonic() - start, skipped)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.dev_check", description=__doc__)
    parser.add_argument("--full", action="store_true", help="bütün testler (Docker hariç)")
    parser.add_argument("--docker", action="store_true", help="Docker testlerini de çalıştır")
    args = parser.parse_args(argv)

    tests = ["tests"] if args.full else RELEVANT_TESTS
    results = [
        run("lint", [str(BIN / "ruff"), "check", "src", "tests", "tools"]),
        run("format", [str(BIN / "ruff"), "format", "--check", "src", "tests", "tools"]),
        run("typecheck", [str(BIN / "mypy")]),
        run(
            "testler" + (" (tam, Docker hariç)" if args.full else " (ilgili)"),
            [str(BIN / "pytest"), "-q", "-rs", "-p", "no:cacheprovider", "-m", "not docker", *tests],
        ),
    ]
    if args.docker:
        pytest = [str(BIN / "pytest"), "-q", "-rs", "-p", "no:cacheprovider"]
        results.append(run("docker testleri", [*pytest, "-m", "docker"]))

    print("\n=== ÖZET")
    for r in results:
        print(f"{'GEÇTİ ' if r.code == 0 else 'HATA  '} {r.name:<28} exit={r.code}  {r.seconds:5.1f} sn")
    skipped = [s for r in results for s in r.skipped]
    if not args.docker:
        print("ATLANDI docker testleri               bu kontrolde çalıştırılmadı (--docker ile çalışır)")
    for s in skipped:
        print(f"ATLANDI/BLOCKED {s}")
    failed = [r.name for r in results if r.code != 0]
    print(f"SONUÇ: {'BAŞARISIZ (' + ', '.join(failed) + ')' if failed else 'BAŞARILI'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
