"""Ana plan E: pinli bileşenlerin yayımı, yükseltme etkisi ve eski yayınların korunması (sahte katalog)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentask.application.errors import PlanInvalid, PublishConflict
from agentask.application.services.designer import DesignerService
from agentask.application.services.publishing import PublishService
from agentask.domain.catalog import (
    Confirmation,
    OperationDraft,
    ParameterDef,
    StepStatus,
    compile_operation,
)
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from tests.fake_catalog_store import FakeCatalogStore
from tests.wizard import CASE_NO, CUSTOMER_NO, CUSTOMER_SCREEN


def make_ready(d: OperationDraft) -> None:
    for s in d.steps:
        s.status = StepStatus.TARGET_SELECTED
        s.confirmation = Confirmation(meaning=True, target=True, effect=True, params=True, by="ayse")
        for st in (
            StepStatus.MEANING_AND_TARGET_CONFIRMED,
            StepStatus.TRIAL_REQUESTED,
            StepStatus.OBSERVED,
            StepStatus.OUTCOME_CONFIRMED,
            StepStatus.READY_FOR_REVIEW,
        ):
            s.move(st)
    d.record_fresh_test(run_id="run-fresh0001", passed=True)


def component_draft(title: str = "Müşteri yaz ve vaka oku") -> OperationDraft:
    d = OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id="musteri_yaz", title=title, description=""
    )
    d.parameters.append(
        ParameterDef(name="musteri_no", title="Müşteri No", max_length=20, source="user_input")
    )
    d.add_element("musteri", "Müşteri numarası", CUSTOMER_NO, "observed")
    d.add_element("vaka_no", "Vaka numarası", CASE_NO, "observed")
    w = d.add_step("yaz")
    w.op, w.element_id, w.value_template = "ensure_value", "musteri", "{musteri_no}"
    r = d.add_step("oku")
    r.op, r.element_id = "read", "vaka_no"
    d.screen = CUSTOMER_SCREEN
    return d


@pytest.fixture
def env(tmp_path: Path) -> tuple[PublishService, DesignerService, LocalFileDraftRepository]:
    store, repo = FakeCatalogStore(), LocalFileDraftRepository(tmp_path / "drafts")
    pub = PublishService(store, repo, LAB_ACTION_SET, environment="arge")
    designer = DesignerService(repo, None, None, None, LAB_ACTION_SET, 1, publishing=pub)  # type: ignore[arg-type]
    return pub, designer, repo


async def publish(pub: PublishService, repo: LocalFileDraftRepository, d: OperationDraft, req: str) -> str:
    make_ready(d)
    if repo.get(d.draft_id) is None:
        repo.create(d)
    else:
        repo.update(d, repo.get(d.draft_id).revision)  # type: ignore[union-attr]
    current = repo.get(d.draft_id)
    assert current is not None
    pub.approve("pub", d.draft_id, current.revision)
    return (await pub.publish("pub", d.draft_id, req)).release_id


async def test_pinned_component_survives_new_revision(env) -> None:  # type: ignore[no-untyped-def]
    pub, designer, repo = env
    comp = component_draft()
    await publish(pub, repo, comp, "req-a1")
    listed = await pub.available_components("lab")
    assert [(c["operation_id"], c["revision"]) for c in listed] == [("musteri_yaz", 1)]
    assert listed[0]["outputs"] == [{"name": "vaka_no", "title": "Vaka numarası"}]

    caller = designer.create_draft(
        "ayse", application_id="lab", operation_id="akis", title="Akış", description=""
    )
    caller = designer.add_parameter(
        "ayse", caller.draft_id, caller.revision, name="no", title="No", max_length=20, source="user_input"
    )
    caller, step = designer.add_step("ayse", caller.draft_id, caller.revision, "bileşeni çağır")
    with pytest.raises(PlanInvalid):  # yayımlanmamış revizyon pinlenemez
        await designer.set_call(
            "ayse",
            caller.draft_id,
            caller.revision,
            step.step_id,
            operation_id="musteri_yaz",
            component_revision=9,
            arguments={},
        )
    caller = await designer.set_call(
        "ayse",
        caller.draft_id,
        caller.revision,
        step.step_id,
        operation_id="musteri_yaz",
        component_revision=1,
        arguments={"musteri_no": "{no}"},
    )
    assert caller.steps[0].call is not None and caller.steps[0].call.outputs == ["vaka_no"]
    caller.screen = CUSTOMER_SCREEN  # çağıranın başlangıç ekranı = bileşenin başlangıç ekranı
    first = await publish(pub, repo, caller, "req-b1")
    manifest = await pub.release(first)
    assert manifest is not None and {e.operation_id for e in manifest.operations} == {"musteri_yaz", "akis"}

    # Bileşenin yeni revizyonu yayımlanır; çağıran kendiliğinden değişmez (pin).
    comp2 = repo.get(comp.draft_id)
    assert comp2 is not None
    comp2.title = "Müşteri yaz ve vaka oku (v2)"
    await publish(pub, repo, comp2, "req-a2")
    active = await pub.active_release("lab")
    assert active is not None
    entry = next(e for e in active.operations if e.operation_id == "akis")
    rev = await pub.operation("lab", entry)
    assert rev is not None and rev.definition["steps"][0]["call"]["revision"] == 1
    published = await pub.published_draft(active, rev)
    lookup = await pub.component_lookup("lab", published)
    commands = compile_operation(published, {"no": "5"}, LAB_ACTION_SET, components=lookup)
    assert [c["op"] for c in commands].count("read") == 1  # bileşen v1 içeriği açıldı

    updates = await designer.component_updates("ayse", caller.draft_id)
    assert updates == [
        {
            "step_id": step.step_id,
            "step": 1,
            "operation_id": "musteri_yaz",
            "pinned_revision": 1,
            "latest_revision": 2,
            "new_inputs": [],
            "removed_inputs": [],
            "lost_outputs": [],
            "screen_changed": False,
            "compatible": True,
            "retest_required": True,
        }
    ]
    # Yükseltme açık bir işlemdir: adım ve yeni oturum testi yeniden gerekir.
    current = repo.get(caller.draft_id)
    assert current is not None
    upgraded = await designer.set_call(
        "ayse",
        caller.draft_id,
        current.revision,
        step.step_id,
        operation_id="musteri_yaz",
        component_revision=2,
        arguments={"musteri_no": "{no}"},
    )
    issues = upgraded.validation_issues(LAB_ACTION_SET)
    assert "step_1_not_ready" in issues and "fresh_session_test_stale" in issues
    # Eski yayın yerinde değişmedi.
    old = await pub.release(first)
    assert old == manifest


async def test_publish_rejects_missing_component_revision(env) -> None:  # type: ignore[no-untyped-def]
    pub, designer, repo = env
    comp = component_draft()
    await publish(pub, repo, comp, "req-a1")
    caller = designer.create_draft(
        "ayse", application_id="lab", operation_id="akis", title="A", description=""
    )
    caller = designer.add_parameter(
        "ayse", caller.draft_id, caller.revision, name="no", title="No", max_length=20, source="user_input"
    )
    caller, step = designer.add_step("ayse", caller.draft_id, caller.revision, "çağır")
    caller = await designer.set_call(
        "ayse",
        caller.draft_id,
        caller.revision,
        step.step_id,
        operation_id="musteri_yaz",
        component_revision=1,
        arguments={"musteri_no": "{no}"},
    )
    caller.screen = CUSTOMER_SCREEN
    store = pub._store
    store.revisions.pop(("lab", "musteri_yaz", 1))  # type: ignore[attr-defined]
    with pytest.raises(PublishConflict):
        await publish(pub, repo, caller, "req-b1")


async def test_self_call_is_rejected(env) -> None:  # type: ignore[no-untyped-def]
    pub, designer, repo = env
    comp = component_draft()
    await publish(pub, repo, comp, "req-a1")
    again = designer.create_draft(
        "ayse", application_id="lab", operation_id="musteri_yaz", title="Kendini çağıran", description=""
    )
    again, step = designer.add_step("ayse", again.draft_id, again.revision, "çağır")
    with pytest.raises(PlanInvalid) as exc:
        await designer.set_call(
            "ayse",
            again.draft_id,
            again.revision,
            step.step_id,
            operation_id="musteri_yaz",
            component_revision=1,
            arguments={},
        )
    assert exc.value.details["reason"] == "component_cycle"
