# Runner sözleşmesi ve gerçek Pega/SSO entegrasyon kontrol listesi (P8)

Bu belge gerçek ortamda doğrulanması gerekenleri listeler. Hiçbir madde yerel deney uygulamasıyla "tamamlandı" sayılmaz.

## 1. Runner sözleşmesi (yerel → uzak)
Mevcut: `RUNNER_MODE=local` — web ve runner aynı süreç, tek worker, bellek içi oturum kilidi.
Uzak runner (PC veya OpenShift) için uygulanması gereken sözleşme (henüz yok; `RUNNER_MODE` başka değer kabul etmez):
- **Görev alma:** runner, `run_id` + derlenmiş plan + `binding` (release_id, revision, content_hash) alır; plan
  runner'da yeniden doğrulanır (komut şeması, onaylı aksiyon kümesi, adım bütçesi).
- **Lease/fencing:** her run için süreli lease (`SESSION_LEASE_SECONDS`) ve artan fencing token; lease kaybında runner
  yeni dispatch yapmaz; geç gelen checkpoint yazımı token ile reddedilir.
- **Checkpoint:** RunRepository portu (yerel dosya → MongoDB `automation_runs` adapteri); `dispatched` checkpoint'i
  tıklamadan önce kalıcı olmalı.
- **Oturum sahipliği:** browser context runner'da; web katmanı yalnız komut/iptal/durum iletir. İptal yeni adımı durdurur.
- **Kurtarma:** runner yeniden başlarsa yarım run'lar `recover_interrupted` kurallarıyla (dispatched → outcome_unknown).
- **Gözlem/vurgu/seçim:** headed ekran gerektirir; uzak runner'da kullanıcıya görüntü aktarımı ayrıca tasarlanmalı.

## 2. Gerçek Pega bilinmeyenleri (kurum bilgisi gerekli — BLOCKED)
| Konu | Gerekli bilgi | Etkilediği bileşen |
|---|---|---|
| Pega sürümü, Traditional/Constellation UI | Örnek DOM, shadow DOM kullanımı, iframe yapısı | P2 envanter (shadow DOM desteklenmiyor), picker |
| Kontrol aileleri | Gerçek combobox/autocomplete, tarih, tablo/grid, modal davranışları | P3 adapterleri (input tabanlı combobox yok) |
| Oturum/SSO | Giriş akışı, yönlendirme zinciri, oturum süresi, oturum kaybı belirtisi | origin politikası, AppProfile.session_lost_* |
| İzinli origin listesi | Uygulama, SSO, CDN, statik kaynak origin'leri | TARGET_ALLOWED_ORIGINS (route.fetch tabanlı koruma, ADR 0002) |
| Kayıt/aksiyon kimliği | Yazma sonrası doğrulanabilir kayıt anahtarı, sürüm/aksiyon id'si | P3 uzlaştırma (lab'da liste sayımı) |
| DX API erişimi | Okuma uç noktaları, yetki | ApplicationMetadataPort (yok), uzlaştırma güçlendirme |
| Bilinen engelleyiciler | Onaylı uyarı pencereleri ve izinli düğmeler | ActionSet.blockers |
| Kimlik/yetki servisi | JWT/SSO doğrulama, rol eşleme, işlem bazında yetki | IdentityPort (yalnız dev/unconfigured), PolicyPort |
| On-prem LLM | Endpoint, auth, model, context, structured output | HttpxLLM (sahte sunucuyla test edildi) |
| MongoDB | TLS/CA, auth, replica set, yedekleme | MongoCatalogStore (yerel mongod ile test edildi) |
| Runner yerleşimi | PC/OpenShift, headed ekran erişimi, ağ | RUNNER_MODE |

## 3. İlk gerçek ortam doğrulama sırası (izinli test ortamı ve test verisiyle)
1. Settings: kurum `.env` (secret'lar ortamdan/secret store'dan), `--check-config`.
2. Okuma-yalnız: oturum aç → gözlem (P2) → kapsam raporu; her kontrol ailesi için hedef çözümü ve vurgu.
3. Seçim modu: gerçek sayfada tıklama/klavye sızıntısı yok (DevTools ağ ve olay kaydı ile).
4. UI-yerel ensure adımları (yazma yok): textbox, liste, sekme, tablo arama.
5. Onaylı, geri dönüşü olan test aksiyonu (izinli ortam, sahte kayıt) + uzlaştırma okuması tanımı.
6. Oturum kaybı, bilinmeyen pencere, yanıt kaybı senaryolarının gerçek belirtileri.
Sonuçlar `docs/13_PEGA_VALIDATION_LOG.md` şablonuna kaydedilir; başarısız aile için adapter eklenir ve senaryo lab
fixture'ına regresyon testi olarak eklenir.
