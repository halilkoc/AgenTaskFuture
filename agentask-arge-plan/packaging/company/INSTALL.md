# AgenTask şirket testi kurulumu (Windows, tek kullanıcı, yerel)

Bu paket bir **test adayıdır**. Geçici admin girişi kurumsal SSO değildir. Bu kurulumla Pega, kurumsal MongoDB,
model hizmeti veya S3 kabul edilmiş sayılmaz; kabul `MANUAL_ACCEPTANCE.md` Bölüm S ile şirkette yapılır.

## 1. Gereksinimler
- Windows 10/11 x64, PowerShell 5.1+.
- **Python 3.12 x64** (kurum yazılım merkezinden). 3.13 desteklenmez.
- Tarayıcı (bölüm 3) ve erişilebilir MongoDB 8.x (bölüm 4).
- İnternet gerekmez: `wheels/` tüm Windows bağımlılıklarını kesin sürüm ve hash ile içerir.

## 2. Kurulum
```powershell
Expand-Archive agentask-company-test-*.zip -DestinationPath C:\AgenTask
cd C:\AgenTask\agentask-company-test-*
powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\hash-admin.ps1
```
Çıkan satırı `.env` içindeki `ADMIN_PASSWORD_HASH=` satırına yazın. Parola en az 12 karakterdir; düz metin saklanmaz.

Bütünlük: `SHA256SUMS.txt` paket dosyalarının özetlerini içerir. Kurum politikası isterse `Get-FileHash` ile doğrulayın.

## 3. Tarayıcı (Mac'ten kopyalamayın)
Motor `.env` içindeki `BROWSER_ENGINE` ile seçilir: `chromium` (varsayılan; satır yoksa da chromium) veya `firefox`.
Uygulama **yalnız seçilen motoru** başlatır; bulunamazsa hata verir, başka motora geçmez.
Playwright tarayıcı dosyaları platforma özeldir; Windows için Windows'ta hazırlanmalıdır.

### 3.1 Chromium kullanılamıyorsa: Firefox
```
BROWSER_ENGINE=firefox
BROWSER_EXECUTABLE_PATH=
PLAYWRIGHT_BROWSERS_PATH=C:\AgenTask\pw-browsers
BROWSER_HEADLESS=false
```
- Bilgisayarda kurulu olağan Firefox **kullanılamaz**: Playwright Firefox'u yalnız kendi derlemesiyle sürer. Bu yüzden
  `BROWSER_EXECUTABLE_PATH` Firefox ile reddedilir; boş bırakın.
- Bu paketteki Playwright sürümü **1.64.1**'dir ve `firefox-1555` (Firefox 157.0) derlemesini bekler. Klasör adındaki
  numara farklıysa tarayıcı bulunamaz.
- `playwright install firefox` yalnız Firefox'u ve Playwright'ın yardımcı dosyalarını (ffmpeg; Windows'ta winldd)
  indirir; **Chromium indirmez**. `install.ps1` hiçbir tarayıcı indirmez.

Tarayıcı dosyalarını sağlamanın iki yolu (ikisi de kurum onaylı kaynaktan):
- **Kurum aynası (şirket bilgisayarında):**
  ```powershell
  $env:PLAYWRIGHT_BROWSERS_PATH="C:\AgenTask\pw-browsers"
  $env:PLAYWRIGHT_DOWNLOAD_HOST="https://ayna.kurum.example/playwright"
  .\.venv\Scripts\playwright.exe install firefox
  ```
  Ayna, Playwright'ın indirme yolunu (`.../builds/firefox/1555/...`) aynen sunmalıdır.
- **Çevrimdışı (internet olan, onaylı başka bir Windows x64 bilgisayarda hazırlanır):**
  1. O bilgisayarda Python 3.12 ile `pip install playwright==1.64.1`.
  2. `$env:PLAYWRIGHT_BROWSERS_PATH="C:\pw-browsers"` sonra `playwright install firefox`.
  3. `C:\pw-browsers` klasörünün **tamamını** (`firefox-1555`, `ffmpeg-*`, `winldd-*`) kurum onaylı yolla şirket
     bilgisayarına, örneğin `C:\AgenTask\pw-browsers` altına kopyalayın.
  4. `.env` içinde `PLAYWRIGHT_BROWSERS_PATH=C:\AgenTask\pw-browsers` yazın ve `doctor.ps1` çalıştırın.

`doctor.ps1` seçili motoru, tarayıcı dosyasının bulunup bulunmadığını ve başlatma sonucunu ayrı satırlarda gösterir;
kendi başına indirme yapmaz. Firefox yalnız Mac üzerindeki deney uygulamasında denendi; **Windows'ta kurulumu ve gerçek
Pega/SSO ile çalışması doğrulanmadı** (bkz. `KNOWN_LIMITS.md`).

**WebKit kullanılamaz.** `BROWSER_ENGINE=webkit` yazılırsa uygulama başlamaz ve nedenini söyler:
```
BROWSER_ENGINE=webkit   # REDDEDİLİR: "BROWSER_ENGINE=webkit bu sürümde kullanılamaz ..."
```
WebKit, uygulamanın izinli adres sınırını korumak için kullandığı yönlendirme denetimini desteklemiyor; giriş dahil
yönlendirme içeren akışlar çalışmıyor. Sınır gevşetilerek çalıştırılmadı.

### 3.2 Chromium (varsayılan)
Birini seçin:
- **A. Kurulu Edge/Chrome:** `.env` içinde `BROWSER_EXECUTABLE_PATH=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`.
  İndirme gerekmez. Kurulu tarayıcı sürümüyle uyum bu ortamda doğrulanmalıdır. Yalnız `BROWSER_ENGINE=chromium` ile geçerlidir.
- **B. Kurum aynası:** `$env:PLAYWRIGHT_DOWNLOAD_HOST="https://ayna.kurum.example/playwright"` sonra
  `.\.venv\Scripts\playwright.exe install chromium`.
- **C. Başka bir Windows bilgisayarda hazırlanmış Playwright tarayıcı klasörü:** `PLAYWRIGHT_BROWSERS_PATH` ile gösterin.

Elle giriş için `BROWSER_HEADLESS=false` kalmalıdır.

## 4. `.env` ayarları
| Ayar | Açıklama |
|---|---|
| `TARGET_ALLOWED_ORIGINS` | Pega ve **giriş sırasında geçilen SSO/IdP adreslerinin tamamı**. Listede olmayan adrese gidiş engellenir. |
| `TARGET_BASE_URL`, `AUTOMATION_APPLICATIONS_JSON` | Hedef uygulama adresi. Örnek adresleri değiştirin. |
| `MONGO_URI`, `MONGO_DATABASE`, `MONGO_TLS_CA_FILE` | Bu teste ayrılmış veritabanı. TLS için kurum CA dosyası. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` | Geçici giriş. Varsayılan hesap yoktur; eksikse uygulama başlamaz. |
| `APPROVED_ACTION_SET=file`, `APPROVED_ACTIONS_FILE` | Kurumun onayladığı işlemler (`approved-actions.example.json` biçiminde). Her aksiyon `application_id` taşır ve `AUTOMATION_APPLICATIONS_JSON` içindeki bir uygulamayla eşleşmelidir. `profile.session_lost_path_prefixes` Pega giriş yolunu bildirir. |
| `ARTIFACT_MAX_BYTES` | Yüklenecek dosyanın en büyük boyutu. |
| `LLM_ENABLED`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_AUTH_MODE`, `LLM_CA_BUNDLE` | Varsayılan kapalı. Açılırsa `doctor.ps1` yalnız erişimi denetler. |
| `ARTIFACT_BACKEND=s3`, `S3_*` | Varsayılan yerel. Açılırsa `doctor.ps1` kovayı listeler; yazma denemez. |

Kurum Python paket kaynağı ancak yeni sürüm hazırlanırken gerekir; bu paket `wheels/` ile kurulur.
CA: Tarayıcı Windows sertifika deposunu kullanır; MongoDB `MONGO_TLS_CA_FILE`, S3 `S3_CA_BUNDLE`, model için ilgili CA ayarı.

## 5. Kontrol ve başlatma
```powershell
powershell -ExecutionPolicy Bypass -File .\doctor.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```
Adres: `http://127.0.0.1:8000`. `start.ps1` önce kontrolü çalıştırır; `HATA` varsa başlatmaz.

| Görülen | Olası neden | Çözüm |
|---|---|---|
| `[HATA] Tarayıcı dosyası` / `Tarayıcı başlatma` | Seçili motorun dosyaları yok veya açılamıyor | Bölüm 3 |
| `BROWSER_EXECUTABLE_PATH yalnız BROWSER_ENGINE=chromium ...` | Firefox ile özel tarayıcı yolu verilmiş | Yolu boş bırakın (Bölüm 3.1) |
| `[HATA] MongoDB` | URI, ağ veya CA | Bölüm 4 |
| `[UYARI] Hedef uygulama` | Ağ/CA; tarayıcı yine erişebilir | Tarayıcıda açmayı deneyin |
| Giriş sonrası hedefe gidilemiyor | SSO adresi izinli listede yok | `TARGET_ALLOWED_ORIGINS` |
| Yapılandırma hatası | Eksik/hatalı ayar | Mesajdaki ayar adını düzeltin (değer yazdırılmaz) |

## 6. Kayıtlar
- Loglar yalnız konsola yazılır (JSON). Saklamak için: `.\start.ps1 *> agentask.log`.
- Çalışmalar `var\runs`, taslaklar `var\drafts` altında kalır ve yeniden başlatmada korunur.
- Yayınlar MongoDB'dedir. Destek için ekranlardaki **Destek numarası**nı kullanın.
