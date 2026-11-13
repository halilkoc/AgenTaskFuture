"""Çalışmanın kullanıcıya anlaşılır özeti ve log alanları. Yalnız kod tablolarından ve katalog etiketlerinden
üretilir; adım değerleri (yazılan/okunan/seçilen) kullanılmaz."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agentask.domain.runtime import Run, RunStatus, StepRecord, StepState

_RETRY = "Ekranı kontrol edip işlemi yeniden başlatın."
ERROR_TEXT: dict[str, tuple[str, str]] = {
    "FRAME_CHANGED": ("Ekran işlem sırasında yenilendi.", _RETRY),
    "TARGET_NOT_READY": ("Alan süre içinde kullanılabilir olmadı.", _RETRY),
    "TARGET_AMBIGUOUS": (
        "Ekranda bu tanıma uyan birden fazla alan var; yanlış alana işlem yapılmadı.",
        "Doğru kaydın ve ekranın açık olduğunu kontrol edin; sorun sürerse tasarımcıya bildirin.",
    ),
    "TARGET_NOT_FOUND": ("Beklenen alan ekranda bulunamadı.", "Doğru ekranın açık olduğunu kontrol edin."),
    "CONTROL_UNSUPPORTED": (
        "Bu ekrandaki kontrol türü desteklenmiyor.",
        "İşlemin tanımı için tasarımcıya başvurun.",
    ),
    "RECORD_NOT_LOADED": ("Aranan kayıt listede bulunamadı.", "Kayıt bilgisini kontrol edin."),
    "SESSION_EXPIRED": ("Uygulama oturumu sona erdi.", "Uygulamaya yeniden giriş yapıp işlemi sürdürün."),
    "KNOWN_OVERLAY": (
        "Ekranda işlemi engelleyen bir pencere var.",
        "Pencereyi kontrol edip işlemi sürdürün.",
    ),
    "UNKNOWN_DIALOG": (
        "Ekranda tanınmayan bir pencere açıldı; otomatik kapatılmadı.",
        "Pencereyi siz değerlendirin, ardından işlemi sürdürün.",
    ),
    "BUSINESS_VALIDATION": (
        "Girilen seçenek veya bilgi uygulamada geçerli değil.",
        "Bilgiyi güncel ekrandaki seçeneklerle karşılaştırıp yeniden başlatın.",
    ),
    "WRITE_RESULT_UNKNOWN": (
        "İşlem gönderildi ancak sonucu doğrulanamadı; yeniden gönderilmedi.",
        "Uygulamada sonucu kontrol edin. İşlemi kontrol etmeden tekrarlamayın.",
    ),
    "VERIFICATION_FAILED": (
        "İşlem yapıldı ama beklenen sonuç görülmedi.",
        "Uygulamadaki durumu kontrol edin; tekrar başlatmadan önce sonucu doğrulayın.",
    ),
    "BUDGET_EXCEEDED": ("İşlem izin verilen süre veya deneme sınırını aştı.", _RETRY),
    "POLICY_DENIED": ("Bu işlem politika gereği çalıştırılamaz.", "Yetkiliye başvurun."),
    "SCREEN_NOT_RECOGNIZED": (
        "Açık ekran beklenen ekran olarak tanınmadı; işlem yapılmadı.",
        "Doğru ekranı açıp yeniden başlatın.",
    ),
    "TRANSITION_TIMEOUT": (
        "Beklenen ekran süre içinde açılmadı; geçiş yeniden tetiklenmedi.",
        "Ekranı kontrol edip yeni bir çalıştırma başlatın.",
    ),
    "UNEXPECTED_SCREEN": ("Beklenmeyen bir ekran açıldı.", "Ekranı kontrol edin; sonucu doğrulayın."),
    "TRANSITION_NOT_COMPLETED": (
        "İşlem uygulandı ancak beklenen ekrana geçilmedi.",
        "Kalan adımlar için ekranı kontrol edin. İşlemi tekrarlamayın.",
    ),
    "RECORD_CONTEXT_MISMATCH": (
        "Açık kayıt istenen kayıt değil; işlem yapılmadı.",
        "Doğru kaydı açıp yeniden başlatın.",
    ),
    "TARGET_BLOCKED": (
        "Alan açık bir pencerenin veya katmanın arkasında kaldı; işlem yapılmadı.",
        "Pencereyi kapatıp işlemi sürdürün.",
    ),
    "NEW_WINDOW": (
        "Yeni bir pencere açıldı; otomatik geçilmedi.",
        "Pencereyi değerlendirip işlemi sürdürün.",
    ),
    "PRIOR_OUTPUT_UNAVAILABLE": (
        "Önceki adımdan beklenen bilgi alınamadı; işlem yapılmadı.",
        "Kaynak alanı kontrol edip yeniden başlatın.",
    ),
}
_REASON_TEXT: dict[str, tuple[str, str]] = {
    "process_restart": (
        "Uygulama işlem sırasında yeniden başladı.",
        "Uygulamadaki durumu kontrol edip işlemi sürdürün.",
    ),
    "process_restart_before_start": (
        "Uygulama işlem başlamadan yeniden başladı.",
        "İşlemi yeniden başlatın.",
    ),
    "internal_error": (
        "Beklenmeyen bir sistem hatası oluştu.",
        "Uygulamadaki durumu kontrol edin ve destek numarasıyla destek ekibine bildirin.",
    ),
    "run_duration_exceeded": ("İşlem izin verilen süreyi aştı.", _RETRY),
    "shutdown": ("Uygulama kapatıldığı için işlem duraklatıldı.", "Uygulama açılınca işlemi sürdürün."),
    "context_revalidation_failed": (
        "Devam için beklenen ekran veya kayıt doğrulanamadı; işlem yapılmadı.",
        "Doğru ekranı açıp yeniden deneyin.",
    ),
}
_CANCEL_TEXT = {
    "user": "İşlem kullanıcı tarafından durduruldu.",
    "system_timeout": "İşlem süre sınırını aştığı için sistem tarafından durduruldu.",
}
_CANCEL_REASON_TEXT = {"cancelled_during_restart": "Uygulama yeniden başlarken işlem durduruldu."}
_FALLBACK = ("İşlem tamamlanamadı.", "Destek numarasıyla destek ekibine başvurun.")
_STAGE = {
    "assert_screen": "Ekran doğrulama",
    "ensure_value": "Alana değer yazma",
    "ensure_choice": "Listeden seçim",
    "ensure_checked": "Onay kutusu",
    "ensure_choices": "Çoklu seçim",
    "ensure_date": "Tarih yazma",
    "upload_file": "Dosya yükleme",
    "read": "Bilgi okuma",
    "activate_tab": "Sekme açma",
    "find_record": "Kayıt bulma",
    "invoke_approved_action": "Onaylı işlem",
    "follow_transition": "Ekran geçişi",
    "assert_condition": "Sonuç kontrolü",
    "evaluate_condition": "Koşul kontrolü",
}
_OUTCOME = {
    RunStatus.COMPLETED: "success",
    RunStatus.FAILED: "failed",
    RunStatus.OUTCOME_UNKNOWN: "unknown",
    RunStatus.CANCELLED: "cancelled",
    RunStatus.PAUSED_SESSION: "paused",
    RunStatus.PAUSED_AMBIGUOUS: "paused",
    RunStatus.PAUSED_BLOCKED: "paused",
}
_OPEN = {StepState.SUCCEEDED, StepState.SKIPPED, StepState.PENDING}


def outcome_of(status: RunStatus) -> str:
    return _OUTCOME.get(status, "in_progress")


def run_kind(run: Run) -> str:
    if run.binding is not None:
        return "assistant"
    if run.request_id.startswith("trial-"):
        return "trial"
    return "fresh_test" if run.request_id.startswith("fresh-") else "manual"


def failed_step(run: Run) -> StepRecord | None:
    """Sorunun oluştuğu adım: hata kodu taşıyan veya tamamlanmamış ilk adım."""
    return next((s for s in run.steps if s.error_class and s.state is not StepState.SUCCEEDED), None) or next(
        (s for s in run.steps if s.state not in _OPEN), None
    )


def run_log_fields(run: Run) -> dict[str, Any]:
    binding = run.binding or {}
    return {
        "run_id": run.run_id,
        "actor": run.owner_id,
        "run_kind": run_kind(run),
        "application_id": binding.get("application_id"),
        "operation_id": binding.get("operation_id"),
        "release_id": binding.get("release_id"),
        "revision": binding.get("revision"),
    }


def _stage(step: StepRecord) -> str:
    command = step.command
    name = _STAGE.get(str(command.get("op")), "İşlem adımı")
    screen = command.get("screen") or command.get("to_screen")
    target = command.get("target") or command.get("trigger") or (command.get("condition") or {}).get("target")
    what = None
    if isinstance(target, dict) and target.get("labels"):
        region = target.get("region")
        what = f"{region} › {target['labels'][0]}" if region else str(target["labels"][0])
    elif isinstance(screen, dict) and screen.get("title"):
        what = str(screen["title"])
    return f"{step.index + 1}. adım · {name}{f' · “{what}”' if what else ''}"


@dataclass(frozen=True, slots=True)
class RunSummary:
    title: str
    failed_stage: str | None
    reason: str | None
    next_step: str | None
    correlation_id: str | None


def _title(run: Run) -> str:
    if run.title:
        return run.title
    kind = run_kind(run)
    if kind == "assistant":
        return str((run.binding or {}).get("operation_id") or "Birleşik görev")
    return {"trial": "Tasarım denemesi", "fresh_test": "Yeni oturum testi"}.get(
        kind, "Elle başlatılan deneme"
    )


def summarize(run: Run) -> RunSummary:
    title = _title(run)
    if run.status in {RunStatus.CREATED, RunStatus.RUNNING, RunStatus.CANCEL_REQUESTED, RunStatus.COMPLETED}:
        return RunSummary(title, None, None, None, run.correlation_id)
    if run.status is RunStatus.CANCELLED:
        step = failed_step(run)
        reason = _CANCEL_TEXT.get(run.cancelled_by or "") or _CANCEL_REASON_TEXT.get(run.status_reason or "")
        return RunSummary(
            title,
            _stage(step) if step else None,
            reason or "İşlem durduruldu (durduran bu eski kayıtta tutulmamış).",
            "Başlamış adımlar geri alınmaz; gerekiyorsa uygulamada kontrol edin.",
            run.correlation_id,
        )
    step = failed_step(run)
    code = step.error_class if step else None
    reason, next_step = ERROR_TEXT.get(code or "") or _REASON_TEXT.get(run.status_reason or "") or _FALLBACK
    return RunSummary(title, _stage(step) if step else None, reason, next_step, run.correlation_id)


def summary_dict(run: Run) -> dict[str, Any]:
    return asdict(summarize(run))
