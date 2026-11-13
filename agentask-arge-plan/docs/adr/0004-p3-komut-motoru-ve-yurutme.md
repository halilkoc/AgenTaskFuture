# ADR 0004 — P3 kontrol adapterleri, sınırlı komut motoru, yürütme ve uzlaştırma

Tarih: 2026-11-05 · Durum: kabul

## Kararlar
1. **Adapter + sürücü ayrımı.** Adapter mantığı (`application/controls.py`: textbox, native select, custom
   combobox, tab, table) yalnız P2 adayı ve `ControlDriver` portuna bağlıdır; Playwright ilkelleri
   `infrastructure/browser/driver.py`'dadır. Her adapter mevcut durumu okur, istenen durum zaten varsa işlem
   yapmaz, sonrasını doğrular; desteklenmeyen kontrol (hassas alan, input tabanlı combobox) açıkça reddedilir.
2. **Komut dili** yedi tipli komuttur (discriminated union, extra=forbid). `invoke_approved_action` yalnız
   kayıtlı aksiyon kimliğiyle çalışır; aksiyon şeması hedef (düğme), etki, sonuç kanıtı ve veri değiştiren
   aksiyonda uzlaştırma okumasını zorunlu tutar. Bu aşamada yalnız lab aksiyonları (`APPROVED_ACTION_SET=lab`).
3. **Durum makineleri** (`domain/runtime.py`): geçersiz geçiş hata üretir. Gönderilmiş adım `prepared`'a
   dönemez; `outcome_unknown` yalnız uzlaştırma kanıtıyla `succeeded` olur.
4. **Dispatch sınırı:** niyet + taban (uzlaştırma listesindeki eşleşme sayısı) checkpoint → `dispatched`
   checkpoint → tıklama → `verifying` → sonuç kanıtı. Belirsizse sayfa yenilenir, eşleşme sayısı tam 1
   artmışsa başarılı; aksi halde `outcome_unknown` ve durma. Non-idempotent aksiyon asla yeniden gönderilmez.
   UI tıklamasıyla exactly-once iddia edilmez; lab'da tekillik not metni + liste sayımına dayanır.
5. **Checkpoint deposu portu** + yerel dosya adapteri (atomik yazma). Açılışta yarım run'lar:
   gönderilmiş adım → `outcome_unknown`, diğerleri → `paused_session`. Browser nesneleri geri yüklenmez;
   devam yeni oturumda engelleyici/oturum kontrolü, uzlaştırma ve güvenli bağlam adımlarının yeniden
   uygulanmasıyla başlar.
6. **Toparlanma:** frame/eleman bayatlığı → yeniden çözüm (yalnız gönderim öncesi veya retry-safe); hazır
   olmayan hedef → DOM/frame değişimine bağlı süre sınırlı bekleme; bilinen engelleyici → yalnız tanımlı
   düğme; bilinmeyen/native dialog → kapatmadan `paused_blocked`; oturum kaybı → `paused_session`; ambiguous →
   `paused_ambiguous`. Deneme ve süre sınırları Settings'ten.
7. **Eşzamanlılık:** run oturum kilidini baştan sona tutar (tek worker). İptal yeni adım/dispatch'i durdurur;
   başlamış adım tamamlanır/uzlaştırılır; otomatik rollback yoktur.

## Riskler
- Uzlaştırma lab'daki "liste öğesi sayısı" kanıtına dayanır; gerçek Pega'da kayıt/aksiyon kimliği veya sürüm
  okuması gerekir (P8 doğrulaması).
- Route.fetch tabanlı origin koruması (ADR 0002) ve native dialog'un açık bırakılması görünmez modda insan
  müdahalesi gerektirir.
