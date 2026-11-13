# ADR 0005 — P4 Katalog Tasarımcısı (yerel taslak, modelsiz yönlendirilmiş hazırlama)

Tarih: 2026-11-05 · Durum: kabul

## Kararlar
1. **Taslak modeli** `OperationDraft` (domain/catalog.py): parametreler (user_input | prior_output |
   approved_constant | secret_ref), elemanlar (`element_id` slug + anlam + TargetSpec + provenance), adım kartları.
   Kalıcı tanımda selector/id/frame sırası/koordinat/URL yok. Deneme ve test değerleri taslakta saklanmaz.
2. **Adım kartı durum makinesi** docs/04 sırasıyla; `meaning_and_target_confirmed` ancak anlam, hedef, etki ve
   parametre ayrı ayrı işaretlenince. Tanım değişince onay ve deneme sıfırlanır.
3. **Canonical içerik hash'i** yalnız tanımsal alanlardan (durum/deneme/provenance hariç). Yeni oturum testi
   hash'e bağlıdır; test sonrası değişiklik `fresh_session_test_stale` üretir (P5 onayı da bu hash'e bağlanacak).
4. **Kural tabanlı öneri** (domain/authoring.py): Türkçe fiil → komut; adaylar etiket/bağlam token örtüşmesiyle
   puanlanır, eşit puanlılar birlikte gösterilir, ilk aday seçilmez. Seçilen adaydan türetilen TargetSpec
   ekranda P2 ile yeniden çözülür; tekil değilse seçim reddedilir (`target_not_unique`).
5. **Deneme** P3 RunService ile; veri değiştiren adım açık etki onayı ister. "Sistem doğrulaması" P3 sonuç
   kontrolüdür (assert/outcome); kullanıcı sonucu ancak sistem doğruladıktan sonra onaylayabilir.
6. **Yeni oturum testi** yeni browser context açar, başlangıç ekranına gider, derlenmiş işlemi çalıştırır, oturumu kapatır.
7. **Depo:** `DraftRepository` portu + yerel dosya adapteri, revizyon kontrollü (409). Yayımlanmış katalog P5.
