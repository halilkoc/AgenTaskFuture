"""Katalog Tasarımcısı uçları (docs/09 drafts). Yalnız taslak deposuna yazar; yayın P5'tedir."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from agentask.application.errors import Forbidden
from agentask.domain.catalog import OperationDraft
from agentask.domain.identity import Capability, Principal
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


async def _designer(principal: PrincipalDep) -> Principal:
    if not principal.can(Capability.DESIGN_CATALOG):
        raise Forbidden()
    return principal


Designer = Annotated[Principal, Depends(_designer)]


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateDraft(_Req):
    application_id: str
    operation_id: str
    title: str
    description: str = ""
    intent_phrases: list[str] = Field(default_factory=list)


class Revisioned(_Req):
    expected_revision: int


class PatchDraft(Revisioned):
    title: str | None = None
    description: str | None = None
    intent_phrases: list[str] | None = None


class AddParameter(Revisioned):
    name: str
    title: str
    max_length: int
    required: bool = True
    source: str
    constant: str | None = None
    secret_ref: str | None = None
    prior_step: int | None = None
    prior_output: str | None = None
    choices: list[dict[str, str | None]] | None = Field(default=None, max_length=200)
    multiple: bool = False
    file: bool = False


class AddStep(Revisioned):
    intent_text: str = Field(min_length=1, max_length=500)


class Propose(_Req):
    session_id: str


class SelectTarget(Revisioned):
    session_id: str
    candidate_id: str
    element_id: str
    meaning: str
    provenance: Literal["observed", "human_verified"] = "observed"
    include_region: bool = True
    in_found_row: bool = False


class PatchStep(Revisioned):
    op: str | None = None
    value_template: str | None = None
    choice_template: str | None = None
    key_template: str | None = None
    navigation: Literal["none", "paged", "scroll"] | None = None
    action_id: str | None = None
    action_params: dict[str, str] | None = None
    success_check: Literal["auto", "none"] | None = None
    next_labels: list[str] | None = Field(default=None, max_length=5)
    end_text: str | None = Field(default=None, max_length=200)
    in_found_row: bool | None = None
    choice_value: str | None = Field(default=None, max_length=200)
    choice_effect: Literal["ui_local", "unknown"] | None = None
    checked: bool | None = None
    autocomplete: bool | None = None
    choice_set: list[str] | None = Field(default=None, min_length=1, max_length=50)
    date_format: Literal["DD.MM.YYYY", "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"] | None = None
    file_types: list[str] | None = Field(default=None, min_length=1, max_length=4)
    search_text: str | None = Field(default=None, min_length=1, max_length=200)
    result_text: str | None = Field(default=None, max_length=300)
    standard_text: str | None = None
    screen_id: str | None = Field(default=None, max_length=61)
    transition_id: str | None = Field(default=None, max_length=61)


class ContextIn(_Req):
    target: dict[str, Any]
    value_template: str = Field(min_length=1, max_length=200)


class DefineTransition(Revisioned):
    transition_id: str
    from_screen: str
    to_screen: str
    trigger_kind: Literal["control", "approved_action", "choice", "window_return"]
    window: Literal["new"] | None = None
    window_origin: str | None = Field(default=None, max_length=200)
    close: bool = True
    session_id: str | None = None
    trigger_candidate_id: str | None = None
    trigger_in_found_row: bool = False
    timeout_ms: int = Field(default=10_000, ge=500, le=60_000)
    completion: list[ContextIn] = Field(default_factory=list, max_length=5)


class StartContext(Revisioned):
    checks: list[ContextIn] = Field(default_factory=list, max_length=5)


class OptionalDialogIn(_Req):
    dialog_name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=300)
    button_label: str = Field(min_length=1, max_length=100)
    confirm_no_data: Literal[True]  # veri etkili pencere yalnız onaylı işlem akışından yönetilir


class OptionalDialogs(Revisioned):
    dialogs: list[OptionalDialogIn] = Field(default_factory=list, max_length=10)


class ConfirmStep(Revisioned):
    meaning: bool
    target: bool
    effect: bool
    params: bool


class Trial(Revisioned):
    session_id: str
    args: dict[str, str] = Field(default_factory=dict)
    acknowledge_effect: bool = False


class RegionIn(_Req):
    name: str = Field(min_length=1, max_length=200)
    region_id: str | None = Field(default=None, max_length=61)


class DefineScreen(Revisioned):
    session_id: str
    screen_id: str
    title: str
    marker_candidate_ids: list[str] = Field(min_length=1, max_length=10)
    regions: list[RegionIn] = Field(default_factory=list, max_length=20)
    absent_markers: list[dict[str, Any]] = Field(default_factory=list, max_length=10)


class VerifyScreen(_Req):
    session_id: str
    screen_id: str | None = None


class StartMigration(_Req):
    operation_id: str = Field(min_length=1, max_length=61)
    application_id: str | None = Field(default=None, min_length=1, max_length=61)


class FreshTest(Revisioned):
    args: dict[str, str] = Field(default_factory=dict)
    entry_url: str = Field(min_length=1, max_length=2048)
    # Lab'da elle giriş denemek için. Gerçek uygulamada sunucu her zaman elle giriş kullanır.
    manual_login: bool = False


def _fresh_test_entry(c: Any, application_id: str) -> dict[str, Any]:
    """Yeni oturum testinin başlangıç adresi politikası (sunucu kararı). Otomatik giriş yalnız yerel deney
    uygulamasında: LAB_PRIMARY_ORIGIN tanımlı VE taslağın uygulama adresi aynı origin'de. Gerçek uygulamalarda
    otomatik giriş yoktur; tam adres istenir ve neden açıklanır."""
    lab = c.settings.lab_primary_origin
    app = c.applications.get(application_id)
    if lab and app is not None and app.origin == lab:
        return {"mode": "lab_autologin", "origin": lab}
    if app is None:
        reason = "Taslağın uygulaması AUTOMATION_APPLICATIONS_JSON içinde yok."
    elif not lab:
        reason = "Deney uygulaması ayarı (LAB_PRIMARY_ORIGIN) tanımlı değil; bu bir gerçek uygulama sayılır."
    else:
        reason = "Uygulama adresi deney uygulamasıyla (LAB_PRIMARY_ORIGIN) aynı origin'de değil."
    return {"mode": "url", "reason": reason}


def _out(c: Any, draft: OperationDraft) -> dict[str, Any]:
    actions = c.designer.actions
    data = draft.model_dump(mode="json")
    data["content_hash"] = draft.content_hash()
    data["issues"] = draft.validation_issues(actions)
    data["fresh_test_failure"] = c.designer.fresh_test_failure(draft)
    data["fresh_test_entry"] = _fresh_test_entry(c, draft.application_id)
    data["fresh_wait"] = c.designer.fresh_wait(draft)
    for step, raw in zip(draft.steps, data["steps"], strict=True):
        raw["effect"] = step.effect(actions)
        raw["changes_screen"] = step.changes_screen
        raw["expected_screen"] = draft.step_screen_id(step)
    return data


@router.get("/migrations")
async def migration_candidates(
    p: Designer, c: ContainerDep, application_id: Annotated[str | None, Query()] = None
) -> dict[str, Any]:
    """Etkin yayında ekran tanımı olmayan (geçiş gerektiren) işlemler. Salt okunur."""
    return await c.designer.migration_candidates(application_id or c.settings.catalog_application_id)


@router.post("/migrations", status_code=201)
async def start_migration(body: StartMigration, p: Designer, c: ContainerDep) -> dict[str, Any]:
    """Eski yayından geçiş taslağı açar; yayımlanmış kayıtlar değişmez."""
    application = body.application_id or c.settings.catalog_application_id
    return _out(c, await c.designer.start_migration(p.user_id, application, body.operation_id))


@router.post("", status_code=201)
async def create(body: CreateDraft, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return _out(c, c.designer.create_draft(p.user_id, **body.model_dump()))


@router.get("")
async def list_drafts(p: Designer, c: ContainerDep) -> list[dict[str, Any]]:
    return [
        {
            "draft_id": d.draft_id,
            "operation_id": d.operation_id,
            "title": d.title,
            "revision": d.revision,
            "steps": len(d.steps),
            "ready": d.is_ready_for_review,
            "screen_id": d.screen.screen_id if d.screen else None,
            "migrated_from": d.migrated_from.model_dump() if d.migrated_from else None,
            "updated_at": d.updated_at.isoformat(),
        }
        for d in c.designer.list_drafts(p.user_id)
    ]


class SetCall(Revisioned):
    operation_id: str = Field(min_length=1, max_length=61)
    revision: int = Field(ge=1)
    arguments: dict[str, str] = Field(default_factory=dict)


@router.get("/{draft_id}/components")
async def available_components(draft_id: str, p: Designer, c: ContainerDep) -> dict[str, Any]:
    """E: etkin yayındaki çağrılabilir işlemler (bileşen adayları) ve sözleşme özetleri."""
    return {"components": await c.designer.available_components(p.user_id, draft_id)}


@router.get("/{draft_id}/component-updates")
async def component_updates(draft_id: str, p: Designer, c: ContainerDep) -> dict[str, Any]:
    """E: pinli bileşenlerin daha yeni revizyonları ve yükseltme etkisi (salt okunur)."""
    return {"updates": await c.designer.component_updates(p.user_id, draft_id)}


@router.put("/{draft_id}/steps/{step_id}/call")
async def set_call(
    draft_id: str, step_id: str, body: SetCall, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    """E: adımı yayımlanmış işlemin belirli revizyonuna pinli bileşen çağrısı yapar."""
    draft = await c.designer.set_call(
        p.user_id,
        draft_id,
        body.expected_revision,
        step_id,
        operation_id=body.operation_id,
        component_revision=body.revision,
        arguments=body.arguments,
    )
    return _out(c, draft)


@router.get("/{draft_id}")
async def get_draft(draft_id: str, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return _out(c, c.designer.get(p.user_id, draft_id))


@router.patch("/{draft_id}")
async def patch_draft(draft_id: str, body: PatchDraft, p: Designer, c: ContainerDep) -> dict[str, Any]:
    fields = body.model_dump(exclude={"expected_revision"}, exclude_none=True)
    return _out(c, c.designer.update_meta(p.user_id, draft_id, body.expected_revision, **fields))


@router.post("/{draft_id}/parameters")
async def add_parameter(draft_id: str, body: AddParameter, p: Designer, c: ContainerDep) -> dict[str, Any]:
    fields = body.model_dump(exclude={"expected_revision"}, exclude_none=True)
    return _out(c, c.designer.add_parameter(p.user_id, draft_id, body.expected_revision, **fields))


@router.delete("/{draft_id}/parameters/{name}")
async def remove_parameter(
    draft_id: str, name: str, p: Designer, c: ContainerDep, expected_revision: Annotated[int, Query()]
) -> dict[str, Any]:
    return _out(c, c.designer.remove_parameter(p.user_id, draft_id, expected_revision, name))


@router.post("/{draft_id}/steps")
async def add_step(draft_id: str, body: AddStep, p: Designer, c: ContainerDep) -> dict[str, Any]:
    draft, _ = c.designer.add_step(p.user_id, draft_id, body.expected_revision, body.intent_text)
    return _out(c, draft)


@router.delete("/{draft_id}/steps/{step_id}")
async def remove_step(
    draft_id: str, step_id: str, p: Designer, c: ContainerDep, expected_revision: Annotated[int, Query()]
) -> dict[str, Any]:
    return _out(c, c.designer.remove_step(p.user_id, draft_id, expected_revision, step_id))


@router.post("/{draft_id}/steps/{step_id}/propose")
async def propose(draft_id: str, step_id: str, body: Propose, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return await c.designer.propose_targets(p.user_id, draft_id, step_id, body.session_id)


@router.post("/{draft_id}/steps/{step_id}/select-target")
async def select_target(
    draft_id: str, step_id: str, body: SelectTarget, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    draft = await c.designer.select_target(
        p.user_id,
        draft_id,
        body.expected_revision,
        step_id,
        body.session_id,
        body.candidate_id,
        element_id=body.element_id,
        meaning=body.meaning,
        provenance=body.provenance,
        include_region=body.include_region,
        in_found_row=body.in_found_row,
    )
    return _out(c, draft)


@router.patch("/{draft_id}/steps/{step_id}")
async def patch_step(
    draft_id: str, step_id: str, body: PatchStep, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    fields = body.model_dump(exclude={"expected_revision"}, exclude_none=True)
    return _out(c, c.designer.configure_step(p.user_id, draft_id, body.expected_revision, step_id, **fields))


@router.post("/{draft_id}/steps/{step_id}/confirm")
async def confirm(
    draft_id: str, step_id: str, body: ConfirmStep, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    return _out(
        c,
        c.designer.confirm_step(
            p.user_id,
            draft_id,
            body.expected_revision,
            step_id,
            meaning=body.meaning,
            target=body.target,
            effect=body.effect,
            params=body.params,
        ),
    )


@router.post("/{draft_id}/steps/{step_id}/trial")
async def trial(draft_id: str, step_id: str, body: Trial, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return _out(
        c,
        await c.designer.trial_step(
            p.user_id,
            draft_id,
            body.expected_revision,
            step_id,
            body.session_id,
            body.args,
            acknowledge_effect=body.acknowledge_effect,
        ),
    )


@router.post("/{draft_id}/steps/{step_id}/confirm-outcome")
async def confirm_outcome(
    draft_id: str, step_id: str, body: Revisioned, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    return _out(c, c.designer.confirm_outcome(p.user_id, draft_id, body.expected_revision, step_id))


@router.post("/{draft_id}/fresh-test")
async def fresh_test(draft_id: str, body: FreshTest, p: Designer, c: ContainerDep) -> dict[str, Any]:
    application = c.designer.get(p.user_id, draft_id).application_id
    if body.manual_login or _fresh_test_entry(c, application)["mode"] == "url":
        return _out(c, await c.designer.begin_fresh_test(p.user_id, draft_id, body.args, body.entry_url))
    return _out(
        c,
        await c.designer.fresh_session_test(
            p.user_id, draft_id, body.expected_revision, body.args, body.entry_url
        ),
    )


@router.post("/{draft_id}/fresh-test/continue")
async def fresh_test_continue(draft_id: str, p: Designer, c: ContainerDep) -> dict[str, Any]:
    """Kullanıcı elle giriş yaptı: giriş ve beklenen ekran yeniden doğrulanır, sonra test sürer."""
    return _out(c, await c.designer.continue_fresh_test(p.user_id, draft_id))


@router.post("/{draft_id}/fresh-test/cancel")
async def fresh_test_cancel(draft_id: str, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return _out(c, await c.designer.cancel_fresh_test(p.user_id, draft_id))


@router.put("/{draft_id}/screen")
async def define_screen(draft_id: str, body: DefineScreen, p: Designer, c: ContainerDep) -> dict[str, Any]:
    draft, verdict = await c.designer.define_screen(
        p.user_id,
        draft_id,
        body.expected_revision,
        body.session_id,
        screen_id=body.screen_id,
        title=body.title,
        marker_candidate_ids=body.marker_candidate_ids,
        regions=[r.model_dump(exclude_none=True) for r in body.regions],
        absent_markers=body.absent_markers,
    )
    return {**_out(c, draft), "screen_verdict": verdict}


@router.delete("/{draft_id}/screen")
async def remove_screen(
    draft_id: str,
    p: Designer,
    c: ContainerDep,
    expected_revision: Annotated[int, Query()],
    screen_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return _out(c, c.designer.remove_screen(p.user_id, draft_id, expected_revision, screen_id))


@router.post("/{draft_id}/screen/verify")
async def verify_screen(draft_id: str, body: VerifyScreen, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return await c.designer.verify_screen(p.user_id, draft_id, body.session_id, body.screen_id)


@router.put("/{draft_id}/transitions")
async def define_transition(
    draft_id: str, body: DefineTransition, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    """R4: onaylı ekran geçişi tanımı. Tetikleyici adayı yalnız çözülür; tıklama yapılmaz."""
    fields = body.model_dump(exclude={"expected_revision"})
    return _out(c, await c.designer.define_transition(p.user_id, draft_id, body.expected_revision, **fields))


@router.delete("/{draft_id}/transitions/{transition_id}")
async def remove_transition(
    draft_id: str,
    transition_id: str,
    p: Designer,
    c: ContainerDep,
    expected_revision: Annotated[int, Query()],
) -> dict[str, Any]:
    return _out(c, c.designer.remove_transition(p.user_id, draft_id, expected_revision, transition_id))


@router.put("/{draft_id}/start-context")
async def start_context(draft_id: str, body: StartContext, p: Designer, c: ContainerDep) -> dict[str, Any]:
    checks = [x.model_dump() for x in body.checks]
    return _out(c, c.designer.set_start_context(p.user_id, draft_id, body.expected_revision, checks))


@router.post("/{draft_id}/validate")
async def validate(draft_id: str, p: Designer, c: ContainerDep) -> dict[str, Any]:
    issues = c.designer.validate(p.user_id, draft_id)
    return {"issues": issues, "ready": not issues}


@router.put("/{draft_id}/optional-dialogs")
async def optional_dialogs(
    draft_id: str, body: OptionalDialogs, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    dialogs = [
        {
            "blocker_id": f"optional.{i}",
            "dialog_name": x.dialog_name,
            "text": {"mode": "contains", "text": x.text},
            "button_label": x.button_label,
        }
        for i, x in enumerate(body.dialogs)
    ]
    return _out(c, c.designer.set_optional_dialogs(p.user_id, draft_id, body.expected_revision, dialogs))
