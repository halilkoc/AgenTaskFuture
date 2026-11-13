"""AUTH_MODE=local_admin HTTP davranışı: yönlendirme, cookie, CSRF, dev başlığı yok sayılır."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agentask.config import load_settings
from agentask.domain.passwords import hash_password
from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory

LOCAL = ("127.0.0.1", 50000)
PASSWORD = "dogru-parola-12345"
Logs = Callable[[], list[dict[str, Any]]]


@pytest.fixture
def client(make_env_file: EnvFileFactory) -> Iterator[TestClient]:
    settings = load_settings(
        make_env_file(
            AUTH_MODE="local_admin",
            DEV_AUTH_ENABLED="false",
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD_HASH=hash_password(PASSWORD),
            ADMIN_LOGIN_MAX_ATTEMPTS="3",
            CATALOG_BACKEND="disabled",
        )
    )
    with TestClient(create_app(settings), client=LOCAL, follow_redirects=False) as c:
        yield c


def login(client: TestClient) -> str:
    assert client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 204
    page = client.get("/runs")
    assert page.status_code == 200
    return page.text.split('name="agentask-csrf" content="')[1].split('"')[0]


def test_unauthenticated_page_redirects_and_api_is_401(client: TestClient) -> None:
    page = client.get("/assistant", headers={"accept": "text/html"})
    assert page.status_code == 303 and page.headers["location"] == "/login?next=/assistant"
    assert client.get("/api/runs").status_code == 401
    assert client.get("/login").status_code == 200


def test_dev_headers_never_grant_access(client: TestClient) -> None:
    headers = {"X-Dev-User": "admin", "X-Dev-Roles": "designer,operator,publisher"}
    assert client.get("/api/me", headers=headers).status_code == 401


def test_cookie_flags_csrf_and_logout(client: TestClient, json_logs: Logs) -> None:
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=" in cookie
    assert client.get("/api/me").json()["user_id"] == "admin"
    assert client.post("/api/sessions").status_code == 403  # CSRF belirteci yok
    csrf = login(client)
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "yanlis"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/runs").status_code == 401
    text = json.dumps(json_logs(), ensure_ascii=False)
    assert PASSWORD not in text and csrf not in text and "agentask_admin_session" not in text


def test_wrong_password_is_generic_and_rate_limited(client: TestClient) -> None:
    for _ in range(3):
        wrong = client.post("/api/auth/login", json={"username": "admin", "password": "yanlis-parola"})
        assert wrong.status_code == 401 and wrong.json()["code"] == "login_failed"
    locked = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert locked.status_code == 429 and locked.json()["code"] == "login_locked"


@pytest.mark.parametrize("target", ["https://kotu.example/", "//kotu.example/x", "javascript:alert(1)"])
def test_login_next_is_only_relative(client: TestClient, target: str) -> None:
    assert 'data-next="/"' in client.get("/login", params={"next": target}).text


def test_other_auth_modes_have_no_login(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled"))
    with TestClient(create_app(settings), client=LOCAL) as c:
        assert c.get("/login").status_code == 404
        assert c.post("/api/auth/login", json={"username": "a", "password": "b"}).status_code == 400
