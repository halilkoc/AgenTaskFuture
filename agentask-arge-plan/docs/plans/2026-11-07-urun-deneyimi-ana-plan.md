# Ana uygulama planı — ürün deneyimine taşıma (2026-11-07)

Tek devam noktası: `docs/STATUS.md`. Bu belge aşamaların hedefini, kullanılacak parçaları ve durumunu tutar.
Durum değerleri: TODO / IN_PROGRESS / DONE / BLOCKED / PARTIAL. PARTIAL, aşamanın bir kısmının bittiğini, kalanının
açıkça listelendiğini anlatır; PARTIAL bir aşama DONE sayılmaz.

## Ön inceleme bulguları (kod ↔ belge)
- **Depo:** git deposu değil. `git init` veya toplu ekleme yapılmadı. `.env` ve çalışma verileri (`var/`)
  sürüm dışında kalmalı.
- **Çekirdek (doğrulanmış, korunur):**
  - P0–P8, R1–R4 (lab).
  - Taslak deposu: `DraftRepository` portu + `LocalFileDraftRepository` (dosya, revizyon kontrollü, kalıcı).
  - Yayın: MongoDB'de değişmez revizyon + manifest (ADR 0006).
  - Yürütücü: ekran/geçiş/uzlaştırma (ADR 0010/0011).
  - Pencere bağlamı (ADR 0014).
- **Yeni tasarımcı (`/prototype/designer`):**
  - Akış durumu tarayıcı belleğinde.
  - Gerçek oturumdan seçim ve yeniden çözüm var; kalıcı taslak, gerçek deneme, onay ve yayın bağlantısı yoktu.
- **Mevcut tasarımcı (`/designer`):** taslak, adım, hedef seçimi (`select-target` kaydetme anında yeniden
  çözer), 4 onay, deneme, yeni oturum testi, onay ve yayın — tamamı API ile.
- **Asistan:** uygulama kapsamlı, kural tabanlı eşleşme ve model önerisi (onay ister), sunucuda plan, P8
  birleşik plan (COMPOSITION_ENABLED). Modeli kullanıp kullanmamaya çalışan bir onay kutusuyla karar veriyor
  (Aşama F'de politikaya taşınacak).
- **Depolama:** yalnız `ARTIFACT_DIRECTORY` ayarı var; artifact/storage portu yok (denetim K4 açık).
  S3 kararı ADR 0013.
- **R4 manuel kabulü:** beklemede ve **tamamlanmadı**. Kanıt yok, değiştirilmedi.

## Aşamalar

### A — Mevcut hataları kapat — DONE
- **Hedef:** 2 başarısız testi ve pop-up güvenilirlik açıklarını kapatmak.
- **Yapılan:**
  - `.env.example` tekil; etkin örnek tek uygulamalı lab.
  - dotenv/ortam değişkeni tırnak ayrımı ve redakte hata.
  - Boyuttan bağımsız katman kuralı ve eylem anı kontrolü.
  - Beklenen pencere açık doğrulaması.
  - Kimliğe bağlı kesinti kararları (ADR 0014 eki).
- **Kabul:** tam takım başarısızsız; sınırlar ADR 0014 ekinde.
- **Kanıt:** bu oturumun başında 600 passed, 3 skipped.

### B — Gerçek alan seçimini sağlamlaştır — DONE
- **Kullanılan:**
  - Oturum, gezinme, gözlem, picker, `resolve` ve vurgulama uçları.
  - `AUTOMATION_APPLICATIONS_JSON`.
  - Origin politikası ve oturum sahipliği.
- **Yapılan:**
  - İki seçim yolu: ekrandaki alanlar / tarayıcıda kendim seçeyim.
  - Önerilerde olmayan alan seçilebiliyor.
  - Seçim sırasında olay engelleniyor (IME/yapıştırma dahil).
  - İptal, süre ve kapanışta temizlik.
  - Seçim sonrası yeniden çözüm.
  - Bölüm ve etkileşim bağlamı (ADR 0014).
  - Nested frame: mevcut geç frame ve frame yeniden yükleme testleri.
  - Tek uygulamada seçim yükü azaltıldı: uygulama adı gösteriliyor, seçim kutusu gizli.
- **Kabul:**
  - e2e `test_prototype_real_session_ui`;
  - `test_popups_dynamic` (modal içinde seçim, temizlik);
  - `test_picker` (geç frame, iptal).

### C — Otomatik tanım ve kalıcı taslak — DONE (lab; ADR 0015, 0017)
- **Kullanılan:** `/api/drafts` (oluştur, parametre, adım, `select-target`, `PATCH step`, geçiş, ekran, sil),
  revizyon kontrolü (`expected_revision` → 409), `LocalFileDraftRepository` (kalıcı).
- **Yapılan (önceki):** "Taslağı kaydet"; teknik kimlikleri kod üretir; değer kaynakları sabit/sor; hedef kaydetme
  anında yeniden çözülür; değişen adımlar yeniden oluşturulur; taslaklar yeniden açılır.
- **Yapılan (bu tur):**
  - **Ekran geçişi:** gerçek oturumda "Ekrana geç" adımı düğmeyi gerçek ekrandan seçer (liste veya tarayıcıda
    seçim), açılacak ekranın adını analist yazar. Kaydetmede geçiş `PUT …/transitions` ile kalıcıdır (tetikleyici
    tekil çözülür, tıklanmaz); hedef ekran sonra "Ekranı tanıt" ile tanıtılır. Canlı panel rotadaki her ekranı
    "tanıtıldı/tanıtılmadı" olarak gösterir.
  - **İş etkisi ve sonuç koşulu:** "Alan doldur"da "Yazılan değeri doğrula (önerilen) / Ek kontrol yapma"
    (`success_check`) ve sabit etki metni; veri değiştiren işlem ayrı "Onaylı işlem" adımı (onaylı aksiyon
    kataloğundan; etki katalog beyanından).
  - **Bilgi oku ve önceki çıktı:** "Bilgi oku" (`op=read`) yalnız gerçek oturumda; sonraki "Alan doldur" bu
    çıktıya bağlanabilir (`prior_output`). Çalışma anı bağlaması yürütücüye eklendi; gerçek okuma yoksa adım hiçbir
    işlem yapmadan durur.
  - **Yeniden açma:** okuma, önceki çıktı, geçiş ve onaylı işlem adımları düzenlenebilir açılır; ekran tanımı artık
    salt okunur nedeni değildir.
- **Sınır:** adıma özel ekran, tamamlanma koşullu geçiş, aksiyon tetikleyicili geçiş ve başlangıç kayıt bağlamı
  yeni tasarımcıda salt okunur. "Kayıt bul" yok ("Seçim yap" için bkz. H).
- **Kabul:** `tests/e2e/test_new_designer_multi_screen_ui.py` (oku → bağla → geçiş → iki ekran tanıt → yeniden
  aç), `test_designer.py::test_transition_saved_before_screens_and_prior_output_trial`,
  `test_executor.py::test_prior_*`, `tests/unit/test_prior_output.py`; mevcut C/D testleri.

### D — Deneme, onay ve yayın — DONE (lab + geçici MongoDB)
- **Kullanılan:** mevcut `/api/drafts` uçları (`screen`, `confirm`, `trial`, `confirm-outcome`, `fresh-test`) ve
  `/api/drafts/{id}/approve|publish` (yayıncı rolü, değişmez yayın/manifest).
- **Yapılan:** yeni tasarımcıda "Gerçek deneme ve yayın" paneli.
  - Ekranı tanıt: sistem işlem hedefi olmayan tanıtıcı işaretleri önerir, analist onaylar, sunucu doğrular.
  - Adım başına 4 onay (sade metin).
  - Gerçek deneme: etkisi açıkça onaylanır; sistem doğrulaması tıklama değil değer/ekran kontrolüdür.
  - Sonuç onayı, yeni oturum testi, onay ve yayın düğmeleri.
  - Katalog kapalıysa açık hata verilir; başarı uydurulmaz.
  - Tanım değişince adım yeniden oluşur ve deneme/onay geçersizleşir.
  - Mevcut tasarımcı ve derin bağlantı korunur.
- **Kabul:** e2e `test_real_selection_is_saved_as_persistent_draft_and_reopened`. Lab'da gerçek deneme alana
  gerçekten yazar; yeni oturum testi geçer; "Eksik yok"; onay katalog kapalıyken açık hata verir; değişiklik
  sonrası "Onay bekliyor".
- **Kabul (Mongo):** `tests/e2e/test_new_designer_publish_mongo.py`.
  - Akış: yeni tasarımcıdan taslak → ekranı tanıt → 4 onay → gerçek deneme → sonuç onayı → yeni oturum testi →
    yayıncı onayı → yayın (`rel-…` etkin) → İşlem Asistanı'nda hazır işlem → özet → başlat.
  - Sonuç "Başarılı / Tamamlandı"; kayıtta yeni değer görülüyor.

### E — Yeniden kullanılabilir bileşenler (katalog) — DONE (lab + geçici MongoDB; ADR 0019)
- **Yapılan:**
  - Bileşen = yayımlanmış işlem; `call_operation` adımı revizyon + içerik hash'ine pinli (catalog-v4).
  - Girdi bağlama (sabit/sor), çıktı bağlama (bileşenin okuma adımları → `prior_output`).
  - Sürüm değişikliği etkisi (`component-updates`) ve açık yükseltme; yükseltme onay/deneme/yeni oturum testini
    sıfırlar.
  - Yayında pinli revizyon doğrulanır; bileşenin ekranları manifeste girer; eski yayınlar değişmez.
- **Kabul:** döngü, eksik girdi, uyumsuz çıktı, değişmiş içerik ve geçersiz ekran sırası çalıştırmadan reddedilir
  (`tests/unit/test_components.py`); yeni revizyon eski çağıranı değiştirmez, eski manifest aynı kalır
  (`tests/unit/test_component_publishing.py`); arayüz uçtan uca
  (`tests/e2e/test_new_designer_components_mongo.py`).
- **Sınır:** bileşen girdisi önceki çıktıdan alınamaz (yalnız sabit/sor); bileşen içi adımlar çağıranda
  düzenlenmez.

### F — İşlem Asistanını sadeleştir — DONE (test ikameleriyle); gerçek model kabulü BLOCKED (ADR 0015, 0020)
- **Önceki:** 5 bölümlü sade görünüm, hazır işlemler, model politikası, plan geçersizleşmesi, durum sözcükleri.
- **Bu tur:**
  - Model, etkin yayındaki işlemlerden en fazla 5 adımlık doğrusal plan önerir (`/plan/propose`); kod şemayı,
    işlem/argüman kümesini, uydurma değerleri, hassas talebi, bütçeyi ve ekran sırasını denetler.
  - Öneri kendiliğinden çalışmaz: eksik bilgi → sunucuda yeniden derlenen özet → açık başlatma
    (`/plan/preview`, `/plan/execute`); veri değiştiren işlemde etki onayı.
  - Bağlayıcı (`HttpxLLM`) plan şemasıyla sahte model sunucusu üzerinden test edildi.
- **Kabul:** `tests/integration/browser/test_assistant.py` (plan testleri), `tests/e2e/test_assistant_plan_ui.py`,
  `tests/integration/test_llm_adapter.py::test_plan_schema_through_real_connector`.
- **BLOCKED:** gerçek kurum modeliyle kabul (erişim yok).

### G — Dosya ve kanıt depolama — DONE (sahte S3 + geçici MongoDB); kurum S3 kabulü BLOCKED (ADR 0016, 0018)
- **Yapılan:**
  - Port async'e çevrildi.
  - S3 uyumlu adaptör (SigV4, httpx; yeni bağımlılık yok), `ARTIFACT_BACKEND=s3` ve `S3_*` ayarları (docs/05).
  - MongoDB metadata adaptörü (`ARTIFACT_INDEX_BACKEND=mongo`, `artifact_index`).
  - Maskelemesi piksel düzeyinde doğrulanmış kanıt (EVIDENCE_SCREENSHOTS_ENABLED; başarısız/belirsiz/duran run);
    doğrulanamayan görüntü saklanmaz; run yalnız `artifact_id` tutar.
- **Kabul:** `tests/unit/test_object_store_contract.py` (AWS SigV4 örnek vektörü, yerel+S3 ortak sözleşme),
  `tests/integration/mongo/test_artifact_index_contract.py`, `tests/integration/browser/test_evidence.py`,
  `tests/unit/test_settings.py` (S3 ayar doğrulaması).
- **BLOCKED:** kurum S3 uç noktası, kimlik, CA ve kova politikası ile gerçek bağlantı kabulü.
- **Sınır:** gölge DOM içindeki alanlar maske kutusu olarak listelenmez (ADR 0018).

### H — “Seçim yap” bileşeni — DONE (lab + geçici MongoDB; ADR 0021, catalog-v5)
- **Kullanılan:** mevcut `ensure_choice`, adaptör kaydı, çözümleyici, yürütücü, taslak ve yayın uçları. Paralel yürütücü yok.
- **Yapılan:**
  - Analist alanı gerçek tarayıcıdan seçer; seçenekler güncel ekrandan okunur, özel liste ayrı ve açık eylemle açılır.
  - Değer kaynağı: sabit seçenek (listeden), her çalıştırmada sor, önceki okuma çıktısı.
  - Etki beyanı, seçilen değer doğrulaması, isteğe bağlı durum mesajı, kalıcı kayıt ve yeniden açma.
  - İşlem Asistanı: sabit listede seçim kutusu, değişken listede açık ekrandan güncel seçenek; çalışırken yeniden doğrulama.
  - Etiket/değer ayrımı; etkisi bilinmeyen seçimde tekrar yok, yalnız okuma ile uzlaştırma.
- **Kabul:** `tests/unit/test_choices.py`, `tests/integration/browser/test_choice_runtime.py`,
  `tests/e2e/test_new_designer_choice_mongo.py`. Gerçek Pega doğrulaması **yapılmadı**.
- **Sınır:** çoklu seçim, yazarak arama, shadow DOM, rolsüz özel liste yok; seçimle tetiklenen onaylı geçiş yok.
  “Kayıt bul” kapsam dışı kaldı.

### I — Loglama ve çalışma geçmişi — DONE (ADR 0022)

### J — Şirket testi aday sürümü — lab doğrulaması DONE; kullanıcı yerel kabulü ve şirket kabulü bekliyor (ADR 0023)
Değerlendirme `docs/16_COMPANY_TEST_READINESS.md`, yerel kabul `docs/17_LOCAL_ACCEPTANCE.md`, paket `tools/build_company_package.py`.

### Gerçek ortam kabul belgesi — DONE
`docs/15_REAL_ENV_ACCEPTANCE.md`. Gerçek Pega/SSO kabulü **yapılmadı** (BLOCKED: kurum erişimi).

## Sınırlar ve kararlar
- Tek uygulama; çok uygulamalı katalog/yayın kapsam dışı.
- Runner yeri (kullanıcı bilgisayarı/OpenShift) ve SSO yöntemi kararı beklemede. Yerel Playwright geliştirme ve
  test adaptörüdür.
- Model zorunlu değil; model çıktısı yetki değil. Yalnız onaylı katalog öğelerine referans verebilir.
- Koşullu/dallanan genel workflow motoru kapsam dışı; doğrusal rota.

## J — Şirket sürümü (2026-11-09)
S1–S9 tamamlandı (lab + geçici MongoDB; ADR 0024). Plan: `2026-11-09-sirket-surumu-son-gelistirme-plani.md`. Pega, Windows ve kullanıcı yerel kabulü açık.
