from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

LOCAL = ("127.0.0.1", 50000)
AYSE = {"X-Dev-User": "ayse", "X-Dev-Roles": "designer"}
MEHMET = {"X-Dev-User": "mehmet", "X-Dev-Roles": "designer"}


@pytest.fixture(autouse=True)
def _reset(lab: LabServer) -> None:
    lab.reset()


def _login(c: TestClient, sid: str, lab: LabServer) -> None:
    # Lab girişini oturumun tarayıcısında yapmak için yalnız navigate + gözlem API'si yeterli değil;
    # test bunun için sunucudaki handle'a doğrudan erişir (yalnız test kurulumu).
    import asyncio  # noqa: F401

    portal = c.portal  # type: ignore[attr-defined]
    service = c.app.state.container.sessions  # type: ignore[attr-defined]

    async def _do() -> None:
        handle = service.peek("ayse", sid)
        await handle.navigate(f"{lab.primary}/login")
        await handle.page.get_by_label("Kullanıcı adı").fill("ayse")
        await handle.page.get_by_role("button", name="Giriş yap").click()
        await handle.page.wait_for_url(f"{lab.primary}/")

    portal.call(_do)


@pytest.mark.browser
def test_observation_api_flow(make_env_file: EnvFileFactory, lab: LabServer) -> None:
    app = create_app(lab_settings(make_env_file, lab))
    with TestClient(app, client=LOCAL) as c:
        sid = c.post("/api/sessions", headers=AYSE).json()["session_id"]
        _login(c, sid, lab)
        base = f"/api/sessions/{sid}"

        nav = c.post(f"{base}/navigate", headers=AYSE, json={"url": f"{lab.primary}/pages/duplicates"})
        assert nav.status_code == 200 and nav.json()["url"].endswith("/pages/duplicates")
        blocked = c.post(f"{base}/navigate", headers=AYSE, json={"url": "http://127.0.0.1:1/"})
        assert blocked.status_code == 403 and blocked.json()["code"] == "navigation_not_allowed"

        observed = c.post(f"{base}/observe", headers=AYSE).json()
        assert observed["coverage"] == "complete"
        assert any(ctl["label"] == "Müşteri No" for ctl in observed["controls"])
        assert all("value" not in ctl for ctl in observed["controls"])

        amb = c.post(
            f"{base}/resolve", headers=AYSE, json={"kind": "textbox", "labels": ["Müşteri No"]}
        ).json()
        assert amb["outcome"] == "ambiguous" and len(amb["candidates"]) == 2
        res = c.post(
            f"{base}/resolve",
            headers=AYSE,
            json={"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"},
        ).json()
        assert res["outcome"] == "resolved" and res["snapshot_revision"]
        hl = c.post(f"{base}/candidates/{res['candidate_id']}/highlight", headers=AYSE)
        assert hl.status_code == 200 and "Kefil" in hl.json()["caption"]
        none = c.post(f"{base}/resolve", headers=AYSE, json={"kind": "textbox", "labels": ["Yok"]}).json()
        assert none["outcome"] == "unresolved" and none["reason"] == "not_found"
        bad = c.post(
            f"{base}/resolve", headers=AYSE, json={"kind": "textbox", "labels": ["A"], "xpath": "//x"}
        )
        assert bad.status_code == 422

        stale = c.post(f"{base}/candidates/{res['candidate_id']}/highlight", headers=AYSE)
        assert stale.status_code == 409 and stale.json()["details"]["reason"] == "snapshot_superseded"
        assert c.delete(f"{base}/highlight", headers=AYSE).status_code == 204

        assert c.post(f"{base}/picker/start", headers=AYSE).status_code == 204
        empty = c.get(f"{base}/picker/selection?wait_ms=100", headers=AYSE)
        assert empty.status_code == 200 and empty.json() == {"selected": False, "pick": None}
        assert c.post(f"{base}/picker/stop", headers=AYSE).status_code == 204

        for method, path in [
            ("post", "observe"),
            ("post", "resolve"),
            ("post", "picker/start"),
            ("get", "picker/selection"),
            ("delete", "highlight"),
        ]:
            kwargs = {"json": {"kind": "textbox", "labels": ["A"]}} if path == "resolve" else {}
            r = getattr(c, method)(f"{base}/{path}", headers=MEHMET, **kwargs)
            assert r.status_code == 404, (path, r.status_code)


def test_observation_requires_design_or_assist_capability(
    make_env_file: EnvFileFactory, lab: LabServer
) -> None:
    with TestClient(create_app(lab_settings(make_env_file, lab)), client=LOCAL) as c:
        r = c.post("/api/sessions/x/observe", headers={"X-Dev-User": "p", "X-Dev-Roles": "publisher"})
    assert r.status_code == 403
