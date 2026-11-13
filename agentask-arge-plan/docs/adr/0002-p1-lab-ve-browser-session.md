# ADR 0002 — P1 deney uygulaması ve tarayıcı oturumları

Tarih: 2026-11-05 · Durum: kabul

## Bağlam
P1, gerçek Pega yerine yerel bir deney uygulaması ve kullanıcı başına izole, sahiplik/kilit kontrollü async Playwright
oturumları istiyor (docs/06 P1, docs/03, T12/T13). Güvenlik sınırı: hedef uygulamaya yalnızca izinli origin'lerden
gidilir (docs/08).

## Kararlar
1. **Deney uygulaması ayrı paket (`agentask_lab`).** Ürün kodu ona bağımlı değildir (mimari test). Her sayfada
   "Deney uygulaması — gerçek Pega değildir" bandı. Aynı FastAPI uygulaması iki uvicorn sunucusuyla (LAB_PRIMARY_ORIGIN,
   LAB_SECONDARY_ORIGIN) tek process'te ve ortak bellek içi `LabState` ile servis edilir; ikincil origin
   cross-origin frame içindir. LAB_* yalnız loopback http; production'da reddedilir.
2. **Senaryolar HTTP kontrol API'si ile tetiklenir** (`/__lab/*`, yalnız loopback istemci). Senaryo parametreleri
   fixture verisidir, ortam ayarı değildir; bu yüzden .env'de değil, `Scenario` modelindedir.
3. **Oturum kuralları framework'süz servistedir** (`BrowserSessionService`): sahip olmayan → 404 (varlık sızmaz);
   oturum başına tek işlem, ikinci işlem beklemeden 409 (kuyruk yok); kullanıcı/toplam limit (slot await'ten önce
   rezerve edilir); boşta kalan oturumlar `BROWSER_SESSION_IDLE_SECONDS` sonra kapanır, işlemdekiler kapanmaz;
   shutdown bütün context'leri ve browser sürecini kapatır. Kilit bellek içidir, yalnız tek worker için geçerlidir.
4. **Tek browser süreci, oturum başına ayrı BrowserContext.** Browser ilk oturumda başlar, koparsa yeniden başlar.
   `SESSION_LEASE_SECONDS` run lease'i için (P3) ayrılmıştır; boşta kalma süresi ayrı ayardır.
5. **Origin sınırı bütün http(s) isteklerine uygulanır** (yalnız document değil): iframe, popup, img/script,
   `location` değişimi ve sunucu yönlendirmesi. Playwright `route` handler'ı yönlendirme adımlarında çağrılmadığı
   için (testte izinsiz sunucuya isabet görüldü) izinli istekler `route.fetch(max_redirects=0)` ile alınır,
   `Location` politikaya göre denetlenir ve yanıt `route.fulfill` ile tarayıcıya verilir.

## Sonuçlar ve riskler
- (5) nedeniyle sayfa istekleri tarayıcının ağ katmanı yerine Playwright request context'i ile yapılır: yanıtlar
  tamponlanır; HTTP cache, streaming/SSE ve bazı başlık davranışları farklı olabilir; WebSocket bu yoldan geçmez
  (origin kontrolü yok). Gerçek Pega'da (SSO yönlendirmeleri, büyük yanıtlar, push) doğrulanmadan yeterli sayılmaz.
  Alternatif (Chromium'a özel CDP Fetch domain'i) gerekirse ayrı ADR ile değerlendirilecek.
- İzinli listede olmayan kaynaklar (CDN, SSO sağlayıcısı) yüklenmez; TARGET_ALLOWED_ORIGINS gerçek ortamda buna göre
  doldurulmalıdır.
