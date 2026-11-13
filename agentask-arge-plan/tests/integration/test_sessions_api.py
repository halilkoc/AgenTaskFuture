from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agentask.config import load_settings
from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.support_lab import LabServer

LOCAL = ("127.0.0.1", 50000)


@pytest.fixture
def api_settings(make_env_file: EnvFileFactory, lab: LabServer):  # type: ignore[no-untyped-def]
    return load_settings(
        make_env_file(
            TARGET_ALLOWED_ORIGINS=json.dumps([lab.primary, lab.secondary]),
            TARGET_BASE_URL=lab.primary,
            LAB_PRIMARY_ORIGIN=lab.primary,
            LAB_SECONDARY_ORIGIN=lab.secondary,
            AUTOMATION_APPLICATIONS_JSON=json.dumps(
                [{"id": "lab", "name": "Deney uygulaması", "base_url": f"{lab.primary}/"}]
            ),
            BROWSER_HEADLESS="true",
            BROWSER_MAX_SESSIONS="3",
            BROWSER_MAX_SESSIONS_PER_USER="1",
        )
    )


@pytest.mark.browser
def test_session_api_lifecycle_and_ownership(api_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(api_settings)
    ayse = {"X-Dev-User": "ayse", "X-Dev-Roles": "operator"}
    mehmet = {"X-Dev-User": "mehmet", "X-Dev-Roles": "operator"}
    with TestClient(app, client=LOCAL) as c:
        created = c.post("/api/sessions", headers=ayse)
        assert created.status_code == 201, created.text
        session_id = created.json()["session_id"]
        assert created.json()["owner_id"] == "ayse" and created.json()["purpose"] == "interactive"

        assert c.post("/api/sessions", headers=ayse).json()["code"] == "session_limit_reached"
        assert [s["session_id"] for s in c.get("/api/sessions", headers=ayse).json()] == [session_id]
        assert c.get("/api/sessions", headers=mehmet).json() == []

        foreign = c.delete(f"/api/sessions/{session_id}", headers=mehmet)
        assert foreign.status_code == 404 and foreign.json()["code"] == "session_not_found"

        assert c.delete(f"/api/sessions/{session_id}", headers=ayse).status_code == 204
        assert c.delete(f"/api/sessions/{session_id}", headers=ayse).status_code == 404
        c.post("/api/sessions", headers=mehmet)
        factory = app.state.container.browser_factory
        assert factory.is_running
    assert not factory.is_running, "lifespan kapanışı browser'ı kapatmalı"


def test_session_api_requires_capability(api_settings) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(api_settings), client=LOCAL) as c:
        response = c.post("/api/sessions", headers={"X-Dev-User": "p", "X-Dev-Roles": "publisher"})
    assert response.status_code == 403


def test_session_limit_maps_to_429(api_settings) -> None:  # type: ignore[no-untyped-def]
    from agentask.application.errors import SessionBusy, SessionLimitReached, SessionNotFound
    from agentask.presentation.errors import status_for

    assert status_for(SessionLimitReached()) == 429
    assert status_for(SessionBusy()) == 409
    assert status_for(SessionNotFound()) == 404


def test_session_api_returns_503_when_browser_cannot_start(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(
        make_env_file(BROWSER_HEADLESS="true", BROWSER_EXECUTABLE_PATH="/nonexistent/chrome")
    )
    with TestClient(create_app(settings), client=LOCAL) as c:
        response = c.post("/api/sessions", headers={"X-Dev-User": "ayse", "X-Dev-Roles": "operator"})
        assert response.status_code == 503
        assert response.json()["code"] == "dependency_unavailable"
        assert c.get("/api/sessions", headers={"X-Dev-User": "ayse", "X-Dev-Roles": "operator"}).json() == []


@pytest.mark.browser
def test_interruptions_and_picker_respect_session_ownership(api_settings) -> None:  # type: ignore[no-untyped-def]
    ayse = {"X-Dev-User": "ayse", "X-Dev-Roles": "designer"}
    mehmet = {"X-Dev-User": "mehmet", "X-Dev-Roles": "designer"}
    publisher = {"X-Dev-User": "ayse", "X-Dev-Roles": "publisher"}
    with TestClient(create_app(api_settings), client=LOCAL) as c:
        sid = c.post("/api/sessions", headers=ayse).json()["session_id"]
        url = f"/api/sessions/{sid}/interruptions"
        stale = {"action": "close_new_windows", "ids": ["0123456789abcdef"]}
        own = c.get(url, headers=ayse)
        assert own.status_code == 200
        assert own.json() == {"browser_dialog": None, "new_windows": [], "focused_window": None}
        for action in ("close_new_windows", "dismiss_browser_dialog", "design_new_window"):
            assert c.post(url, headers=ayse, json={"action": action, "ids": []}).status_code == 409
        # Başkasının oturumu: kesinti, karar ve seçim modu uçları "bulunamadı" döner.
        assert c.get(url, headers=mehmet).status_code == 404
        assert c.post(url, headers=mehmet, json=stale).status_code == 404
        assert c.post(f"/api/sessions/{sid}/picker/start", headers=mehmet).status_code == 404
        # Yetkisiz rol, tanımsız karar (ör. onaylama) ve kimliksiz karar reddedilir.
        assert c.get(url, headers=publisher).status_code == 403
        assert c.post(url, headers=publisher, json=stale).status_code == 403
        assert (
            c.post(
                url, headers=ayse, json={"action": "accept_browser_dialog", "ids": ["0123456789abcdef"]}
            ).status_code
            == 422
        )
        assert c.post(url, headers=ayse, json={"action": "close_new_windows"}).status_code == 422
        # Görülmemiş/eski kimlik: hiçbir şey kapatılmaz, durum değişti.
        changed = c.post(url, headers=ayse, json=stale)
        assert changed.status_code == 409 and changed.json()["code"] == "interruption_changed"
        dialog = c.post(
            url, headers=ayse, json={"action": "dismiss_browser_dialog", "ids": ["0123456789abcdef"]}
        )
        assert dialog.status_code == 409
        # Oturum yaşam döngüsü: kapatılan oturumda kesinti uçları "bulunamadı" döner.
        assert c.delete(f"/api/sessions/{sid}", headers=ayse).status_code == 204
        assert c.get(url, headers=ayse).status_code == 404
        assert c.post(url, headers=ayse, json=stale).status_code == 404
