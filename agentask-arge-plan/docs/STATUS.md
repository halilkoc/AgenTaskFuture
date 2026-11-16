# Güncel durum (tek devam noktası) — 2026-11-09

- **Ana plan:** [docs/plans/2026-11-07-urun-deneyimi-ana-plan.md](plans/2026-11-07-urun-deneyimi-ana-plan.md).
- **Tarihsel kayıt:** [docs/10_PROGRESS.md](10_PROGRESS.md); önceki STATUS içeriği oradaki "STATUS.md arşivi"
  bölümünde.
- **Denetim ve düzeltmeler:** [docs/12_IMPLEMENTATION_AUDIT.md](12_IMPLEMENTATION_AUDIT.md),
  [docs/14_REMEDIATION_LOG.md](14_REMEDIATION_LOG.md).

## Ana plan durumu
| Aşama | Durum |
|---|---|
| A — hataları kapat | DONE |
| B — gerçek alan seçimi | DONE |
| C — otomatik tanım ve kalıcı taslak | DONE (lab; ADR 0017) |
| D — deneme, onay ve yayın | DONE (lab + geçici MongoDB) |
| E — sürümlü bileşenler | DONE (lab + geçici MongoDB; ADR 0019, catalog-v4) |
| F — sade İşlem Asistanı + model plan önerisi | DONE (test ikameleriyle; ADR 0020); **gerçek model kabulü BLOCKED** |
| G — dosya/kanıt depolama | DONE (sahte S3 + geçici MongoDB; ADR 0018); **kurum S3 bağlantı kabulü BLOCKED** |
| H — “Seçim yap” bileşeni | DONE (lab + geçici MongoDB; ADR 0021, catalog-v5); **gerçek Pega doğrulaması yok** |
| I — loglama ve çalışma geçmişi | DONE (ADR 0022); kurum log altyapısı ve gerçek Pega/SSO ile doğrulanmadı |
| J — şirket sürümü S1–S9 | DONE (lab + geçici MongoDB; ADR 0024, catalog-v6); **Pega/Windows doğrulaması yok, kullanıcı yerel kabulü bekliyor** |

## Yeni Akış Tasarımcısında ne çalışıyor (lab)
| Yetenek | Durum |
|---|---|
| Gerçek oturumdan alan seçimi | Çalışıyor (ekrandaki alanlar / tarayıcıda kendim seçeyim, yeniden çözüm). |
| Kalıcı kayıt ve yeniden açma | Çalışıyor: alan doldur, bilgi oku, önceki çıktı, ekrana geç (gerçek düğme), onaylı işlem, yayımlanmış bileşen çağrısı. |
| Ekran geçişi | Geçiş hedef ekrana gidilmeden kaydedilir; her ekran "Ekranı tanıt" ile tanıtılır (rota listesi). Tasarımda sistem düğmeye basmaz. |
| Sonuç koşulu / iş etkisi | "Yazılan değeri doğrula / Ek kontrol yapma"; veri değiştiren işlem yalnız onaylı aksiyon kataloğundan. |
| Seçim yap | Standart select, özel combobox/listbox, iç içe frame. Sabit seçenek, her çalıştırmada sor veya önceki okuma çıktısı; etki beyanı ve sonuç doğrulaması. Desteklenmeyen tür açıkça bildirilir. |
| Bileşenler | Yayımlanmış işlem sürümüne pinli çağrı; çıktı bağlama; yeni sürüm etkisi ve açık yükseltme. |
| Gerçek deneme, onay, yayın | Çalışıyor (lab + geçici MongoDB). |
| Kayıt ve satır | Kayıt bul, bulunan satırda alan/düğme, başlangıç ve geçiş kayıt bağlamı. |
| Yeni kontroller | Onay kutusu, seçenek grubu, yazınca öneri açan alan, çoklu seçim, tarih (takvim yok), dosya yükleme. |
| Geçiş ve pencere | Bağlantı ve seçimle geçiş, tek beklenen yeni pencere ve dönüş, isteğe bağlı bilgi penceresi. |

## İşlem Asistanı
- Tek işlem (kural/model) ve **model önerili sıralı plan** (en fazla 5 yayımlanmış işlem; kodla doğrulanır; özet
  ve açık başlatma). Pinli bileşenler değişmez revizyonundan çalışır.
- Gerçek model hizmetiyle kabul **yapılmadı** (BLOCKED).

## Dosya/kanıt
- `ARTIFACT_BACKEND=local|s3`, `ARTIFACT_INDEX_BACKEND=local|mongo` (varsayılan local; mevcut .env'ler çalışır).
- Kanıt: `EVIDENCE_SCREENSHOTS_ENABLED=true` iken başarısız/belirsiz/duran run için maskeli ve piksel düzeyinde
  doğrulanmış tek görüntü; doğrulanamazsa saklanmaz.

## Manuel kabul kaydı (kullanıcı bildirimi, 2026-11-08)
İlk manuel uçtan uca kabul tamamlandı: “Kefil müşteri numarası gir yaz.” taslağı hazırlandı, gerçek deneme ve yeni
oturum testi geçti, yayıncı onayı verildi, yayın etkinleştirildi, İşlem Asistanı'ndan 00456 ile çalıştırıldı ve kullanıcı
işlemin gerçekleştiğini bildirdi. **Bu kabul yalnız tek alanlı lab senaryosudur; Pega/SSO veya ürünün tümünün kabulü
değildir.**

## Son doğrulama (2026-11-08, loglama aşaması; güncel sonuç için Devam noktası)
**Son geçerli koşu (08):** `caffeinate -i .venv/bin/pytest -q -rs` → 769 passed, 3 skipped, pytest çıkış kodu 0. Atlanan 3 test Docker daemon kapalı olduğu için BLOCKED. ruff, format, mypy ve `tools.dev_check` çıkış 0.

**Başarısız koşu kaydı (07, aynı kod):** `.venv/bin/pytest -q -rs` → 2 failed, 767 passed, 3 skipped, pytest çıkış kodu **1** (`test_choice_component_end_to_end`, `test_prototype_designer_core_flow`). Teşhis: Mac 17:01:10–17:06:11 arasında uyku moduna geçti; adımın ~14:01:17 UTC'de bitmesi gerekirken 14:01:45 UTC'de bitti ve test beklemeleri bu pencerede doldu. Ayrıntı: `07-diagnosis.md`. Bu kayıt silinmemeli.

Çıktı ve çıkış kodları: `var/verification/logging-2026-11-08/`. **Doğrulama notu:** tam takım makine uyurken güvenilir değildir; uzun koşularda `caffeinate -i` kullanın.

Önceki kayıt:
`.venv/bin/pytest -q -rs` → 719 passed, 3 skipped (Docker daemon kapalı; BLOCKED). ruff, format, mypy ve JS sözdizimi
temiz. `tools.dev_check` üç kez başarılı (565 passed); ondan önceki bir koşuda “ilgili testler” adımı bir kez başarısız oldu, çıktısı saklanmadığı için neden belirlenemedi ve tekrarlanmadı (izlenmeli). “Seçim yap” kabul senaryoları: ADR 0021 ve ana plan H bölümündeki testler. Yeni bileşen için kullanıcı manuel
kabulü henüz yapılmadı.

## Loglama ve geçmiş (2026-11-08)
- **Loglar:** stdout, satır başına JSON (`LOG_LEVEL`, `LOG_FORMAT`; yeni ayar yok). Uygulama log dosyası tutmaz.
- **Kullanıcı olayları:** `category=audit`; taslak, onay, yayın, başlatma, durdurma, devam, müdahale, sonuç.
- **Çalışma geçmişi:** `/runs` ve İşlem Asistanı; kayıt `RUN_DIRECTORY` altında dosya, yeniden başlatmada korunur.
- **Doğrulama çıktıları:** `var/verification/logging-2026-11-08/` (çıktı ve çıkış kodları).

## Loglama manuel kontrolleri (kullanıcı bildirimi, 2026-11-08)
Yalnız lab kabulüdür; kurum log altyapısı, Pega/SSO veya ürünün tümünün kabulü değildir.
- Başarılı işlemde destek numarası İşlem Asistanı ve Çalışmalar ekranında aynı.
- Yanlış ekranda çalıştırmada işlem yapılmadan duruldu ve hata bilgisi gösterildi.

## Güncel durum ve kesin devam noktası (2026-11-16) — tarayıcı motoru seçimi, 0.3.0

**Geçerli aday paket:** `dist/agentask-company-test-0.3.0-20261116.zip`, sürüm **0.3.0**.
- SHA-256 `b91f750cb4c4ebf8efa558d7cf8154f7085d7327932754187fb425fecd52acad`, 44.792.801 bayt, 41 dosya.
- Dosya listesi ve üretim kaydı: `var/verification/company-candidate-0.3.0-20261116/package/`.
- 0.2.1 ZIP'ine dokunulmadı (özeti aynı: `5cf37964…`); yalnız Chromium ile kullanılabilen önceki adaydır.

**Yeni (ADR 0025):** `BROWSER_ENGINE=chromium|firefox`. Verilmezse chromium (eski `.env` çalışır). Yalnız seçilen motor başlatılır;
bulunamazsa motor adıyla hata verilir, başka motora geçilmez. `BROWSER_EXECUTABLE_PATH` yalnız chromium içindir; firefox ile
reddedilir. `--doctor` motoru, tarayıcı dosyasını ve başlatma sonucunu ayrı satırlarda gösterir; indirme yapmaz.

**WebKit reddedilir (açık karar):** WebKit, hedef adres sınırının dayandığı “yönlendirme yanıtını denetleyip iletme” adımını
desteklemiyor (`Route.fulfill: Cannot fulfill with redirect status`). Giriş dahil yönlendirme içeren akışlar çalışmıyor.
`BROWSER_ENGINE=webkit` ayar doğrulamasında gerekçesiyle reddedilir; sınır gevşetilmedi. Yeniden üretim:
`var/verification/browser-engines-20261116/kesif/webkit-yonlendirme-yeniden-uretim.py`. WebKit gerekiyorsa ayrı iş ve karar gerekir.

**Firefox ile bulunan ve düzeltilen ürün hataları:**
- Engellenen alt çerçeve yalnız Chromium'un `chrome-error://` adresiyle tanınıyordu. Firefox'ta engellenen çerçeve “tarandı”
  sayılıyor, eksik tarama işlemi durdurmuyordu. Engelleme artık isteği kesen yerde kaydediliyor (`blocked_frames.py`).
- Kaydırma alanından büyük tablonun merkezi alan dışında kalınca tablo “katman arkasında” sayılıyordu (motordan bağımsız;
  Chromium'da da yeniden üretildi). Regresyon: `test_table_larger_than_its_scroll_area_is_not_reported_as_covered`.
- Önceki adımın açtığı fazladan pencerenin bildirimi adım başındaki kontrolden sonra gelirse sonraki yazma yapılıyordu.
  Yeni pencere artık hedef çözüldükten sonra, eylemden hemen önce de denetleniyor.

**Test ve lab değişiklikleri (başarı ölçütü gevşetilmeden):**
- Testlerin arayüz tarayıcısı ve uygulamanın hedef tarayıcısı `AGENTASK_TEST_BROWSER_ENGINE` ile aynı motoru kullanır
  (`tests/support_browser.py`); 29 test dosyasındaki sabit `chromium.launch` kaldırıldı.
- Lab “isteğe bağlı pencere” sayfası pencereyi 30 ms gecikme yerine yazmanın sonucu olarak hemen açıyor (gecikme sonraki adımla
  yarışıyordu). Gezinmeyle ekran değişimi testinde hatanın 1. veya 2. adımda kaydedilmesi kabul edilir; iki durumda da tek
  yazma, `SCREEN_NOT_RECOGNIZED` ve sonraki adımların beklemesi aynen doğrulanır. Engellenen gezinmenin hata metni motora göre
  seçilir; ölçüt “izinsiz adrese istek gitmedi”dir. Sayfalı tablo testinin yardımcısı, yürütücü gibi tablo hazır olana dek bekler.

**Sonuçlar (kanıt: `var/verification/company-candidate-0.3.0-20261116/regression/`):**
- Chromium tam regresyon: 947 passed, çıkış 0; Docker 3 passed; ruff, format, mypy, JS, `dev_check` çıkış 0 (kod özeti `b0e131fc…`).
- Firefox: tarayıcı entegrasyon + lab 251 passed (ilk koşuda 1 test yardımcısı hatası; düzeltilip tümü yeniden koşuldu, `32-…`),
  uçtan uca 38 passed. Regresyondan sonra değişen tek dosya o test yardımcısıdır (`tests/integration/browser/test_driver_adapters.py`).
- Firefox ile tek komutlu kabul: **28/28 GEÇTİ, araç çıkış 0, pytest çıkış 0** (114 passed). Arayüz 91, hedef 15 başlatmanın
  hepsi firefox; başka motor 0. Yalıtım değişmedi. Rapor: `acceptance-reports/20261116-164525/report.md`.
- WebKit: başlatma dışında hiçbir akış doğrulanmadı; geçti sayılmaz.
- `--check-config` / `--doctor` çıktıları: `var/verification/browser-engines-20261116/cli-kontrolleri.log`.

**Bu Mac'e özgü not:** Firefox gerçek kullanıcı dizininde “Could not find profile folder” ile kapanıyor (neden belirlenemedi).
Testler Firefox'u geçici kullanıcı diziniyle başlatır. Uygulamayı bu Mac'te Firefox ile elle çalıştırmak aynı hataya takılabilir.

**Doğrulanmadı (şirkette):** Windows'ta Firefox kurulumu ve çevrimdışı tarayıcı klasörü, Windows `.ps1` betikleri, gerçek
Pega/SSO (Firefox ile dahil), kurumsal MongoDB/TLS, model, S3, görünür tarayıcıda pencere deneyimi.

**Kesin devam noktası:** paket 0.3.0 şirkete taşınır; `INSTALL.md` bölüm 3.1 ile Firefox dosyaları sağlanır, `.env` içinde
`BROWSER_ENGINE=firefox` yazılır, `doctor.ps1` ve ardından `MANUAL_ACCEPTANCE.md` S0–S25 uygulanır.

## Önceki durum (2026-11-13) — 0.2.1

**Geçerli aday paket:** `dist/agentask-company-test-0.2.1-20261113.zip`, sürüm **0.2.1**.
- SHA-256 `5cf379642d5dc296c953481afe1024b73755b79ce7c8a033d66259cd16455d95`, 41 dosya.
- Dosya listesi: `var/verification/company-candidate-0.2.1-20261113/package/04-file-list.txt`.
- 0.2.0 eski adaydır (öneri alanı hatası; `dist/...0.2.0-20261109.ESKI.txt`). 0.1.0 geçersizdir.

**Ürün düzeltmesi (0.2.1, `src/agentask/application/controls.py`):** öneri alanında eşleşme yoksa eski metin geri yazılıyordu. Alandaki gerçek seçim (`data-value`) kaybolsa da sonuç “eski değerine döndürüldü” diye bildiriliyordu. Artık metin ve gerçek değer birlikte doğrulanıyor; ikisi birden geri gelmezse sonuç “Belirsiz”.
- Regresyon testi: `test_controls_runtime.py::test_autocomplete_lost_selection_is_not_reported_as_restored`.
- Eski davranışla başarısız olduğu kanıtlandı: `acceptance-reports/2026-11-13-controls-regresyon-kaniti/`.

**Test düzeltmeleri (yalnız test kurgusu):**
- `test_company_candidate_flow`: betikle eklenen öğe ekran işareti oluyordu.
- `test_wizard_acceptance_mongo`: kayıt bağlamı kontrolü tanımlı değildi; `docs/17` madde 14 de güncellendi.
- `test_action_file_mongo`: yeni tarayıcıda oturum açıkça seçiliyor; yalnız aksiyon adımı yeniden denendiğinde ön koşul (Not alanı) analistçe hazırlanıyor.
- `test_controls_flow_mongo`: hedef sayfa test döngüsünden çağrıldığı için sonsuz bekleme vardı; çağrı `in_server` ile yapılıyor.
- Kanıtlar: `acceptance-reports/2026-11-13-*`.

**Tam regresyon (0.2.1, kod özeti `15c1f15c…`):** 933 passed, pytest çıkış 0. Docker testleri 3 passed. ruff, format, mypy, JS ve `dev_check` çıkış 0. Kanıt: `var/verification/company-candidate-0.2.1-20261113/regression/`. Paket sonrasında yalnız kabul aracının test eklentisi (`tools/local_acceptance/guard.py`) değişti; bu dosya paketlenmez. Paketteki kod kaynakla aynı (madde 28: wheel ↔ kaynak 0 fark).

**Otomatik yerel kabul:** `.venv/bin/python -m tools.local_acceptance`. Son koşu **28/28 GEÇTİ, araç çıkış 0, pytest çıkış 0** (114 passed). Yalıtım: `.env`, `var/` ve kalıcı MongoDB değişmedi. Rapor: `acceptance-reports/20261113-202235/report.md`. Önceki koşu (`20261113-201632`) araç hatası nedeniyle geçersizdir; ayrıntı `GECERSIZ_KOSU.md`. Kapsam eşlemesi ve şirket yaklaşımı: `docs/18_LOCAL_ACCEPTANCE_AUTOMATION.md`.

**Manuel kanıt:** kısmi lab kanıtı olarak yalnız kullanıcı bildirimi var: “Kefil şubesi seçimi İşlem Asistanı'nda başarılı.” Otomatik GEÇTİ sonuçları kullanıcı kabulü sayılmaz.

**Bilinen kayıp (geliştirme hatası):** 2026-11-13'te kapsamı dar bir `ruff --fix` komutu, test ve araç dosyalarındaki 27 `# noqa` açıklamasını sildi. Hepsi aynı satırlara geri kondu ve lint temiz. Ancak dördü dışında gerekçe metinleri geri getirilemedi; yalnız kural kodu duruyor.

**Doğrulanmadı (şirkette):** Windows `.ps1` betikleri ve Windows wheel kurulumu; gerçek Pega/SSO; kurumsal MongoDB/TLS, kurum modeli, S3, log aktarımı; kurulu Edge/Chrome; görünür tarayıcıda pencere deneyimi.

**Kesin devam noktası:** paket 0.2.1 şirkete taşınır. `INSTALL.md` ile kurulur, ardından `MANUAL_ACCEPTANCE.md` S0–S25 uygulanır. Yerelde ek geliştirme yok. Kod değişirse yeni aday sürüm, tam regresyon ve yeni paket gerekir.

## Devam noktası (2026-11-09, son) — şirket testi paketi 0.2.0

> **Not (2026-11-13):** bu bölümdeki 0.2.0 paketinin yerini 0.2.1 aldı; güncel durum yukarıda.
**Durum:** S1–S9 (`docs/plans/2026-11-09-sirket-surumu-son-gelistirme-plani.md`, K1–K5, ADR 0024) lab ve geçici MongoDB üzerinde tamamlandı.

**Geçerli paket:** `dist/agentask-company-test-0.2.0-20261109.zip`, SHA-256 `e4000fc6fc2cd33207d0b6abc2993878c41ec087d50c66f1b7f57de516a89816`, 41 dosya (`SHA256SUMS.txt` dahil). Dosya listesi: `var/verification/company-final-2026-11-09/package/04-file-list.txt`.

**Geçersiz aday:** `dist/agentask-company-test-0.1.0-20261109.zip` kullanılmamalı (S1–S8 öncesi; yanında `.GECERSIZ.txt`).

**Son doğrulama (kod özeti `6af81050…`, koşu başı ve sonu aynı; `caffeinate -i`, koşu sırasında uyku kaydı yok):** pytest **916 passed**, atlanan yok, pytest çıkış 0 (3 Docker testi dahil). Docker testleri ayrıca 3 passed, çıkış 0. ruff, format, mypy, JS, `tools.dev_check` çıkış 0. Çıktılar: `var/verification/company-final-2026-11-09/regression/`.

**Başarısız koşu kaydı (silinmemeli):** ilk tam koşu 1 failed, 915 passed, pytest çıkış 1. Neden S8'de bilerek eklenen `focused_window` alanını görmeyen eski birebir karşılaştırma; uyku ile ilgisi yok. Teşhis: `regression-attempt1-failed/DIAGNOSIS.md`.

**S1–S7 temel kanıtı (S8 öncesi):** `s1-s7-baseline/`, yedi aşama çıkış 0, 102 test. S8: `test_window_modal_runtime`, `test_window_modal_flow_mongo`.

**Paket doğrulaması (`package/`):** `SHA256SUMS` 40 dosya uyuştu; wheel'deki 177 dosya test edilen kaynakla birebir aynı; yasak yol 0. Mac'te temiz sanal ortamda kurulum (0.2.0), `--check-config` ve `--doctor` çıkış 0; doctor'da iki beklenen uyarı (onaylı işlem dosyası tanımsız, hedef örnek adrese erişilemedi).

**Denenmedi (doğrulandı sayılmaz):** Windows'ta `install.ps1`, `start.ps1`, `doctor.ps1`, `hash-admin.ps1` hiç çalıştırılmadı (bu makinede PowerShell yok); Windows wheel kümesi kurulmadı. Gerçek Pega/SSO, kurumsal MongoDB/TLS, kurum modeli, kurum S3, log aktarımı, kurulu Edge/Chrome. Yeni kontrollerin Pega DOM'unda davranışı.

**Sıradaki:** aşağıdaki “Gün sonu ve kesin devam noktası (2026-11-09)” bölümü. Kod değişirse paket geçersiz olur; tam regresyon ve yeni paket gerekir.

**Bilinen sınırlar:** takvim açılır penceresi yok (Pega DOM'u gerekir); tablo anahtarı yalnız ilk sütunda; yeni pencerede duran çalışma sürdürülemez; Ctrl ile çoklu seçim isteyen ARIA listesi doğrulanmadı; K3 lease/fencing, K7 işlem bazlı yetki, run'ların Mongo'da olmaması; dallanma yok. Hepsi `KNOWN_LIMITS.md`.

**Ertelendi (başlanmadı):** kurumsal SSO, OpenShift, kuyruk, çok kullanıcılı ölçekleme, runner ayrıştırma, kapasite testi, geniş kod temizliği. Eski `/designer` silinmedi.

**Korunacaklar:** `var/` altındaki veriler, MongoDB yayınları, gerçek `.env`.

## Gün sonu ve kesin devam noktası (2026-11-09)

**Geçerli paket:** `dist/agentask-company-test-0.2.0-20261109.zip`, SHA-256 `e4000fc6fc2cd33207d0b6abc2993878c41ec087d50c66f1b7f57de516a89816`. `src/` paketten sonra değişmedi (wheel ↔ kaynak: 177 dosya, 0 fark). Son tamamlanmış tam regresyon: 916 passed, çıkış 0 (`var/verification/company-final-2026-11-09/regression/`); bu koşu aşağıdaki test genişletmelerinden **öncedir**.

### Otomatik kabul çalışması: yapılanlar ve durum
**Yapıldı (dosyalar diskte, `src/` dışında):**
- 28 madde mevcut testlerle eşlendi: `tools/local_acceptance/coverage.py`.
- Mevcut e2e testlerine sonuç doğrulamaları eklendi: hedef dışı alanlar, gönderim sayısı, etkin yayın, aksiyon özeti, destek numarası (`tests/e2e/flow_helpers.py` ve 7 test dosyası).
- Yeni test: `tests/e2e/test_wizard_acceptance_mongo.py` (madde 14–16).
- Tek komut aracı yazıldı: `tools/local_acceptance/` (ön koşul, gerçek adres reddi, yalıtım kanıtı, başarısızlık ekran görüntüsü, rapor).

**Yapılmadı veya doğrulanmadı:**
- `tools/local_acceptance` **hiç çalıştırılmadı** (yalnız derlendi); `acceptance-reports/` altında 28 maddelik rapor yok.
- Araç için birim testleri yazılmadı; ruff 64 bulgu veriyor (araç ve yeni test satırları).
- `docs/18` (kapsam eşlemesi, elle SSO sonrası şirket kabul yaklaşımı) yazılmadı.

**Kalan hata:** genişletilmiş test koşusu tamamlanmadı, çıkış kodu yok. İlerleme `FF..F`, ardından `test_controls_flow_mongo` 30 dakikadır takılı. Ayrıntı: `acceptance-reports/2026-11-09-tamamlanmamis-kosu/DURUM.md`. Üç başarısızlığın nedeni henüz okunmadı; ürün hatası olasılığı dışlanmış değildir. Testler genişletildiği için tam `pytest` şu an geçer durumda sayılmamalı.

### 28 maddenin otomatik sonucu
Tek komutlu koşu çalışmadığı için **hiçbir madde GEÇTİ veya KALDI olarak değerlendirilmedi; 28 maddenin tamamı OTOMATİK DOĞRULANAMADI.** Sağ sütun yalnız tamamlanmamış koşudan gözlemdir, sonuç değildir.

| Madde | Sonuç | Eşlenen test ve gözlem | Kanıt |
|---|---|---|---|
| 1–11 | OTOMATİK DOĞRULANAMADI | `test_company_candidate_flow`: başarısız (neden okunmadı) | `acceptance-reports/2026-11-09-tamamlanmamis-kosu/` |
| 12–13 | OTOMATİK DOĞRULANAMADI | `test_approved_action_through_designer_and_assistant`: geçti görünüyor (rapor yok) | aynı |
| 14–16 | OTOMATİK DOĞRULANAMADI | `test_wizard_acceptance_mongo`: başarısız (neden okunmadı) | aynı |
| 17 | OTOMATİK DOĞRULANAMADI | `test_action_file_mongo`: başarısız (neden okunmadı) | aynı |
| 18 | OTOMATİK DOĞRULANAMADI | `test_release_activation_ui`: geçti görünüyor (rapor yok) | aynı |
| 19–21 | OTOMATİK DOĞRULANAMADI | Genişletilmiş koşuya dahil değildi; önceki 916 passed içinde | `var/verification/company-final-2026-11-09/regression/` |
| 22–23 | OTOMATİK DOĞRULANAMADI | `test_controls_flow_mongo`: takılı | `acceptance-reports/2026-11-09-tamamlanmamis-kosu/` |
| 24–27 | OTOMATİK DOĞRULANAMADI | E2E testlerine sıra gelmedi | aynı |
| 28 | OTOMATİK DOĞRULANAMADI | Araçla çalıştırılmadı; paket elle doğrulandı (S9) | `var/verification/company-final-2026-11-09/package/` |

### Kullanıcının yaptığı manuel kontroller
**Kısmi manuel lab kanıtı (kullanıcı bildirimi, 2026-11-11'de iletildi):** “Kefil şubesi seçimi İşlem Asistanı'nda başarılı.” Bu bildirim `docs/17` 2–11 senaryosuna karşılık gelir; madde madde sonuç verilmediği için tek tek kabul sayılmaz. Diğer maddeler için sonuç bildirilmedi; **28 maddenin tamamı geçmiş sayılmaz.** Kabul alanında kullanım izi var (`var/kabul-20261109`: 2 taslak, 5 çalışma; `agentask_kabul_20261109`: 1 yayın); bu kayıtlar madde sonucu değildir. Önceki kullanıcı bildirimleri yalnız yukarıdaki 2026-11-08 lab kayıtlarıdır.

### 2026-11-11: test_company_candidate_flow teşhisi
Yalnız bu test bir kez çalıştırıldı (`-x`, süre sınırı, geçici ortam): **pytest çıkış 1.** Test, elle girişten sonraki yeni oturum testinde (satır 210) başarısız oldu. Ürün “Beklenen başlangıç ekranı görünmüyor; işlem başlatılmadı” diyerek işlemi güvenli biçimde başlatmadı. Önceki doğrulamalar geçti; madde 4–6 ve 8'in yeni kontrolleri dahil. **Kaynak belirsiz:** test zamanlaması mı, ekran işareti seçimi mi, kanıtlanamadı. Kanıt: `acceptance-reports/2026-11-11-company-candidate-teshis/` (`TESHIS.md`, `pytest.log`, `pytest-exit-code.txt`). Diğer üç başarısızlık ve takılma henüz incelenmedi.

**Yarın ilk tek adım:** `test_company_candidate_flow`'u tasarımdaki ekran işaretlerini ve doğrulama penceresinin adresini kanıt olarak kaydedecek biçimde yeniden teşhis et; nedeni test zamanlaması, ekran işareti seçimi veya ürün olarak kanıtla. Ancak ondan sonra diğer testlere geç.

### 2026-11-13: test_company_candidate_flow düzeltildi
- **Teşhis:** neden test kurgusu. Betikle eklenen “Zengin Metin” öğesi tasarım sayfasında kalıyor, başlangıç ekranının gerekli işareti oluyordu; yeni oturumda yoktu. Doğrulama penceresi doğru yoldaydı (`/pages/selections`) ve geç yüklenme yoktu. Kanıt: `acceptance-reports/2026-11-13-ekran-tanima-teshis/TESHIS.md`.
- **Düzeltme (yalnız test):** desteklenmeyen hedef kontrolü bitince, “Ekranı tanıt”tan önce öğe sayfadan kaldırılıyor ve kaldırıldığı doğrulanıyor. Desteklenmeyen hedef kontrolü ve başarı koşulları aynı; ürün kodu değişmedi.
- **Sonuç:** yalnız bu test, yalıtılmış lab ortamında, `-x` ve 600 sn sınırla bir kez çalıştı: **1 passed, pytest çıkış 0.** Kanıt: `acceptance-reports/2026-11-13-company-candidate-duzeltme/` (`pytest.log`, `pytest-exit-code.txt`).
- **Lint düzeltmesi:** 2 ruff E501 uyarısı satırlar bölünerek giderildi; davranış ve doğrulamalar aynı. Ruff check ve format --check çıkış 0. Test yeniden bir kez çalıştı (yalıtılmış, `-x`, 600 sn): **1 passed, pytest çıkış 0.** Kanıt: `acceptance-reports/2026-11-13-company-candidate-lint/`.
- **Açık:** `test_wizard_acceptance_mongo`, `test_action_file_mongo` başarısızlıkları ve `test_controls_flow_mongo` takılması incelenmedi. Paket 0.2.0 değişmedi.

### 2026-11-13: test_wizard_acceptance_mongo düzeltildi
- **Teşhis:** neden test kurgusu. “Ekrana geç” adımında kayıt bağlamı kontrolü tanımlı değildi; bu yüzden `other_case` ile açılan C-2001-B ekranında işlem “Başarılı” bitti. Kanıt: `acceptance-reports/2026-11-13-wizard-teshis/TESHIS.md` (pytest çıkış 1).
- **Düzeltme (yalnız test ve `docs/17` madde 14):** “Açılan ekranda kayıt doğrulansın mı?” = Sabit değer; alan `Vaka` › `Vaka No`, beklenen `C-2001`. Test, kontrolün kaydedilen geçiş tanımına (`completion`) yansıdığını API'den doğruluyor. `other_case` sonrası iki yeni doğrulama var: açılan vaka `C-2001-B` ve teminat tutarı boş. Madde 15'in beklentisi değişmedi. Test dosyasının ilk satırındaki önceki E501 uyarısı da giderildi.
- **Sonuç:** Ruff check çıkış 0; format --check çıkış 0. Yalnız bu test, yalıtılmış lab ortamında, `-x` ve 600 sn sınırla bir kez çalıştı: **1 passed, pytest çıkış 0.** Doğrulananlar: doğru vakada tamamlanma, C-2001-B'de durma ve tutarın yazılmaması, geçmiş ayrıntısı, doğru vakada yeniden çalışma, çıkış. Kanıt: `acceptance-reports/2026-11-13-wizard-duzeltme/` (`pytest.log`, `pytest-exit-code.txt`, `ruff-*.exit`).
- Ürün kodu ve paket 0.2.0 değişmedi. Açık: `test_action_file_mongo` başarısızlığı ve `test_controls_flow_mongo` takılması.

### Kesin devam noktası
Takılı koşu bittiyse veya durdurulduysa, **önce** `test_company_candidate_flow`, `test_wizard_acceptance_mongo`, `test_action_file_mongo` hatalarını ve `test_controls_flow_mongo` takılmasını teşhis et; her birini ürün hatası veya test beklentisi olarak kanıtla. Sonra: araç lint ve birim testleri → `docs/18` → `.venv/bin/python -m tools.local_acceptance` (tek koşu). Ürün kodu değişirse 0.2.0 sessizce değiştirilmez; yeni aday sürüm ve tam regresyon gerekir.

**Yarın kabul alanıyla başlatma:** `docs/17_LOCAL_ACCEPTANCE.md`, “Kabul alanıyla başlatma” bölümü.

## BLOCKED
- Gerçek Pega/SSO kabulü ([docs/15_REAL_ENV_ACCEPTANCE.md](15_REAL_ENV_ACCEPTANCE.md)).
- Kurum S3 bağlantı kabulü (uç nokta, kimlik, CA, kova politikası).
- Gerçek model hizmetiyle kabul.
- Runner yeri (kullanıcı bilgisayarı/OpenShift) ve SSO yöntemi kararı.

## Beklemede
- R4 manuel kabulü ([docs/R4_ACCEPTANCE.md](R4_ACCEPTANCE.md)): **tamamlanmadı**.
- Çok uygulamalı katalog/yayın: kapsam dışı.
