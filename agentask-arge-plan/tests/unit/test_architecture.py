"""Katman sınırları: domain framework import etmez; Settings dışında env okunmaz."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "agentask"
LAB = SRC.parent / "agentask_lab"
FORBIDDEN_IN_DOMAIN = (
    "fastapi",
    "starlette",
    "playwright",
    "pymongo",
    "motor",
    "httpx",
    "agentask.infrastructure",
    "agentask.presentation",
    "agentask.config",
)


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_domain_has_no_framework_or_outer_layer_imports() -> None:
    for path in (SRC / "domain").rglob("*.py"):
        bad = {n for n in _imports(path) if n.startswith(FORBIDDEN_IN_DOMAIN)}
        assert not bad, f"{path.name}: {bad}"


def test_application_does_not_import_infrastructure_or_presentation() -> None:
    for path in (SRC / "application").rglob("*.py"):
        bad = {
            n
            for n in _imports(path)
            if n.startswith(("agentask.infrastructure", "agentask.presentation", "fastapi", "starlette"))
        }
        assert not bad, f"{path.name}: {bad}"


def test_product_code_does_not_depend_on_lab() -> None:
    for path in SRC.rglob("*.py"):
        assert not {n for n in _imports(path) if n.startswith("agentask_lab")}, path


def test_only_settings_layer_touches_environment() -> None:
    for path in [*SRC.rglob("*.py"), *LAB.rglob("*.py")]:
        text = path.read_text(encoding="utf-8")
        if path.parent.name == "config":
            continue
        assert "os.environ" not in text and "os.getenv" not in text and "dotenv" not in _imports(path), path
