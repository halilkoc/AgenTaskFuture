"""R4 sözleşmesi: çok ekranlı rota doğrulaması, hash/sürüm uyumluluğu, yayın manifestosu, etki
bağımlılıkları."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agentask.application.errors import PlanInvalid
from agentask.application.services.assistant import AssistantService
from agentask.application.services.publishing import PublishService
from agentask.domain.catalog import OperationDraft, compile_operation, definition_schema
from agentask.domain.impact import PublishedOperation, impact_of
from agentask.domain.routes import ContextCheck, TransitionDef
from agentask.domain.targeting import TargetSpec
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from tests.fake_catalog_store import FakeCatalogStore
from tests.unit.test_catalog_domain import draft as single_screen_draft
from tests.unit.test_publishing import ready_draft
from tests.wizard import ARGS, NEXT, TO_COLLATERAL, wizard_draft


def issues(d: OperationDraft) -> list[str]:
    return d.validation_issues(LAB_ACTION_SET)


def test_wizard_route_is_valid_and_versioned_v3() -> None:
    d = wizard_draft()
    assert issues(d) == []
    assert definition_schema(d.definition()) == "catalog-v3"
    assert d.route() == {
        s.step_id: sid
        for s, sid in zip(
            d.steps,
            ["basvuru_musteri", "basvuru_musteri", "basvuru_teminat", "basvuru_teminat", "basvuru_teminat"],
            strict=True,
        )
    }
    blob = str(d.definition())
    for forbidden in ("css", "xpath", "candidate", "/wizard/", "http"):
        assert forbidden not in blob


def test_single_screen_definition_unchanged_by_r4() -> None:
    d = single_screen_draft()
    definition = d.definition()
    assert definition_schema(definition) == "catalog-v2"
    assert set(definition) == {
        "application_id",
        "operation_id",
        "title",
        "description",
        "intent_phrases",
        "parameters",
        "elements",
        "steps",
        "screen_ref",
    }
    assert all("screen_id" not in s and "transition_id" not in s for s in definition["steps"])
    assert not d.is_multi_screen


def test_compiled_plan_starts_with_context_and_carries_transitions() -> None:
    commands = compile_operation(wizard_draft(), ARGS, LAB_ACTION_SET)
    assert commands[0]["op"] == "assert_screen" and commands[0]["screen"]["screen_id"] == "basvuru_musteri"
    assert commands[0]["context"] == [
        {
            "type": "value_equals",
            "target": {"kind": "textbox", "labels": ["Vaka No"], "region": "Vaka"},
            "value": "C-2001",
        }
    ]
    follow = next(c for c in commands if c["op"] == "follow_transition")
    assert follow["trigger"] == {"kind": "button", "labels": ["Devam"]}
    assert follow["to_screen"]["screen_id"] == "basvuru_teminat" and follow["timeout_ms"] == 4000
    invoke = commands[-1]
    assert invoke["op"] == "invoke_approved_action" and invoke["params"] == {
        "case_no": "C-2001",
        "amount": "1500",
    }
    assert invoke["transition"]["to_screen"]["screen_id"] == "basvuru_ozet"
    assert invoke["transition"]["context"][0]["value"] == "C-2001"


def test_trial_of_later_step_asserts_its_own_screen() -> None:
    d = wizard_draft()
    commands = compile_operation(d, ARGS, LAB_ACTION_SET, steps=[d.steps[2]], screen_check="if_present")
    assert commands[0]["screen"]["screen_id"] == "basvuru_teminat" and "context" not in commands[0]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda d: setattr(d.steps[2], "screen_id", "basvuru_musteri"),
            "step_3_screen_out_of_route:basvuru_musteri",
        ),
        (lambda d: setattr(d.steps[0], "screen_id", "yok"), "step_1_unknown_screen:yok"),
        (lambda d: setattr(d.steps[1], "transition_id", None), "transition_used_0_times:teminata_gec"),
        (
            lambda d: setattr(d.steps[4], "transition_id", "teminata_gec"),
            "transition_used_2_times:teminata_gec",
        ),
        (lambda d: setattr(d.steps[4], "op", "ensure_value"), "step_5_transition_trigger_mismatch"),
        (
            lambda d: setattr(
                d,
                "transitions",
                [TO_COLLATERAL.model_copy(update={"from_screen": "basvuru_ozet"}), d.transitions[1]],
            ),
            "step_2_transition_source_mismatch:teminata_gec",
        ),
        (
            lambda d: setattr(
                d,
                "transitions",
                [
                    TO_COLLATERAL.model_copy(
                        update={
                            "completion": [
                                ContextCheck(
                                    target=TargetSpec(kind="textbox", labels=["Vaka No"]),
                                    value_template="{baska}",
                                )
                            ]
                        }
                    ),
                    d.transitions[1],
                ],
            ),
            "transition_undeclared_param:teminata_gec:baska",
        ),
    ],
)
def test_route_rules(mutate, expected: str) -> None:  # type: ignore[no-untyped-def]
    d = wizard_draft()
    mutate(d)
    assert expected in issues(d)


def test_each_screen_needs_markers_beyond_its_own_targets() -> None:
    d = wizard_draft()
    only_targets = d.extra_screens[0].model_copy(
        update={
            "markers": [TargetSpec(kind="textbox", labels=["Teminat Tutarı"], region="Teminat")],
            "regions": d.extra_screens[0].regions[1:],
        }
    )
    d.extra_screens = [only_targets, d.extra_screens[1]]
    assert "screen_markers_only_targets@basvuru_teminat" in issues(d)


def test_transition_model_rejects_unsafe_definitions() -> None:
    with pytest.raises(ValidationError):  # tetikleyici metin alanı olamaz (genel tıklama yok)
        TransitionDef(
            transition_id="t",
            from_screen="a",
            to_screen="b",
            trigger={"kind": "control", "target": {"kind": "textbox", "labels": ["X"]}},
        )
    with pytest.raises(ValidationError):
        TransitionDef(transition_id="t", from_screen="a", to_screen="a", trigger={"kind": "approved_action"})
    with pytest.raises(ValidationError):  # sınırsız bekleme yok
        TransitionDef(
            transition_id="t",
            from_screen="a",
            to_screen="b",
            trigger={"kind": "approved_action"},
            timeout_ms=120_000,
        )
    with pytest.raises(ValidationError):
        TransitionDef.model_validate({**TO_COLLATERAL.model_dump(mode="json"), "url": "/wizard/x"})


def test_screen_or_transition_change_invalidates_test_and_approval_hash() -> None:
    d = wizard_draft()
    h = d.content_hash()
    d.transitions = [TO_COLLATERAL.model_copy(update={"timeout_ms": 5000}), d.transitions[1]]
    assert d.content_hash() != h and "fresh_session_test_stale" in issues(d)
    d = wizard_draft()
    d.extra_screens = [d.extra_screens[0].model_copy(update={"title": "Başka"}), d.extra_screens[1]]
    assert d.content_hash() != h


def test_unknown_schema_is_not_interpreted() -> None:
    definition = {**wizard_draft().definition(), "loops": []}
    assert definition_schema(definition) == "unknown"


@pytest.fixture
def pub(tmp_path: Path) -> tuple[PublishService, FakeCatalogStore, LocalFileDraftRepository]:
    store, repo = FakeCatalogStore(), LocalFileDraftRepository(tmp_path / "drafts")
    return PublishService(store, repo, LAB_ACTION_SET, "arge"), store, repo


async def test_publish_multi_screen_pins_all_screens_and_keeps_v2(pub) -> None:  # type: ignore[no-untyped-def]
    service, store, repo = pub
    v2 = ready_draft(repo, "kefil_musteri_no", "Kefil")
    service.approve("pub", v2.draft_id, v2.revision)
    first = await service.publish("pub", v2.draft_id, "r1")
    w = wizard_draft()
    repo.create(w)
    service.approve("pub", w.draft_id, w.revision)
    release = await service.publish("pub", w.draft_id, "r2")
    assert {s.screen_id for s in release.screens} == {
        "basvuru_taraflar",
        "basvuru_musteri",
        "basvuru_teminat",
        "basvuru_ozet",
    }
    assert store.revisions[("lab", "basvuru_gonder", 1)].schema_version == "catalog-v3"
    assert store.revisions[("lab", "kefil_musteri_no", 1)].schema_version == "catalog-v2"
    old = await service.release(first.release_id)
    assert old is not None and [s.screen_id for s in old.screens] == ["basvuru_taraflar"]  # yerinde değişmedi
    rev = store.revisions[("lab", "basvuru_gonder", 1)]
    rebuilt = await service.published_draft(release, rev)
    assert rebuilt.content_hash() == rev.content_hash and len(rebuilt.extra_screens) == 2
    # Bilinmeyen (ileri) şema okunmaz.
    with pytest.raises(PlanInvalid) as err:
        await service.screens_of(release, "x", 1, {**rev.definition, "loops": []})
    assert err.value.details["reason"] == "unsupported_schema"

    assistant = AssistantService(service, None, LAB_ACTION_SET, UnavailableLLM("x"), 2000, 200, 1, "lab")  # type: ignore[arg-type]
    preview = await assistant.preview("ayse", release.release_id, "basvuru_gonder", ARGS)
    assert preview["navigation"] is True and preview["effect"] == "mutating"
    assert preview["route"] == ["Başvuru — müşteri seçimi", "Başvuru — teminat bilgileri", "Başvuru — özet"]
    assert any("→ ekran geçişi: Başvuru — teminat bilgileri" in s for s in preview["steps"])


def test_impact_covers_shared_screens_and_transition_triggers() -> None:
    w = wizard_draft()
    ops = [
        PublishedOperation(
            operation_id="basvuru_gonder", revision=1, content_hash="h", definition=w.definition()
        ),
        PublishedOperation(
            operation_id="kefil_musteri_no",
            revision=1,
            content_hash="k",
            definition=single_screen_draft().definition(),
        ),
        PublishedOperation(
            operation_id="baska",
            revision=1,
            content_hash="b",
            definition={
                **w.definition(),
                "operation_id": "baska",
                "elements": {"devam": {"meaning": "Devam", "target": NEXT.model_dump(mode="json")}},
            },
        ),
    ]
    by_screen = impact_of(ops, screen_ids={"basvuru_teminat"})
    assert [(i.operation_id, i.reasons) for i in by_screen] == [
        ("basvuru_gonder", ["screen:basvuru_teminat"]),
        ("baska", ["screen:basvuru_teminat"]),
    ]
    by_trigger = impact_of(ops, elements={("baska", "devam")})
    reasons = {i.operation_id: i.reasons for i in by_trigger}
    assert "transition:teminata_gec" in reasons["basvuru_gonder"]


async def test_designer_transition_change_reopens_affected_steps(tmp_path: Path) -> None:
    from agentask.application.services.designer import DesignerService
    from agentask.domain.catalog import StepStatus

    repo = LocalFileDraftRepository(tmp_path / "drafts")
    designer = DesignerService(repo, None, None, None, LAB_ACTION_SET, 1)  # type: ignore[arg-type]
    w = wizard_draft()
    repo.create(w)
    assert issues(w) == []
    # Aynı tanımla yeniden kaydetmek adımları geri almaz; değiştirmek alır (onay + deneme geçersiz).
    same = await designer.define_transition(
        "ayse",
        w.draft_id,
        w.revision,
        transition_id="ozete_gec",
        from_screen="basvuru_teminat",
        to_screen="basvuru_ozet",
        trigger_kind="approved_action",
        timeout_ms=4000,
        completion=[c.model_dump(mode="json") for c in w.transitions[1].completion],
    )
    assert same.steps[4].status is StepStatus.READY_FOR_REVIEW
    changed = await designer.define_transition(
        "ayse",
        w.draft_id,
        same.revision,
        transition_id="ozete_gec",
        from_screen="basvuru_teminat",
        to_screen="basvuru_ozet",
        trigger_kind="approved_action",
        timeout_ms=6000,
    )
    assert changed.steps[4].status is StepStatus.TARGET_SELECTED and changed.steps[4].confirmation is None
    assert changed.steps[0].status is StepStatus.READY_FOR_REVIEW  # ilgisiz adım etkilenmez
    assert "fresh_session_test_stale" in issues(changed) and "step_5_not_ready" in issues(changed)
    # ADR 0017: hedef ekran henüz tanıtılmamış olabilir; geçiş kaydedilir ama eksiklik olarak kalır ve
    # taslak hazır/derlenebilir olmaz.
    pending = await designer.define_transition(
        "ayse",
        w.draft_id,
        changed.revision,
        transition_id="x",
        from_screen="basvuru_teminat",
        to_screen="yok",
        trigger_kind="approved_action",
    )
    assert "transition_unknown_screen:x:yok" in issues(pending)
    with pytest.raises(PlanInvalid):  # başlangıç ekranı diğer ekranlar varken kaldırılamaz
        designer.remove_screen("ayse", w.draft_id, pending.revision)
