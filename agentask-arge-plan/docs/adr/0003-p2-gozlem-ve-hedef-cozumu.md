# ADR 0003 — P2 frame takibi, anlamsal envanter, hedef çözümü ve manuel seçim

Tarih: 2026-11-05 · Durum: kabul

## Kararlar
1. **Frame kimliği runtime ref + epoch + lineage.** `FrameRegistry` Playwright Frame nesnesini opak anahtar olarak
   kullanır; frame sırası/HTML id kullanılmaz. Yönlenme epoch'u artırır; snapshot her frame için ata zinciri
   epoch'larını saklar. Bir frame yönlenince/ayrılınca kendisinin ve alt ağacının adayları `frame_changed` olur,
   kardeş frame'ler etkilenmez.
2. **Envanter sabit, salt-okur bir sayfa betiğiyle** her frame'de ayrı ayrı (cross-origin dahil Playwright frame
   API'siyle) çıkarılır: tür, rol, erişilebilir ad, etiket, görünürlük, etkinlik, hassaslık, mantıksal bağlam
   (region/form/group/dialog/tabpanel/table_row+ilk hücre anahtarı) ve iframe başlık zinciri. **Hiçbir alan
   değeri toplanmaz** (yalnız `has_value`); select için seçili metin yalnız hassas değilse.
3. **Adaylar geçici:** `c-<snapshot_revision>-<n>`. Element handle'ları yalnız bellekte. Doğrulama sırası:
   snapshot güncel mi → frame lineage güncel mi → eleman bağlı mı → anlamsal parmak izi aynı mı.
   Yeni gözlem eski adayları geçersiz kılar (`snapshot_superseded`).
4. **Bütçeli iki aşamalı çözüm:** önce bütün frame'lerin hafif özeti (yalnız ad/etiket metinleri), sonra yalnız
   aranan adı içeren frame'lerin ayrıntısı. Özeti tam olup adı içermeyen frame "eşleşme yok" kanıtıdır.
   Sınırlar: `FRAME_SCAN_TIMEOUT_MS` (frame başına), `OBSERVE_TIMEOUT_MS` (toplam), `FRAME_SCAN_MAX_DEPTH`,
   `OBSERVE_MAX_FRAMES`, `FRAME_SCAN_MAX_ELEMENTS` (frame başına), `FRAME_SCAN_CONCURRENCY`.
   Durumlar: complete, partial, timed_out, inaccessible (engelli/hata sayfası), not_scanned (+neden).
5. **Çözümleyici kuralları:** 2+ eşleşme → ambiguous (ilk seçilmez; gizli/devre dışı kopyalar da sayılır).
   Kapsam eksikse tek eşleşme bile resolved değildir, sıfır eşleşme `not_found` değildir → `coverage_incomplete`.
   Tek eşleşme görünür/etkin değilse `evidence_missing`. Güven puanı yoktur.
6. **Manuel seçim:** her frame belgesine şeffaf katman + pencere capture aşamasında fare/klavye/form olaylarının
   iptali; alt iframe alanları clip-path ile katmandan çıkarılır, o frame'in kendi katmanı seçer. Seçilen eleman
   token'lı binding ile (indeks + anlamsal parmak izi) bildirilir; Python elemanı yeniden alıp parmak izini doğrular.
   Sonradan yüklenen/yönlenen frame'lere katman yeniden kurulur. Vurgu `pointer-events:none` bir kutudur, kaydırma
   yapmaz (kaydırmalı yükleme tetiklenmesin).

## Riskler / doğrulanmamışlar
- Shadow DOM, canvas ve `contenteditable` kontrolleri envantere girmez; gerçek Pega (özellikle Constellation)
  bileşen yapısıyla doğrulanmalı.
- Seçim katmanı sayfanın daha önce kaydettiği window-capture dinleyicilerinden önce çalışamaz; bu dinleyiciler
  katman hedefli olayı görebilir (hedef kontrolü görmez). Frame yüklenirken kısa bir kurulumsuz pencere olabilir.
- Hassas alan tespiti sezgiseldir (type/autocomplete/ad kalıpları); değer hiç toplanmadığı için hata değer sızdırmaz.
