# ADR 0019 — Sürümlü, yeniden kullanılabilir bileşenler (catalog-v4) (Ana plan E)

Tarih: 2026-11-07 · Durum: kabul edildi (lab + geçici MongoDB; gerçek Pega doğrulanmadı)

## Bağlam
Yeni tasarımcıdaki "Akış çağır" yalnız sayfa belleğindeki temsili bileşenleri kullanıyordu. P8 birleşik plan
(`COMPOSITION_ENABLED`, deneysel) işlemleri **etkin yayındaki** sürümleriyle çağırır; bileşen yeni sürümle
yayımlanınca onu kullanan akış sessizce değişir. Hedef: bileşen = yayımlanmış işlem; akış, çağırdığı işlemin
revizyonuna pinlenir.

## Karar
1. **Sözleşme (catalog-v4):** yeni adım `op=call_operation` + `call`:
   `{operation_id, revision, content_hash, arguments, inputs, outputs, start_screen, end_screen}`.
   - `arguments`: bileşen parametresi → çağıranın güvenli şablonu (`{ad}`).
   - `inputs/outputs/start_screen/end_screen`: pinlenen revizyondan **sunucuda** çıkarılan özet; istemci bildiremez
     (`PUT /api/drafts/{id}/steps/{sid}/call`). Derlemede gerçek bileşenle yeniden karşılaştırılır.
   - Çıktı = bileşenin okuma adımları (element_id). Çağıran, `prior_output` parametresine yeni
     `prior_output: <element_id>` alanıyla bağlar (ADR 0017 çalışma anı bağlaması aynen kullanılır).
   - `definition_schema`: adımlardan biri `call` taşıyorsa `catalog-v4`; diğer tanımlar ve hash'leri değişmez.
     `SCHEMA_VERSION` (manifest hash sabiti) değişmedi.
2. **Derleme:** bileşen komutları çağıranın planına açılır (bileşenin kendi `assert_screen`'i dahil), çıktı
   başvuruları kaydırılır. Reddedilen (çalıştırmadan): eksik/bilinmeyen girdi, pinli revizyon yok, hash/sözleşme
   uyuşmazlığı, döngü (doğrudan ve dolaylı), derinlik > 3, uyumsuz çıktı, geçersiz ekran sırası
   (`call.start_screen` çağıranın o anki ekranı olmalı; çağrıdan sonra rota `end_screen` ile sürer).
3. **Yayın:** pinli bileşen revizyonu (ve onun bileşenleri) katalogda hash'iyle var olmalı; yoksa
   `PublishConflict`. Bileşenin ekran revizyonları manifeste eklenir (önceki yayındaki ekran, hash ile bulunur).
   Pinli bileşen etkin yayında olmasa da değişmez revizyonundan yüklenir (`PublishService.component`).
4. **Sürüm değişikliği:** `GET /api/drafts/{id}/component-updates` daha yeni revizyonları ve etkisini gösterir
   (yeni girdi, kalkan kullanılan çıktı, ekran değişimi, uyumluluk). Yükseltme açık işlemdir; adım onayı, denemesi
   ve yeni oturum testi sıfırlanır (hash değişir).
5. **Etki:** çağrı adımının etkisi `component` kabul edilir; tasarımcı denemesi etki onayı ister. Asistan
   önizlemesi etkiyi açılan komutlardan hesaplar (çağrı, içindeki veri değiştiren aksiyonu gizleyemez).
6. **Arayüz:** yeni tasarımcıda gerçek oturumda "Akış çağır" yayımlanmış ve onaylı işlemleri sürümüyle listeler;
   girdiler sabit/sorulur; çıktılar sonraki "Alan doldur"da "Önceki adımın çıktısı" olarak seçilir. Canlı
   panelde "Bileşen sürümleri" bloğu yükseltmeyi gösterir.

## Migrasyon notu
- catalog-v1/v2/v3 tanımları ve yayınları **yerinde değiştirilmez**; okunma yolu aynıdır.
- catalog-v4 yalnız yeni bileşen çağrısı içeren taslaklar yayımlanınca oluşur. v4'ü okuyamayan eski sürüm uygulama
  bu tanımları `unsupported_schema` ile reddeder (sessizce yorumlamaz).
- Temsili (sayfa içi) bileşenler kalıcı taslağa aktarılmaz.

## Doğrulama
`tests/unit/test_components.py`, `tests/unit/test_component_publishing.py`,
`tests/e2e/test_new_designer_components_mongo.py`.
