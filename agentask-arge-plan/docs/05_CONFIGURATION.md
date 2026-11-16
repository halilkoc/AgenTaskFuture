# Bütün ortam ayarları .env üzerinden

## Bağlayıcı kural
URL/host/port, bağlantı bilgileri, model adı ve auth, CA/TLS, browser/headless, dosya yolları, timeout, token/step/scan/retry limitleri, log seviyesi ve özellik bayrakları kaynak koduna gömülmez. Tek typed Settings sınıfından okunur. Aynı anahtarlar .env.example içinde açıklamalı ve güvenli örneklerle bulunur.
Öncelik: process environment > seçili .env dosyası. Varsayılan dosya repo kökündeki .env; başka dosya yolu bootstrap'ta açık --env-file ile seçilebilir. Settings dışındaki modüller os.getenv/dotenv çağırmaz. İş verileri, kataloglar, workflow parametreleri ve sıradan fonksiyon değişkenleri .env'ye taşınmaz. Değişmez protocol enum'ları ve kod sabitleri de konfigürasyon değildir.
Katalogdaki operasyon politikaları .env limitlerini aşamaz; .env sistem üst sınırıdır. Sayısal limit bir iş yetkisi vermez.

## Tip ve güvenlik
Pydantic Settings ile startup validation; boolean 'false' gerçekten false, pozitif limitler ve URL/enum doğrulaması; geçersiz değer sessizce default'a düşmez. SecretStr ve redakte hata mesajları. İlgisiz process env yok sayılabilir; seçili dotenv içindeki bilinmeyen uygulama anahtarları yazım hatası olarak reddedilir.
LLM_ENABLED=false iken model credential zorunlu değil. true ise endpoint/model/auth modu için gereken alanlar zorunlu. TLS_VERIFY=true temel ayar; CA_BUNDLE isteğe bağlıdır. verify=false yalnızca development'ta açık seçilmişse kullanılabilir; varsayılan değildir.
Production: dev identity adapteri, http dış servise credential taşıma ve güvenlik kontrollerini kapatan modlar reddedilir. AUTH_MODE=unconfigured gerçek ortama hazır auth değildir.
.env gitignored; .env.example sürümlenir. Build image içinde secret/.env yok. OpenShift gelecekte aynı env isimlerini Secret/ConfigMap veya güvenli .env mount ile verebilir; kod değişmez.
Frontend'e backend Settings dökümü verilmez. Public config endpoint sadece allowlist alanları verir; Mongo/LLM/SSO secretları frontend bundle veya VITE değişkenleriyle dışarı çıkmaz. Kullanıcı oturum sırları kalıcı .env içinde tutulmaz.

## Temel ayar grupları
- APP_ENV, APP_HOST, APP_PORT, APP_TIMEZONE, APP_BASE_URL, AUTH_MODE, DEV_AUTH_ENABLED, SESSION_SIGNING_KEY
- MONGO_URI, MONGO_DATABASE, MONGO_TLS_CA_FILE, MONGO_SERVER_SELECTION_TIMEOUT_MS
- CATALOG_BACKEND (mongo|disabled), CATALOG_ENVIRONMENT, CATALOG_APPLICATION_ID (P5/P6; readiness'te mongo etkinse zorunlu bileşen)
- DRAFT_BACKEND, DRAFT_DIRECTORY, ARTIFACT_DIRECTORY, ARTIFACT_MAX_BYTES (dosya başına üst sınır; ADR 0016), RUNNER_MODE, BROWSER_ENGINE, BROWSER_HEADLESS, BROWSER_EXECUTABLE_PATH, PLAYWRIGHT_BROWSERS_PATH
- ARTIFACT_BACKEND (local|s3), ARTIFACT_INDEX_BACKEND (local|mongo) ve S3_ENDPOINT_URL, S3_BUCKET, S3_REGION,
  S3_PREFIX, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_CA_BUNDLE, S3_ADDRESSING_STYLE (path|virtual),
  S3_TIMEOUT_MS (ADR 0018). Varsayılan `local`; mevcut .env dosyaları değişmeden çalışır. `s3` seçilince uç nokta,
  kova, bölge ve kimlik zorunludur; uç nokta https olmalıdır (yalnız loopback test deposu http), adreste kimlik
  bilgisi olamaz, TLS doğrulaması kapatılamaz. `mongo` metadata dizini CATALOG_BACKEND=mongo ile aynı MongoDB'yi
  kullanır. Gizli değerler yalnız güvenli .env/Secret ile verilir; loglanmaz, frontend'e verilmez.
- BROWSER_LAUNCH_TIMEOUT_MS, BROWSER_MAX_SESSIONS, BROWSER_MAX_SESSIONS_PER_USER (≤ toplam, etkileşimli), BROWSER_MAX_VERIFICATION_SESSIONS_PER_USER (≤ toplam, geçici doğrulama; R2), BROWSER_SESSION_IDLE_SECONDS (P1)
- TARGET_ALLOWED_ORIGINS, TARGET_BASE_URL; örnek hedef sadece 127.0.0.1 test uygulaması
- AUTOMATION_APPLICATIONS_JSON (zorunlu; JSON liste, `[]` geçerli): kullanıcıya gösterilen otomasyon uygulamaları.
  Kayıt: `id` (sabit, benzersiz, katalog `application_id` ile aynı anlam), `name`, `base_url`. Doğrulama:
  - bozuk JSON, yinelenen id, boş ad, http(s) dışı veya kimlik bilgisi içeren adres reddedilir;
  - `base_url` origin'i TARGET_ALLOWED_ORIGINS içinde olmalı;
  - liste boş değilse CATALOG_APPLICATION_ID listedeki bir id olmalı.

  Listede olmak yetki vermez. Frontend'e yalnız id/ad/başlangıç adresi gider. Ayrıntı: ADR 0012.
- **JSON değerlerde tırnak:**
  - .env dosyasında `'...'` tırnakları okunurken kaldırılır.
  - Aynı değer doğrudan ortam değişkeni olarak verilirken tırnak eklenmemelidir; ortam değişkeninde tırnak
    değerin parçası sayılır.
  - Çözülemeyen JSON, redakte bir yapılandırma hatasıyla (alan adı, değer yok) reddedilir.
- .env.example'da etkin anahtarlar tekildir (testle denetlenir); alternatif örnekler yorum satırıdır.
- LAB_PRIMARY_ORIGIN, LAB_SECONDARY_ORIGIN (P1, opsiyonel, birlikte): yerel deney uygulaması; yalnız loopback http, birbirinden farklı; production'da reddedilir. Hedef olarak kullanılacaksa TARGET_ALLOWED_ORIGINS içinde de olmalı.
- ACTION_TIMEOUT_MS, NAVIGATION_TIMEOUT_MS (P1), READINESS_TIMEOUT_MS, FRAME_SCAN_TIMEOUT_MS, FRAME_SCAN_MAX_DEPTH, FRAME_SCAN_MAX_ELEMENTS (frame başına), FRAME_SCAN_CONCURRENCY, OBSERVE_TIMEOUT_MS (≥ FRAME_SCAN_TIMEOUT_MS), OBSERVE_MAX_FRAMES, PICKER_WAIT_MAX_MS (P2)
- CHOICE_SETTLE_MS (varsayılan 300), CHOICE_OPTIONS_WAIT_MS (varsayılan 5000): seçim sonrası DOM durulma süresi ve geç yüklenen seçenekleri bekleme üst sınırı (ADR 0021). İsteğe bağlı; mevcut .env dosyaları değişmeden çalışır.
- RUN_MAX_STEPS, RUN_MAX_DURATION_SECONDS, TABLE_MAX_PAGES, TABLE_MAX_ROWS, RECOVERY_MAX_ATTEMPTS, SESSION_LEASE_SECONDS
- RUN_DIRECTORY, APPROVED_ACTION_SET (none|lab; production'da lab reddedilir), OUTCOME_TIMEOUT_MS, RECONCILE_TIMEOUT_MS, TABLE_NO_PROGRESS_LIMIT (P3)
- COMPOSITION_ENABLED (varsayılan false), COMPOSITION_MAX_DEPTH, COMPOSITION_MAX_ITEMS (P8)
- LLM_ENABLED, LLM_BASE_URL, LLM_MODEL, LLM_AUTH_MODE, LLM_API_KEY, LLM_USERNAME, LLM_PASSWORD, LLM_TLS_VERIFY, LLM_CA_BUNDLE, LLM_TIMEOUT_SECONDS
- LLM_CONTEXT_TOKENS, LLM_MAX_INPUT_TOKENS, LLM_MAX_OUTPUT_TOKENS, LLM_CONTEXT_RESERVE_TOKENS, LLM_MAX_CALLS_PER_RUN
- LOG_LEVEL, LOG_FORMAT, EVIDENCE_RETENTION_DAYS, EVIDENCE_SCREENSHOTS_ENABLED

Context değerleri modelin gerçek sınırı öğrenildiğinde ayarlanır. input+output+reserve <= context startup kontrolü yap. Reasoning tokenları provider sınırına göre output/reserve içinde hesaba katılmalı. Tokenizer yoksa tahminin kesin olmadığını bildir ve conservative budget uygula; limitsiz gönderme.
Varsayılanları .env.example'dan Settings'e iki ayrı yerde kopyalamak yerine zorunlu alanlar/tek kaynak yaklaşımı seç. Gereken yeni bir ayar eklendiğinde bu belge, .env.example ve config testi birlikte güncellenir.

## Uygulanan değer kümeleri (P0)
APP_ENV: development | test | production · AUTH_MODE: dev | unconfigured · DRAFT_BACKEND: local_file ·
RUNNER_MODE: local · BROWSER_ENGINE: chromium (varsayılan; verilmezse) | firefox — webkit doğrulamada gerekçesiyle reddedilir (ADR 0025) · LLM_AUTH_MODE: none | basic | bearer ·
AUTH_MODE: dev | unconfigured | local_admin (ADR 0023; ADMIN_USERNAME, ADMIN_PASSWORD_HASH, ADMIN_SESSION_TTL_SECONDS, ADMIN_LOGIN_MAX_ATTEMPTS, ADMIN_LOGIN_LOCKOUT_SECONDS, ADMIN_COOKIE_SECURE). APPROVED_ACTION_SET: none | lab | file (APPROVED_ACTIONS_FILE). FRESH_TEST_LOGIN_TIMEOUT_SECONDS: elle giriş bekleme sınırı. Yeni ayarlar varsayılanlıdır; mevcut .env değişmeden çalışır.

LOG_LEVEL: DEBUG..CRITICAL · LOG_FORMAT: json | text (stdout; alanlar ve maskeleme aynı, ADR 0022). SESSION_SIGNING_KEY en az 32 karakter.
TARGET_BASE_URL origin'i TARGET_ALLOWED_ORIGINS içinde olmalı. Ayrıntı ve gerekçe: docs/adr/0001-p0-iskelet-ve-settings.md.

BROWSER_EXECUTABLE_PATH yalnız BROWSER_ENGINE=chromium ile geçerlidir; firefox ile verilirse doğrulama reddeder. Seçilen motor dışında bir motor başlatılmaz (ADR 0025).
PLAYWRIGHT_BROWSERS_PATH Settings'ten okunur ve Playwright sürücüsü başlatılmadan önce `config/runtime_env.py` ile process env'e aktarılır (sürücü bu değeri yalnızca env'den okur).

## Yerel MongoDB otomatik başlatma (sökülebilir geliştirme aracı)
**Uygulama Settings'i:**
- `LOCAL_MONGO_AUTOSTART` (bool, varsayılan `false`) tanınır. `true` yalnız `APP_ENV=development` ile kabul edilir;
  aksi halde startup yapılandırma hatası verilir ve hiçbir container başlatılmaz.
- `MONGO_URI` ve `MONGO_DATABASE` otomatik başlatmadan bağımsız normal ayarlardır.
- `LOCAL_MONGO_` önekli diğer anahtarlar yerel araca ayrılmıştır; uygulama bunları yok sayar. Diğer bilinmeyen dotenv
  anahtarları eskisi gibi reddedilir.

**Araç ayarları** (`tools/local_mongo/settings.py::LocalMongoSettings`):
- Aynı seçili .env ve ortamdan okunur; yalnız araç çalışırken zorunludur.
- Önekli yazım hataları araç tarafından reddedilir.
- Anahtarlar:
  - `LOCAL_MONGO_IMAGE`
  - `LOCAL_MONGO_PROJECT` (Compose proje kimliği)
  - `LOCAL_MONGO_VOLUME` (named volume)
  - `LOCAL_MONGO_PORT` (yalnız 127.0.0.1)
  - `LOCAL_MONGO_START_TIMEOUT_SECONDS`
  - `LOCAL_MONGO_BACKUP_DIR`
  - `LOCAL_MONGO_ROOT_USERNAME`, `LOCAL_MONGO_ROOT_PASSWORD` (opsiyonel; SecretStr; loglanmaz, frontend'e gitmez).

**Bağımlılık yönü:** geliştirme başlatıcısı → yerel araç → normal uygulama. `src/` altındaki hiçbir modül `tools`'u
import etmez (`tests/unit/test_local_mongo_tool.py::test_app_does_not_import_tools`).
