"""Yerel deney uygulamasının onaylı test aksiyonları. Gerçek Pega aksiyonu değildir; P4 kataloğu gelene kadar
yalnız APPROVED_ACTION_SET=lab ile yüklenir (production'da reddedilir)."""

from __future__ import annotations

from agentask.domain.actions import ActionSet

LAB_ACTION_SET = ActionSet.model_validate(
    {
        "actions": {
            "lab.add_case_note": {
                "action_id": "lab.add_case_note",
                "title": "Vakaya not ekle (deney, veri değiştirir)",
                "target": {"kind": "button", "labels": ["Kaydet"]},
                "effect": "mutating",
                "retry_safe": False,
                "params": [{"name": "text", "title": "Not metni", "max_length": 500}],
                "requires_fields": [{"target": {"kind": "textbox", "labels": ["Not"]}, "param": "text"}],
                "outcome": {
                    "evidence": {"kind": "status_text"},
                    "success": {"mode": "prefix", "text": "Kaydedildi (Not #"},
                    "failures": [
                        {
                            "match": {"mode": "equals", "text": "Oturumunuz sona erdi."},
                            "error_class": "SESSION_EXPIRED",
                        },
                        {
                            "match": {"mode": "equals", "text": "Kayıt başarısız."},
                            "error_class": "BUSINESS_VALIDATION",
                        },
                    ],
                    "unknown": [{"mode": "equals", "text": "Yanıt alınamadı — işlem sonucu bilinmiyor"}],
                },
                "reconcile": {
                    "reload": True,
                    "evidence": {"kind": "list_items", "name": "Mevcut notlar"},
                    "match": {"mode": "contains", "text": ": {text} ("},
                },
            },
            "lab.submit_application": {
                "action_id": "lab.submit_application",
                "title": "Başvuruyu gönder (deney, veri değiştirir ve özet ekranına geçer)",
                "target": {"kind": "button", "labels": ["Gönder"], "region": "Teminat"},
                "effect": "mutating",
                "retry_safe": False,
                "params": [
                    {"name": "case_no", "title": "Vaka No", "max_length": 40},
                    {"name": "amount", "title": "Teminat tutarı", "max_length": 40},
                ],
                "requires_fields": [
                    {
                        "target": {"kind": "textbox", "labels": ["Teminat Tutarı"], "region": "Teminat"},
                        "param": "amount",
                    }
                ],
                "outcome": {
                    "evidence": {"kind": "status_text"},
                    "success": {"mode": "prefix", "text": "Başvuru alındı (No #"},
                    "unknown": [{"mode": "equals", "text": "Yanıt alınamadı — işlem sonucu bilinmiyor"}],
                },
                "reconcile": {
                    "reload": True,
                    "evidence": {"kind": "list_items", "name": "Gönderilen başvurular"},
                    "match": {"mode": "contains", "text": ": {case_no} — {amount} ("},
                },
            },
            "lab.save_guarantor": {
                "action_id": "lab.save_guarantor",
                "title": "Kefil bölümünü kaydet (deney, yalnız ekran)",
                "target": {"kind": "button", "labels": ["Kaydet"], "region": "Kefil"},
                "effect": "non_mutating",
                "retry_safe": True,
                "params": [],
                "outcome": {
                    "evidence": {"kind": "status_text"},
                    "success": {"mode": "prefix", "text": "Bilgiler kaydedildi"},
                    "failures": [
                        {
                            "match": {"mode": "equals", "text": "Ad Soyad zorunludur"},
                            "error_class": "BUSINESS_VALIDATION",
                        }
                    ],
                },
            },
        },
        "blockers": [
            {
                "blocker_id": "lab.case_updated_notice",
                "dialog_name": "Uyarı",
                "text": {"mode": "contains", "text": "Bu vaka başka bir kullanıcı tarafından güncellendi."},
                "button_label": "Tamam",
            }
        ],
        "profile": {
            "session_lost_path_prefixes": ["/login"],
            "session_lost_texts": [{"mode": "equals", "text": "Oturumunuz sona erdi."}],
        },
    }
)
