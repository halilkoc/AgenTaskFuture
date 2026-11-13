# Geliştirme talimatı

Bu projeyi tek uygulamada iki çalışma alanı olarak geliştir: İşlem Asistanı ve yetkili kullanıcı için Katalog Tasarımcısı. Amaç Pega RPA bakım yükünü azaltmaktır. Her prompt için özel robot yazmak veya serbest otonom tarayıcı ajanı kurmak değildir.

## Değişmez gereksinimler
- Tamamen kurum içinde çalışabilen ürün; runtime'da dış LLM, telemetri veya bulut bağımlılığı ekleme.
- MongoDB yayımlanmış katalogların kaynağıdır. Taslaklar onay öncesinde yayımlanmış koleksiyonlara yazılmaz.
- Kalıcı CSS/XPath, DOM id'si, frame sıra yolu veya koordinatı kataloğa koyma. Anlamsal kimlik, kanıt ve kontrol davranışı tut. Çalışma anındaki locator geçicidir.
- Model açıklama, parametre ve izinli işlem/adayı önerir. Yetki, kapsam ve yürütme kodla denetlenir. Modelin güven puanı yürütme izni değildir.
- Serbest kod üretip çalıştırma, eval/exec, serbest JS veya keyfi HTTP aracı yok. Önceden tanımlı komut ve uyarlayıcı kayıtları kullan.
- Yanlış hedefe işlem yapmaktansa açıkça belirsiz sonuç ver. İlk eşleşeni seçme; force click ile kontrolleri atlama.
- Veri değiştiren belirsiz sonuçları körlemesine tekrar etme. UI tıklamasıyla exactly-once garantisi iddia etme.
- Bütün dağıtıma/ortama bağlı yapılandırma .env veya aynı isimli process environment değişkenlerinden, tek Settings katmanıyla okunacak. docs/05_CONFIGURATION.md bağlayıcıdır. İş verilerini ve programdaki bütün yerel değişkenleri .env'ye taşıma.
- Kullanıcıya gösterilen metinler Türkçe; kod kimlikleri İngilizce; açıklamalar ve belgeler Türkçe olabilir.

## Uygulama biçimi
Python 3.12, FastAPI, Pydantic v2/pydantic-settings ve asenkron Playwright. Ar-Ge başlangıç arayüzü Jinja2 + sade JavaScript, aynı origin. Bu UI tercihi önerilen başlangıçtır; kesin kurumsal frontend kararı değildir. SOLID, bağımlılık tersine çevirme, DTO/use case/port/adapter ayrımı uygula. Başlangıçta modüler monolit; gereksiz mikroservis, Redis, Argo ve agent framework ekleme.

Kurulu Python/Playwright/browser/driver sürüm uyumluluğunu doğrula; gerçek bağımlılık sürümlerini test edip kilitle. Belgedeki örnekleri güncel API'ymiş gibi kopyalama. Mevcut projeye ekleniyorsa çalışan davranışları koru.

## Çalışma disiplini
Önce docs/00_SCOPE_AND_DECISIONS.md ve docs/06_IMPLEMENTATION_PLAN.md, sonra çalışılan alanın ayrıntı belgesini oku. Dosyaların hepsini CLAUDE.md içine kopyalama.
P0→P8 sırasını izle. Aşama bitişinde test kanıtı ve değişen dosyalarla docs/10_PROGRESS.md güncelle; sıradaki bağımsız işe devam et. Kullanıcı onayı gereken ürün akışı ile kod geliştirme onayını karıştırma.
Gerçek Pega/SSO erişimi yokken test ikameleriyle ilerle; eksik erişimi tamamlanmış özellik gibi sunma. Testte çalışması Pega uyumluluğu değildir.
Mimari değişiklikleri bir ADR dosyasına gerekçesiyle ekle. İşlemin anlamını veya güvenlik sınırını değiştiren kararları sessizce alma.
Testleri anlamlı katmanlarda yaz; yalnızca implementasyonun kopyası testlerle yetinme. Güvenilirlik, yetki ve veri değiştirme davranışlarının testleri zorunludur.
Gerçek .env, kimlik bilgileri ve müşteri verilerini okuma çıktılarında, ekran görüntülerinde veya kaynak kontrolünde ifşa etme.
