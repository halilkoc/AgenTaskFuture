"""Kalıcı taslak: mevcut taslak deposu (LocalFileDraftRepository, DRAFT_DIRECTORY) uygulama yeniden başlayınca
korunur; eşzamanlı güncellemede revizyon kontrolü (409) üzerine yazmayı engeller; başka kullanıcı erişemez."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from agentask.config import load_settings
from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory

LOCAL = ("127.0.0.1", 50000)
AYSE = {"X-Dev-User": "ayse", "X-Dev-Roles": "designer"}
MEHMET = {"X-Dev-User": "mehmet", "X-Dev-Roles": "designer"}


def test_draft_survives_restart_and_rejects_stale_revision(
    make_env_file: EnvFileFactory, tmp_path: Path
) -> None:
    env = make_env_file(CATALOG_BACKEND="disabled", DRAFT_DIRECTORY=str(tmp_path / "drafts"))
    with TestClient(create_app(load_settings(env)), client=LOCAL) as c:
        created = c.post(
            "/api/drafts",
            headers=AYSE,
            json={"application_id": "lab", "operation_id": "kefil_no_ab12", "title": "Kefil no gir"},
        )
        assert created.status_code == 201, created.text
        draft_id, revision = created.json()["draft_id"], created.json()["revision"]
        added = c.post(
            f"/api/drafts/{draft_id}/parameters",
            headers=AYSE,
            json={
                "expected_revision": revision,
                "name": "kefil_musteri_no",
                "title": "Kefilin müşteri numarası nedir?",
                "max_length": 200,
                "source": "user_input",
            },
        )
        assert added.status_code == 200, added.text
        saved_revision = added.json()["revision"]

    # Yeniden başlatma: aynı DRAFT_DIRECTORY ile yeni uygulama örneği taslağı aynen okur.
    with TestClient(create_app(load_settings(env)), client=LOCAL) as c:
        again = c.get(f"/api/drafts/{draft_id}", headers=AYSE)
        assert again.status_code == 200
        assert again.json()["revision"] == saved_revision
        assert [p["title"] for p in again.json()["parameters"]] == ["Kefilin müşteri numarası nedir?"]
        # Eski revizyonla güncelleme üzerine yazmaz.
        stale = c.patch(
            f"/api/drafts/{draft_id}", headers=AYSE, json={"expected_revision": revision, "title": "x"}
        )
        assert stale.status_code == 409 and stale.json()["code"] == "draft_conflict"
        assert c.get(f"/api/drafts/{draft_id}", headers=AYSE).json()["title"] == "Kefil no gir"
        # Başka kullanıcının taslağı görünmez.
        assert c.get(f"/api/drafts/{draft_id}", headers=MEHMET).status_code == 404
        assert c.get("/api/drafts", headers=MEHMET).json() == []


def test_artifact_download_is_owner_only_and_never_presents_missing_content(
    make_env_file: EnvFileFactory, tmp_path: Path
) -> None:
    env = make_env_file(CATALOG_BACKEND="disabled", ARTIFACT_DIRECTORY=str(tmp_path / "artifacts"))
    app = create_app(load_settings(env))
    with TestClient(app, client=LOCAL) as c:
        ref = asyncio.run(
            app.state.container.artifacts.store("ayse", "evidence", "text/plain", b"sonuc: basarili")
        )
        own = c.get(f"/api/artifacts/{ref.artifact_id}", headers=AYSE)
        assert own.status_code == 200 and own.content == b"sonuc: basarili"
        assert own.headers["content-type"].startswith("text/plain")
        assert own.headers["cache-control"] == "no-store"
        assert c.get(f"/api/artifacts/{ref.artifact_id}", headers=MEHMET).status_code == 404
        assert c.get("/api/artifacts/art_" + "0" * 20, headers=AYSE).status_code == 404
        assert c.get("/api/artifacts/..%2Fsecret", headers=AYSE).status_code in {404, 422}
        # İçerik depodan kaybolursa var gibi gösterilmez.
        (tmp_path / "artifacts" / "objects" / ref.artifact_id).unlink()
        missing = c.get(f"/api/artifacts/{ref.artifact_id}", headers=AYSE)
        assert missing.status_code == 503 and missing.json()["code"] == "artifact_missing"


def _policy(make_env_file: EnvFileFactory, tmp_path: Path, **env: str | None) -> dict[str, object]:
    settings = load_settings(
        make_env_file(CATALOG_BACKEND="disabled", DRAFT_DIRECTORY=str(tmp_path / "drafts"), **env)
    )
    with TestClient(create_app(settings), client=LOCAL) as c:
        d = c.post(
            "/api/drafts",
            json={"application_id": "lab", "operation_id": "kefil_no", "title": "Kefil no"},
            headers=AYSE,
        ).json()
        return c.get(f"/api/drafts/{d['draft_id']}", headers=AYSE).json()["fresh_test_entry"]


def test_fresh_test_entry_policy_is_lab_only(make_env_file: EnvFileFactory, tmp_path: Path) -> None:
    """Otomatik giriş yalnız LAB_PRIMARY_ORIGIN tanımlı ve uygulama aynı origin'deyse; gerçekte yok."""
    assert _policy(make_env_file, tmp_path) == {"mode": "lab_autologin", "origin": "http://127.0.0.1:8100"}
    real = _policy(make_env_file, tmp_path / "r", LAB_PRIMARY_ORIGIN=None, LAB_SECONDARY_ORIGIN=None)
    assert real["mode"] == "url" and "LAB_PRIMARY_ORIGIN" in str(real["reason"])
    other = _policy(
        make_env_file,
        tmp_path / "o",
        TARGET_ALLOWED_ORIGINS='["http://127.0.0.1:8100","http://127.0.0.1:8101","http://127.0.0.1:9000"]',
        TARGET_BASE_URL="http://127.0.0.1:9000",
        AUTOMATION_APPLICATIONS_JSON='[{"id":"lab","name":"Başka","base_url":"http://127.0.0.1:9000/"}]',
    )
    assert other["mode"] == "url" and "aynı origin" in str(other["reason"])


def test_pages_are_not_cached_and_static_revalidates(make_env_file: EnvFileFactory, tmp_path: Path) -> None:
    env = make_env_file(CATALOG_BACKEND="disabled", DRAFT_DIRECTORY=str(tmp_path / "drafts"))
    with TestClient(create_app(load_settings(env)), client=LOCAL) as c:
        page = c.get("/prototype/designer", headers=AYSE)
        assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
        js = c.get("/static/prototype_designer.js")
        assert js.headers["cache-control"] == "no-cache" and js.headers.get("etag")
