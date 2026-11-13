# Güven sınırları ve işletim

## Kimlik ve politika
Roles: operator, designer, publisher (ayrı yetenekler; kurum kararıyla aynı kişide olabilir). Backend her endpoint/use case'de kontrol eder. Run/session/draft owner check. İşlem anında application/resource/record scope kontrolü. Yayın onayı kullanıcı yetkisi sağlamaz.
Kimlik provider portu gerçek JWT/SSO doğrulamasını açık bırakır; doğrulanmamış JWT decode auth kabul edilmez. Dev impersonation production'da çalışamaz. Cookie tabanlı auth varsa CSRF; CORS allowlist; WebSocket/SSE sahibine özel.
Allowed origins kontrolü navigation/popup/redirect ve metadata/LLM endpoint için uygulanır. Kurum içi olması otomatik trusted instruction yapmaz. Credential veya ham DOM dış servise taşınmaz.

## Hassas veri
Parola ve secret değerleri model, prompt history, DOM inventory, trace veya screenshots'a girmez. Redaksiyon kayıt öncesi yapılır; sonradan regex ile temizlemeye güvenme. Trace full DOM/network capture sensitive olabilir: varsayılan kapalı; izinli test fixture veya doğrulanmış masking ile kullan.
Loglarda düşünce zinciri değil kısa karar özeti, seçilen tanım/aday, doğrulama sonucu ve hata sınıfı tutulur. Kullanıcı kayıt değerleri gerekmedikçe saklanmaz. SecretRef resolver değeri sadece yürütücüye verir.
ArtifactStore erişimi yetkili, retention configurable; path traversal ve public static serve yok. Screenshot üretimi varsayılan kapalı; açık olduğunda redaksiyon ve erişim sınırı zorunlu.

## Log ve çalışma geçmişi (uygulanan; ADR 0022)
- **Loglar:** stdout, satır başına bir JSON. İnceleme: `agentask | jq 'select(.correlation_id=="…")'`; kullanıcı olayları için `select(.category=="audit")`. Konteynerde aynı çıktı platform log aracından okunur.
- **Yazılmayanlar:** alan değerleri, parola, token, cookie, Authorization, bağlantı sırları, tam prompt, ham DOM, sorgu dizgisi, yabancı istisna mesajı.
- **Çalışma geçmişi:** `RUN_DIRECTORY` altında run başına JSON; yeniden başlatmada korunur, otomatik silinmez, kalıcı disk gerekir. `/runs` ekranında yalnız sahibi görür.

## Çalışma kaydı
run_id/correlation_id, actor ref, application/env, release hash, adapter/compiler version, step state, target evidence summary, dispatch/reconciliation outcome, timings, recoveries.
Teknik teşhis kayıtları ve iş audit olayları ayrı amaç taşır. Her click için kurumsal audit kaydı üretme; iş başlangıcı/tamamlanması/yayın ve yetki reddi gibi anlamlı olaylar yeterli. Mevcut SQL audit sistemine bağlantı zorunlu MVP bağımlılığı değildir; AuditPort ile açık bırakılabilir.

## Sağlık ve kapanış
Health liveness process; readiness Mongo/worker gibi etkin özelliklerin bağımlılığına göre. LLM kapalıysa readiness'i bozmaz. Graceful shutdown yeni dispatch'i durdurur; in-flight write durumunu unknown olarak kaydetmeden başarısız sayma.
Test sırasında dış telemetri yok. Browser/LLM/Mongo kapasite limitleri .env. Her request için yeni browser açma; lifecycle ve cleanup testleri yap.
