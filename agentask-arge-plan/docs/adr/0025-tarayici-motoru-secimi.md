# ADR 0025 — Tarayıcı motoru seçimi: Chromium ve Firefox; WebKit reddedilir

**Durum:** Kabul edildi (2026-11-16). WebKit kararı kullanıcı onayına açıktır (aşağıda "Açık karar").

## Bağlam
Şirket geliştirme ortamında Chromium kullanılamıyor. `BROWSER_ENGINE` ayarı baştan beri vardı ama zorunluydu, yalnız
Chromium ile denenmişti ve iki yerde Chromium'a özgü varsayım taşıyordu. İkinci bir ayar veya paralel tarayıcı
uyarlayıcısı eklenmedi; mevcut ayar ve tek `PlaywrightContextFactory` genişletildi. Playwright sürümü (1.64.1) değişmedi.

## Kararlar
- **Tek ayar:** `BROWSER_ENGINE=chromium|firefox`. Verilmezse `chromium` (eski `.env` dosyaları çalışır). Uygulama yalnız
  seçilen motoru başlatır; bulunamaz veya açılamazsa `DependencyUnavailable` (motor adıyla) verir. Başka motora geçiş yoktur.
- **Motor ile kurulu ikili ayrı:** `BROWSER_EXECUTABLE_PATH` yalnız `chromium` içindir (Edge/Chrome). Firefox ile verilirse
  ayar doğrulaması reddeder: Playwright, Firefox'u yalnız kendi derlemesiyle sürer. Kanal ayarı yoktur, eklenmedi.
- **Engellenen çerçeve motordan bağımsız izlenir:** Chromium engellenen alt çerçeveyi `chrome-error://` adresine taşır,
  Firefox taşımaz. Yalnız bu adrese bakıldığı için Firefox'ta engellenen çerçeve "tarandı" sayılıyor ve eksik tarama
  işlemi durdurmuyordu. Engelleme artık isteği kesen yerde (`blocked_frames.py`) kaydedilir; gözlem, pencere taraması ve
  seçici aynı kaydı kullanır. Bu bir güvenlik düzeltmesidir: eksik kapsam yine "erişilemez" sayılır.
- **Kırpılan merkez katman sayılmaz:** kaydırma alanından büyük hedefin (tablo) merkezi alanın dışındaysa o noktadaki
  komşu öğe "hedefi kapatan katman" değildir. Motordan bağımsız bir hataydı; Firefox satır ölçüleriyle görünür oldu.
  Tıklama öncesi görünür alana kaydırma ve Playwright'ın kendi isabet denetimi değişmedi.
- **`--doctor`:** seçili motoru, tarayıcı dosyasının varlığını ve başlatma sonucunu ayrı satırlarda yazar; indirme yapmaz.

## WebKit neden reddediliyor
Hedef adres sınırı (ADR 0002) her isteği `route.fetch(max_redirects=0)` ile alır, `Location` hedefini denetler ve yanıtı
tarayıcıya `route.fulfill` ile verir. WebKit bu adımı desteklemez: Playwright 1.64.1 `Route.fulfill: Cannot fulfill with
redirect status: 303` hatası verir (en küçük yeniden üretim:
`var/verification/browser-engines-20261116/kesif/webkit-yonlendirme-yeniden-uretim.py`; Chromium ve Firefox aynı betikte
geçer). Giriş dahil yönlendirme içeren hiçbir akış çalışmaz. `BROWSER_ENGINE=webkit` bu yüzden ayar doğrulamasında
gerekçesiyle reddedilir; geç ve anlaşılmaz bir hata yerine `--check-config` açık mesaj verir.

Değerlendirilip seçilmeyen yollar:
- Yönlendirmeyi tarayıcıya bırakmak (`route.continue_`): Playwright yönlendirme adımlarında denetleyiciyi çağırmaz; izinsiz
  adrese en az bir istek gider. Güvenlik sınırını gevşetir.
- Yönlendirmeyi uygulamada taklit etmek (200 + betikle yönlendirme veya hedefi sunucu tarafında izlemek): adres çubuğu,
  geçmiş, `Referer` ve 307/308'de istek yöntemi değişir; SSO/SAML zincirlerini bozabilir ve burada doğrulanamaz.

## Açık karar (kullanıcı)
WebKit gerçekten gerekiyorsa yönlendirme taklidi ayrı bir iş olarak, gerçek SSO akışında denenerek ele alınmalıdır.
Bu sürümde yapılmadı.

## Doğrulanmayanlar
Firefox yalnız macOS üzerinde deney uygulamasıyla denendi. Windows'ta Firefox kurulumu, çevrimdışı tarayıcı klasörü ve
gerçek Pega/SSO ile çalışma doğrulanmadı.
