"""Uygulama katmanı hata sınıfları; presentation bunları error envelope'a çevirir."""

from __future__ import annotations


class ApplicationError(Exception):
    code = "application_error"
    safe_message = "İşlem tamamlanamadı."
    retryable = False

    def __init__(self, safe_message: str | None = None, details: dict[str, object] | None = None) -> None:
        if safe_message is not None:
            self.safe_message = safe_message
        # Yalnız redakte, istemciye gösterilebilir ayrıntılar (değer/secret yok).
        self.details: dict[str, object] = dict(details or {})
        super().__init__(self.safe_message)


class Unauthenticated(ApplicationError):
    code = "unauthenticated"
    safe_message = "Kimlik doğrulanamadı."


class Forbidden(ApplicationError):
    code = "forbidden"
    safe_message = "Bu işlem için yetkiniz yok."


class DependencyUnavailable(ApplicationError):
    code = "dependency_unavailable"
    safe_message = "Gerekli bir bağımlılık şu anda kullanılamıyor."


class SessionNotFound(ApplicationError):
    # Başka kullanıcının oturumu da "bulunamadı" döner; varlığı sızdırılmaz.
    code = "session_not_found"
    safe_message = "Tarayıcı oturumu bulunamadı."


class SessionBusy(ApplicationError):
    code = "session_busy"
    safe_message = "Bu tarayıcı oturumunda başka bir işlem sürüyor."


class SessionLimitReached(ApplicationError):
    code = "session_limit_reached"
    safe_message = "Açık tarayıcı oturumu sınırına ulaşıldı."


class NavigationNotAllowed(ApplicationError):
    code = "navigation_not_allowed"
    safe_message = "Bu adrese gitmeye izin verilmiyor."


class ServiceShuttingDown(ApplicationError):
    code = "service_shutting_down"
    safe_message = "Servis kapanıyor; yeni işlem başlatılamaz."


class CandidateStale(ApplicationError):
    # Ekran/frame değişti veya yeni gözlem alındı; eski aday kimliği kabul edilmez.
    code = "candidate_stale"
    safe_message = "Seçilen aday artık geçerli değil; ekranı yeniden gözlemleyin."


class PlanInvalid(ApplicationError):
    code = "plan_invalid"
    safe_message = "İşlem planı geçersiz veya desteklenmiyor."


class IdempotencyConflict(ApplicationError):
    code = "idempotency_conflict"
    safe_message = "Aynı istek kimliği farklı içerikle daha önce kullanıldı."


class RunNotFound(ApplicationError):
    code = "run_not_found"
    safe_message = "Çalıştırma bulunamadı."


class RunNotResumable(ApplicationError):
    code = "run_not_resumable"
    safe_message = "Bu çalıştırma bu durumda devam ettirilemez."


class DraftNotFound(ApplicationError):
    code = "draft_not_found"
    safe_message = "Taslak bulunamadı."


class DraftConflict(ApplicationError):
    code = "draft_conflict"
    safe_message = "Taslak başka bir düzenlemeyle değişti; yenileyip tekrar deneyin."


class TargetNotUnique(ApplicationError):
    code = "target_not_unique"
    safe_message = "Seçilen hedefin tanımı ekranda tekil değil; bölüm/frame bağlamı ekleyin."


class EffectNotAcknowledged(ApplicationError):
    code = "effect_not_acknowledged"
    safe_message = "Bu deneme veri değiştirebilir; etkisini açıkça onaylayın."


class DraftNotReady(ApplicationError):
    code = "draft_not_ready"
    safe_message = "Taslak bu işlem için hazır değil."


class ContentConflict(ApplicationError):
    code = "content_conflict"
    safe_message = "Aynı işlem revizyonu farklı içerikle zaten yayımlanmış."


class StaleApproval(ApplicationError):
    code = "stale_approval"
    safe_message = "Onay yok veya içerik onaydan sonra değişti; yeniden onay gerekli."


class PublishConflict(ApplicationError):
    code = "publish_conflict"
    safe_message = "Aktif yayın bu sırada değişti; yeniden deneyin."
    retryable = True


class ReleaseSuperseded(ApplicationError):
    code = "release_superseded"
    safe_message = "Bu yayın artık etkin değil; talebi yeniden yorumlayın."
