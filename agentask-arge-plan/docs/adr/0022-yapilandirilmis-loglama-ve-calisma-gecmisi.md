# ADR 0022 — Yapılandırılmış loglama ve anlaşılır çalışma geçmişi

Tarih: 2026-11-08. Durum: kabul edildi. Yeni log platformu, kuyruk veya yeni ayar eklenmedi.

## Kararlar
1. **Tek çıkış:** Loglar stdout'a JSON satırı olarak yazılır (`LOG_LEVEL`, `LOG_FORMAT`). Uygulama log dosyası tutmaz; saklama
   süreci/konteyner altyapısının işidir.
2. **Bağlam:** `correlation_id`, `actor`, `run_id`, `step_id` `contextvars` ile taşınır (`application/observability.py`).
   Eşzamanlı istekler karışmaz; arka plan run görevi başlatan isteğin bağlamını devralır. Run, korelasyon numarasını
   kalıcı saklar; yeniden başlatma sonrası da aynı numara kullanılır.
3. **Alan izinli listesi:** Çıktıya yalnız `infrastructure/logging.ALLOWED_FIELDS` yazılır. Bilinmeyen alan düşer; değer, prompt,
   DOM ve başlık loga taşınamaz.
4. **İstisna:** Yabancı istisnaların mesajı yazılmaz (Playwright çağrı günlüğü, pydantic girdi değeri, sürücü URI'si
   içerebilir). Tür, neden zinciri ve `dosya:satır:fonksiyon` yazılır. Yalnız projenin kendi güvenli mesajları maskeden
   geçirilerek yazılır. Serbest metinler `domain/redaction.py`'den geçer; bu son savunmadır, tek koruma değildir.
5. **Hata ayrımı ve tek kayıt:** `error_kind` = `business` (beklenen) veya `software`. Bir istek için tek `http_request`
   kaydı, bir run için tek `run_finished` kaydı yazılır; hata kodu bu kayıtlarda bulunur, katmanlarda tekrarlanmaz.
6. **Kullanıcı olayları (`category=audit`):** `draft_saved`, `draft_approved`, `release_published`, `run_started`,
   `run_cancel_requested`, `run_resume_requested`, `interruption_resolved`, `run_finished`, `run_recovered`. Hepsi işlem
   kalıcı olduktan sonra üretilir. Kimlik olarak yalnız `user_id` yazılır. Ayrı denetim deposu eklenmedi; kurumsal denetim
   gerekirse bu olaylar log altyapısından alınır veya AuditPort eklenir.
7. **Geçmiş:** Mevcut run deposu (`RUN_DIRECTORY`) ve `/runs` ekranı kullanılır. `RunOut.summary` kod tablolarından üretilir;
   alan değeri içermez. Sahiplik denetimi aynen korunur.

## Sonuçlar
- Başarılı `GET` ve statik istekler `DEBUG` seviyesindedir; `INFO`'da yazılmaz. uvicorn erişim logu kapalıdır (sorgu dizgisi içerir).
- Doğal metinde geçen müşteri adı redaksiyonla tanınamaz; koruma izinli alan ve yabancı mesajın yazılmamasıyla sağlanır.
- Yerel dosya deposu tek sunucu içindir; kalıcı disk olmadan konteyner yeniden oluşunca geçmiş kaybolur.
