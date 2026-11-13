# ADR 0001 — P0 iskelet, tek Settings katmanı ve dev kimlik sınırı

Tarih: 2026-11-05 · Durum: kabul

## Bağlam
docs/05_CONFIGURATION.md bütün ortam ayarlarının tek typed Settings sınıfından okunmasını, varsayılanların iki yerde
kopyalanmamasını ve secret'ların hiçbir hata mesajına/frontend'e sızmamasını istiyor. Gerçek SSO henüz yok.

## Kararlar
1. **Tek kaynak:** Zorunlu ayarların Settings'te varsayılanı yok; değerlerin tek kaynağı `.env.example`.
   Yalnızca opsiyonel path/secret alanları `None` varsayılanlıdır. Test, `.env.example` anahtarlarının Settings
   alanlarıyla birebir eşleştiğini doğrular.
2. **Boş = ayarlanmamış** (`env_ignore_empty`): opsiyonelde None, zorunluda açık hata.
3. **Öncelik:** process env > `--env-file` ya da cwd'deki `.env`. `--env-file` verilip dosya yoksa hata.
   dotenv'deki bilinmeyen anahtar reddedilir (`extra=forbid`), ilgisiz process env yok sayılır.
4. **Redaksiyon:** `ValidationError` girdisiz (`include_input=False`) `ConfigurationError`'a çevrilir, zincir
   koparılır (`from None`). Mongo URI de kimlik bilgisi taşıyabildiği için `SecretStr`.
5. **Kimlik:** `AUTH_MODE` değerleri şimdilik `dev | unconfigured`. `dev` yalnızca development + açık
   `DEV_AUTH_ENABLED=true` + loopback `APP_HOST`; adapter ayrıca her istekte istemcinin loopback olduğunu denetler.
   `unconfigured` tüm kimlik isteklerini 503 ile reddeder, readiness `not_ready` olur; production'da startup reddi.
   Gerçek SSO adapteri kurum sözleşmesi gelince yeni bir `AUTH_MODE` değeri olarak eklenecek.
6. **Production sertliği:** dev auth, `LLM_TLS_VERIFY=false`, http üzerinden LLM credential reddedilir.
   `LLM_TLS_VERIFY=false` test ortamında da reddedilir (yalnız development'ta açık seçim).
7. **LLM:** P0'da httpx adapteri yok; `LLM_ENABLED=true` olsa bile `UnavailableLLM("adapter_not_implemented")`
   bağlanır ve bu durum açıkça raporlanır.
8. **Tek worker:** uvicorn `workers=1` ile başlatılır; bellek içi session kilidi çok worker için yeterli değildir.
9. Settings dışında `os.environ`/`os.getenv`/`dotenv` kullanımı ruff banned-api ve mimari testiyle engellenir.

## Sonuçlar
Yeni bir ayar eklenirken Settings, `.env.example`, docs/05 ve config testi birlikte güncellenmeli; aksi halde
`test_env_example_documents_exactly_the_settings_fields` başarısız olur.
