from __future__ import annotations

from fastapi.testclient import TestClient

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

LOCAL = ("127.0.0.1", 50000)
AYSE = {"X-Dev-User": "ayse", "X-Dev-Roles": "designer"}
MEHMET = {"X-Dev-User": "mehmet", "X-Dev-Roles": "designer"}


def test_drafts_api_rules(make_env_file: EnvFileFactory, lab: LabServer, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = lab_settings(
        make_env_file, lab, DRAFT_DIRECTORY=str(tmp_path / "drafts"), RUN_DIRECTORY=str(tmp_path / "runs")
    )
    with TestClient(create_app(settings), client=LOCAL) as c:
        assert (
            c.post(
                "/api/drafts",
                headers={"X-Dev-Roles": "operator"},
                json={"application_id": "lab", "operation_id": "x", "title": "X"},
            ).status_code
            == 403
        )
        d = c.post(
            "/api/drafts",
            headers=AYSE,
            json={"application_id": "lab", "operation_id": "kefil_no", "title": "Kefil no"},
        ).json()
        assert d["revision"] == 1 and "fresh_session_test_missing" in d["issues"]
        assert c.get(f"/api/drafts/{d['draft_id']}", headers=MEHMET).status_code == 404
        assert c.get("/api/drafts", headers=MEHMET).json() == []
        d2 = c.post(
            f"/api/drafts/{d['draft_id']}/steps",
            headers=AYSE,
            json={"expected_revision": 1, "intent_text": "Kefil müşteri numarasını yaz"},
        ).json()
        assert (
            d2["steps"][0]["op"] == "ensure_value" and d2["steps"][0]["provenance"]["op"] == "rule_generated"
        )
        stale = c.post(
            f"/api/drafts/{d['draft_id']}/steps",
            headers=AYSE,
            json={"expected_revision": 1, "intent_text": "ikinci"},
        )
        assert stale.status_code == 409 and stale.json()["code"] == "draft_conflict"
        sel = c.patch(
            f"/api/drafts/{d['draft_id']}/steps/{d2['steps'][0]['step_id']}",
            headers=AYSE,
            json={"expected_revision": 2, "css": "#x"},
        )
        assert sel.status_code == 422
        bad_param = c.post(
            f"/api/drafts/{d['draft_id']}/parameters",
            headers=AYSE,
            json={
                "expected_revision": 2,
                "name": "parola",
                "title": "Parola",
                "max_length": 8,
                "source": "approved_constant",
                "constant": "1234",
            },
        )
        assert bad_param.status_code == 422
        confirm_early = c.post(
            f"/api/drafts/{d['draft_id']}/steps/{d2['steps'][0]['step_id']}/confirm",
            headers=AYSE,
            json={"expected_revision": 2, "meaning": True, "target": True, "effect": True, "params": True},
        )
        assert confirm_early.status_code in {409, 422}
