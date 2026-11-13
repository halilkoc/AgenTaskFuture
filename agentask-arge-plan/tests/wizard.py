"""YALNIZ TEST: deney uygulamasının üç ekranlı başvuru sihirbazı için anlamsal katalog (R4).

Ekranlar URL veya DOM kimliğiyle değil, anlamsal işaretlerle tanınır; kayıt bağlamı (Vaka No)
şablonla bağlanır.
Ürün kodunda bu ekranlara özel bir koşul yoktur; bu dosya katalog verisi gibi davranır."""

from __future__ import annotations

import secrets

from agentask.domain.catalog import Confirmation, OperationDraft, ParameterDef, StepStatus
from agentask.domain.routes import ContextCheck, TransitionDef
from agentask.domain.screens import RegionDef, ScreenDef
from agentask.domain.targeting import TargetSpec

CASE_NO = TargetSpec(kind="textbox", labels=["Vaka No"], region="Vaka")
CUSTOMER_NO = TargetSpec(kind="textbox", labels=["Müşteri No"], region="Müşteri")
NEXT = TargetSpec(kind="button", labels=["Devam"])
AMOUNT = TargetSpec(kind="textbox", labels=["Teminat Tutarı"], region="Teminat")
DOCUMENT = TargetSpec(kind="textbox", labels=["Belge No"], frame_title="Teminat Belgeleri")
SUBMIT = TargetSpec(kind="button", labels=["Gönder"], region="Teminat")
PRINT = TargetSpec(kind="button", labels=["Yazdır"])
REJECT_NOTE = TargetSpec(kind="textbox", labels=["Açıklama"], region="Red Nedeni")

CUSTOMER_SCREEN = ScreenDef(
    screen_id="basvuru_musteri",
    title="Başvuru — müşteri seçimi",
    regions=[RegionDef(region_id="vaka", name="Vaka"), RegionDef(region_id="musteri", name="Müşteri")],
    markers=[CASE_NO, CUSTOMER_NO, NEXT],
    absent_markers=[AMOUNT],
)
COLLATERAL_SCREEN = ScreenDef(
    screen_id="basvuru_teminat",
    title="Başvuru — teminat bilgileri",
    regions=[RegionDef(region_id="vaka", name="Vaka"), RegionDef(region_id="teminat", name="Teminat")],
    markers=[CASE_NO, SUBMIT, DOCUMENT],
    absent_markers=[CUSTOMER_NO, REJECT_NOTE],
)
SUMMARY_SCREEN = ScreenDef(
    screen_id="basvuru_ozet",
    title="Başvuru — özet",
    regions=[RegionDef(region_id="vaka", name="Vaka")],
    markers=[CASE_NO, PRINT],
    absent_markers=[SUBMIT],
)
CASE_CONTEXT = ContextCheck(target=CASE_NO, value_template="{vaka_no}")

TO_COLLATERAL = TransitionDef(
    transition_id="teminata_gec",
    from_screen="basvuru_musteri",
    to_screen="basvuru_teminat",
    trigger={"kind": "control", "target": NEXT},
    timeout_ms=4000,
    completion=[CASE_CONTEXT],
)
TO_SUMMARY = TransitionDef(
    transition_id="ozete_gec",
    from_screen="basvuru_teminat",
    to_screen="basvuru_ozet",
    trigger={"kind": "approved_action"},
    timeout_ms=4000,
    completion=[CASE_CONTEXT],
)

ARGS = {"vaka_no": "C-2001", "musteri_no": "00456", "tutar": "1500", "belge_no": "B-77"}


def _ready(step: object) -> None:
    s = step  # type: ignore[assignment]
    s.move(StepStatus.TARGET_SELECTED)  # type: ignore[attr-defined]
    s.confirmation = Confirmation(meaning=True, target=True, effect=True, params=True, by="ayse")  # type: ignore[attr-defined]
    for st in (
        StepStatus.MEANING_AND_TARGET_CONFIRMED,
        StepStatus.TRIAL_REQUESTED,
        StepStatus.OBSERVED,
        StepStatus.OUTCOME_CONFIRMED,
        StepStatus.READY_FOR_REVIEW,
    ):
        s.move(st)  # type: ignore[attr-defined]


def wizard_draft(op_id: str = "basvuru_gonder", *, fresh: bool = True) -> OperationDraft:
    d = OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id=op_id, title="Başvuruyu gönder", description=""
    )
    d.intent_phrases = ["başvuruyu gönder"]
    d.parameters = [
        ParameterDef(name=n, title=t, max_length=40, source="user_input")
        for n, t in (
            ("vaka_no", "Vaka No"),
            ("musteri_no", "Müşteri No"),
            ("tutar", "Teminat Tutarı"),
            ("belge_no", "Belge No"),
        )
    ]
    d.add_element("musteri_no", "Müşteri numarası", CUSTOMER_NO, "observed")
    d.add_element("tutar", "Teminat tutarı", AMOUNT, "observed")
    d.add_element("belge_no", "Teminat belge numarası", DOCUMENT, "observed")
    d.screen = CUSTOMER_SCREEN
    d.extra_screens = [COLLATERAL_SCREEN, SUMMARY_SCREEN]
    d.transitions = [TO_COLLATERAL, TO_SUMMARY]
    d.start_context = [CASE_CONTEXT]
    for intent, op, element, template in (
        ("Müşteri numarasını yaz", "ensure_value", "musteri_no", "{musteri_no}"),
        ("Devam et", "follow_transition", None, None),
        ("Teminat tutarını yaz", "ensure_value", "tutar", "{tutar}"),
        ("Belge numarasını yaz", "ensure_value", "belge_no", "{belge_no}"),
        ("Başvuruyu gönder", "invoke_approved_action", None, None),
    ):
        s = d.add_step(intent)
        s.op = op  # type: ignore[assignment]
        s.element_id, s.value_template = element, template
        if op == "follow_transition":
            s.transition_id = "teminata_gec"
        if op == "invoke_approved_action":
            s.action_id, s.action_params = (
                "lab.submit_application",
                {"case_no": "{vaka_no}", "amount": "{tutar}"},
            )
            s.transition_id = "ozete_gec"
            s.screen_id = "basvuru_teminat"
        _ready(s)
    if fresh:
        d.record_fresh_test(run_id=f"run-{secrets.token_hex(4)}", passed=True)
    return d
