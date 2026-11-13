# ADR 0011 — R4: Çok ekranlı işlemler ve kontrollü ekran geçişleri

Tarih: 2026-11-06 · Durum: kabul edildi (lab kapsamında doğrulandı; gerçek Pega/SSO doğrulanmadı)

## Bağlam
R3'te bir işlem tek ekrana bağlıydı ve ekran değişince sonraki adımlar reddediliyordu. Gerçek iş akışları birden
fazla ekranı kapsar. Ancak çalışma anında ekran, rota veya geçiş kararı verilmemelidir; buna model kararı da dahil.

## Karar
1. **Sözleşme (catalog-v3, v2 ile geriye uyumlu):**
   - Ekranlar: `screen` (başlangıç) ve `extra_screens`.
   - `transitions`, `TransitionDef` ile tanımlanır: kaynak, hedef, tetikleyici, `timeout_ms` (500–60000) ve
     tamamlanma koşulu (`completion`: hedef ekran + kayıt bağlamı).
   - `start_context` başlangıç ekranındaki kayıt bağlamını tutar.
   - Adımlar `screen_id` (beklenen ekran) ve `transition_id` (ekran değiştiren adım) taşır.
2. **Tetikleyici ile iş etkisi ayrıdır:**
   - `control` tetikleyici yalnız ekran değiştiren onaylı bir düğme veya sekmedir ve `follow_transition` komutuyla
     çalışır; iş etkisi yoktur.
   - `approved_action` tetikleyicide adımın onaylı aksiyonu iş etkisini taşır (sonuç kanıtı ve uzlaştırma); geçiş
     ayrıca doğrulanır.
3. **Hash ve sürüm:**
   - Tek ekranlı tanımın kanonik içeriği R3 ile birebir aynıdır, catalog-v2 hash'leri değişmez.
   - Çok ekranlı tanım `screens_ref`, `transitions` ve `start_context` ekler; revizyon `schema_version=catalog-v3`
     olur.
   - Okuyucu v2 ve v3'ü kabul eder; v1 → `migration_required`; tanınmayan anahtar → `unsupported_schema`.
   - Bütün ekran revizyonları manifestoya, geçişler ve ekran referansları onay hash'ine girer.
4. **Yürütme:**
   - Etkin ekran ve kayıt bağlamı her sayfa adımından önce güncel gözlemle doğrulanır.
   - Geçiş adımları:
     1. Kaynak doğrulanır, tetikleyici tekil çözülür.
     2. Niyet ve `DISPATCHED` kaydedilir; sonra tek tıklama yapılır.
     3. Etkin ekran boşaltılır; böylece eski ekran kuralı meşru geçişi engellemez.
     4. Hedef ekran ve bağlam `timeout_ms` içinde DOM/frame değişimine bağlı beklenir; sabit sleep yok.
   - Tekrar tıklama yoktur.
   - Hata sınıfları: `TRANSITION_TIMEOUT` (kaynak hâlâ görünüyor), `UNEXPECTED_SCREEN`, belirsizlikte
     `PAUSED_AMBIGUOUS`, `RECORD_CONTEXT_MISMATCH`.
   - Geçişli aksiyonda kanıt sayfa düzeyinde okunur ve hedef ekranın görünmesi başarı sayılmaz.
   - Belirsiz sonuçta mevcut uzlaştırma kullanılır. İş etkisi doğrulanıp hedefe geçilmezse
     `TRANSITION_NOT_COMPLETED` döner; yeniden gönderim yoktur.
   - **Resume:**
     - Geçişler ve aksiyonlar yeniden oynatılmaz.
     - Son başarılı ekran segmentinin ekranı ve bağlamı doğrulanır; yalnız o segmentin idempotent `ensure_*`
       adımları yeniden kurulur.
     - Doğrulanamazsa `context_revalidation_failed` döner.
5. **Tasarımcı:**
   - Ekran ekleme ve güncelleme yapılabilir.
   - Adım başına ekran seçilir.
   - Geçiş tanımlanır; tetikleyici adayı yalnız çözülür, tıklanmaz.
   - Ekran değiştiren denemeler açık onay ister.
   - Ekran veya geçiş değişikliği ilgili adımları yeniden onaya döndürür; test ve onay hash'le geçersizleşir.
6. **Changes:** her ekran ortak çekirdekle değerlendirilir. Paylaşılan ekran (`screen:<id>`) ve geçiş tetikleyicisi
   (`transition:<id>`) etki nedenidir.

## Sonuçlar
- Rota doğrusaldır: dallanma ve koşullu geçiş yoktur. Koşullu akışlar mevcut kontrollü birleştirme fazındadır.
- Geçiş tetikleyicisi düğme veya sekmeyle sınırlıdır; bağlantı ve menü yoktur.
- Ortama bağlı başlangıç adresi kataloğa konmaz. Ekran, adres değil anlamsal kanıtla tanınır. Bu nedenle yeni
  ortam ayarı gerekmedi.
