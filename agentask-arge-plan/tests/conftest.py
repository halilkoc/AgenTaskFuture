from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from agentask.config import Settings, load_settings
from tests.support_browser import engine_name, isolate_browser_home, remove_browser_home

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
TEST_SIGNING_KEY = "test-signing-key-0123456789abcdef-XYZ"
SETTING_KEYS = sorted(name.upper() for name in Settings.model_fields)
_browser_home: str | None = None


def pytest_configure(config: pytest.Config) -> None:
    global _browser_home
    _browser_home = isolate_browser_home()


def pytest_unconfigure(config: pytest.Config) -> None:
    remove_browser_home(_browser_home)


def parse_env_example() -> dict[str, str]:
    """.env.example'ı uygulamanın gerçek dotenv okuma kurallarıyla (python-dotenv) okur: tırnaklar kaldırılır,
    yorumlar atlanır. Böylece değerler hem dotenv dosyasına hem doğrudan ortam değişkenine aynı anlamla
    verilebilir. Yinelenen anahtar ayrı testte reddedilir."""
    # Test girdisi olan örnek dosya, uygulamanın kullandığı dotenv kurallarıyla okunur (uygulama ayarı değil).
    from dotenv import dotenv_values  # noqa: TID251

    return {k: (v or "") for k, v in dotenv_values(ENV_EXAMPLE, encoding="utf-8").items()}


def env_example_active_keys() -> list[str]:
    """Örnek dosyadaki etkin (yorum olmayan) anahtarlar, yinelemeler dahil, dosya sırasıyla."""
    keys = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            keys.append(stripped.partition("=")[0].strip())
    return keys


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Geliştirici kabuğundaki uygulama ayarları testleri etkilemesin; cwd'deki .env okunmasın."""
    import os as _os

    for key in SETTING_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key in [k for k in _os.environ if k.startswith("LOCAL_MONGO_")]:  # noqa: TID251 - test yalıtımı
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    yield


EnvFileFactory = Callable[..., Path]


@pytest.fixture
def make_env_file(tmp_path: Path) -> EnvFileFactory:
    """.env.example tabanlı dotenv üretir; kwargs ile anahtarları değiştirir, None verilen anahtar silinir."""

    def _make(name: str = "test.env", **overrides: str | None) -> Path:
        values = parse_env_example()
        values["SESSION_SIGNING_KEY"] = TEST_SIGNING_KEY
        values["BROWSER_ENGINE"] = engine_name()
        for key, value in overrides.items():
            if value is None:
                values.pop(key, None)
            else:
                values[key] = value
        path = tmp_path / name
        path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
        return path

    return _make


@pytest.fixture
def dev_settings(make_env_file: EnvFileFactory) -> Settings:
    return load_settings(make_env_file())


@pytest.fixture
def json_logs() -> Iterator[Callable[[], list[dict[str, Any]]]]:
    """Kök logger'a gerçek JSON biçimleyicisini bağlar; yakalanan satırları çözümleyerek döndürür."""
    import io
    import logging

    from agentask.infrastructure.logging import JsonFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    def lines() -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]

    yield lines
    root.removeHandler(handler)
    root.setLevel(previous)
