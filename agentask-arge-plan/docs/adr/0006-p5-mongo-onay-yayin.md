# ADR 0006 — P5 MongoDB, hash-bağlı onay ve pointer-last yayımlama

Tarih: 2026-11-05 · Durum: kabul

## Kararlar
1. **Onay kaydı** (`ApprovalRecord`) taslakta sunucu tarafında tutulur: onaylayan, canonical içerik hash'i, yeni oturum
   testi kanıtı hash'i, adapter ve şema sürümü. İstemci boolean'ı kullanılmaz. İçerik veya test değişirse onay
   geçersizdir (`stale_approval`). Onay ve yayın `PUBLISH_CATALOG` yetkisi ister; aynı kişinin tasarlaması ve
   onaylaması kurum kararına bırakıldı (engellenmedi, kayıt altında).
2. **Yayın sırası:** değişmez operasyon revizyonu (aynı hash → mevcut revizyon; farklı hash aynı numarayla →
   `content_conflict`) → bütün referansları doğrulanmış tam manifest (önceki etkin manifestteki diğer işlemler +
   yeni revizyon) → aktif pointer compare-and-set. CAS kaybı `publish_conflict` (manifest pasif kalır, yeniden
   deneme yeni tabanla). Replica set/transaction gerekmez.
3. **Mongo şeması:** `$jsonSchema` validator (strict) + unique indexler, açılışta `ensure_schema` (idempotent).
   Zaman damgaları milisaniyeye yuvarlanır (değişmez kaydın geri okunduğunda birebir eşitliği için).
4. **Erişilemeyen Mongo:** uygulama açılır; `/health/ready` `catalog_mongo: unavailable` ile 503; yayın uçları 503.
   `CATALOG_BACKEND=disabled` iken taslak/deneme çalışır, yayın kapalıdır.
5. **Test stratejisi:** gerçek Mongo testleri PATH'teki `mongod` ile geçici örnek (scratch dbpath, rastgele port)
   başlatır; `mongod` yoksa BLOCKED olarak atlanır. Bellek içi depo yalnız `tests/fake_catalog_store.py`.

## Doğrulanmayanlar
Kurumsal Mongo (TLS/CA, kimlik doğrulama, replica set), büyük katalog performansı, şema migration'ı sürüm geçişi.
