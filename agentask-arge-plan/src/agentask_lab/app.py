"""Deney uygulaması HTTP katmanı. Birincil ve ikincil origin aynı uygulamayla servis edilir."""

from __future__ import annotations

import asyncio
import ipaddress
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from agentask_lab.state import LabState, ScenarioUpdate

SESSION_COOKIE = "lab_sid"
CASE_ID = "C-1001"
BRANCHES = [("kadikoy", "Kadıköy"), ("besiktas", "Beşiktaş"), ("cankaya", "Çankaya"), ("konak", "Konak")]
PRODUCTS = ["Bireysel Kart", "Ticari Kart", "Ek Kart"]
STATUSES = ["Yeni", "İncelemede", "Onay Bekliyor", "Tamamlandı"]
CUSTOMERS = ["Ayşe Yılmaz", "Mehmet Demir", "Zeynep Kaya", "Ali Çelik", "Elif Şahin", "Can Öztürk"]
_DELAYED_PREFIXES = ("/pages/", "/frames/", "/lab-api/")
_HERE = Path(__file__).parent


class IdFactory:
    """Her render'da yeni, anlamsız HTML kimlikleri (Pega'daki dinamik id davranışı)."""

    def __call__(self) -> str:
        return f"pz{secrets.token_hex(4)}"


class SubmitRequest(BaseModel):
    customer_no: str = Field(min_length=1, max_length=40)
    amount: str = Field(min_length=1, max_length=40)
    document_no: str = Field(min_length=1, max_length=40)


class NoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    client_request_id: str = Field(min_length=8, max_length=64)


def _is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _row(index: int) -> dict[str, str]:
    return {
        "key": f"B-{1000 + index}",
        "customer": CUSTOMERS[index % len(CUSTOMERS)],
        "status": STATUSES[index % len(STATUSES)],
    }


class LoginRequired(Exception):
    def __init__(self, api: bool) -> None:
        self.api = api


def _state(request: Request) -> LabState:
    state: LabState = request.app.state.lab
    return state


def page_user(request: Request) -> str:
    user = _state(request).user_for(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise LoginRequired(api=False)
    return user


def api_user(request: Request) -> str:
    user = _state(request).user_for(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise LoginRequired(api=True)
    return user


def loopback_only(request: Request) -> None:
    if not _is_loopback(request):
        raise HTTPException(403)


PageUser = Annotated[str, Depends(page_user)]
ApiUser = Annotated[str, Depends(api_user)]
CONTROL = [Depends(loopback_only)]


async def _login_required(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, LoginRequired)
    had_cookie = SESSION_COOKIE in request.cookies
    if exc.api:
        return JSONResponse({"error": "session_expired" if had_cookie else "login_required"}, 401)
    reason = "expired" if had_cookie else "required"
    return RedirectResponse(f"/login?reason={reason}&next={request.url.path}", status_code=303)


def create_lab_app(state: LabState, primary_origin: str, secondary_origin: str) -> FastAPI:
    app = FastAPI(title="AgenTask Deney Uygulaması", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.lab = state
    app.add_exception_handler(LoginRequired, _login_required)
    templates = Jinja2Templates(directory=str(_HERE / "templates"))
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    def render(request: Request, name: str, **context: Any) -> HTMLResponse:
        base = {
            "new_id": IdFactory(),
            "primary": primary_origin,
            "secondary": secondary_origin,
            "scenario": state.scenario,
            "user": state.user_for(request.cookies.get(SESSION_COOKIE)),
        }
        return templates.TemplateResponse(request, name, base | context)

    @app.middleware("http")
    async def delay(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path.startswith(_DELAYED_PREFIXES) and state.scenario.delay_ms:
            await asyncio.sleep(state.scenario.delay_ms / 1000)
        return await call_next(request)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, reason: str | None = None, next: str = "/") -> HTMLResponse:
        return render(request, "login.html", reason=reason, next=next if next.startswith("/") else "/")

    @app.post("/login")
    async def login(
        user: Annotated[str, Form(min_length=1, max_length=64)], next: str = Form("/")
    ) -> Response:
        target = next if next.startswith("/") and not next.startswith("//") else "/"
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(SESSION_COOKIE, state.login(user.strip()), httponly=True, samesite="lax")
        return response

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "index.html")

    # ---- senaryo sayfaları ----------------------------------------------------

    @app.get("/pages/frames", response_class=HTMLResponse)
    async def frames(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "frames.html")

    @app.get("/frames/level1", response_class=HTMLResponse)
    async def frame_level1(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "frame_level1.html")

    @app.get("/frames/level2", response_class=HTMLResponse)
    async def frame_level2(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "frame_level2.html")

    @app.get("/frames/late", response_class=HTMLResponse)
    async def frame_late(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "frame_late.html")

    @app.get("/frames/cross", response_class=HTMLResponse)
    async def frame_cross(request: Request) -> HTMLResponse:
        # İkincil origin'deki "dış sistem"; kendi oturumu yoktur.
        return render(request, "frame_cross.html")

    def parties(request: Request, layout: str | None) -> HTMLResponse:
        layouts = {"standard", "similar", "duplicate_guarantor", "with_change_note"}
        chosen = layout if layout in layouts else None
        return render(request, "duplicates.html", layout=chosen or state.scenario.party_layout)

    @app.get("/pages/duplicates", response_class=HTMLResponse)
    async def duplicates(request: Request, user: PageUser, layout: str | None = None) -> HTMLResponse:
        return parties(request, layout)

    @app.get("/cases/{case_id}/parties", response_class=HTMLResponse)
    async def case_parties(request: Request, case_id: str, user: PageUser) -> HTMLResponse:
        # Aynı ekran farklı (vaka bazlı) adreste: ekran tanıma URL'ye dayanmamalı.
        return parties(request, None)

    @app.get("/pages/dropdowns", response_class=HTMLResponse)
    async def dropdowns(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "dropdowns.html", branches=BRANCHES, products=PRODUCTS)

    @app.get("/pages/windows", response_class=HTMLResponse)
    async def windows(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "windows.html")

    @app.get("/pages/window-child", response_class=HTMLResponse)
    async def window_child(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "window_child.html")

    @app.get("/pages/optional-modal", response_class=HTMLResponse)
    async def optional_modal(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "optional_modal.html")

    @app.get("/pages/controls", response_class=HTMLResponse)
    async def controls(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "controls.html")

    @app.get("/pages/records", response_class=HTMLResponse)
    async def records(request: Request, user: PageUser, page: int = 1) -> HTMLResponse:
        keys = [f"R-{1000 + n}" for n in range(1, 10)]
        if state.scenario.selection_catalog == "changed":
            keys.reverse()  # satır sırası değişir; iş anahtarı değişmez
        if state.scenario.selection_redraw:
            keys[4] = keys[3]  # yinelenen iş anahtarı
        size, pages = 3, 3
        current = max(1, min(page, pages))
        return render(
            request,
            "records.html",
            keys=keys[(current - 1) * size : current * size],
            page=current,
            pages=pages,
        )

    @app.get("/pages/records/{key}", response_class=HTMLResponse)
    async def record_detail(request: Request, user: PageUser, key: str) -> HTMLResponse:
        return render(request, "record_detail.html", key=key)

    @app.get("/pages/transitions", response_class=HTMLResponse)
    async def transitions(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "transitions.html")

    @app.get("/pages/transition-target", response_class=HTMLResponse)
    async def transition_target(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "transition_target.html")

    @app.get("/pages/selections", response_class=HTMLResponse)
    async def selections(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "selections.html", branches=BRANCHES)

    @app.get("/frames/selection-outer", response_class=HTMLResponse)
    async def selection_outer(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "selection_frame_outer.html")

    @app.get("/frames/selection-inner", response_class=HTMLResponse)
    async def selection_inner(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "selection_frame_inner.html")

    @app.post("/lab-api/selection")
    async def selection_commit(body: dict[str, str], user: ApiUser) -> dict[str, str]:
        state.selection_commits.append(body.get("value", ""))
        return {"outcome": state.scenario.selection_outcome}

    @app.get("/pages/table-paged", response_class=HTMLResponse)
    async def table_paged(
        request: Request, user: PageUser, page: Annotated[int, Query(ge=1)] = 1
    ) -> HTMLResponse:
        size, total = state.scenario.page_size, state.scenario.table_rows
        page_count = max(1, -(-total // size))
        page = min(page, page_count)
        start = (page - 1) * size
        rows = [_row(i) for i in range(start, min(start + size, total))]
        return render(request, "table_paged.html", rows=rows, page=page, page_count=page_count)

    @app.get("/pages/table-scroll", response_class=HTMLResponse)
    async def table_scroll(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "table_scroll.html")

    @app.get("/lab-api/rows")
    async def rows(
        user: ApiUser,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 15,
    ) -> dict[str, Any]:
        total = state.scenario.table_rows
        items = [_row(i) for i in range(offset, min(offset + limit, total))]
        return {"rows": items, "total": total, "done": offset + len(items) >= total}

    @app.get("/lab-api/redirect-out")
    async def redirect_out(user: ApiUser, to: str) -> Response:
        # Sunucu tarafı yönlendirme senaryosu; açık yönlendirme olmasın diye yalnız loopback http hedef.
        parts = urlsplit(to)
        if parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"}:
            raise HTTPException(400)
        return RedirectResponse(to, status_code=302)

    @app.get("/pages/sensitive", response_class=HTMLResponse)
    async def sensitive(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "sensitive.html")

    @app.get("/pages/heavy", response_class=HTMLResponse)
    async def heavy(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "heavy.html", count=state.scenario.heavy_fields)

    @app.get("/pages/popups", response_class=HTMLResponse)
    async def popups(
        request: Request,
        user: PageUser,
        modal: str | None = None,
        two: int = 0,
        overlay: int | None = None,
        ticker: int = 0,
        cover: int = 0,
    ) -> HTMLResponse:
        # overlay: kaplayan katman; 0 ise kalıcı, >0 ise o kadar ms sonra kalkar.
        return render(
            request,
            "popups.html",
            modal_open=modal == "open",
            decoy=modal == "decoy",
            two=bool(two),
            overlay=overlay,
            ticker=bool(ticker),
            cover=bool(cover),
        )

    @app.get("/pages/delayed", response_class=HTMLResponse)
    async def delayed(request: Request, user: PageUser) -> HTMLResponse:
        return render(request, "delayed.html")

    @app.get("/pages/note-form", response_class=HTMLResponse)
    async def note_form(request: Request, user: PageUser) -> HTMLResponse:
        notes = [c for c in state.commits if c.case_id == CASE_ID]
        return render(request, "note_form.html", case_id=CASE_ID, notes=notes)

    @app.post("/lab-api/cases/{case_id}/notes")
    async def add_note(case_id: str, body: NoteRequest, user: ApiUser) -> dict[str, Any]:
        if case_id != CASE_ID:
            raise HTTPException(404)
        commit = state.commit_note(case_id, body.text, body.client_request_id, user)
        if state.scenario.lose_next_commit_response:
            # İşlem kaydedildi; yanıt istemciye ulaşmıyor (istemci zaman aşımına düşer).
            state.apply(ScenarioUpdate(lose_next_commit_response=False))
            await asyncio.sleep(state.scenario.lost_response_hang_ms / 1000)
            raise HTTPException(504)
        return {"note_no": commit.note_no}

    # ---- R4: çok ekranlı başvuru sihirbazı (yalnız test ikamesi) ----------------

    def base_context(request: Request) -> dict[str, Any]:
        return {
            "new_id": IdFactory(),
            "primary": primary_origin,
            "secondary": secondary_origin,
            "scenario": state.scenario,
            "user": state.user_for(request.cookies.get(SESSION_COOKIE)),
        }

    def collateral_context(case_id: str, variant: str) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "shown_case": f"{case_id}-B" if variant == "other_case" else case_id,
            "duplicate": variant == "duplicate",
            "applications": [a for a in state.applications if a.case_id == case_id],
        }

    @app.get("/wizard/{case_id}", response_class=HTMLResponse)
    async def wizard_customer(request: Request, case_id: str, user: PageUser) -> HTMLResponse:
        return render(request, "wizard_customer.html", case_id=case_id)

    @app.post("/lab-api/wizard/{case_id}/advance")
    async def wizard_advance(request: Request, case_id: str, user: ApiUser) -> dict[str, Any]:
        # Tetikleme sayacı: geçiş düğmesine kaç kez basıldığı (tekrar tetikleme testleri).
        state.wizard_advances[case_id] = state.wizard_advances.get(case_id, 0) + 1
        if state.scenario.wizard_delay_ms:
            await asyncio.sleep(state.scenario.wizard_delay_ms / 1000)
        target = state.scenario.wizard_target
        if target == "none":
            return {"html": None, "url": None}
        if target == "unexpected":
            body = templates.get_template("wizard_rejected_body.html").render(
                {**base_context(request), "case_id": case_id}
            )
            return {"html": body, "url": f"/wizard/{case_id}/rejected"}
        body = templates.get_template("wizard_collateral_body.html").render(
            {**base_context(request), **collateral_context(case_id, target)}
        )
        return {"html": body, "url": f"/wizard/{case_id}/collateral"}

    @app.get("/wizard/{case_id}/collateral", response_class=HTMLResponse)
    async def wizard_collateral(request: Request, case_id: str, user: PageUser) -> HTMLResponse:
        return render(request, "wizard_collateral.html", **collateral_context(case_id, "collateral"))

    @app.get("/wizard/{case_id}/rejected", response_class=HTMLResponse)
    async def wizard_rejected(request: Request, case_id: str, user: PageUser) -> HTMLResponse:
        return render(request, "wizard_rejected.html", case_id=case_id)

    @app.get("/wizard/{case_id}/documents", response_class=HTMLResponse)
    async def wizard_documents(request: Request, case_id: str, user: PageUser) -> HTMLResponse:
        return render(request, "wizard_documents.html", case_id=case_id)

    @app.post("/lab-api/wizard/{case_id}/submit")
    async def wizard_submit(case_id: str, body: SubmitRequest, user: ApiUser) -> dict[str, Any]:
        application = state.submit_application(case_id, body.customer_no, body.amount, body.document_no, user)
        if state.scenario.lose_next_submit_response:
            # Gönderim kaydedildi; yanıt istemciye ulaşmıyor (istemci zaman aşımına düşer, gezinme olmaz).
            state.apply(ScenarioUpdate(lose_next_submit_response=False))
            await asyncio.sleep(state.scenario.lost_response_hang_ms / 1000)
            raise HTTPException(504)
        return {"application_no": application.application_no}

    @app.get("/wizard/{case_id}/summary", response_class=HTMLResponse)
    async def wizard_summary(request: Request, case_id: str, user: PageUser, no: int = 0) -> HTMLResponse:
        apps = [a for a in state.applications if a.case_id == case_id]
        return render(request, "wizard_summary.html", case_id=case_id, number=no, applications=apps)

    # ---- kontrol API (yalnızca loopback) --------------------------------------

    @app.get("/__lab", response_class=HTMLResponse, dependencies=CONTROL)
    async def control_page(request: Request) -> HTMLResponse:
        return render(request, "control.html")

    @app.get("/__lab/autologin", dependencies=CONTROL)
    async def autologin(
        user: Annotated[str, Query(min_length=1, max_length=64)], next: str = "/"
    ) -> Response:
        # Headless/API demoları için; yalnız loopback istemci. Açık yönlendirme yok.
        target = next if next.startswith("/") and not next.startswith(("//", "/\\")) else "/"
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(SESSION_COOKIE, state.login(user.strip()), httponly=True, samesite="lax")
        return response

    @app.get("/__lab/state", dependencies=CONTROL)
    async def get_state() -> dict[str, Any]:
        return {
            "scenario": state.scenario.model_dump(),
            "commits": [c.model_dump(mode="json") for c in state.commits],
            "applications": [a.model_dump(mode="json") for a in state.applications],
            "wizard_advances": dict(state.wizard_advances),
            "selection_commits": list(state.selection_commits),
            "active_sessions": state.active_sessions,
        }

    @app.put("/__lab/scenario", dependencies=CONTROL)
    async def put_scenario(update: ScenarioUpdate) -> dict[str, Any]:
        return state.apply(update).model_dump()

    @app.post("/__lab/sessions/expire", dependencies=CONTROL)
    async def expire() -> dict[str, int]:
        return {"expired": state.expire_sessions()}

    @app.post("/__lab/reset", dependencies=CONTROL)
    async def reset() -> dict[str, str]:
        state.reset()
        return {"status": "reset"}

    return app
