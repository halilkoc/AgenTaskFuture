"""R3 API davranışları: U2 alan bazlı doğrulama hataları (değer sızdırmadan), U1 liste adım sayısı, geçiş ve
ekran uçlarının yetki ve katalog-kapalı yanıtları."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

LOCAL = ("127.0.0.1", 50000)
AYSE = {"X-Dev-User": "ayse", "X-Dev-Roles": "designer"}


def client(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> TestClient:
    settings = lab_settings(
        make_env_file, lab, DRAFT_DIRECTORY=str(tmp_path / "drafts"), RUN_DIRECTORY=str(tmp_path / "runs")
    )
    return TestClient(create_app(settings), client=LOCAL)


def test_validation_errors_name_field_and_reason_without_values(
    make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path
) -> None:
    with client(make_env_file, lab, tmp_path) as c:
        d = c.post(
            "/api/drafts",
            headers=AYSE,
            json={"application_id": "lab", "operation_id": "kefil_no", "title": "K"},
        ).json()
        secret_like = "Parola-Gizli-987"
        r = c.post(
            f"/api/drafts/{d['draft_id']}/parameters",
            headers=AYSE,
            json={
                "expected_revision": 1,
                "name": "Müşteri No!",
                "title": secret_like,
                "max_length": 0,
                "source": "user_input",
            },
        )
        assert r.status_code == 422
        body = r.json()
        errors = {e["field"]: e["message"] for e in body["details"]["errors"]}
        assert "name" in errors and "küçük harfle başlamalı" in errors["name"]
        assert errors["max_length"] == "1 veya daha büyük olmalı"
        assert body["safe_message"].startswith("Girdi doğrulanamadı:")
        assert secret_like not in r.text and "Müşteri No!" not in r.text  # girdi değeri geri yansıtılmaz

        missing = c.post(f"/api/drafts/{d['draft_id']}/steps", headers=AYSE, json={"expected_revision": 1})
        assert missing.status_code == 422
        assert missing.json()["details"]["errors"] == [
            {"field": "intent_text", "reason": "missing", "message": "zorunlu alan boş bırakılamaz"}
        ]
        model_rule = c.post(
            f"/api/drafts/{d['draft_id']}/parameters",
            headers=AYSE,
            json={
                "expected_revision": 1,
                "name": "sube",
                "title": "Şube",
                "max_length": 5,
                "source": "approved_constant",
            },
        )
        assert model_rule.status_code == 422
        [err] = model_rule.json()["details"]["errors"]
        assert err["field"] == "(genel)" and "approved_constant" in err["message"]


def test_draft_list_step_count_and_screen_state(
    make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path
) -> None:
    with client(make_env_file, lab, tmp_path) as c:
        d = c.post(
            "/api/drafts",
            headers=AYSE,
            json={"application_id": "lab", "operation_id": "kefil_no", "title": "K"},
        ).json()
        for i, text in enumerate(["Kefil müşteri numarasını yaz", "Başvuran numarasını yaz"], start=1):
            c.post(
                f"/api/drafts/{d['draft_id']}/steps",
                headers=AYSE,
                json={"expected_revision": i, "intent_text": text},
            )
        [row] = c.get("/api/drafts", headers=AYSE).json()
        assert row["steps"] == 2 and row["screen_id"] is None and row["migrated_from"] is None
        full = c.get(f"/api/drafts/{d['draft_id']}", headers=AYSE).json()
        assert "screen_missing" in full["issues"]


def test_migration_and_screen_endpoints_guarded(
    make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path
) -> None:
    with client(make_env_file, lab, tmp_path) as c:
        operator = {"X-Dev-User": "op", "X-Dev-Roles": "operator"}
        assert c.get("/api/drafts/migrations", headers=operator).status_code == 403
        assert (
            c.post("/api/drafts/migrations", headers=operator, json={"operation_id": "x"}).status_code == 403
        )
        # CATALOG_BACKEND=disabled: geçiş listesi açıkça 'bağımlılık yok' der, boş liste uydurmaz.
        r = c.get("/api/drafts/migrations", headers=AYSE)
        assert r.status_code == 503 and r.json()["code"] == "dependency_unavailable"
        d = c.post(
            "/api/drafts",
            headers=AYSE,
            json={"application_id": "lab", "operation_id": "kefil_no", "title": "K"},
        ).json()
        bad = c.put(
            f"/api/drafts/{d['draft_id']}/screen",
            headers=AYSE,
            json={
                "expected_revision": 1,
                "session_id": "s",
                "screen_id": "x",
                "title": "X",
                "marker_candidate_ids": [],
                "css": "#a",
            },
        )
        assert bad.status_code == 422
        fields = {e["field"] for e in bad.json()["details"]["errors"]}
        assert {"marker_candidate_ids", "css"} <= fields
        verify = c.post(f"/api/drafts/{d['draft_id']}/screen/verify", headers=AYSE, json={"session_id": "s"})
        assert verify.status_code == 409 and verify.json()["code"] == "draft_not_ready"
