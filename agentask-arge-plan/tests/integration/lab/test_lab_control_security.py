from __future__ import annotations

from fastapi.testclient import TestClient

from agentask_lab.app import create_lab_app
from agentask_lab.state import LabState

PRIMARY, SECONDARY = "http://127.0.0.1:8100", "http://127.0.0.1:8101"


def test_control_api_refuses_non_loopback_client() -> None:
    app = create_lab_app(LabState(), PRIMARY, SECONDARY)
    with TestClient(app, client=("10.0.0.9", 1234)) as c:
        assert c.put("/__lab/scenario", json={"delay_ms": 1}).status_code == 403
        assert c.post("/__lab/reset").status_code == 403


def test_autologin_refuses_non_loopback_client() -> None:
    app = create_lab_app(LabState(), PRIMARY, SECONDARY)
    with TestClient(app, client=("10.0.0.9", 1234)) as c:
        assert c.get("/__lab/autologin?user=x", follow_redirects=False).status_code == 403
