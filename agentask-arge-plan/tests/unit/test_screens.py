"""R3 ekran tanımı ve ortak doğrulama çekirdeği (saf alan katmanı; tarayıcı testleri integration/browser)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agentask.domain.actions import ActionSet
from agentask.domain.catalog import OperationDraft, compile_operation, requires_migration
from agentask.domain.observation import ContextEntry, ScanStatus, Snapshot
from agentask.domain.release import ReleaseManifest, ScreenEntry
from agentask.domain.screens import RegionDef, ScreenDef, ScreenStatus, judge, static_issues
from agentask.domain.targeting import TargetSpec, resolve
from tests.screens import APPLICANT_NO, GUARANTOR_NAME, GUARANTOR_NO, PARTIES_SCREEN
from tests.unit.test_catalog_domain import draft
from tests.unit.test_targeting import control, frame


def region(name: str) -> tuple[ContextEntry, ...]:
    return (ContextEntry("region", name, None),)


def parties(*, guarantors: int = 1, similar: bool = False, partial: bool = False) -> Snapshot:
    controls = [
        control(1, label="Müşteri No", contexts=region("Başvuran")),
        control(2, label="Ad Soyad", contexts=region("Başvuran")),
    ]
    n = 3
    for _ in range(guarantors):
        controls.append(control(n, label="Müşteri No", contexts=region("Kefil")))
        if similar:
            controls.append(control(n + 1, label="Talep Notu", contexts=region("Kefil")))
        else:
            controls.append(control(n + 1, label="Ad Soyad", contexts=region("Kefil")))
        n += 2
    frames = [frame("f1")]
    if partial:
        frames.append(frame("f2", title="Ek Belgeler", parent="f1", status=ScanStatus.TIMED_OUT))
    return Snapshot("s1", datetime.now(UTC), tuple(frames), tuple(controls))


def verdict(snapshot: Snapshot, screen: ScreenDef = PARTIES_SCREEN):  # type: ignore[no-untyped-def]
    return judge(screen, lambda spec: resolve(spec, snapshot))


def test_definition_is_semantic_only() -> None:
    dumped = PARTIES_SCREEN.model_dump(mode="json")
    blob = str(dumped)
    for forbidden in ("selector", "xpath", "css", "frame_index", "url", "candidate_id", "x", "y"):
        assert f"'{forbidden}'" not in blob
    with pytest.raises(ValidationError):
        ScreenDef.model_validate({**dumped, "url": "/pages/duplicates"})
    with pytest.raises(ValidationError):
        ScreenDef.model_validate({**dumped, "markers": [{**dumped["markers"][0], "css": "#a"}]})


def test_every_region_needs_an_observable_marker() -> None:
    with pytest.raises(ValidationError, match="Teminat"):
        ScreenDef(
            screen_id="x",
            title="X",
            regions=[RegionDef(region_id="teminat", name="Teminat")],
            markers=[APPLICANT_NO],
        )
    with pytest.raises(ValidationError, match="iki kez"):
        ScreenDef(screen_id="x", title="X", markers=[APPLICANT_NO, APPLICANT_NO])
    with pytest.raises(ValidationError, match="hem zorunlu hem yasak"):
        ScreenDef(screen_id="x", title="X", markers=[APPLICANT_NO], absent_markers=[APPLICANT_NO])
    with pytest.raises(ValidationError):
        ScreenDef(screen_id="x", title="X", markers=[])


def test_correct_screen_recognized() -> None:
    v = verdict(parties())
    assert v.status is ScreenStatus.RECOGNIZED and v.recognized
    assert [m.outcome for m in v.markers] == ["resolved", "resolved", "unresolved"]


def test_similar_wrong_screen_rejected_even_though_target_resolves() -> None:
    snap = parties(similar=True)
    # İşlemin kendi hedefi bu yanlış ekranda da TEKİL bulunur; tanıma buna dayanmaz.
    assert resolve(GUARANTOR_NO, snap).outcome.value == "resolved"
    v = verdict(snap)
    assert v.status is ScreenStatus.NOT_RECOGNIZED and "olmaması gereken" in v.explanation


def test_duplicated_region_is_ambiguous() -> None:
    v = verdict(parties(guarantors=2))
    assert v.status is ScreenStatus.AMBIGUOUS and "Ad Soyad" in v.explanation


def test_missing_marker_not_recognized() -> None:
    snap = Snapshot("s2", datetime.now(UTC), (frame("f1"),), (control(1, label="Başka"),))
    assert verdict(snap).status is ScreenStatus.NOT_RECOGNIZED


def test_incomplete_scan_is_not_proof_either_way() -> None:
    v = verdict(parties(partial=True))
    assert v.status is ScreenStatus.INCOMPLETE and not v.recognized


def test_nested_frame_markers_scoped_by_frame_title() -> None:
    screen = ScreenDef(
        screen_id="vaka_frame",
        title="Vaka frame ekranı",
        markers=[
            TargetSpec(kind="textbox", labels=["Vaka Durumu"], frame_title="Vaka Ayrıntıları"),
            TargetSpec(kind="textbox", labels=["Adres"], frame_title="Adres Bilgileri"),
        ],
    )
    frames = (frame("top"), frame("l1", title="Vaka Ayrıntıları"), frame("l2", title="Adres Bilgileri"))
    controls = (
        control(1, frame_ref="l1", label="Vaka Durumu", frame_titles=("Vaka Ayrıntıları",)),
        control(2, frame_ref="l2", label="Adres", frame_titles=("Vaka Ayrıntıları", "Adres Bilgileri")),
    )
    assert verdict(Snapshot("s", datetime.now(UTC), frames, controls), screen).recognized
    # Aynı etiket yanlış frame'de: eşleşme yok sayılır.
    moved = (controls[0], control(3, frame_ref="top", label="Adres"))
    assert not verdict(Snapshot("s", datetime.now(UTC), frames, moved), screen).recognized


def test_static_rules_reject_target_only_recognition_and_foreign_regions() -> None:
    elements = {"kefil_no": GUARANTOR_NO}
    assert static_issues(None, elements, ["kefil_no"]) == ["screen_missing"]
    only_target = ScreenDef(
        screen_id="x", title="X", regions=[RegionDef(region_id="kefil", name="Kefil")], markers=[GUARANTOR_NO]
    )
    assert "screen_markers_only_targets" in static_issues(only_target, elements, ["kefil_no"])
    narrow = ScreenDef(
        screen_id="x",
        title="X",
        regions=[RegionDef(region_id="basvuran", name="Başvuran")],
        markers=[APPLICANT_NO],
    )
    assert "element_region_not_in_screen:kefil_no" in static_issues(narrow, elements, ["kefil_no"])
    assert static_issues(PARTIES_SCREEN, elements, ["kefil_no"]) == []


def test_screen_is_part_of_operation_hash_and_definition() -> None:
    d = draft()
    with_screen = d.content_hash()
    assert d.definition()["screen_ref"] == PARTIES_SCREEN.ref()
    d.screen = PARTIES_SCREEN.model_copy(update={"title": "Başka başlık"})
    assert d.content_hash() != with_screen  # ekran değişirse işlem onayı geçersizleşir
    d.screen = None
    assert "screen_missing" in d.validation_issues()
    assert requires_migration(d.definition())


def test_published_definition_requires_matching_screen() -> None:
    definition = draft().definition()
    with pytest.raises(ValueError, match="screen_revision_mismatch"):
        OperationDraft.from_definition(definition, created_by="c")
    other = PARTIES_SCREEN.model_copy(update={"markers": [GUARANTOR_NAME]})
    with pytest.raises(ValueError, match="screen_revision_mismatch"):
        OperationDraft.from_definition(definition, created_by="c", screen=other)
    rebuilt = OperationDraft.from_definition(definition, created_by="c", screen=PARTIES_SCREEN)
    assert rebuilt.content_hash() == draft().content_hash()


def test_legacy_definition_never_compiles_without_screen_check() -> None:
    legacy = draft()
    legacy.screen = None
    model = OperationDraft.from_definition(legacy.definition(), created_by="c")
    with pytest.raises(ValueError, match="migration_required"):
        compile_operation(model, {"musteri_no": "1"}, ActionSet())
    # Tasarımcıdaki tek adım denemesi ekran yokken izinli; ekran varsa yine assert_screen ile başlar.
    trial = compile_operation(model, {"musteri_no": "1"}, ActionSet(), screen_check="if_present")
    assert trial[0]["op"] == "ensure_value"
    assert (
        compile_operation(draft(), {"musteri_no": "1"}, ActionSet(), screen_check="if_present")[0]["op"]
        == "assert_screen"
    )


def test_legacy_manifest_reads_without_screens_and_new_hash_covers_screens() -> None:
    legacy_doc = {
        "release_id": "rel-old",
        "request_id": "r",
        "application_id": "lab",
        "environment": "arge",
        "operations": [{"operation_id": "kefil_musteri_no", "revision": 1, "content_hash": "a" * 64}],
        "base_release_id": None,
        "approvals": [],
        "adapter_version": "controls-p3.1",
        "schema_version": "catalog-v1",
        "manifest_hash": "b" * 64,
        "created_by": "x",
        "created_at": datetime.now(UTC),
    }
    legacy = ReleaseManifest.model_validate(legacy_doc)
    assert legacy.screens == [] and legacy.schema_version == "catalog-v1"
    ops = legacy.operations
    entry = ScreenEntry(screen_id="s", revision=1, content_hash="c" * 64)
    assert ReleaseManifest.compute_hash("lab", "arge", ops, [entry]) != ReleaseManifest.compute_hash(
        "lab", "arge", ops
    )
