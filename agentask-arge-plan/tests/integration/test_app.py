from __future__ import annotations

import json
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from agentask.bootstrap import build_container
from agentask.config import Settings, load_settings
from agentask.presentation.app import create_app
from tests.conftest import TEST_SIGNING_KEY, EnvFileFactory

LOCAL = ("127.0.0.1", 50000)
# İki uygulama davranışı örnek dosyadan bağımsız, açıkça verilir.
TWO_APPS = (
    '[{"id":"lab","name":"Yerel deney uygulaması","base_url":"http://127.0.0.1:8100/"},'
    '{"id":"lab_ikinci","name":"Yerel deney uygulaması (ikinci origin)","base_url":"http://127.0.0.1:8101/"}]'
)


@pytest.fixture
def client(make_env_file: EnvFileFactory) -> Iterator[TestClient]:
    # Katalog Mongo'su bu P0 testlerinin konusu değil; erişilemeyen Mongo ayrı testte doğrulanır.
    dev_settings = load_settings(
        make_env_file(CATALOG_BACKEND="disabled", AUTOMATION_APPLICATIONS_JSON=TWO_APPS)
    )
    with TestClient(create_app(dev_settings), client=LOCAL) as c:
        yield c


def test_health_live_and_ready(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    llm = next(c for c in ready.json()["components"] if c["name"] == "llm")
    assert llm == {"name": "llm", "required": False, "status": "disabled"}


def test_public_config_is_allowlisted_and_secret_free(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(
        make_env_file(
            MONGO_URI="mongodb://admin:mongo-pass-123@127.0.0.1:27017",
            LLM_API_KEY="llm-key-456",
            LLM_PASSWORD="llm-pass-789",
        )
    )
    with TestClient(create_app(settings), client=LOCAL) as c:
        body = c.get("/api/config/public").json()
        page = c.get("/").text
    assert set(body) == {"app_env", "timezone", "llm_available", "evidence_screenshots_enabled"}
    for secret in (TEST_SIGNING_KEY, "mongo-pass-123", "llm-key-456", "llm-pass-789", "mongodb://"):
        assert secret not in str(body)
        assert secret not in page


def test_me_returns_dev_principal_without_secrets(client: TestClient) -> None:
    body = client.get("/api/me", headers={"X-Dev-User": "ayse", "X-Dev-Roles": "designer"}).json()
    assert body["user_id"] == "ayse"
    assert body["roles"] == ["designer"]
    assert body["capabilities"] == ["design_catalog"]
    assert body["identity_source"] == "dev"


def test_non_loopback_client_is_refused_by_dev_identity(dev_settings: Settings) -> None:
    with TestClient(create_app(dev_settings), client=("10.0.0.5", 50000)) as c:
        response = c.get("/api/me")
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


@pytest.mark.parametrize(
    ("path", "roles", "status"),
    [
        ("/assistant", "operator", 200),
        ("/assistant", "designer", 403),
        ("/designer", "designer", 200),
        ("/designer", "operator", 403),
        ("/designer", "publisher", 403),
        ("/prototype/designer", "designer", 200),
        ("/prototype/designer", "operator", 403),
    ],
)
def test_pages_enforce_role_on_backend(client: TestClient, path: str, roles: str, status: int) -> None:
    response = client.get(path, headers={"X-Dev-Roles": roles})
    assert response.status_code == status
    if status == 200:
        assert "text/html" in response.headers["content-type"]


def test_index_page_renders_turkish_ui(client: TestClient) -> None:
    page = client.get("/").text
    assert "İşlem Asistanı" in page and "Katalog Tasarımcısı" in page
    assert '<html lang="tr">' in page


def test_error_envelope_shape_and_correlation_id(client: TestClient) -> None:
    response = client.get("/api/me", headers={"X-Dev-Roles": "admin", "X-Correlation-Id": "abcd1234-test"})
    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"code", "safe_message", "correlation_id", "retryable", "details"}
    assert body["correlation_id"] == "abcd1234-test" == response.headers["X-Correlation-Id"]
    assert body["retryable"] is False


def test_invalid_correlation_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Correlation-Id": "<script>"})
    assert response.headers["X-Correlation-Id"] != "<script>"


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json()["code"] == "http_404"


def test_unconfigured_identity_refuses_and_marks_not_ready(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(AUTH_MODE="unconfigured", DEV_AUTH_ENABLED="false"))
    assert build_container(settings).identity.source == "unconfigured"
    with TestClient(create_app(settings), client=LOCAL) as c:
        me = c.get("/api/me")
        ready = c.get("/health/ready")
        page = c.get("/designer")
    assert me.status_code == 503 and me.json()["code"] == "dependency_unavailable"
    assert ready.status_code == 503 and ready.json()["status"] == "not_ready"
    assert page.status_code == 503


def test_llm_enabled_is_available_without_startup_connection(make_env_file: EnvFileFactory) -> None:
    # P6: kurum içi httpx adapteri var. Açılışta modele bağlanılmaz (uç erişilemez olsa da readiness
    # bozulmaz).
    settings = load_settings(
        make_env_file(
            LLM_ENABLED="true",
            LLM_BASE_URL="http://127.0.0.1:1/v1",
            LLM_MODEL="m",
            CATALOG_BACKEND="disabled",
        )
    )
    with TestClient(create_app(settings), client=LOCAL) as c:
        assert c.get("/api/config/public").json()["llm_available"] is True
        assert c.get("/health/ready").status_code == 200


def test_security_headers_present(client: TestClient) -> None:
    headers = client.get("/health/live").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_target_lab_page_requires_designer_and_renders(client: TestClient) -> None:
    ok = client.get("/designer/targets", headers={"X-Dev-Roles": "designer"})
    assert ok.status_code == 200
    page = ok.text
    for text in (
        "Hedef Deneme",
        "Oturum aç",
        "Ekranı gözlemle",
        "Hedef ara",
        "Seçimi başlat",
        "target_lab.js",
    ):
        assert text in page
    assert client.get("/designer/targets", headers={"X-Dev-Roles": "operator"}).status_code == 403
    assert client.get("/static/target_lab.js").status_code == 200


def test_run_lab_page_renders(client: TestClient) -> None:
    ok = client.get("/designer/runs", headers={"X-Dev-Roles": "designer"})
    assert ok.status_code == 200
    for text in ("İşlem Deneme", "Adımı ekle", "Çalıştır", "İptal et", "Hedefi doğrula (P2)", "run_lab.js"):
        assert text in ok.text
    assert client.get("/designer/runs", headers={"X-Dev-Roles": "operator"}).status_code == 403


def test_ready_reports_unavailable_mongo_when_enabled(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(
        make_env_file(
            CATALOG_BACKEND="mongo",
            MONGO_URI="mongodb://127.0.0.1:1",
            MONGO_SERVER_SELECTION_TIMEOUT_MS="300",
        )
    )
    with TestClient(create_app(settings), client=LOCAL) as c:
        ready = c.get("/health/ready")
        publish = c.post("/api/drafts/draft-xxxxxx/publish", json={"request_id": "r"})
    assert ready.status_code == 503 and ready.json()["status"] == "not_ready"
    assert {"name": "catalog_mongo", "required": True, "status": "unavailable"} in ready.json()["components"]
    assert publish.status_code in {404, 503}


def test_publish_requires_publisher_role(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled"))
    with TestClient(create_app(settings), client=LOCAL) as c:
        r = c.post(
            "/api/drafts/draft-xxxxxx/publish", headers={"X-Dev-Roles": "designer"}, json={"request_id": "r"}
        )
        disabled = c.post(
            "/api/drafts/draft-xxxxxx/publish", headers={"X-Dev-Roles": "publisher"}, json={"request_id": "r"}
        )
    assert r.status_code == 403
    assert disabled.status_code == 503


def test_composite_api_disabled_by_default(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled"))
    with TestClient(create_app(settings), client=LOCAL) as c:
        page = c.get("/assistant", headers={"X-Dev-Roles": "operator"}).text
        r = c.post(
            "/api/assistant/composite/preview",
            headers={"X-Dev-Roles": "operator"},
            json={
                "application_id": "lab",
                "plan": {"nodes": [{"kind": "call_operation", "operation_id": "x", "arguments": {}}]},
            },
        )
    assert "Birleşik görev" not in page
    assert r.status_code == 422 and r.json()["details"]["reason"] == "composition_disabled"


def test_composite_section_visible_when_enabled(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled", COMPOSITION_ENABLED="true"))
    with TestClient(create_app(settings), client=LOCAL) as c:
        page = c.get("/assistant", headers={"X-Dev-Roles": "operator"}).text
    assert "Birleşik görev (deneysel" in page


# ---- uygulama listesi (AUTOMATION_APPLICATIONS_JSON) ------------------------


def test_assistant_api_requires_configured_application_and_keeps_role_check(client: TestClient) -> None:
    op = {"X-Dev-Roles": "operator"}
    missing = client.get("/api/assistant/catalog", headers=op)
    unknown = client.get("/api/assistant/catalog", params={"application_id": "bilinmeyen"}, headers=op)
    interp = client.post(
        "/api/assistant/interpret", headers=op, json={"application_id": "bilinmeyen", "prompt": "x"}
    )
    designer = client.get(
        "/api/assistant/catalog", params={"application_id": "lab"}, headers={"X-Dev-Roles": "designer"}
    )
    known = client.get("/api/assistant/catalog", params={"application_id": "lab_ikinci"}, headers=op)
    assert missing.status_code == 422
    assert unknown.status_code == 422 and unknown.json()["code"] == "application_not_configured"
    assert interp.status_code == 422 and interp.json()["code"] == "application_not_configured"
    # Listede olmak yetki değildir: designer rolü İşlem Asistanı'nı kullanamaz.
    assert designer.status_code == 403
    # Bilinen uygulama kapsam kontrolünü geçer; bu testte katalog kapalı olduğu için bağımlılık hatası döner.
    assert known.status_code == 503 and known.json()["code"] == "dependency_unavailable"


def test_pages_receive_only_allowlisted_application_fields(client: TestClient) -> None:
    assistant = client.get("/assistant", headers={"X-Dev-Roles": "operator"}).text
    prototype = client.get("/prototype/designer", headers={"X-Dev-Roles": "designer"}).text
    for page in (assistant, prototype):
        assert "mongodb://" not in page and "SESSION_SIGNING_KEY" not in page
    assert "Yerel deney uygulaması (ikinci origin)" in assistant
    assistant_apps = json.loads(re.search(r'id="as-apps">(.*?)</script>', assistant, re.S).group(1))  # type: ignore[union-attr]
    prototype_apps = json.loads(re.search(r'id="pd-apps">(.*?)</script>', prototype, re.S).group(1))  # type: ignore[union-attr]
    assert [sorted(a) for a in assistant_apps] == [["base_url", "id", "name"]] * len(assistant_apps)
    # Gerçek oturum modunda uygulamayı açmak için prototip de başlangıç adresini alır (aynı allowlist).
    assert [sorted(a) for a in prototype_apps] == [["base_url", "id", "name"]] * len(prototype_apps)


def test_empty_application_list_shows_clear_empty_state(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled", AUTOMATION_APPLICATIONS_JSON="[]"))
    with TestClient(create_app(settings), client=LOCAL) as c:
        assistant = c.get("/assistant", headers={"X-Dev-Roles": "operator"}).text
        prototype = c.get("/prototype/designer", headers={"X-Dev-Roles": "designer"}).text
        refused = c.get(
            "/api/assistant/catalog", params={"application_id": "lab"}, headers={"X-Dev-Roles": "operator"}
        )
    assert "Yapılandırılmış uygulama yok" in assistant
    assert 'id="pd-apps">[]<' in prototype
    assert refused.status_code == 422 and refused.json()["code"] == "application_not_configured"
