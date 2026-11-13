"""R2B: oturumun sayfalar arasında bulunması/seçilmesi; sahiplik ve amaç sınırı API düzeyinde."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agentask.config import load_settings
from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory

LOCAL = ("127.0.0.1", 50000)
AYSE = {"X-Dev-User": "ayse", "X-Dev-Roles": "designer,operator"}
MEHMET = {"X-Dev-User": "mehmet", "X-Dev-Roles": "designer,operator"}


def test_overview_status_and_ownership(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled", BROWSER_HEADLESS="true"))
    assert settings.browser_max_sessions_per_user == 1  # .env.example varsayılanı
    with TestClient(create_app(settings), client=LOCAL) as c:
        empty = c.get("/api/sessions/overview", headers=AYSE).json()
        assert empty["sessions"] == [] and empty["quota"]["interactive_limit"] == 1
        sid = c.post("/api/sessions", headers=AYSE, json={"purpose": "verification"}).json()
        assert sid["purpose"] == "interactive"  # istemci amacı seçemez
        sid = sid["session_id"]
        full = c.post("/api/sessions", headers=AYSE)
        assert full.status_code == 429 and full.json()["details"] == {
            "interactive_limit": 1,
            "interactive_used": 1,
        }
        overview = c.get("/api/sessions/overview", headers=AYSE).json()
        assert [s["session_id"] for s in overview["sessions"]] == [sid]
        assert overview["sessions"][0]["alive"] is True and overview["sessions"][0]["busy_operation"] is None
        status = c.get(f"/api/sessions/{sid}", headers=AYSE)
        assert status.status_code == 200 and status.json()["current_url"] == "about:blank"
        assert c.get(f"/api/sessions/{sid}", headers=MEHMET).status_code == 404
        assert c.get("/api/sessions/overview", headers=MEHMET).json()["sessions"] == []
        assert c.get("/api/sessions/yok-boyle-bir-oturum", headers=AYSE).status_code == 404


def test_verification_session_id_rejected_by_public_endpoints(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled", BROWSER_HEADLESS="true"))
    app = create_app(settings)
    with TestClient(app, client=LOCAL) as c:
        sessions = app.state.container.sessions

        async def open_temp() -> str:
            view = await sessions.open("ayse", purpose="verification")
            return view.session_id

        temp = c.portal.call(open_temp)  # type: ignore[attr-defined]
        for method, path, body in [
            ("get", f"/api/sessions/{temp}", None),
            ("post", f"/api/sessions/{temp}/observe", None),
            ("post", f"/api/sessions/{temp}/navigate", {"url": "http://127.0.0.1:8100/"}),
            ("delete", f"/api/sessions/{temp}", None),
            (
                "post",
                "/api/runs",
                {
                    "session_id": temp,
                    "request_id": "r1",
                    "steps": [{"op": "read", "target": {"kind": "textbox", "labels": ["A"]}}],
                },
            ),
        ]:
            r = getattr(c, method)(path, headers=AYSE, **({"json": body} if body else {}))
            assert r.status_code == 404, (path, r.status_code)
        assert c.get("/api/sessions/overview", headers=AYSE).json()["quota"]["verification_in_use"] == 1
