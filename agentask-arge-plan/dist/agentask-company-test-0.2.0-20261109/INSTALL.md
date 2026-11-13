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
Playwright tarayıcı dosyaları platforma özeldir. Birini seçin:
- **A. Kurulu Edge/Chrome:** `.env` içinde `BROWSER_EXECUTABLE_PATH=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`.
  İndirme gerekmez. Kurulu tarayıcı sürümüyle uyum bu ortamda doğrulanmalıdır.
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
| `[HATA] Tarayıcı` | Tarayıcı kurulu değil | Bölüm 3 |
| `[HATA] MongoDB` | URI, ağ veya CA | Bölüm 4 |
| `[UYARI] Hedef uygulama` | Ağ/CA; tarayıcı yine erişebilir | Tarayıcıda açmayı deneyin |
| Giriş sonrası hedefe gidilemiyor | SSO adresi izinli listede yok | `TARGET_ALLOWED_ORIGINS` |
| Yapılandırma hatası | Eksik/hatalı ayar | Mesajdaki ayar adını düzeltin (değer yazdırılmaz) |

## 6. Kayıtlar
- Loglar yalnız konsola yazılır (JSON). Saklamak için: `.\start.ps1 *> agentask.log`.
- Çalışmalar `var\runs`, taslaklar `var\drafts` altında kalır ve yeniden başlatmada korunur.
- Yayınlar MongoDB'dedir. Destek için ekranlardaki **Destek numarası**nı kullanın.
