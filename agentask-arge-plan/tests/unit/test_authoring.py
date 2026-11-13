"""Kural tabanlı öneriler: niyet → komut, aday sıralama (ilk eşleşen seçilmez), hedef tanımı türetme."""

from __future__ import annotations

from agentask.domain.authoring import propose_op, rank_candidates, spec_from_control, standard_text
from agentask.domain.observation import ContextEntry, ControlKind, ObservedControl


def c(
    n: int, kind: ControlKind, label: str, region: str | None = None, frames: tuple[str, ...] = ()
) -> ObservedControl:
    ctx = (ContextEntry("region", region, None),) if region else ()
    return ObservedControl(
        candidate_id=f"c-s1-{n}",
        frame_ref="f1",
        kind=kind,
        role=kind.value,
        accessible_name=label,
        label=label,
        visible=True,
        enabled=True,
        sensitive=False,
        has_value=False,
        selected_text=None,
        options=(),
        contexts=ctx,
        frame_titles=frames,
        tag="input",
    )


def test_propose_op_from_turkish_verbs() -> None:
    assert propose_op("Kefil müşteri numarasını yaz") == "ensure_value"
    assert propose_op("Şube olarak Konak'ı seç") == "ensure_choice"
    assert propose_op("Teslimat sekmesine geç") == "activate_tab"
    assert propose_op("B-1027 başvurusunu bul") == "find_record"
    assert propose_op("Notu kaydet") == "invoke_approved_action"
    assert propose_op("Bir şeyler yap") is None


def test_rank_candidates_keeps_ties_and_filters_kind() -> None:
    controls = [
        c(0, ControlKind.TEXTBOX, "Müşteri No", "Başvuran"),
        c(1, ControlKind.TEXTBOX, "Müşteri No", "Kefil"),
        c(2, ControlKind.BUTTON, "Kaydet", "Kefil"),
        c(3, ControlKind.TEXTBOX, "Ad Soyad", "Kefil"),
    ]
    ranked = rank_candidates("Kefil müşteri no alanına yaz", controls, "ensure_value")
    assert [r.control.candidate_id for r in ranked][:1] == ["c-s1-1"]
    assert all(r.control.kind is ControlKind.TEXTBOX for r in ranked)
    tie = rank_candidates("müşteri no yaz", controls, "ensure_value")
    assert tie[0].score == tie[1].score and {tie[0].control.candidate_id, tie[1].control.candidate_id} == {
        "c-s1-0",
        "c-s1-1",
    }


def test_spec_from_control_uses_semantics_only() -> None:
    spec = spec_from_control(c(1, ControlKind.TEXTBOX, "Müşteri No", "Kefil", ("Vaka", "Adres Bilgileri")))
    assert spec.model_dump(exclude_none=True) == {
        "kind": "textbox",
        "labels": ["Müşteri No"],
        "region": "Kefil",
        "frame_title": "Adres Bilgileri",
        "require_visible": True,
        "require_enabled": True,
    }


def test_standard_text() -> None:
    assert (
        standard_text("ensure_value", "Kefil müşteri numarası", "{musteri_no}")
        == "'Kefil müşteri numarası' alanına {musteri_no} değerini yaz"
    )
