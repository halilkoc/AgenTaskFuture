# R4 — Çok ekranlı işlemler ve kontrollü ekran geçişleri (uygulama planı)

Dayanak: CLAUDE.md, docs/02 (Screen/Operation), ADR 0010 (R3), docs/14 R3 bölümü.

## Sözleşme (catalog-v3, v2 ile geriye uyumlu)
- `OperationDraft.screen`: başlangıç ekranı (R3'teki alan).
- `extra_screens`: diğer ekranlar; `ScreenDef`, R3'teki model.
- `transitions: [TransitionDef]`:
  - `transition_id`, `from_screen`, `to_screen`;
  - `trigger`: `control` (yalnız ekran değiştiren onaylı düğme/sekme TargetSpec'i) veya `approved_action` (adımın
    onaylı aksiyonu hem iş etkisi yaratır hem ekran değiştirir);
  - `timeout_ms` (sınırlı);
  - `completion`: hedef ekran tanınmalı ve bağlam koşulları (`ContextCheck`: alan + değer şablonu, ör. Vaka No =
    `{vaka_no}`) sağlanmalı.
- `start_context`: başlangıç ekranı için kayıt bağlamı koşulları.
- `StepCard.screen_id` (beklenen ekran; boşsa başlangıç ekranı) ve `StepCard.transition_id` (ekran değiştiren adım).
  Yeni işlem `follow_transition` (yalnız control tetikleyicili geçiş).
- **Hash:** tek ekranlı tanımın kanonik içeriği R3 ile birebir aynıdır; v2 hash'leri değişmez. Çok ekranlı tanım
  `screens_ref` ve `transitions` anahtarları ekler; revizyon `schema_version=catalog-v3`.
  - Okuyucu v2 ve v3'ü kabul eder.
  - v1 → `migration_required`.
  - Bilinmeyen sürüm → `unsupported_schema`.
- **Statik rota doğrulaması** (`route_issues`):
  - Adımlar sırayla ekranları izler; geçiş adımının kaynağı o anki ekran olmalı, adımdan sonra hedef ekran etkin olur.
  - Geçiş yalnız bir adımda kullanılır.
  - Eleman bölgeleri adımın ekranında bulunmalı.
  - Her ekranın işaretleri yalnız o ekranın hedeflerinden oluşamaz.

## Komutlar
- `assert_screen` + isteğe bağlı `context`.
- Yeni `follow_transition`: `{transition_id, trigger, to_screen, timeout_ms, context}`.
- `invoke_approved_action` + isteğe bağlı `transition` (aynı alanlar, trigger hariç).

## Yürütücü
- Etkin ekran ve bağlamı her sayfa adımından önce yeniden doğrulanır (R3 + bağlam).
- **Geçiş:**
  1. Kaynak doğrulanır, tetikleyici tekil çözülür.
  2. Niyet ve `DISPATCHED` kaydedilir; sonra tek tıklama yapılır.
  3. Etkin ekran boşaltılır.
  4. Hedef ekran `timeout_ms` içinde `wait_for_change` ile beklenir (sleep yok); sonra bağlam koşulları kontrol edilir.
  5. Tekrar tıklama yoktur.
  6. Hata ayrımı: `TRANSITION_TIMEOUT` (kaynak hâlâ tanınıyor → geçiş olmadı), `UNEXPECTED_SCREEN` (ne kaynak ne
     hedef), belirsiz → `PAUSED_AMBIGUOUS`, `RECORD_CONTEXT_MISMATCH`.
- **Yazma etkili geçiş:**
  - Sonuç kanıtı sayfa düzeyinde okunur; hedef ekranın görünmesi başarı sayılmaz.
  - Belirsiz sonuçta mevcut uzlaştırma kullanılır. Uzlaştırma "uygulandı" derse ama hedef ekrana geçilmemişse
    `TRANSITION_NOT_COMPLETED` döner; yeniden gönderim yok.
- **Resume:**
  - Geçişler ve onaylı aksiyonlar asla yeniden oynatılmaz.
  - Yalnız son başarılı geçişten sonraki segmentin ekranı ve bağlamı doğrulanır; o segmentin idempotent `ensure_*`
    adımları yeniden kurulur.
  - Doğrulanamazsa `context_revalidation_failed`.

## Tasarımcı / Changes / Asistan
- Tasarımcı:
  - Ekranlar `screen_id` ile eklenir; ilk eklenen başlangıç ekranıdır.
  - Adım için ekran seçilir; geçiş ekle (trigger adayı güncel gözlemden; tamamlanma koşulu alan + şablon).
  - Geçiş adımının denemesi açık "ekran değişir" onayı ister.
  - Ekran veya geçiş değişince ilgili adımlar yeniden onaya döner, test/onay hash'le geçersizleşir.
- Changes: işlemin bütün ekranları için karar; paylaşılan ekran ve tetikleyici bağımlılığı etki analizine girer.
- Asistan: önizlemede ekran ve geçiş satırları, iş etkisi ile ekran etkisi ayrı gösterilir.

## Laboratuvar
- `/wizard/{vaka}` sihirbazı (yalnız test ikamesi):
  - müşteri ekranı → (SPA "Devam") teminat ekranı (iç içe, yeniden oluşan frame) → ("Gönder", yazma + gezinme)
    özet ekranı.
  - Senaryo bayrakları: gecikme, beklenmeyen hedef, yinelenen bölge, farklı vaka, yanıt kaybı, bilinmeyen pencere.
  - Sunucu sayaçları: geçiş tetiklemesi ve gönderim.

## Testler
- Birim:
  - rota/hash/uyumluluk;
  - yayın (çok ekran manifesti);
  - yasak işaret (zorunlular mevcut + yalnız yasak eklendi).
- Tarayıcı:
  - 3 ekran başarılı;
  - gecikmeli hedef + tek tetikleme;
  - beklenmeyen hedef;
  - zaman aşımı;
  - yinelenen;
  - eksik tarama;
  - yanlış vaka;
  - yanıt kaybı;
  - resume yanlış ekran / doğru ekran;
  - yasak işaret.
- Mongo roundtrip (v2 + v3, ham belgeler değişmez).
- E2E: tasarım → deneme → yeni oturum testi → onay → yayın → asistan.
- Regresyon: tam paket.
