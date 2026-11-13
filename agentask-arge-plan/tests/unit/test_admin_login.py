"""Geçici admin girişi: hash, oturum süresi, CSRF, deneme sınırı, yapılandırma ve sır koruması."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from agentask.__main__ import main
from agentask.application.errors import Forbidden, LoginFailed, LoginLocked, Unauthenticated
from agentask.application.ports.identity import IdentityRequest
from agentask.bootstrap import build_container
from agentask.config import ConfigurationError, load_settings
from agentask.domain.identity import Role
from agentask.domain.passwords import hash_password, is_valid_hash, verify_password
from agentask.infrastructure.identity.local_admin import COOKIE_NAME, CSRF_HEADER, LocalAdminIdentity
from tests.conftest import EnvFileFactory

PASSWORD = "dogru-parola-12345"
HASH = hash_password(PASSWORD)
Logs = Callable[[], list[dict[str, Any]]]


class Clock:
    now = 1000.0

    def __call__(self) -> float:
        return self.now


def identity(clock: Clock | None = None, attempts: int = 3) -> LocalAdminIdentity:
    return LocalAdminIdentity("admin", HASH, 60, attempts, 30, clock or Clock())


def request(token: str | None, method: str = "GET", csrf: str | None = None) -> IdentityRequest:
    headers = {}
    if token:
        headers["cookie"] = f"{COOKIE_NAME}={token}"
    if csrf:
        headers[CSRF_HEADER] = csrf
    return IdentityRequest("127.0.0.1", headers, method)


def test_hash_is_salted_and_verifies() -> None:
    other = hash_password(PASSWORD)
    assert other != HASH and PASSWORD not in HASH and is_valid_hash(HASH)
    assert verify_password(PASSWORD, HASH) and not verify_password("yanlis-parola-1", HASH)
    assert not is_valid_hash(PASSWORD) and not is_valid_hash("scrypt:1:1:1:abc:def")


async def test_login_gives_all_roles_and_requires_csrf_for_changes() -> None:
    auth = identity()
    token = await auth.login("ADMIN", PASSWORD, "c1")
    principal = await auth.authenticate(request(token))
    assert principal.user_id == "admin" and principal.roles == frozenset(Role)
    assert principal.identity_source == "local_admin"
    with pytest.raises(Forbidden):
        await auth.authenticate(request(token, "POST"))
    with pytest.raises(Forbidden):
        await auth.authenticate(request(token, "POST", "yanlis"))
    csrf = auth.csrf_for(f"{COOKIE_NAME}={token}")
    assert (await auth.authenticate(request(token, "POST", csrf))).user_id == "admin"


async def test_no_cookie_or_expired_or_logged_out_is_rejected() -> None:
    clock = Clock()
    auth = identity(clock)
    with pytest.raises(Unauthenticated):
        await auth.authenticate(request(None))
    with pytest.raises(Unauthenticated):
        await auth.authenticate(request("sahte"))
    token = await auth.login("admin", PASSWORD, "c")
    clock.now += 61
    with pytest.raises(Unauthenticated):
        await auth.authenticate(request(token))
    clock.now += 1
    token = await auth.login("admin", PASSWORD, "c")
    auth.logout(f"{COOKIE_NAME}={token}")
    with pytest.raises(Unauthenticated):
        await auth.authenticate(request(token))


async def test_failed_attempts_lock_then_recover() -> None:
    clock = Clock()
    auth = identity(clock, attempts=2)
    for name, secret in (("admin", "yanlis-parola-1"), ("baskasi", PASSWORD)):
        with pytest.raises(LoginFailed):
            await auth.login(name, secret, "c")
    with pytest.raises(LoginLocked):  # doğru parola da kilitliyken kabul edilmez
        await auth.login("admin", PASSWORD, "c")
    assert await auth.login("admin", PASSWORD, "baska-istemci")
    clock.now += 31
    assert await auth.login("admin", PASSWORD, "c")


async def test_logs_never_contain_credentials(json_logs: Logs) -> None:
    auth = identity()
    with pytest.raises(LoginFailed):
        await auth.login("yanlislikla-parola-yazildi", "gizli-deneme-1", "c")
    token = await auth.login("admin", PASSWORD, "c")
    text = json.dumps(json_logs(), ensure_ascii=False)
    assert "yanlislikla-parola-yazildi" not in text and "gizli-deneme-1" not in text
    assert PASSWORD not in text and token not in text and HASH not in text
    assert [x["outcome"] for x in json_logs() if x["event"] == "auth_login"] == ["failed", "success"]


def values(**extra: str) -> dict[str, str]:
    return {
        "AUTH_MODE": "local_admin",
        "DEV_AUTH_ENABLED": "false",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD_HASH": HASH,
        **extra,
    }


def test_local_admin_builds_without_dev_fallback(make_env_file: EnvFileFactory) -> None:
    container = build_container(load_settings(make_env_file(CATALOG_BACKEND="disabled", **values())))
    assert container.identity.source == "local_admin" and container.admin_auth is container.identity


@pytest.mark.parametrize(
    ("extra", "fragment"),
    [
        ({"ADMIN_PASSWORD_HASH": ""}, "ADMIN_PASSWORD_HASH"),
        ({"ADMIN_PASSWORD_HASH": "duz-metin-parola"}, "ADMIN_PASSWORD_HASH"),
        ({"ADMIN_USERNAME": ""}, "ADMIN_USERNAME"),
        ({"DEV_AUTH_ENABLED": "true"}, "DEV_AUTH_ENABLED"),
        ({"APP_HOST": "0.0.0.0"}, "ADMIN_COOKIE_SECURE"),  # noqa: S104
    ],
)
def test_bad_admin_config_stops_startup(
    make_env_file: EnvFileFactory, extra: dict[str, str], fragment: str
) -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_settings(make_env_file(**values(**extra)))
    assert fragment in str(caught.value) and "duz-metin-parola" not in str(caught.value)


def test_hash_command_prints_only_hash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("getpass.getpass", lambda _: PASSWORD)
    assert main(["--hash-admin-password"]) == 0
    out = capsys.readouterr().out.strip()
    assert is_valid_hash(out) and verify_password(PASSWORD, out) and PASSWORD not in out
    monkeypatch.setattr("getpass.getpass", lambda _: "kisa")
    assert main(["--hash-admin-password"]) == 2
