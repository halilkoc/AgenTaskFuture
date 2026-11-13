# AgenTask — Pega katalog tabanlı otomasyon: uygulama geliştirme paketi

Sürüm: 1.0 · Tarih: 2026-11-05 · Durum: Ar-Ge uygulama şartnamesi.
Bu paket uygulama kaynak kodu değildir. Claude Code'un uygulamayı geliştirmesi için bağlam, görevler, sözleşmeler ve doğrulama koşulları içerir. Gerçek Pega sisteminde test edilmiş başarı iddiası içermez.

## Kullanım
1. Arşivi boş bir proje klasörüne açın. Mevcut depoda kullanılacaksa önce mevcut CLAUDE.md/AGENTS.md talimatlarını okuyup çakışmaları birleştirin; dosyaları körlemesine ezmeyin.
2. Claude Code'u bu klasörde başlatın. Önce CLAUDE.md, sonra docs/00_SCOPE_AND_DECISIONS.md, docs/06_IMPLEMENTATION_PLAN.md ve docs/10_PROGRESS.md dosyalarını okumasını isteyin.
3. Aşağıdaki başlangıç talimatını kullanın. Paket bir uygulamayı dış ortama yayımlama talimatı vermez.

> CLAUDE.md ve referans verdiği proje belgelerini oku. Önce mevcut çalışma alanını incele. docs/06_IMPLEMENTATION_PLAN.md içindeki P0'dan başlayarak uygulamayı geliştir. Ortama bağlı bütün ayarlar tek Settings katmanından .env/ortam değişkenleriyle okunacak. Her aşamada anlamlı testleri çalıştır ve docs/10_PROGRESS.md dosyasını güncelle. Rutin ve geri alınabilir uygulama kararlarında durmadan ilerle. Pega erişimi veya kurum bilgisi gerektiren bilinmeyenleri gerçekmiş gibi üretme; port ve test ikamesiyle ilerle, gerçek sistem doğrulamasını bekleyen olarak işaretle. Katalogda kalıcı selector tutma; model önerileri doğrudan çalıştırılmasın. Uygulamayı yalnızca yerel Ar-Ge ortamında çalıştır; gerçek banka işlemi veya dış dağıtım yapma.

## Okuma sırası
- [Claude Code talimatları](CLAUDE.md)
- [Kapsam ve kararlar](docs/00_SCOPE_AND_DECISIONS.md)
- [Mimari](docs/01_ARCHITECTURE.md)
- [Katalog ve plan sözleşmeleri](docs/02_CATALOG_CONTRACTS.md)
- [Çalışma motoru ve kurtarma](docs/03_RUNTIME_AND_RECOVERY.md)
- [Arayüz ve katalog hazırlama](docs/04_UI_AND_AUTHORING.md)
- [.env ve yapılandırma](docs/05_CONFIGURATION.md)
- [Uygulama planı](docs/06_IMPLEMENTATION_PLAN.md)
- [Test ve kabul](docs/07_ACCEPTANCE_TESTS.md)
- [Güvenlik ve izleme](docs/08_SECURITY_AND_OPERATIONS.md)
- [API sözleşmeleri](docs/09_API_CONTRACTS.md)
- [İlerleme kaydı](docs/10_PROGRESS.md)
- [Teknik kaynaklar](docs/11_REFERENCES.md)

.env.example yalnızca güvenli Ar-Ge örnek ayarları içerir. Gerçek parolalar, banka adresleri veya kullanıcı verileri yoktur. Kopyalayıp .env oluşturun; .env dosyasını sürüm kontrolüne eklemeyin.

## Yerel geliştirme (P0 itibarıyla)
```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock && .venv/bin/pip install -e ".[dev]" --no-deps
.venv/bin/playwright install chromium
cp .env.example .env            # SESSION_SIGNING_KEY'e en az 32 karakterlik rastgele değer yazın
.venv/bin/agentask --check-config
.venv/bin/python -m tools.dev_check   # lint + format + typecheck + ilgili testler (--full, --docker)
.venv/bin/agentask               # veya: agentask --env-file /yol/dosya.env
```
Kontroller: `.venv/bin/pytest -q`, `.venv/bin/ruff check src tests`, `.venv/bin/mypy`.

Dev kimliği yalnızca loopback'te çalışır; kullanıcı/rol `X-Dev-User` ve `X-Dev-Roles` (operator, designer,
publisher; virgülle) başlıklarıyla seçilir, başlık yoksa bütün roller verilir. Gerçek SSO değildir.

## Deney uygulaması (P1) — gerçek Pega değildir
```bash
.venv/bin/agentask-lab            # http://127.0.0.1:8100 (+ cross-origin frame için :8101)
.venv/bin/agentask                # ayrı terminalde ana uygulama, http://127.0.0.1:8000
```
Giriş: http://127.0.0.1:8100/login (herhangi bir kullanıcı adı). Sayfalar: `/pages/frames`, `/pages/duplicates`,
`/pages/dropdowns`, `/pages/table-paged`, `/pages/table-scroll`, `/pages/delayed`, `/pages/note-form`.
Senaryo kontrolü: http://127.0.0.1:8100/__lab paneli veya
`curl -X PUT -H 'Content-Type: application/json' -d '{"delay_ms":1500}' http://127.0.0.1:8100/__lab/scenario`.
Alanlar: delay_ms, reveal_delay_ms, late_frame_delay_ms, combobox_delay_ms, dialog (none|modal|native),
lose_next_commit_response, lost_response_hang_ms, client_timeout_ms, table_rows, page_size, scroll_batch.
`POST /__lab/sessions/expire` oturumları düşürür, `POST /__lab/reset` her şeyi sıfırlar, `GET /__lab/state` commit
kayıtlarını gösterir. Testler: `.venv/bin/pytest -q` (gerçek Chromium dahil) veya yalnız tarayıcı testleri `-m browser`.

## Gözlem ve hedef çözümü (P2)
Deneme ekranı: http://127.0.0.1:8000/designer/targets (designer rolü; dev kimlikte varsayılan). Seçim ve vurguyu
görmek için `BROWSER_HEADLESS=false`. Akış: Oturum aç → Adres (lab `/login`, açılan pencerede giriş) → Ekranı
gözlemle / Hedef ara / Seçimi başlat.

API ile (headless da çalışır; lab girişi için yalnız-loopback `/__lab/autologin` kullanılır):
```bash
H=(-H "X-Dev-User: ayse" -H "X-Dev-Roles: designer" -H "Content-Type: application/json")
SID=$(curl -s -X POST "${H[@]}" http://127.0.0.1:8000/api/sessions | python3 -c "import json,sys;print(json.load(sys.stdin)['session_id'])")
B=http://127.0.0.1:8000/api/sessions/$SID
curl -s -X POST "${H[@]}" $B/navigate -d '{"url":"http://127.0.0.1:8100/__lab/autologin?user=ayse&next=/pages/duplicates"}'
curl -s -X POST "${H[@]}" $B/resolve -d '{"kind":"textbox","labels":["Müşteri No"],"region":"Kefil"}'
```
TargetSpec alanları: `kind` (textbox|button|select|combobox|tab|table), `labels` (en az bir), `region`,
`frame_title`, `row_key`, `require_visible`, `require_enabled`. Selector/id/xpath alanı yoktur (422).

## İşlem Deneme (P3)
http://127.0.0.1:8000/designer/runs — oturum aç → "Deney ekranını aç" → örnek senaryo seç veya formdan adım ekle
(hedefi "Hedefi doğrula (P2)" / "Tarayıcıda seç" ile belirle) → Çalıştır. Adım durumları: Hazırlandı, İşlem
gönderildi, Sonuç doğrulanıyor, Başarılı, Bilinen başarısızlık, Sonuç belirsiz, Atlandı. Sonuç rozeti: Başarılı /
Başarısız / Belirsiz / Duraklatıldı / İptal edildi. Senaryolar lab kontrol panelinden (http://127.0.0.1:8100/__lab):
`lose_next_commit_response` (yanıt kaybı → uzlaştırma), `dialog=modal` (bilinen uyarı), `dialog=unknown_modal`
(durur), `dialog=native` (durur, kapatmaz), "Oturumları sonlandır" (oturum kaybı → duraklatma).

## Katalog Tasarımcısı ve yayın (P4–P5)
- http://127.0.0.1:8000/designer — taslak → parametre → adım (niyet) → adaylar/işaretleme → ayrı onaylar → deneme →
  sonuç onayı → yeni oturum testi → Onayla (yayıncı) → Yayımla. Yayınlar: http://127.0.0.1:8000/catalogs
- Yayın MongoDB ister (`CATALOG_BACKEND=mongo`, `MONGO_URI`). Yerelde örnek: `mongod --dbpath ./var/mongo --port 27017
  --bind_ip 127.0.0.1`. Mongo yoksa `CATALOG_BACKEND=disabled` ile taslak/deneme çalışır, yayın 503 döner.

## İşlem Asistanı (P6)
http://127.0.0.1:8000/assistant — talep yazın (ör. "Kefil müşteri numarasını 00123 olarak gir") → Yorumla → eksik
parametreyi doldurun → Planı göster → Oturum aç + ekranı aç → Çalıştır. Yayımlanmış işlem gerekir (P5). Model
varsayılan kapalı (`LLM_ENABLED=false`); açmak için kurum içi OpenAI uyumlu uç (`LLM_BASE_URL`, `LLM_MODEL`, auth).

## Değişiklik/etki ve çalışmalar (P7)
- http://127.0.0.1:8000/changes — işlem seç → oturum + ekran aç → "Ekranla karşılaştır" → değişen elemanlar, etkilenen
  işlemler, yeniden test listesi → "Onarım taslağı oluştur". Etiket değişikliği denemek için lab kontrol panelinde
  `guarantor_customer_label` değerini değiştirin.
- http://127.0.0.1:8000/runs — metrikler ve adım zaman çizelgesi.

## Birleştirme (P8, deneysel)
`COMPOSITION_ENABLED=true` ile /assistant'ta "Birleşik görev" bölümü açılır (işlem zinciri). Koşul ve sınırlı döngü
API ile: `/api/assistant/composite/preview|execute` (`{"plan": {"nodes": [...]}}`). Gerçek ortam kontrol listesi:
docs/12_RUNNER_AND_INTEGRATION_CHECKLIST.md.

## Yerel MongoDB: otomatik başlatma (yalnız geliştirme) ve mevcut MongoDB'ye bağlanma
Bağlantı (`MONGO_URI`, `MONGO_DATABASE`) uygulamanın normal ayarıdır. Altyapıyı başlatma işi ise ayrı, sökülebilir
geliştirme aracındadır (`tools/local_mongo/`, `compose.local-mongo.yml`). Uygulama bu aracı import etmez.

**Mevcut MongoDB'ye bağlanma (varsayılan, gerçek ortam):** `.env`'de `LOCAL_MONGO_AUTOSTART=false` ve
`MONGO_URI=...` ayarlanır, uygulama `.venv/bin/agentask` ile başlatılır. Bu modda Docker kurulu veya açık olmak
zorunda değildir. Mongo erişilemezse `/health/ready` 503 döner ve yayın uçları 503 verir; başka bir depoya
sessizce geçilmez.

**Yerel otomatik başlatmayı açmak (yalnız `APP_ENV=development`):**
1. `.env`'de `LOCAL_MONGO_AUTOSTART=true` yapın. `MONGO_URI`, yerel servisi göstermelidir:
   `mongodb://127.0.0.1:<LOCAL_MONGO_PORT>`.
2. Başlatın: `.venv/bin/python -m tools.local_mongo dev` (`agentask` ile aynı argümanları alır, ör. `--env-file`).
   Araç Docker Compose ile Mongo'yu hazır eder, ping başarılı olunca uygulamayı başlatır.
   - Mevcut container ve volume yeniden kullanılır; hiçbir veri sıfırlanmaz.
   - `MONGO_URI` uzak bir sunucuyu, başka bir portu veya uyuşmayan kimlik bilgisini gösterirse açık hata verir;
     URI'yi değiştirmez.
   - Port başka bir servisteyse o servise dokunmaz ve hata verir.

**Diğer komutlar** (`.venv/bin/python -m tools.local_mongo ...`):
- `up` / `status`
- `stop`: durdurur, **veriyi silmez**. Uygulama kapanınca Mongo çalışmaya devam eder (`restart: unless-stopped`).
- `backup`: `LOCAL_MONGO_BACKUP_DIR` altına `<db>-<zaman>.archive.gz` yazar.
- `restore <arşiv> <hedef_db>`: arşivi yalnız **ayrı** bir veritabanına geri yükler (ör. `agentask_restore_test`).
  Ana katalog veritabanına geri yükleme reddedilir.

**Veri ve güvenlik:**
- Veri, `LOCAL_MONGO_VOLUME` adlı named volume'dadır. Proje ve volume adı çalışma klasörüne bağlı değildir.
- Port yalnız `127.0.0.1`'e açılır.
- Veriyi gerçekten silmek isterseniz bunu ancak bilerek ve elle yapın: `docker volume rm <LOCAL_MONGO_VOLUME>`.

VS Code görevleri `.vscode/tasks.json` içindedir.

**Yerel aracı kaldırmak:** Aşağıdakiler silinir; uygulama kodunda değişiklik gerekmez:
- `tools/local_mongo/` (başka araç yoksa `tools/` de),
- `compose.local-mongo.yml`,
- `.vscode/tasks.json` içindeki `local-mongo:` görevleri,
- `.env` / `.env.example` içindeki `LOCAL_MONGO_` önekli araç satırları (bırakılırsa uygulama yok sayar),
- `tests/unit/test_local_mongo_tool.py`, `tests/integration/test_local_mongo_off.py`, `tests/integration/docker/`,
- `pyproject.toml`'daki `docker` marker'ı, `tools/...` per-file ignore satırları ve mypy `packages` içindeki
  `"tools"` girdisi.

`LOCAL_MONGO_AUTOSTART=false` satırı kalabilir. Ek dev bağımlılığı yoktur: araç Docker SDK değil Docker Compose CLI
kullanır.
