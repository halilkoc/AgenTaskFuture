# Düzeltme kaydı

Kaynak: `docs/12_IMPLEMENTATION_AUDIT.md` (2026-11-05). Denetim raporu tarihsel kayıt olarak değiştirilmedi.

## Aşama 1 (2026-11-05): R1 ve R2

Kapsam yalnız R1 (denetim K2) ve R2 (denetim K1). Diğer bulgular (K3–K7 ve ikincil eksikler) uygulanmadı.

### R1 — Asistan girdilerinin hassas veri sınırı (denetim K2)

**Yeniden doğrulama (düzeltme öncesi, mevcut kodla):** `tests/integration/test_assistant_sensitive.py` yazıldı ve
mevcut koda karşı çalıştırıldı: 6 testten 5'i başarısız.
- Kart numaralı, kural eşleşmeyen talep modele gönderildi: kayıt eden ikame `payloads` boş değildi.
- Kart numarası parametreye bağlandı: `{'no': '4111111111111111'}`.
- Hassas argüman önizleme/yürütmede reddedilmedi (`DID NOT RAISE PlanInvalid`).
- `Interpretation` nesnesinde hassasiyet bilgisi yoktu.

Temiz talebin payload testi zaten geçiyordu; mevcut davranış korunmuştur.

**Kök neden:**
- `AssistantService._model_suggestion` kullanıcı talebini `json.dumps({"talep": prompt, …})` ile olduğu gibi
  gönderiyordu.
- `extract_arguments` her sayı ve tırnaklı değeri parametre adayı sayıyordu.
- `preview` ve `execute`, argüman değerlerini derleyip run checkpoint'ine yazmadan önce denetlemiyordu.
- Hassas veri kontrolü yalnız tasarımcıda (`redact_intent`) vardı ve asistana bağlanmamıştı.

**Tasarım kararı (regex maskeleme değil, şüphede durma):**
- Yeni `domain/sensitive.py::scan` hassas veri *şüphesini* tespit eder. Bulgular değeri değil, yalnız türü ve
  konumu taşır. Kapsananlar:
  - secret anahtar kelimeleri,
  - Luhn geçerli kart numarası,
  - checksum geçerli T.C. kimlik numarası,
  - TR IBAN,
  - JWT,
  - yüksek entropili kimlik bilgisi benzeri dizi.
- Modül, bütün hassas verileri yakaladığını iddia etmez; belgesinde kapsanmayanlar açıkça yazılıdır.
- Şüphe varsa:
  - Model hiç çağrılmaz.
  - Talep "eşleşti" olarak onaylanmaz; durum `needs_clarification` olur ve kullanıcıdan iş parametrelerini ayrı
    alanlardan girmesi istenir.
  - Parola benzeri değerlerin yalnız onaylı `secret_ref` ile kullanılabileceği belirtilir.
  - Şüpheli değer hiçbir parametreye bağlanmaz.
  - Şüpheli olmayan iş parametreleri korunur (ör. `00123`).
- Önizleme ve yürütme, hassas değeri veya hassas adlı parametreyi plan ve run checkpoint'i oluşturmadan
  reddeder: `sensitive_argument`. Değer hata ayrıntısına konmaz.
- Bileşik görev (P8) için düzleştirilmiş plandaki bütün değerler denetlenir: çağrı argümanları ve döngü öğeleri.
- Temiz talepte model payload'u yalnız `{"talep", "islemler"}` alanlarından oluşur. Bu, testte birebir doğrulanır.

**Değişen dosyalar:**
- `src/agentask/domain/sensitive.py` (yeni)
- `src/agentask/domain/assistant.py`: `Interpretation.sensitive`; `extract_arguments` hassas değerleri bağlamaz.
- `src/agentask/application/services/assistant.py`:
  - `interpret`: şüphede modelsiz yol.
  - `_reject_sensitive_arguments`: `preview` ve `execute` için.
  - `_composite`: değer denetimi.

**Yeni regresyon testleri:**
- `tests/unit/test_sensitive.py` (16 test):
  - tespit edilen türler,
  - iş metninin işaretlenmemesi (`00123`, `B-1027`, geçersiz TCKN),
  - bulguların değeri içermemesi.
- `tests/integration/test_assistant_sensitive.py` (7 test, kayıt eden LLM ikamesi ile gerçek payload):
  - `test_clean_prompt_payload_is_exactly_prompt_and_catalog_slice`
  - `test_secret_in_prompt_never_reaches_model_and_business_param_kept`: model çağrılmaz, `00123` korunur,
    secret yanıtta ve logda yok.
  - `test_secret_with_unmatched_prompt_asks_instead_of_calling_model`
  - `test_sensitive_value_not_bound_as_argument`
  - `test_model_disabled_path_flags_without_call`
  - `test_sensitive_argument_rejected_before_persistence`: run deposu boş kalır.
  - `test_composite_arguments_and_loop_items_checked`

### R2 — Yeni oturum testinin varsayılan yapılandırmayla çalışması (denetim K1)

**Yeniden doğrulama (düzeltme öncesi):**
- `tests/e2e/test_designer_ui.py` içindeki özelliğe özel `BROWSER_MAX_SESSIONS_PER_USER="2"` override'ı
  kaldırıldı. Varsayılan `.env.example` ile E2E başarısız oldu ("İncelemeye hazır değil (1 eksik)").
- Yeni `tests/integration/browser/test_fresh_session_test.py`, üretimdeki hatanın aynısını verdi:
  `SessionLimitReached: Açık tarayıcı oturumu sınırına ulaşıldı.`

**Kök neden:**
- Yeni oturum testi, eski snapshot/locator taşımaması için ayrı bir browser context'e ihtiyaç duyar.
  `fresh_session_test` bunu sıradan, etkileşimli bir oturum olarak açıyordu. Kullanıcının ekrandaki tasarım
  oturumu açıkken bu, varsayılan kullanıcı başına 1 etkileşimli oturum sınırını aşıyordu.
- İnceleme sırasında iki ek kusur bulundu:
  - Run zaman aşımına uğrarsa `close()` meşgul oturumda `SessionBusy` fırlatıyor ve geçici oturum sızıyordu.
  - İstek kimliği deneme başına benzersiz değildi.

**Tasarım:**
- Oturumlara `purpose` alanı eklendi: `interactive` | `verification`.
- Doğrulama oturumu kullanıcının etkileşimli kotasına sayılmaz. Kendi kotası vardır:
  `BROWSER_MAX_VERIFICATION_SESSIONS_PER_USER` (varsayılan 1).
- Doğrulama oturumu toplam `BROWSER_MAX_SESSIONS` kapasitesi içindedir. Kapasite doluysa başka hiçbir oturum
  kapatılmaz; açıkça `session_limit_reached` döner.
- `BrowserSessionService.verification_session(owner)` bağlam yöneticisi:
  - Oturum oluşturan kullanıcıya aittir.
  - Blok sonunda (hata, iptal, zaman aşımı dahil) kapanır.
  - İçinde işlem sürüyor olsa bile yalnız bu geçici oturumun context'i kapatılır.
- Etkileşimli oturumlarda meşgulken kapatma reddi aynen korunur.
- `DesignerService.fresh_session_test` bu oturumu kullanır:
  - Run süresi dolarsa önce iptal edilir ve sonucu beklenir; ardından oturum kapanır.
  - İstek kimliği deneme başına benzersizdir.
  - Ana tasarım oturumuna ve başka kullanıcılara dokunulmaz.
- Oturum API yanıtında `purpose` görünür.
- Varsayılan etkileşimli limit **değiştirilmedi** (hâlâ 1).

**Değişen dosyalar:**
- `src/agentask/application/services/browser_sessions.py`: `purpose`, ayrı kota, `verification_session`.
- `src/agentask/application/services/designer.py`: `fresh_session_test`.
- `src/agentask/config/settings.py`: `browser_max_verification_sessions_per_user` + toplam kapasite kontrolü.
- `src/agentask/bootstrap.py`
- `src/agentask/presentation/api/sessions.py`: `purpose`.
- `.env.example`, `docs/05_CONFIGURATION.md`.
- Testler:
  - `tests/e2e/test_designer_ui.py`: override kaldırıldı, varsayılan yapılandırma kullanılır.
  - `tests/integration/test_sessions_api.py`: `purpose` doğrulaması eklendi.

**Yeni regresyon testleri:**
- `tests/unit/test_browser_sessions.py` (+4 test):
  - doğrulama oturumu etkileşimli kotayı tüketmez,
  - doğrulama kotası ve toplam kapasite başka oturum kapatmadan uygulanır,
  - hata ve meşgul durumda kapanır,
  - etkileşimli oturumda meşgul kapatma hâlâ reddedilir.
- `tests/integration/browser/test_fresh_session_test.py` (4 test, varsayılan sınırlar, gerçek Chromium):
  - `test_fresh_test_with_default_limits_keeps_main_and_other_sessions`: ana oturum URL'si ve içeriği korunur;
    mehmet'in oturumu sürer.
  - `test_failed_navigation_closes_temporary_session`
  - `test_failing_operation_records_failure_and_cleans_up`
  - `test_timeout_cancels_run_and_cleans_up`
- `tests/e2e/test_designer_ui.py`: override'sız varsayılan yapılandırmayla tam tasarımcı akışı.

### Çalıştırılan komutlar (düzeltme sonrası)

| Komut | Exit | Sonuç |
|---|---|---|
| `.venv/bin/pytest -q -rs tests/unit/test_sensitive.py tests/integration/test_assistant_sensitive.py tests/unit/test_browser_sessions.py tests/integration/browser/test_fresh_session_test.py tests/e2e/test_designer_ui.py` | 0 | 47 passed |
| `.venv/bin/pytest -q -rs tests/unit` | 0 | 283 passed |
| `.venv/bin/pytest -q -rs tests/integration/browser tests/integration/lab` | 0 | 99 passed |
| `.venv/bin/pytest -q -rs tests/integration/test_{app,cli,sessions_api,observation_api,runs_api,drafts_api,llm_adapter,assistant_sensitive}.py` | 0 | 47 passed |
| `.venv/bin/pytest -q -rs tests/integration/mongo` | 0 | 9 passed (geçici yerel mongod) |
| `.venv/bin/pytest -q -rs tests/e2e` | 0 | 6 passed |
| `.venv/bin/pytest -q -rs` (tamamı, son koşu) | 0 | 444 passed, 0 skipped |
| `.venv/bin/ruff check src tests` / `ruff format --check src tests` | 0 / 0 | temiz / 157 dosya formatlı |
| `.venv/bin/mypy` | 0 | 94 dosya, hata yok |

**Ara hatalar:** Düzeltme sırasında yardımcı satır sarma betiğim iki çok satırlı string ve bir belge metnini
bozdu; ruff/mypy bunları yakaladı ve elle düzeltildi. Bir değişken adı çakışması (`entry`) mypy ile bulunup
düzeltildi. Tam suite bunlardan sonra yeniden çalıştırıldı.

### Kalan sınırlamalar

**R1:**
- Tespit sezgiseldir ve tam değildir: e-posta/telefon gibi kişisel veriler, doğal dilde anlatılmış veya
  bölünmüş secret'lar yakalanmaz.
- Yanlış pozitif durumunda, ör. "parola sıfırlama talebi", model kullanılmaz; kural yolu ve açıklama isteği
  çalışır.
- `secret_ref` çözümü (SecretProvider) hâlâ yok. Gerçekten secret gerektiren işlemler çalıştırılamaz; bu bilinçli
  bir red yoludur.
- Ekranda ayrı "güvenli secret girişi" alanı yok. Uyarı açıklama metniyle gösteriliyor; ekran davranışı ayrı bir
  E2E ile test edilmedi.
- Tasarımcı niyet metni hâlâ eski `redact_intent` ile ayıklanıyor; `domain/sensitive` ile birleştirilmedi.
- İstek gövdesi taşıma sırasında talebi içerir: loglanmaz, kalıcılaştırılmaz.

**R2:**
- Etkileşimli limit 1 olduğundan, tasarımcı oturumu açıkken başka bir sayfada (`/assistant`, `/changes`) ikinci
  etkileşimli oturum açılamaz. Bu ayrı bir kullanılabilirlik bulgusudur; bu aşamada ele alınmadı.
  `tests/e2e/test_{publish,assistant,changes}_ui.py` bu çok sayfalı senaryo için override kullanmaya devam ediyor.
  Override'sız varsayılan yapılandırmayla doğrulanan akış, tasarımcının tam akışıdır.
- İptalden sonra 10 sn içinde bitmeyen run'ın context'i kapatılır; executor bunu hata/belirsiz sonuç yoluyla
  kaydeder.
- Toplam kapasite başka kullanıcılarca doluysa yeni oturum testi açık bir 429 ile reddedilir; kuyruk yoktur.
- Kilit ve kotalar bellek içidir (tek worker, denetim K3).

## Aşama 2 (2026-11-05): R2B — Sayfalar arası oturum kullanılabilirliği

Kapsam: R2 sonrası kalan sınırlama ("tasarımcı oturumu açıkken başka sayfa ikinci etkileşimli oturum açamıyor").
Ekran tanıma, SecretProvider ve dağıtık runner bu aşamada başlatılmadı.

### Kök neden
- **Ön yüz:** Designer, Assistant ve Changes sayfalarının her biri kendi "Oturum aç" düğmesiyle `POST /api/sessions`
  çağırıyordu.
  - Oturum kimliği yalnız o sayfanın JS belleğindeydi; sayfa değişince ya da yenilenince kayboluyordu.
  - Kullanıcının mevcut oturumunu bulmanın ve seçmenin bir yolu yoktu.
  - Kullanıcı başına 1 etkileşimli oturum varsayılanıyla ikinci sayfa `session_limit_reached` (429) alıyordu.
  - `tests/e2e/test_{publish,assistant,changes}_ui.py` bunu `BROWSER_MAX_SESSIONS_PER_USER=2/3` ve
    `BROWSER_MAX_SESSIONS=6` override'larıyla gizliyordu.
- **Backend (incelemede bulunan güvenlik açığı):** Oturumun `purpose` alanı yalnız açılışta kotayı ayırıyordu.
  - Yeni oturum testi sürerken aynı kullanıcı geçici doğrulama oturumunun kimliğiyle public uçları çağırabiliyordu
    (gözlem, gezinme, run, kapatma).
  - Bu, geçici oturumun normal oturum yerine kullanılmasına ve etkileşimli kotanın atlatılmasına izin veriyordu.

### Uygulanan çözüm
- **Amaç sınırı** (`BrowserSessionService._owned`):
  - Doğrulama oturumu, sahibi için bile `operation`, `peek`, `close` ve `status` çağrılarında "bulunamadı" (404)
    döner.
  - Yalnız iç yeni oturum testi akışı açık `allow_verification=True` ile kullanabilir: `DesignerService` gezinmesi
    ve `RunService.create(allow_verification=True)`.
  - Public API istemciye amaç seçtirmez: `POST /api/sessions` her zaman `interactive` açar.
- **Durum ve kota görünümü:**
  - `GET /api/sessions/overview`: yalnız kullanıcının kendi etkileşimli oturumları; adres olarak yalnız origin+yol
    (sorgu gösterilmez), `alive`, `busy_operation` ve kota (`interactive_limit/used`, `total_capacity/used`,
    `verification_in_use`).
  - `GET /api/sessions/{id}`: sahiplik kontrollü durum.
  - 429 yanıtı kota ayrıntısını (`interactive_limit`, `interactive_used`) taşır.
- **Ortak oturum paneli** (`_session_panel.html`, `static/session_panel.js`); Designer, Assistant ve Changes
  sayfalarında aynı:
  - Seçili oturumu, adresini ve durumunu (hazır / meşgul (işlem) / kapanmış) ve kotayı gösterir.
  - Kullanıcının kendi oturumlarını "Bu oturumu kullan" ve "Kapat" (onay ister; meşgulken devre dışı) düğmeleriyle
    listeler.
  - Kota doluyken "Yeni oturum aç" düğmesi devre dışıdır ve açıklama gösterilir.
  - Sessizce oturum açılmaz ve otomatik seçim yapılmaz. Seçim oturumun adresini ya da içeriğini değiştirmez; gezinme
    yalnız kullanıcının "Ekranı aç" eylemiyle olur.
  - Sayfa yüklenince backend'den doğrulama yapılır:
    - `localStorage`'daki kimlik yalnız öneri olarak kullanılır: "Önceki oturumunuz bulundu; kullanmak için seçin".
    - Geçersiz/başkasının kimliği atılır: "Kayıtlı oturum artık geçerli değil".
    - Kapanmış seçili oturum "kapanmış veya geçersiz" olarak gösterilir.
  - Her işlem backend'de sahiplik ve meşguliyet kontrolünden geçer; istemci kimliği yetki sayılmaz.
- **Çakışan işlem:** Mevcut oturum kilidi korunur. Başka sayfadan çakışan işlem 409 alır ve hata metni gösterilir;
  panel "meşgul (run)" gösterir.
- **R2 izolasyon ve temizliği aynen korundu:** geçici doğrulama oturumu kotası, her durumda kapanma, zaman aşımında
  iptal, ana oturuma dokunmama.

### Varsayılan oturum limiti
- **Korundu:** `.env.example` `BROWSER_MAX_SESSIONS_PER_USER=1`, `BROWSER_MAX_SESSIONS=4`,
  `BROWSER_MAX_VERIFICATION_SESSIONS_PER_USER=1`.
- Limit artırılmadı. E2E'deki kullanıcı başına limit override'ları kaldırıldı:
  - `test_publish_ui.py`, `test_assistant_ui.py`, `test_changes_ui.py`: `BROWSER_MAX_SESSIONS_PER_USER`.
  - `test_changes_ui.py`: ayrıca `BROWSER_MAX_SESSIONS`.
- Gerçekten çoklu oturum kapasitesini sınayan testler (açık `SessionLimits(...)` ile birim ve tarayıcı testleri)
  korundu.

### Değişen dosyalar
- `src/agentask/application/services/browser_sessions.py`:
  - `_owned(allow_verification)`, `operation(..., allow_verification)`, `peek(..., allow_verification)`;
  - `status`, `overview`;
  - `SessionView.current_url/alive`;
  - 429 kota ayrıntısı.
- `src/agentask/application/services/runs.py`: `create(..., allow_verification=False)`.
- `src/agentask/application/services/designer.py`: yeni oturum testi iç kullanım bayrakları.
- `src/agentask/presentation/api/sessions.py`: `GET /overview`, `GET /{id}`, `current_url` (origin+yol), `alive`.
- `src/agentask/presentation/templates/_session_panel.html` (yeni), `static/session_panel.js` (yeni).
- `templates/{designer,assistant,changes}.html`, `static/{designer,assistant,changes}.js`: paneli kullanır; sayfaya
  özel "Oturum aç" kaldırıldı.
- Testler:
  - `tests/e2e/test_{designer,publish,assistant,changes}_ui.py`: override kaldırıldı; mevcut oturum açıkça seçilir.
  - `tests/e2e/test_cross_page_sessions.py` (yeni).
  - `tests/integration/test_session_sharing_api.py` (yeni).
  - `tests/unit/test_browser_sessions.py` (+2 test; R2'nin meşgul-kapanma testi iç kullanımı artık açık bayrakla
    yapıyor, beklentisi aynı).

### Testler ve sonuçlar
**Designer → Assistant → Changes geçişi** (`tests/e2e/test_cross_page_sessions.py`): varsayılan `.env.example`
(`BROWSER_MAX_SESSIONS_PER_USER == 1` testte doğrulanır), override yok, gerçek Chromium ve geçici mongod. Sonuç:
**1 passed.**
1. Designer'da "Yeni oturum aç".
2. Taslak hazırlama, deneme, yeni oturum testi (geçici doğrulama oturumu; sonrasında `verification_in_use == 0`),
   onay ve yayın.
3. Assistant'a geçiş:
   - Oturum otomatik seçilmez ("Seçili oturum yok").
   - "Önceki oturumunuz bulundu" notu ve kota 1/1 görünür; "Yeni oturum aç" devre dışıdır.
   - "Bu oturumu kullan" sonrası adres `/pages/duplicates` olarak kalır (değiştirilmedi).
4. İzinli test işlemi çalışır → **Başarılı**. Oturum kimliği değişmez (aynı tek oturum).
5. Changes'e geçiş:
   - Aynı seçim akışı.
   - Sayfa yenilenince seçim kalkar ve yeniden doğrulanarak seçilir.
   - "Ekranı aç" yalnız kullanıcı eylemiyle gezinir.
6. Ret kontrolleri:
   - **Çakışan işlem:** oturumda süren run varken Changes'te "Ekranla karşılaştır" → "başka bir işlem sürüyor" (409);
     panel "meşgul (run)" gösterir.
   - **Başka kullanıcı:** `GET /api/sessions/{id}` → 404, `POST /api/sessions/{id}/observe` → 404, overview boş.
   - **Saklı kimlik:** `localStorage`'a başkasının kimliği yazılınca "Kayıtlı oturum artık geçerli değil", seçim yok.

**Oturum sahipliği ve kota sınırı:**
- `tests/integration/test_session_sharing_api.py::test_overview_status_and_ownership`:
  - istemcinin gönderdiği `{"purpose": "verification"}` yok sayılır (`interactive`);
  - kota doluyken 429 + `{"interactive_limit": 1, "interactive_used": 1}`;
  - başka kullanıcıya 404 ve boş overview.
- `tests/unit/test_browser_sessions.py::test_status_and_overview_are_owner_scoped`.

**Doğrulama oturumu kota atlatmak için kullanılamaz:**
- `tests/integration/test_session_sharing_api.py::test_verification_session_id_rejected_by_public_endpoints`:
  geçici oturum kimliğiyle şu uçların hepsi **404** döner:
  - `GET /api/sessions/{id}`,
  - `POST .../observe`,
  - `POST .../navigate`,
  - `DELETE /api/sessions/{id}`,
  - `POST /api/runs`.
- `tests/unit/test_browser_sessions.py::test_verification_session_not_usable_as_interactive`: `operation`, `peek`,
  `close`, `status` reddedilir; geçersiz amaç da reddedilir.
- **Mutasyon kontrolü:** amaç denetimi geçici olarak kaldırılınca bu iki test kırıldı, geri alınınca yeşile döndü.

### Çalıştırılan komutlar (son durum)
| Komut | Exit | Sonuç |
|---|---|---|
| `.venv/bin/pytest -q -rs tests/e2e` | 0 | 7 passed (cross-page dahil; override'sız) |
| `.venv/bin/pytest -q -rs tests/unit/test_browser_sessions.py tests/integration/test_session_sharing_api.py tests/integration/test_sessions_api.py tests/e2e/test_cross_page_sessions.py` | 0 | 28 passed |
| R1/R2 regresyonu: `.venv/bin/pytest -q -rs tests/unit/test_sensitive.py tests/integration/test_assistant_sensitive.py tests/integration/browser/test_fresh_session_test.py tests/e2e/test_designer_ui.py` | 0 | 28 passed |
| `.venv/bin/pytest -q -rs tests/unit` | 0 | 285 passed |
| `.venv/bin/pytest -q -rs tests/integration/browser tests/integration/lab` | 0 | 99 passed |
| `.venv/bin/pytest -q -rs tests/integration/test_{app,cli,sessions_api,session_sharing_api,observation_api,runs_api,drafts_api,llm_adapter,assistant_sensitive}.py` | 0 | 49 passed |
| `.venv/bin/pytest -q -rs tests/integration/mongo` | 0 | 9 passed (geçici yerel mongod) |
| `.venv/bin/pytest -q -rs` (tamamı, son koşu) | 0 | 449 passed, 0 skipped |
| `.venv/bin/ruff check src tests` / `ruff format --check src tests` | 0 / 0 | temiz / 159 dosya |
| `.venv/bin/mypy` | 0 | 94 dosya, hata yok |

**Ara hatalar (kök nedenle düzeltildi):**
- R2'nin meşgul-kapanma birim testi, yeni amaç sınırı nedeniyle iç kullanım bayrağı olmadan takıldı (görev
  `SessionNotFound` alıp olayı set etmiyordu). Test iç kullanımı açık bayrakla yapacak şekilde güncellendi; beklenti
  değişmedi.
- `_Record.view()` güncellemesi ilk denemede uygulanmamıştı (`current_url=None`); düzeltildi.
- Panelde kota notu "önceki oturum bulundu" notunun üzerine yazıyordu; not önceliği düzeltildi.
- Tip ve satır uzunluğu uyarıları giderildi.

### Kalan sınırlamalar
- **Paneli kullanmayan sayfalar:** `/designer/targets` (Hedef Deneme) ve `/designer/runs` (İşlem Deneme) hâlâ
  kendi "Oturum aç" düğmelerini kullanıyor. Başka sayfada oturum açıkken varsayılan limitle 429 alırlar ve mevcut
  oturumu seçemezler. Bu aşamanın kapsamındaki üç sayfaya uygulandı; E2E testleri o sayfaları ayrı, temiz uygulama
  örneğinde çalıştırıyor.
- **Canlı durum yok:** meşgul/kapanmış durumu sayfa yüklemesinde, işlem sonrasında ve "Durumu yenile" ile güncellenir;
  anlık bildirim yok.
- **Çoklu sekme:** aynı oturumu iki sekmede seçmek mümkün. Çakışma backend kilidiyle (409) engellenir; ama sekmeler
  birbirinin gezinmesini görmez, ancak yenilemede görür.
- **Boşta kapanma:** `BROWSER_SESSION_IDLE_SECONDS` dolunca seçili oturum kapanabilir; panel bunu bir sonraki
  doğrulamada "kapanmış veya geçersiz" olarak gösterir.
- **Tek süreç:** kilit ve kotalar bellek içi (tek worker; denetim K3 açık).
- **Kapatma onayı:** tarayıcının `confirm()` penceresiyle alınır.

## Aşama 3 (2026-11-06): Yerel MongoDB otomatik başlatma (sökülebilir geliştirme aracı)

Kapsam: kullanıcının "MongoDB otomatik başlatma" talimatı. Önceki MongoDB başlatma talimatlarıyla çelişen noktalarda
bu talimat esas alındı. Ekran tanıma, SecretProvider ve dağıtık runner başlatılmadı.

### Durum ve kararlar
- **`.env.example` (kullanıcı değişikliği korunarak düzenlendi):** Görev öncesinde dosyanın sonuna
  `LOCAL_MONGO_AUTOSTART=false` ile yer tutucu değerli ikinci `MONGO_URI=<gerçek ortam bağlantısı>` ve
  `MONGO_DATABASE=<katalog veritabanı>` satırları eklenmişti.
  - Tekrarlı anahtarlar önceki geliştirme değerlerini ezdiği için örnek dosya geçersiz yapılandırma üretiyordu;
    43 ayar testi bu yüzden düştü.
  - `LOCAL_MONGO_AUTOSTART=false` etkin bırakıldı.
  - İki yer tutucu satır silinmedi; metinleri aynen korunarak "Gerçek ortam örneği" yorum bloğuna alındı.
- **Bağlantı ve altyapı ayrımı:**
  - Uygulama yalnız `MONGO_URI`/`MONGO_DATABASE` ile bağlanır ve `LOCAL_MONGO_AUTOSTART` bayrağını tanır.
  - Container başlatma tamamen `tools/local_mongo/` içindedir.
  - Bağımlılık yönü: geliştirme başlatıcısı → araç → uygulama. Uygulama aracı import etmez.
- **İki ayar grubu:**
  - Uygulama Settings'i `LOCAL_MONGO_` önekli araç anahtarlarını (AUTOSTART hariç) ayrılmış kabul edip yok sayar
    (`settings_customise_sources`); diğer bilinmeyen dotenv anahtarlarını eskisi gibi reddeder.
  - Araç kendi `LocalMongoSettings`'ini aynı .env'den okur ve kendi önekli yazım hatalarını reddeder.
  - Araç kapalıyken araç ayarları okunmaz ve zorunlu değildir.
- **Docker Compose CLI kullanılır:** liste argümanlı `subprocess`, `shell` yok. Docker SDK ya da başka yeni
  bağımlılık eklenmedi.
  - Araçta veri silen komut yoktur: `down -v`, `volume rm`, `rm` bulunmaz. Durdurma `stop` ile yapılır.
  - Teste özel kaynak temizliği yalnız test kodunda ve yalnız `agentask-test-*` adlı kaynaklarda yapılır.
- **Açık modda güvenlik denetimleri:**
  - `MONGO_URI` tek ve yerel sunucuyu (`127.0.0.1`/`localhost`), `LOCAL_MONGO_PORT`'u ve araç kimlik ayarıyla
    uyumlu kullanıcıyı göstermelidir. Uyumsuzsa açık hata verilir; URI değiştirilmez ve Docker'a dokunulmaz.
  - Port başka bir servisteyse o servise dokunulmadan hata verilir.
  - Mevcut container/volume yeniden kullanılır; ping başarılı olunca uygulama başlar.
- **Kalıcılık:**
  - Named volume (`LOCAL_MONGO_VOLUME`) ve sabit Compose proje adı (`-p LOCAL_MONGO_PROJECT`) kullanılır; ikisi de
    çalışma klasörüne bağlı değildir.
  - Port yalnız `127.0.0.1`'e açılır; `restart: unless-stopped`.
  - Otomatik seed yoktur. `ensure_schema` idempotent olduğundan mevcut kataloğu ezmez (Docker testinde doğrulandı).
- **Yedek/geri yükleme:** `mongodump`/`mongorestore` container içinde çalışır; geri yükleme yalnız ayrı bir
  veritabanına yapılır.
- **Ortam (bilgi):** Görev başında Docker daemon erişilemiyordu. Daemon'u ben başlatmadım; daha sonra erişilebilir
  hâle geldi (Docker 29.9.2, Compose v5.6.1) ve gerçek Docker testleri çalıştırıldı.
- **Hata ve temizlik:** İlk Docker test koşularında test temizliği, `docker`'ı içermeyen kısıtlı bir PATH ile
  çağrıldığı için başarısız oldu. Bunun sonucunda yalnız testlere ait üç container, üç volume ve üç ağ kaldı
  (`agentask-test-<hex>`). Bunlar ad deseniyle tek tek kaldırıldı; başka bir Docker kaynağına dokunulmadı.
  Temizlik düzeltildi; her koşudan sonra `agentask` kaynağı kalmadığı doğrulandı.

### Değişen / yeni dosyalar
- Uygulama: `src/agentask/config/settings.py` (`local_mongo_autostart`, development kuralı, araç öneki filtresi).
- Araç (yeni):
  - `tools/__init__.py`
  - `tools/local_mongo/{__init__,__main__,settings,compose,manager,launcher}.py`
  - `compose.local-mongo.yml`
  - `.vscode/tasks.json`
- Yapılandırma ve belge: `.env.example`, `docs/05_CONFIGURATION.md`, `README.md`.
- `pyproject.toml`: `docker` marker'ı; araç ve test dosyaları için gerekçeli per-file lint istisnaları; mypy
  `packages`'a `tools`.
- Testler:
  - `tests/unit/test_settings.py`: bayrak testleri; parite testi araç öneki dışındaki anahtarları birebir
    karşılaştırır, araç anahtarları ayrı parite testinde birebir doğrulanır.
  - `tests/conftest.py`: `LOCAL_MONGO_*` ortam yalıtımı.
  - Yeni: `tests/unit/test_local_mongo_tool.py`, `tests/integration/test_local_mongo_off.py`,
    `tests/integration/docker/test_local_mongo_docker.py`.

### Testler
**Açık mod (gerçek Docker, yalnız teste özel proje/volume/port):**
- `test_launcher_prepares_mongo_starts_app_and_release_survives_restarts`:
  - Başlatıcı Compose ile Mongo'yu hazır eder ve uygulamayı başlatır; `/health/ready` `catalog_mongo: available`.
  - Katalog yayımlanır.
  - Uygulama durdurulur, Mongo `stop` edilir, başlatıcı yeniden açılır.
  - `/api/catalogs/releases`'te aynı `active_release_id` ve `manifest_hash`.
- `test_release_survives_mongo_restart_and_container_recreate`: Mongo `stop`/`up` ve container yeniden
  oluşturulduktan (`rm -sf` + `up`, aynı named volume) sonra yayın ve hash korunur; `ensure_schema` veriyi ezmez.
- `test_real_port_conflict_leaves_other_service_untouched`: portu tutan diğer soket açık kalır, container
  oluşturulmaz, komut açık hatayla (çıkış ≠ 0) döner.

**Kapalı mod:**
- `test_launcher_off_mode_starts_app_without_docker`: PATH'te `docker` yok; başlatıcı gerçek (geçici) mongod ile
  uygulamayı başlatır; `catalog_mongo: available`; çıktıda Docker izi yok.
- `test_off_mode_with_unreachable_mongo_fails_explicitly`: readiness `503 not_ready`; sessiz geçiş yok.
- `test_launcher_false_path_never_loads_docker_module`: `compose`/`manager` modülleri yüklenmez.
- `test_tool_settings_not_required_when_autostart_false`: araç ayarları silinmiş .env ile çalışır; Docker çağrısı
  sıfır.
- `test_app_imports_and_starts_without_tool_modules`: `-I` ve `cwd=tmp` ile `tools` bulunamaz; uygulama import
  edilir ve kurulur; `agentask --check-config` başarılı.
- **Fiilî kaldırma denemesi:** `tools/`, `compose.local-mongo.yml` ve `.vscode/` geçici olarak taşındı.
  `test_app.py`, `test_settings.py`, `test_runs_api.py` ve `tests/integration/mongo` geçti (102 passed) ve
  `agentask --check-config` başarılı oldu; ardından dosyalar geri kondu.

**Güvenlik:**
- Development dışında `true` reddedilir (`test_local_mongo_autostart_only_in_development[test|production]`).
- Uzak, `+srv`, çok sunuculu, port uyumsuz ya da kimlik uyumsuz URI otomatik yönetilmez ve Docker çağrılmaz
  (`test_managed_uri_must_match_local_service`, 5 durum).
- Port çakışmasında başka servise dokunulmaz (birim + gerçek Docker).
- Araç komutları veri silmez (`test_commands_never_remove_data`).
- Compose dosyası yalnız loopback'e açılır ve named volume kullanır.
- Geri yükleme ana veritabanına yapılamaz.
- Docker testleri geliştiricinin volume adını (`agentask-local-mongo-data`) asla kullanmaz (assert) ve yalnız kendi
  `agentask-test-*` kaynaklarını temizler.
- Uygulama `tools`'u import etmez.

### Çalıştırılan komutlar
| Komut | Exit | Sonuç |
|---|---|---|
| `.venv/bin/pytest -q -rs tests/unit/test_local_mongo_tool.py tests/unit/test_settings.py` | 0 | 82 passed |
| `.venv/bin/pytest -q -rs tests/integration/test_local_mongo_off.py` | 0 | 3 passed (geçici mongod, PATH'te docker yok) |
| `.venv/bin/pytest -q -rs -m docker tests/integration/docker` | 0 | 3 passed (gerçek Docker 29.9.2; teste özel kaynaklar) |
| R1/R2/R2B regresyonu (`test_sensitive`, `test_assistant_sensitive`, `test_fresh_session_test`, `test_browser_sessions`, `test_session_sharing_api`, `e2e/test_designer_ui`, `e2e/test_cross_page_sessions`) | 0 | 52 passed |
| Araç dosyaları taşınmışken `pytest tests/integration/test_app.py tests/unit/test_settings.py tests/integration/test_runs_api.py tests/integration/mongo` + `agentask --check-config` | 0 / 0 | 102 passed / "Yapılandırma geçerli" |
| `.venv/bin/pytest -q -rs` (tamamı, Docker testleri dahil) | 0 | 473 passed, 0 skipped |
| `.venv/bin/ruff check src tests tools` / `ruff format --check src tests tools` | 0 / 0 | temiz / 170 dosya |
| `.venv/bin/mypy` (src + lab + tools) | 0 | 101 dosya, hata yok |
| Koşu sonrası `docker ps -a` / `docker volume ls` (`agentask` filtresi) | — | kalan kaynak yok |

### Kalan sınırlamalar
- Docker daemon yoksa Docker testleri `BLOCKED` olarak atlanır. Bu ortamda bu koşuda daemon vardı ve testler çalıştı.
- **Sürüm:** Mongo image etiketi `mongo:8.0` (sürüm ailesi, digest değil); tekrar üretilebilirlik için digest
  sabitlenebilir.
- **Kimlik doğrulama:** yerel servis varsayılan olarak kimlik doğrulamasızdır (yalnız 127.0.0.1). Opsiyonel root
  kullanıcı desteği var ama gerçek Docker ile **test edilmedi**. URI denetimi yalnız kullanıcı adının uyumunu
  kontrol eder, parolayı karşılaştırmaz.
- **Yedekleme:** `backup`/`restore` gerçek Docker ile **test edilmedi**; birim testi yalnız ana veritabanına geri
  yükleme reddini doğrular.
- **Container sahipliği:** başlatıcı, Compose projesine ait container'ın "çalışıyor" durumuna güvenir; aynı proje
  adını başka bir Compose kurulumu kullanıyorsa ayırt edemez.
- **Ortam çeşitliliği:** Windows/WSL ve Podman denenmedi.
- **Gerçek ortam:** kurumsal MongoDB (TLS/CA, kimlik doğrulama, replica set) hâlâ doğrulanmadı (denetim notu geçerli).

### Oturum kapanışı (2026-11-06)
- Bu oturumda başlatılan uygulama, lab, geçici mongod ve test süreçlerinin hepsi testlerin kendi temizliğiyle kapandı.
  Kapanış kontrolünde açık `agentask`/`agentask-lab`/pytest süreci yoktu; `agentask` adlı Docker container'ı ya da
  volume'u da yoktu.
- **Homebrew `mongod` (PID 1666):** 2026-11-05'ten beri `127.0.0.1:27017`'de dinliyor. Bu süreç bu çalışmada
  başlatılmadı, kapatılmadı ve verisine dokunulmadı.
  - `LOCAL_MONGO_AUTOSTART=true` ve `LOCAL_MONGO_PORT=27017` ile başlatıcı, tasarım gereği "port başka bir serviste"
    hatası verir.
  - Ya `false` ile bu mongod'u kullanın ya da farklı bir `LOCAL_MONGO_PORT` ve buna uyan `MONGO_URI` seçin.
- Hiçbir MongoDB verisi, container volume'u veya katalog silinmedi.
- Proje klasörü git deposu değil; commit yapılmadı. `.gitignore` `.env` ve `.env.*` dosyalarını dışlar
  (`.env.example` hariç).
- Yeniden başlatma komutları: docs/10_PROGRESS.md → "Devam noktası (2026-11-06)".

## R3 durum kaydı (2026-11-06): Ekran tanımı ve eski katalog geçişi — BAŞLAMADI

**Durum: kod uygulaması başlamadı.** Bu bölüm bir tamamlanma kaydı değildir. Yalnız mevcut durumu, manuel test
bulgularını ve kod incelemesiyle doğrulanan kök nedenleri kaydeder.

### Kanıt (2026-11-06)
- `grep -rniE 'ScreenDef|assert_screen|catalog_screens|SCREEN_NOT_RECOGNIZED|MigrationRequired|migration_required|screen_ref' src tests tools`
  → eşleşme yok.
- Kaynak ve test dosyalarındaki en son değişiklik 2026-11-06 00:15 (yerel Mongo aracı). R3 için dosya
  değişmedi.
- Katalog sözleşmesindeki (docs/02) Screen varlığı ve `catalog_screens` koleksiyonu hâlâ yok. Bu, denetim
  bulgusu K5'in ekran kısmıdır.
  - `domain/release.py`: manifestoda ekran alanı yok.
  - `infrastructure/mongo/catalog_store.py`: yalnız 3 koleksiyon var.
- **Mevcut temel:**

  | Komut | Exit | Sonuç |
  |---|---|---|
  | `.venv/bin/pytest -q -rs` | 0 | 470 passed, 3 skipped |
  | `.venv/bin/ruff check src tests tools` | 0 | temiz |
  | `.venv/bin/mypy` | 0 | 101 dosya, hata yok |

  - 3 skip, `-m docker` testleridir: Docker daemon bu koşuda kapalıydı, testler BLOCKED olarak atlandı.
- **Korunan veri:** MongoDB verisine ve yayımlanmış kataloglara dokunulmadı (`kefil_musteri_no` r1 dahil).
  `LOCAL_MONGO_AUTOSTART=false` değiştirilmedi.
- **Not:** `.env.example` 2026-11-06 11:30'da değişmiş görünüyor. Bu değişiklik bu çalışmada yapılmadı; içerik
  olduğu gibi bırakıldı.

### Kullanıcının manuel testi (bilgi olarak kaydedildi)
`kefil_musteri_no` r1 yayımlandı. Model kapalıyken talep ile `00456` değeri yalnız Kefil alanına yazıldı ve başarı
kontrolü geçti. Bu, lab akışının çalıştığını gösterir; Pega uyumluluğu değildir.

### Manuel testte görülen arayüz bulguları (açık; düzeltilmedi)
| # | Bulgu | Kod incelemesiyle bulunan kök neden |
|---|---|---|
| U1 | Taslak listesinde adım sayısı güncellenmiyor, 0 görünüyor | `static/designer.js`: `loadDrafts()` yalnız sayfa açılışında ve taslak oluşturulunca çağrılıyor; adım ekleme/silme (`mutate`) sonrası liste yenilenmiyor. API (`GET /api/drafts`) `len(d.steps)` döndürüyor. |
| U2 | Form doğrulama hatası hangi alanın neden hatalı olduğunu söylemiyor | `presentation/errors.py`: istek/alan doğrulama hataları yalnız "İstek doğrulanamadı." / "Girdi doğrulanamadı." ile alan yolu listesi (`details.fields`) döndürüyor, neden yok. `designer.js` `call()` yalnız `safe_message` ve `details.reason` gösteriyor, `fields` hiç gösterilmiyor. |
| U3 | Çalıştırma planında parametre yerine `{musteri_no}` görünüyor | `application/services/assistant.py::preview` `steps` alanını `standard_text`'ten şablon doldurulmadan döndürüyor; komutlarda değer doğru bağlanıyor, yalnız gösterilen açıklama doldurulmuyor. |

### R3 kapsamı (uygulanacak; şu an hiçbiri yok)
- [ ] Ekran tanımı (ScreenDef): `screen_id`, başlık, mantıksal bölgeler, tanıma işaretleri (her biri tekil
  çözülmesi gereken anlamsal hedef). Her bölge en az bir işaretle kanıtlanır. Element bölgeleri ekran bölgeleri
  içinde olmalı.
- [ ] Döngüsel doğrulama engeli: işaretlerin hepsi işlemin kendi hedefleri olamaz.
- [ ] Mongo `catalog_screens`: değişmez revizyon, application_id + screen_id + revision unique.
  - Manifestoya `screens` listesi eklenecek; eski manifestolar değişmeden okunacak.
  - Ekran hash'i işlem içeriğine bağlanacak; böylece ekran değişirse yeniden onay gerekecek.
- [ ] Çalışma anı `assert_screen` komutu: planın başında ve devamda yeniden.
  - Tanınmayan, belirsiz veya eksik kanıtlı ekranda hiçbir alana dokunulmadan açık hata verilecek.
- [ ] **Eski yayın uyumluluğu:** ekran tanımı olmayan revizyonlarda (ör. `kefil_musteri_no` r1) önizleme,
  çalıştırma ve bileşik plan açık bir "geçiş gerekli" hatasıyla reddedilecek; sessiz atlama yok.
- [ ] **Geçiş ve yeniden onay:**
  1. Yayımlanmış tanımdan geçiş taslağı oluşturulacak.
  2. Taslağa ekran tanımı eklenecek.
  3. Yeni oturum testi yapılacak.
  4. Hash'e bağlı onay alınıp yeni revizyon (r2) yayımlanacak.

  r1 ve eski manifestolar yerinde değiştirilmeyecek ve silinmeyecek.
- [ ] U1–U3 düzeltmeleri ve testleri.
- [ ] Testler, bu kayda sonuçlar ve exit code'lar.

## R3 (2026-11-06): Ekran tanımı, bölge doğrulaması ve eski katalog geçişi — COMPLETED (lab kapsamında)

Bu bölüm yukarıdaki "R3 durum kaydı — BAŞLAMADI" kaydının yerine geçer; o kayıt tarihçe olarak bırakıldı. Buradaki
her iddia aşağıda adı geçen testlerle ve bu oturumda çalıştırılan komutlarla desteklenir. Gerçek Pega uyumluluğu
iddia edilmez.

### Uygulanan davranış
- **Sürümlü ekran tanımı** (`domain/screens.py`): `ScreenDef` şunlardan oluşur:
  - `markers`: zorunlu, tekil çözülmesi gereken anlamsal TargetSpec'ler;
  - `absent_markers`: benzer yanlış ekranı ayıran ve tam kapsamla "yok" kanıtlanması gereken işaretler;
  - `regions`: her biri en az bir işaretle kanıtlanan mantıksal bölgeler.

  Tanımda selector, XPath, DOM id, frame sırası, URL veya koordinat yoktur (`extra=forbid`). Aday kimlikleri yalnız
  tanımlama isteğinde kullanılır, saklanmaz.
- **Ortak doğrulama çekirdeği** (`judge`): kod kuralıdır, model kullanılmaz. Sonuç dört durumdan biridir:

  | Durum | Koşul |
  |---|---|
  | `recognized` | bütün zorunlu işaretler tekil, hiçbir yasak işaret yok |
  | `not_recognized` | bir işaret yok ya da yasak işaret görüldü (yanlış/benzer ekran) |
  | `ambiguous` | işaret tekil değil (ör. yinelenen bölge) |
  | `incomplete` | kapsam eksik; ekran doğru ya da yanlış kanıtlanamadı |

  - Yürütücü (`assess_screen`), Tasarımcı (kaydetmeden önce canlı doğrulama ve "Ekranı doğrula") ve Değişiklikler
    (`analyze` → `screen`) aynı fonksiyonu kullanır.
- **Döngüsel doğrulama yok:**
  - İşaretlerin hepsi işlemin kendi hedefleriyse tanım reddedilir (`screen_markers_only_targets`).
  - Elemanlar ekran tanınsa da kendi bölge bağlamıyla ayrıca çözülür.
  - Eleman bölgesi ekran bölgeleri içinde olmalıdır (`element_region_not_in_screen:<id>`).
- **Çalışma anı:**
  - Derlenen her plan `assert_screen` ile başlar.
  - Etkin ekran, sonraki her sayfa adımından önce güncel gözlemle yeniden doğrulanır. Gezinme veya frame değişimi
    sonrası eski snapshot ve locator kullanılmaz.
  - Tanınmayan, belirsiz veya eksik kanıtlı ekranda adım hiçbir sürücü eylemi yapmadan durur:
    `SCREEN_NOT_RECOGNIZED`, belirsizlikte `PAUSED_AMBIGUOUS`, aksi halde `FAILED`. Adım mesajı "İşlem yapılmadı"
    der.
  - Geç gelen frame için `READINESS_TIMEOUT_MS` içinde DOM/frame değişimine bağlı beklenir. Devam ederken
    (`_revalidate`) ekran yeniden doğrulanır.
- **MongoDB:**
  - `catalog_screens`: $jsonSchema, (application_id, screen_id, revision) unique; aynı revizyon farklı hash ile
    yazılırsa `ContentConflict`.
  - İşlem tanımındaki `screen_ref` (ekran içerik hash'i) sayesinde onay hash'i ekranı kapsar.
  - Manifest `screens` listesi ekran revizyonlarını pinler ve manifest hash'ine girer. `SCHEMA_VERSION=catalog-v2`.
  - Yayında ekran revizyonu işlem revizyonundan önce yazılır, manifest yazılmadan önce referansı doğrulanır.
    Pointer en son CAS ile değişir.
- **Eski katalog uyumluluğu ve geçiş:**
  - catalog-v1 revizyon ve manifestolar olduğu gibi okunur (`screens` yoksa boş). `ensure_schema` yalnız koleksiyon
    ve indeks ekler; mevcut belge değişmez.
  - Ekransız işlem önizleme, çalıştırma ve bileşik planda 409 `migration_required` döner (details: operation_id,
    revision). Run oluşturulmaz.
  - Asistan ve Değişiklikler ekranları işlemi "geçiş gerekli" olarak gösterir.
  - Geçiş adımları:
    1. Tasarımcı › "Geçiş gereken eski yayınlar" › **Geçiş taslağı oluştur**. Yayına yazılmaz.
    2. Ekran tanımı eklenir; tanım kaydedilmeden önce canlı doğrulanır.
    3. Yeni oturum testi yapılır; eski test kanıtı taşınmaz.
    4. Hash-bağlı onay alınır.
    5. Yayımlanır: yeni revizyon (r2) ve yeni manifest oluşur. r1, eski manifest ve geçmiş run'lar yerinde kalır.
  - Kullanıcının veritabanında otomatik geçiş veya yayın yapılmaz.
- **Arayüz bulguları:**
  - **U1:** taslak listesi her değişiklikten sonra yenilenir. Adım sayısının yanında ekran tanımı ve geçiş kaynağı
    da gösterilir.
  - **U2:** 422 yanıtları `details.errors[] = {field, reason, message}` taşır. Neden Türkçedir (ör. "küçük harfle
    başlamalı…", "500 veya daha küçük olmalı", "zorunlu alan boş bırakılamaz"). Girdi değeri yanıta konmaz.
    Tasarımcı alan adını Türkçe etiketle listeler.
  - **U3:** önizleme `steps` adımlarını bağlı değerle doldurur ve ilk satır "Ekranı doğrula: …" olur. `bindings`
    parametre başlığı ile değeri gösterir. Hassas görünen değer ve secret_ref `••••` olarak maskelenir; yanıttaki
    `commands` kopyası da maskelidir. Yürütme planı sunucuda ayrıca derlenir. Hassas kullanıcı argümanı (R1) yine
    önizlemeden önce reddedilir.

### Değişen / yeni dosyalar
- **Alan:**
  - `domain/screens.py` (yeni)
  - `domain/catalog.py`: `screen`, `migrated_from`, `requires_migration`, `bind_arguments`,
    `compile_operation(screen_check=…)`
  - `domain/release.py`: `ScreenRevision`, `ScreenEntry`, `manifest.screens`, `catalog-v2`
  - `domain/commands.py`: `AssertScreenCommand`
  - `domain/actions.py`: `SCREEN_NOT_RECOGNIZED`
  - `domain/assistant.py`: `migration_required`
  - `domain/impact.py`: onarım taslağı ekranı taşır
- **Uygulama:**
  - `application/errors.py`: `MigrationRequired`, `ScreenNotRecognized`
  - `application/ports/catalog.py`: ekran revizyonu metotları
  - `application/services/observation.py`: `assess_screen`, `assess_screen_on`
  - `application/services/executor.py`: doğrulama ve yeniden doğrulama
  - `application/services/publishing.py`: ekran yazımı, manifest, `screen_of`, `published_draft`
  - `application/services/assistant.py`: geçiş reddi, bağlı değerler, maskeleme
  - `application/services/designer.py`: ekran tanımlama/doğrulama/kaldırma, geçiş listesi ve taslağı
  - `application/services/impact.py`: ekran sonucu
  - `bootstrap.py`: tasarımcıya yayın servisi bağlandı
- **Altyapı:** `infrastructure/mongo/catalog_store.py` (`catalog_screens` + şema + indeks).
- **Sunum:**
  - `presentation/api/drafts.py`: `PUT`/`DELETE /screen`, `POST /screen/verify`, `GET`/`POST /migrations`
  - `presentation/errors.py`: U2, yeni hata eşlemeleri
  - `templates/designer.html`, `static/designer.js`: ekran tanımı, geçiş listesi, U1, U2
  - `static/assistant.js`: U3, geçiş uyarısı
  - `static/changes.js`: ekran sonucu
- **Deney uygulaması (test ikamesi):**
  - `agentask_lab/state.py`: `party_layout` = standard / similar / duplicate_guarantor; `party_switch` = none / dom /
    navigate
  - `agentask_lab/app.py`: `/cases/{id}/parties` aynı ekranı farklı adreste sunar
  - `templates/duplicates.html`
- **Belgeler:**
  - `docs/adr/0010-r3-ekran-tanimi-ve-gecis.md` (yeni)
  - `docs/02_CATALOG_CONTRACTS.md`, `docs/09_API_CONTRACTS.md`: R3 notları
  - bu kayıt ve `docs/10_PROGRESS.md`
- **Testler:**
  - Yeni:
    - `tests/screens.py`, `tests/legacy_catalog.py` (yalnız test deposuna yazar)
    - `tests/unit/test_screens.py` (13)
    - `tests/unit/test_screen_publishing.py` (7)
    - `tests/integration/browser/test_screen_runtime.py` (8)
    - `tests/integration/mongo/test_mongo_screens.py` (3)
    - `tests/integration/test_screen_api.py` (3)
    - `tests/e2e/test_r3_migration_ui.py` (1)
  - Güncellenen: ekran adımını içeren yeni beklentiler, ekran tanımlı test verisi. Hiçbir test silinmedi; beklenti
    gevşetilmedi. `test_assistant_ui`'deki `{musteri_no}` beklentisi U3 hatasını kodluyordu; doğru değer ve
    `{`'nin yokluğu ile değiştirildi.
    - `tests/fake_catalog_store.py`
    - `tests/unit/test_catalog_domain.py`, `test_composition.py`, `test_publishing.py`
    - `tests/integration/test_assistant_sensitive.py`
    - `tests/integration/browser/test_assistant.py`, `test_composition_run.py`, `test_designer.py`,
      `test_impact.py`
    - `tests/e2e/test_designer_ui.py` (ekran tanımı + U1 + yeni U2 testi), `test_assistant_ui.py` (U3)
- **Değişmeyenler:**
  - `.env.example` ve `docs/05_CONFIGURATION.md`: yeni ortam ayarı gerekmedi, değişmedi. Ekran bekleme süresi
    mevcut `READINESS_TIMEOUT_MS` ile yönetilir.
  - Kullanıcının `.env` dosyası ve `LOCAL_MONGO_AUTOSTART=false` değeri.

### Kapsanan senaryolar (testler)
| Senaryo | Test | Yazma/tıklama yok kanıtı |
|---|---|---|
| Doğru ekran, lab'ın bilinen adresi olmayan rastgele vaka adresinde | `test_correct_screen_recognized_at_unrelated_url` | Başvuran alanı boş kalır; adım sonucunda `screen_reverified` var |
| Benzer yanlış ekran (hedef tekil bulunsa da) | `test_similar_wrong_screen_refused_although_target_exists`; birim `test_similar_wrong_screen_rejected_even_though_target_resolves` | sürücü spy'ı boş, Kefil alanı boş |
| Yinelenen bölge | `test_duplicated_region_is_ambiguous_and_untouched` (`PAUSED_AMBIGUOUS`) | iki Kefil alanı boş |
| Eksik tarama (erişilemeyen frame) | `test_incomplete_scan_is_not_treated_as_recognized` (`incomplete`) | spy boş |
| İç içe + geç gelen frame | `test_nested_and_late_frames_wait_for_evidence` / `test_missing_late_frame_evidence_stops_before_nested_write`; birim `test_nested_frame_markers_scoped_by_frame_title` | iç frame alanı boş |
| Eylem öncesi ekran değişimi (SPA DOM ve gezinme) | `test_screen_change_before_next_action_stops_without_writing[dom\|navigate]` | yalnız ilk alana 1 `fill`; Kefil boş; sonraki adımlar `pending`. Gezinmede yazmanın tekrar denemesi de ekran kontrolüne takılır (`FRAME_CHANGED` → `SCREEN_NOT_RECOGNIZED`) |
| Eski yayın reddi | `test_legacy_operation_rejected_with_migration_required` | run oluşmaz, depoya yazılmaz |
| Geçiş akışı | `test_migration_flow_creates_new_revision_and_keeps_legacy` | r1 ve eski manifest aynı |
| Gerçek MongoDB roundtrip, ham v1 belgelerin korunması | `test_screen_revision_roundtrip_and_restart`, `test_catalog_screens_schema_and_immutability`, `test_pre_r3_documents_preserved_rejected_and_migrated` | `ensure_schema` ve geçiş sonrası ham belgeler bayt bayt aynı |
| Arayüz E2E | `test_legacy_release_migrated_through_ui` (red → geçiş → ekran → test → onay → r2 → doğru ekranda çalıştırma → yanlış ekranda `SCREEN_NOT_RECOGNIZED`, başarılı adım 0), `test_designer_screen_guided_authoring`, `test_form_validation_explains_field_and_reason`, `test_assistant_runs_published_operation` | yanlış ekranda başarılı adım satırı yok |
| Changes aynı çekirdek | `test_label_change_detected_and_repair_draft` (tanındı / benzer ekranda tanınmadı / onarım taslağı ekranı taşır) | — |

- **Mutasyon kontrolü:** adım öncesi yeniden doğrulama ve yasak işaret kuralı geçici olarak kapatıldı. 5 test düştü
  (`test_screen_runtime` içinden 4, `test_screens` içinden 1). Kod geri alındı ve 21/21 geçti.
- **Kararlılık:** R3 tarayıcı ve E2E grubu (14 test) üç kez arka arkaya geçti.

### Çalıştırılan komutlar
| Komut | Exit | Sonuç |
|---|---|---|
| `.venv/bin/pytest -q tests/unit/test_screens.py tests/unit/test_screen_publishing.py` | 0 | 20 passed |
| `.venv/bin/pytest -q tests/integration/browser/test_screen_runtime.py` | 0 | 8 passed (gerçek Chromium) |
| `.venv/bin/pytest -q -m mongo tests/integration/mongo` | 0 | 12 passed (geçici mongod 8.0.34, rastgele test DB) |
| `.venv/bin/pytest -q tests/integration/test_screen_api.py tests/integration/browser/test_impact.py tests/integration/browser/test_designer.py` | 0 | 8 passed |
| `.venv/bin/pytest -q tests/e2e/test_r3_migration_ui.py tests/e2e/test_designer_ui.py tests/e2e/test_assistant_ui.py` | 0 | 4 passed |
| R1/R2/R2B/yerel Mongo regresyonu (`test_sensitive`, `test_assistant_sensitive`, `test_fresh_session_test`, `test_browser_sessions`, `test_session_sharing_api`, `e2e/test_cross_page_sessions`, `test_local_mongo_tool`, `test_local_mongo_off`) | 0 | 68 passed |
| `.venv/bin/pytest -q -rs` (tamamı) | 0 | 506 passed, 3 skipped |
| `.venv/bin/ruff check src tests tools` / `ruff format --check src tests tools` | 0 / 0 | temiz / 179 dosya |
| `.venv/bin/mypy` | 0 | 102 dosya, hata yok |
| `docker info` | 1 | **BLOCKED:** Docker daemon kapalı; 3 `-m docker` testi atlandı. Ben başlatmadım. |

### Kullanıcı verisi
- Testlerin hiçbiri kullanıcının MongoDB'sine bağlanmaz: geçici mongod ve rastgele test veritabanı kullanılır.
- `kefil_musteri_no` r1 dahil mevcut yayınlara bu çalışmada dokunulmadı.
- Uygulama bir sonraki başlatılışta (`ensure_schema`) kullanıcı veritabanında boş `catalog_screens` koleksiyonunu ve
  indeksini oluşturur. Mevcut belgeler değişmez.
- r1 bundan sonra asistanda `migration_required` ile reddedilir. Bu, istenen davranıştır.

### Kalan sınırlamalar
- **Tek ekran:** bir işlem tek ekrana bağlıdır. İşlem içinde ekranı değiştiren (gezinen) onaylı aksiyondan sonraki
  adımlar reddedilir; çok ekranlı işlem ve ekran geçişi tanımı yok.
- **Yarış penceresi:** yeniden doğrulama ile sürücü eylemi arasında kısa bir aralık vardır. Bu aralıkta ekran
  değişirse adım ya bayat aday (`FRAME_CHANGED`) ya da sonuç doğrulamasıyla yakalanır; mutlak bir garanti verilmez.
- **İşaret seçimi** tasarımcının sorumluluğundadır. Tek işaretli ve "olmamalı" işareti olmayan tanım, benzer
  ekranları ayırmayabilir. Sistem yalnız "hepsi işlemin kendi hedefi" durumunu ve bölge kanıtı kuralını zorlar.
- **"Olmamalı" işareti** arayüzde elle girilir (tür, etiket, bölge). Benzer yanlış ekrandan gözlemle seçme akışı
  yok.
- **Maliyet:** yeniden doğrulama her sayfa adımında ek gözlem yapar. Ağır ekranlarda süre artışı ölçülmedi.
- **Mevcut yerel taslaklar** (ör. kullanıcının `kefil_musteri_no` taslağı) ekran tanımı eklenmeden onaylanamaz
  (`screen_missing`).
- **Maskeleme sezgiseldir** (`domain/sensitive`). Hassas olup kalıba uymayan değer gösterilebilir. Ancak kullanıcı
  argümanında şüpheli değer zaten reddedilir.
- **Gerçek ortam:** gerçek Pega ekranlarında tanıma yeterliliği, kurumsal MongoDB ve Docker testleri doğrulanmadı.

### Arayüzden doğrulama adımları (kullanıcı için)
Kendi `.env` ayarlarınızla (`LOCAL_MONGO_AUTOSTART=false`, mevcut Homebrew Mongo) uygulamayı başlatın:

```bash
.venv/bin/agentask-lab     # http://127.0.0.1:8100
.venv/bin/agentask         # ayrı terminal, http://127.0.0.1:8000
```

1. **Eski yayının reddi.** `/assistant` sayfasında şunları kontrol edin:
   - Üst satırda "… işlem ekran tanımı olmadığı için geçiş bekliyor" yazmalı.
   - "Kefil müşteri numarasını gir" → **Yorumla** → değer `00456` → **Planı göster**.
   - "ekran tanımı olmayan eski bir yayından…" hatası çıkmalı ve plan gösterilmemeli.
2. **Geçiş taslağı.** `/designer` sayfasında:
   - **Yeni oturum aç** (veya mevcut oturumu seçin) → Deney ekranı "Başvuran/Kefil" → **Ekranı aç**.
   - "Geçiş gereken eski yayınlar" altında `kefil_musteri_no r1` → **Geçiş taslağı oluştur**.
   - "Geçiş taslağı: kefil_musteri_no r1 …" satırı görünmeli.
   - Taslak listesinde adım sayısı ve "ekran tanımı yok" görünmeli (U1).
3. **Ekran tanımı.**
   - Ekran kimliği `basvuru_taraflar`, ad "Başvuru — taraf bilgileri".
   - **Ekrandaki kontrolleri listele** → "Müşteri No · metin alanı · Başvuran" ve "Ad Soyad · metin alanı · Kefil"
     kutularını işaretleyin.
   - "Bu ekranda olmamalı": metin alanı / `Talep Notu` / `Kefil`.
   - **Ekran tanımını doğrula ve kaydet** → "Doğrulama: TANINDI" ve "bölgeler: Başvuran, Kefil" görünmeli.
   - Deneme: yalnız "Müşteri No · Kefil" kutusunu seçip kaydedin → "işlemin kendi hedefine dayanamaz" hatası çıkmalı.
4. **U2.** Parametre formunda adı `Müşteri No`, en fazla `600` girin → hata listesinde iki satır görünmeli:
   - "Ad: küçük harfle başlamalı…"
   - "En fazla: 500 veya daha küçük olmalı"
5. **Test, onay ve yayın.**
   - Başlangıç ekranı "Başvuran/Kefil", test değeri girin → **Yeni oturum testi** → "İncelemeye hazır…".
   - **Onayla (yayıncı)** → **Yayımla** → "kefil_musteri_no r2". Geçiş listesi "Geçiş gereken işlem yok." olmalı.
   - `/catalogs` sayfasında eski yayın pasif olarak duruyor olmalı.
6. **Çalıştırma ve U3.** `/assistant` sayfasında:
   - Aynı talep, değer `00456` → **Planı göster**.
   - "revizyon 2", ilk adım "Ekranı doğrula: Başvuru — taraf bilgileri", "alanına 00456 değerini yaz" ve
     "Müşteri No: 00456" görünmeli; `{musteri_no}` görünmemeli.
   - Oturumu seçin → **Ekranı aç** → **Çalıştır** → "Başarılı". Lab ekranında 00456 yalnız Kefil alanında olmalı.
7. **Yanlış ekran.**
   - Lab denetim sayfasında (`http://127.0.0.1:8100/__lab`) `party_layout` alanına `similar` yazıp **Uygula**'ya basın
     ya da şu komutu çalıştırın:
     `curl -X PUT -H 'Content-Type: application/json' -d '{"party_layout":"similar"}' http://127.0.0.1:8100/__lab/scenario`
   - **Ekranı aç** → **Çalıştır** → adım tablosunda `SCREEN_NOT_RECOGNIZED` ve "İşlem yapılmadı" görünmeli; Kefil
     alanı boş kalmalı.
   - Eski haline dönmek için `party_layout` değerini `standard` yapın.
8. **Değişiklikler.** `/changes` sayfasında işlemi seçip **Ekranla karşılaştır**:
   - Doğru ekranda "Ekran tanındı";
   - benzer ekranda "Ekran tanınmadı" görünmeli.

## R4 (2026-11-06): Çok ekranlı işlemler ve kontrollü ekran geçişleri — COMPLETED (lab kapsamında) — GÜNCEL DURUM

Bu kayıt güncel durumdur. Önceki R3 ve Aşama 1–3 kayıtları tarihçe olarak geçerlidir; R4 onları geri almaz. Gerçek
Pega/SSO doğrulanmadı. Plan: `docs/plans/2026-11-06-r4-multi-screen.md`; gerekçeler:
`docs/adr/0011-r4-cok-ekranli-islemler.md`.

**R3 kullanıcı doğrulaması (kayıt):**
- Kullanıcı arayüzden `kefil_musteri_no` r2 geçişini ve yayınını yaptı; doğru ekranda 00456 yalnız Kefil alanına
  yazıldı.
- Benzer yanlış ekranda `SCREEN_NOT_RECOGNIZED` ile durdu. Bu ret, zorunlu "Kefil › Ad Soyad" işaretinin
  yokluğundan geldi.
- Yasak işaret kuralının tek başına manuel doğrulaması yapılmadı. R4'te otomatik test olarak eklendi:
  `test_only_forbidden_marker_added_rejects_without_writing`.

### Uygulanan davranış
- **Sözleşme (catalog-v3):**
  - İşlem: başlangıç ekranı + `extra_screens`, `transitions` ve `start_context` (kayıt bağlamı).
  - Adım: `screen_id` (beklenen ekran) ve `transition_id` (ekran değiştiren adım).
  - Geçiş tanımı: kaynak ve hedef ekran, tetikleyici, `timeout_ms` (500–60000), tamamlanma (hedef ekran + bağlam
    koşulları, ör. `Vaka No = {vaka_no}`).
  - Tetikleyici ile iş etkisi ayrı: `control` = yalnız ekran değiştiren onaylı düğme/sekme (`follow_transition`,
    iş etkisi yok); `approved_action` = adımın onaylı aksiyonu hem iş etkisi yaratır hem ekranı değiştirir.
  - Selector, XPath, DOM id, frame sırası, URL ve koordinat yok. Ekran kimliği URL'den türetilmez.
- **Statik rota doğrulaması:**
  - Adımlar ekranları sırayla izler; rota dışı ekran yasak.
  - Geçişin kaynağı o anki ekran olmalı ve geçiş tam bir adımda kullanılmalı.
  - Tetikleyici komutla uyumlu olmalı; yazma etkili geçişli aksiyonda uzlaştırma zorunlu.
  - Her ekranın işaretleri o ekrandaki hedeflerden ibaret olamaz.
- **Yürütme:**
  - Başlangıç ekranı ve kayıt bağlamı ilk adımdan önce doğrulanır.
  - Her sayfa adımından önce etkin ekran ve bağlamı güncel gözlemle yeniden doğrulanır.
  - Geçiş:
    - niyet ve `DISPATCHED` kaydedilir, tek tıklama yapılır;
    - etkin ekran boşaltılır (eski ekran kuralı meşru geçişi engellemez);
    - hedef ekran ve bağlam `timeout_ms` içinde DOM/frame değişimine bağlı beklenir (sabit sleep yok);
    - tekrar tıklama yok, başka rota keşfedilmez.
  - SPA geçişi (tam sayfa gezinmesi olmadan, iframe yeniden oluşarak) ve tam sayfa gezinmesi desteklenir.
  - Hata sınıfları:

    | Durum | Sonuç |
    |---|---|
    | Hedef ekran süre içinde gelmedi, kaynak hâlâ görünüyor | `TRANSITION_TIMEOUT` |
    | Ne kaynak ne hedef ekran | `UNEXPECTED_SCREEN` |
    | Hedef ekran belirsiz | `SCREEN_NOT_RECOGNIZED` + `PAUSED_AMBIGUOUS` |
    | Ekran türü doğru, vaka farklı | `RECORD_CONTEXT_MISMATCH` |

  - **Yazma etkili geçiş:**
    - Sonuç kanıtı sayfa düzeyinde okunur; hedef ekranın görünmesi başarı kanıtı değildir.
    - Yanıt kaybında mevcut uzlaştırma kullanılır. Uygulandıysa ve hedefe geçilmediyse `TRANSITION_NOT_COMPLETED`
      döner: adım "uygulandı" olarak kalır, run durur, yeniden gönderim yok.
  - **Resume:**
    - Tamamlanmış geçiş ve aksiyonlar yeniden oynatılmaz.
    - Son başarılı ekran segmentinin ekranı ve bağlamı doğrulanır; yalnız o segmentin idempotent `ensure_*`
      adımları kurulur.
    - Doğrulanamazsa `PAUSED_SESSION` / `context_revalidation_failed` döner.
    - Önceki adımların geri alındığı iddia edilmez.
- **Tasarımcı:**
  - Ekran ekle/güncelle: ilk ekran başlangıç ekranıdır; aynı kimlik günceller.
  - Her ekranın işaretleri listelenir ve doğrulanabilir.
  - Adım başına "Adımın ekranı" seçilir; geçiş formu kaynak, hedef, tetikleyici, bekleme süresi ve tamamlanma
    koşulunu alır. Tetikleyici adayları yalnız listelenir, tanımlarken tıklanmaz.
  - Başlangıç kayıt bağlamı tanımlanabilir.
  - Ekran değiştiren adımın denemesi "tarayıcıda ekran geçişini tetikler" onayı ister.
  - Yeni oturum testi bütün akışı baştan çalıştırır.
  - Ekran veya geçiş değişince ilgili adımlar yeniden onaya döner; test ve onay hash'le geçersizleşir.
  - Tek ekranlı işlemde bu alanlar boş kalır, R3 akışı değişmez.
- **Yayın:**
  - Bütün ekran revizyonları `catalog_screens`'e yazılır ve manifestoda pinlenir.
  - `screens_ref`, `transitions` ve `start_context` onay hash'ine girer. Run yayına pinli.
  - Revizyon `schema_version`'ı içerikten belirlenir (v2 / v3). Okuyucu v2 ve v3'ü kabul eder; tanınmayan anahtar
    `unsupported_schema` olur.
  - Tek ekranlı tanımın kanonik içeriği R3 ile aynı kalır; mevcut v2 hash'leri değişmez.
- **Asistan:** önizleme ekran rotasını, geçiş satırlarını ve iş etkisi ile ekran etkisini (`navigation`) ayrı
  gösterir.
- **Changes:** işlemin bütün ekranları ortak çekirdekle değerlendirilir (`screens[]`). Paylaşılan ekran
  (`screen:<id>`) ve aynı hedefi kullanan geçiş tetikleyicisi (`transition:<id>`) etki nedenidir.
- **Yapılandırma:**
  - Yeni ortam ayarı gerekmedi. Bekleme süreleri katalogdaki `timeout_ms` ve mevcut `READINESS_TIMEOUT_MS` ile
    yönetilir; başlangıç adresi kataloğa konmaz.
  - `.env`, `.env.example` ve `LOCAL_MONGO_AUTOSTART=false` değişmedi.

### Değişen / yeni dosyalar
- **Alan:**
  - `domain/routes.py` (yeni: ContextCheck, ControlTrigger, ActionTrigger, TransitionDef)
  - `domain/catalog.py`: çok ekran alanları, `route()`, `_route_issues`, `definition_schema`, `screen_refs`, segmentli
    derleme
  - `domain/commands.py`: `TransitionSpec`, `FollowTransitionCommand`, `assert_screen.context`,
    `invoke.transition`
  - `domain/actions.py`: 4 hata sınıfı
  - `domain/release.py`: `SCHEMA_VERSION=catalog-v3`
  - `domain/impact.py`: ekran ve tetikleyici bağımlılığı
  - `domain/authoring.py`: `follow_transition` önerisi
- **Uygulama:**
  - `services/executor.py`: bağlam, geçiş, geçişli aksiyon, segmentli resume
  - `services/publishing.py`: çoklu ekran, `screens_of`, sürüm denetimi
  - `services/designer.py`: ekran listesi, geçiş, başlangıç bağlamı, geçersizleştirme, deneme onayı
  - `services/assistant.py`: rota önizlemesi
  - `services/impact.py`
- **Sunum:**
  - `api/drafts.py`: geçiş, başlangıç bağlamı, `screen_id` parametreleri
  - `api/changes.py`: `screen_ids`
  - `templates/designer.html`, `static/designer.js`
  - `templates/assistant.html`, `static/assistant.js`
- **Deney uygulaması (test ikamesi):**
  - `agentask_lab/state.py`: sihirbaz senaryoları, sayaçlar, `with_change_note`
  - `agentask_lab/app.py`: `/wizard/...` rotaları, advance/submit API
  - `static/wizard.js`
  - `templates/wizard_*.html` (7 dosya)
  - `templates/duplicates.html`
  - `infrastructure/approved_actions/lab.py`: `lab.submit_application`
- **Belgeler:**
  - `docs/plans/2026-11-06-r4-multi-screen.md`, `docs/adr/0011-r4-cok-ekranli-islemler.md` (yeni)
  - `docs/02_CATALOG_CONTRACTS.md`, `docs/09_API_CONTRACTS.md`: R4 notları
  - bu kayıt ve `docs/10_PROGRESS.md`
- **Testler:**
  - Yeni:
    - `tests/wizard.py`
    - `tests/unit/test_routes.py` (18)
    - `tests/integration/browser/test_multi_screen_runtime.py` (13)
    - `tests/integration/mongo/test_mongo_routes.py` (1)
    - `tests/e2e/test_r4_multi_screen_ui.py` (1)
  - Güncellenen: `tests/integration/test_runs_api.py` (lab aksiyon kümesine yeni aksiyon eklendi). Hiçbir test
    silinmedi; beklenti gevşetilmedi.

### Doğrulanan durumlar
| Durum | Test | Yapılmadığının kanıtı |
|---|---|---|
| Üç ekranlı başarılı akış | `test_three_screen_flow_completes_once` | sürücü: 3 fill + 2 click; geçiş sayacı 1; tek başvuru |
| SPA geçişi + iç içe/yeniden oluşan frame | aynı test (Devam: pushState + iframe yeniden oluşur; Belge No iframe'de); E2E | — |
| Gecikmeli hedef, tek tetikleme | `test_delayed_target_waits_without_retriggering` | sayaç 1, click 2 |
| Hedef zaman aşımı | `test_target_timeout_reports_and_never_retriggers` (`TRANSITION_TIMEOUT`, "yeniden tetiklenmedi") | yalnız fill + Devam; sayaç 1; sonraki adımlar pending; başvuru yok |
| Beklenmeyen hedef ekran | `test_unexpected_target_screen_is_not_explored` (`UNEXPECTED_SCREEN`) | yalnız fill + Devam; red ekranındaki alan boş |
| Yinelenen hedef kanıtı | `test_duplicated_target_evidence_pauses_ambiguous` (`PAUSED_AMBIGUOUS`) | iki Teminat alanı boş |
| Doğru ekran türü, yanlış vaka (hedefte) | `test_right_screen_type_wrong_case_is_rejected` (geçiş adımının tamamlanma koşulu) | Teminat alanı boş, sonraki adımlar pending |
| Yanlış vaka (başlangıçta) | `test_wrong_case_on_start_screen_does_nothing` | sürücü çağrısı 0, sayaç 0 |
| Eksik tarama | `test_incomplete_scan_stops_before_any_action` (`incomplete`) | sürücü çağrısı 0 |
| Yanıtı kaybolan yazma etkili geçiş | `test_lost_response_on_mutating_transition_is_not_resent` (uzlaştırma → `TRANSITION_NOT_COMPLETED`) | tek başvuru kaydı; tek Gönder tıklaması |
| Resume: yanlış ekran / doğru ekran | `test_resume_on_wrong_screen_stops_and_does_not_replay` | yanlış ekranda sürücü 0; doğru ekranda yalnız Gönder; sayaç 1 (geçiş yeniden oynatılmadı) |
| Yasak işaret tek başına | `test_only_forbidden_marker_added_rejects_without_writing` | bütün zorunlu işaretler resolved; sürücü 0; Kefil boş |
| Tek ekranlı v2 (r2 benzeri) regresyon | `test_single_screen_v2_operation_still_runs`; R3 testleri | Başvuran boş, Kefil dolu |
| Changes çok ekran + bağımlılık | `test_changes_analysis_uses_same_screen_core_for_every_screen`, `test_impact_covers_shared_screens_and_transition_triggers` | — |
| Rota/sürüm/hash sözleşmesi | `tests/unit/test_routes.py` (rota kuralları, güvensiz geçiş tanımı reddi, v2 içeriği değişmez, bilinmeyen şema, geçersizleştirme) | — |
| Gerçek MongoDB roundtrip + değişmez eski belgeler | `test_multi_screen_publish_roundtrip_keeps_v2_documents` | v2 op/manifest/ekran belgeleri bayt bayt aynı |
| Arayüz E2E | `test_multi_screen_designed_published_and_run_from_ui` (tasarım → geçiş denemesi (açık onay) → yeni oturum testi → onay → yayın → asistan) | geçiş tanımlanırken sayaç 0; deneme 1, test 2, çalıştırma 3 |

- **Mutasyon kontrolü:** üç mutasyon denendi:
  - geçiş tamamlanmasında bağlam kontrolünü kaldırmak;
  - resume'da geçişi yeniden oynatmak;
  - zaman aşımı ile beklenmeyen ekranı ayırmamak.

  Her biri testlerce yakalandı. Bağlam mutasyonu ilk denemede yakalanmadı: sonraki adım öncesi yeniden doğrulama
  aynı hatayı yakalıyordu (iki kat koruma). Test, hatanın geçiş adımında verildiğini doğrulayacak şekilde
  sıkılaştırıldı; ardından mutasyon yakalandı. Kod geri alındı.
- **Kararlılık:** R4 ve R3 tarayıcı/E2E grubu (23 test) üç kez arka arkaya geçti.

### Çalıştırılan komutlar
| Komut | Exit | Sonuç |
|---|---|---|
| `.venv/bin/pytest -q tests/unit/test_routes.py` | 0 | 18 passed |
| `.venv/bin/pytest -q tests/integration/browser/test_multi_screen_runtime.py` | 0 | 13 passed (gerçek Chromium) |
| `.venv/bin/pytest -q -m mongo tests/integration/mongo` | 0 | 13 passed (geçici mongod, rastgele test DB) |
| `.venv/bin/pytest -q tests/e2e/test_r4_multi_screen_ui.py` | 0 | 1 passed |
| R3 regresyonu (`test_screens`, `test_screen_publishing`, `test_screen_runtime`, `test_screen_api`, `e2e/test_r3_migration_ui`, `e2e/test_designer_ui`, `e2e/test_assistant_ui`) | 0 | 35 passed |
| `.venv/bin/pytest -q -rs` (tamamı) | 0 | 539 passed, 3 skipped |
| `.venv/bin/ruff check src tests tools` / `ruff format --check src tests tools` | 0 / 0 | temiz / 185 dosya |
| `.venv/bin/mypy` | 0 | 103 dosya, hata yok |
| `docker info` | 1 | **BLOCKED:** Docker daemon kapalı; 3 `-m docker` testi atlandı. |

### Kullanıcı verisi
- Testlerin hiçbiri kullanıcının MongoDB'sine bağlanmaz.
- `kefil_musteri_no` r1/r2 kayıtlarına dokunulmadı; otomatik dönüştürme veya yeniden yayın yapılmadı.
- r2 (catalog-v2) okuyucu tarafından desteklenmeye devam eder.

### Kalan sınırlamalar
- **Rota doğrusal:** koşullu/dallanan geçiş, döngü ve geri dönüş rotası yok. Koşullu akışlar birleştirme fazında.
- **Tetikleyici türü** düğme veya sekmeyle sınırlı; bağlantı, menü ve klavye kısayolu yok.
- **Geçiş zaman aşımında** run `FAILED` olur ve otomatik resume yoktur. Geçiş adımı yeniden tetiklenmez; kullanıcı
  ekranı kontrol edip yeni run başlatmalıdır.
- **TRANSITION_NOT_COMPLETED:** iş etkisi uygulanmış ama hedefe geçilmemiş durumda run sonlanır; kalan adımlar için
  insan kararı gerekir. Önceki adımların geri alındığı iddia edilmez.
- **Kayıt bağlamı** yalnız alan değeri eşitliğine dayanır (ör. Vaka No). Tablo satırı veya çoklu anahtar bağlamı yok.
- **Laboratuvar sınırı:** iç içe frame yeniden oluşumu ve gecikme deney uygulamasında denendi; gerçek Pega'nın
  dinamik bölüm yenileme davranışları denenmedi.
- **Maliyet:** her adımda ekran + bağlam yeniden doğrulaması ek gözlem maliyeti getirir; büyük ekranlarda süre
  ölçülmedi.
- **Tasarımcı arayüzü** tek tamamlanma/bağlam koşulunu formdan ekler; API birden fazla koşulu (en fazla 5) kabul
  eder.
- **BLOCKED:** Docker testleri (daemon kapalı); gerçek Pega/SSO; kurumsal MongoDB.

### Arayüzden doğrulama adımları (kullanıcı için)
Hazırlık: kendi `.env` ayarlarınızla (`LOCAL_MONGO_AUTOSTART=false`) `.venv/bin/agentask-lab` ve `.venv/bin/agentask`
komutlarını çalıştırın. Lab sayaçları `curl http://127.0.0.1:8100/__lab/state` ile okunur (`wizard_advances`,
`applications`). Senaryolar `http://127.0.0.1:8100/__lab` sayfasından ayarlanır.

1. **Tasarım başlangıcı.** `/designer`:
   - Oturum seçin/açın → Deney ekranı **Başvuru sihirbazı (çok ekran)** → **Ekranı aç**.
   - Yeni taslak: `teminat_gir` / "Teminat tutarını gir".
   - Parametreler: `vaka_no` (Vaka No), `musteri_no` (Müşteri No), `tutar` (Teminat Tutarı).
2. **Başlangıç ekranı.**
   - Ekran kimliği `basvuru_musteri`, ad "Başvuru — müşteri seçimi".
   - **Ekrandaki kontrolleri listele** → işaretler: "Vaka No · metin alanı · Vaka", "Müşteri No · metin alanı ·
     Müşteri", "Devam · düğme". Olmamalı: `Teminat Tutarı` / `Teminat`.
   - Kaydedin → "TANINDI" görünmeli.
   - Başlangıç bağlamı: Vaka No / Vaka / `{vaka_no}` → kaydedin.
3. **Teminat ekranı.**
   - **Başvuru sihirbazı — teminat ekranı**'nı açın.
   - Ekran `basvuru_teminat`, "Başvuru — teminat bilgileri". İşaretler: "Vaka No · metin alanı · Vaka", "Gönder ·
     düğme · Teminat". Olmamalı: `Müşteri No` / `Müşteri`.
4. **Geçiş.**
   - Sihirbaz başlangıcını yeniden açın.
   - Geçiş `teminata_gec`: kaynak müşteri, hedef teminat, tetikleyici "Yalnız ekran değiştiren düğme/sekme", 5000 ms.
   - **Tetikleyici adaylarını listele** → "Devam". Tamamlanma: Vaka No / Vaka / `{vaka_no}` → **Geçişi kaydet**.
   - `/__lab/state` → `wizard_advances` hâlâ `{}` olmalı (tanım tıklamaz).
5. **Adımlar.**
   - "Müşteri numarasını yaz": aday "Müşteri", şablon `{musteri_no}`, 4 onay, deneme (C-2001 / 00456 / 1500) →
     BAŞARILI → sonucu onaylayın.
   - "Devam et": Komut "Ekran geçişi" görünür → geçiş `teminata_gec` → kaydedin → kartta "EKRAN DEĞİŞTİRİR".
     Onaysız **Dene** → hata. "ekran geçişini tetikler; onaylıyorum" kutusunu işaretleyip **Dene** → BAŞARILI.
     Sayaç 1 olmalı.
   - "Teminat tutarını yaz": aday "Teminat Tutarı", `{tutar}` → kartta "Beklenen ekran: Başvuru — teminat
     bilgileri" → deneme → onay.
6. **Test, onay, yayın.**
   - Başlangıç ekranı **Başvuru sihirbazı (çok ekran)**, değerleri girin → **Yeni oturum testi** → "İncelemeye
     hazır…".
   - **Onayla** → **Yayımla** → "teminat_gir r1".
7. **Asistan.** `/assistant`:
   - "Teminat tutarını gir", değerler → **Planı göster** → "Ekran rotası: Başvuru — müşteri seçimi → Başvuru —
     teminat bilgileri" ve "→ ekran geçişi" satırı görünmeli.
   - Oturumu seçin → sihirbazı açın → **Çalıştır** → "Başarılı". Sayaç bir artmalı.
8. **Negatif denemeler** (her biri sonrası senaryoyu geri alın):
   - `wizard_target=other_case` → çalıştırın → `RECORD_CONTEXT_MISMATCH`; teminat alanı boş.
   - `wizard_delay_ms=9000` → `TRANSITION_TIMEOUT` ("yeniden tetiklenmedi"); sayaç yalnız 1 artar.
   - `wizard_target=unexpected` → `UNEXPECTED_SCREEN`.
9. **Yasak işaret.**
   - `party_layout=with_change_note` → asistanda `kefil_musteri_no` (r2) → Başvuran/Kefil ekranında
     **Çalıştır**.
   - `SCREEN_NOT_RECOGNIZED` ("olmaması gereken … Talep Notu"); Kefil alanı boş kalmalı.
   - `party_layout=standard` yapın.
10. **Regresyon.** Standart ekranda `kefil_musteri_no` r2 → "Başarılı"; 00456 yalnız Kefil'de olmalı.
