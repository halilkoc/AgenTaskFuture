# P5 — MongoDB, hash-bağlı onay, değişmez revizyonlar ve tutarlı yayımlama Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.

**Goal:** Onaylı taslağı değişmez operasyon revizyonu + tam release manifestosu olarak MongoDB'ye yazmak ve aktif
pointer'ı en son compare-and-set ile değiştirmek; eksik yayın asla aktif olmaz; çalışan run eski release'e bağlı kalır.

**Architecture:** `domain/release.py` (ApprovalRecord, OperationRevision, ReleaseManifest, ActivePointer, hash'ler),
`application/ports/catalog.py` (CatalogStore), `infrastructure/mongo/catalog_store.py` (pymongo async; $jsonSchema
validator + unique index migration), `application/services/publishing.py` (approve/publish/active/list),
`/api/drafts/{id}/approve|publish`, `/api/catalogs/releases`, `/catalogs` ekranı.

**Spec:** docs/02 (MongoDB, Tutarlı yayımlama), docs/06 P5, docs/07 T19–T21, docs/08.

## Global Constraints
- Onay sunucu tarafı kayıttır: onaylayan + canonical content hash + yeni oturum test kanıtı hash'i + adapter/şema
  sürümü. İstemci boolean'ı yetmez. Düzenleme onayı geçersiz kılar. Onay/yayın PUBLISH_CATALOG yetkisi ister.
- Aynı app+op+revision farklı hash ile yazılamaz (ContentConflict). Manifest yalnız bütün referanslar doğrulanınca
  yazılır. Pointer CAS en sondadır; CAS kaybı PublishConflict (manifest pasif kalır).
- Gerçek Mongo testleri: PATH'te mongod varsa geçici örnek (scratch dbpath, rastgele port); yoksa BLOCKED olarak atlanır.
  Bellek içi sahte depo yalnız tests/ altında, gerçek Mongo yerine sunulmaz.
- Yeni ayarlar: CATALOG_BACKEND (mongo|disabled), CATALOG_ENVIRONMENT.

## Review Focus
1. Revizyon yazıldıktan sonra / manifest yazıldıktan sonra hata → aktif değişmez (`test_failure_mid_publish_never_activates`).
2. Eşzamanlı iki yayın → biri kazanır, diğeri conflict; aktif manifest tam (`test_concurrent_publish_one_wins`).
3. Onaydan sonra düzenleme → yayın reddi (`test_stale_approval_rejected`).
4. Eski release değişmez; yeni yayın eskiyi bozmaz (`test_old_release_pinned_and_immutable`).
5. Aynı request_id → aynı release; farklı taslakla → conflict (`test_publish_idempotency`).

### Task 1: Domain + PublishService (sahte depo ile unit)
### Task 2: Mongo adapteri + gerçek mongod entegrasyon testleri
### Task 3: API + ekranlar (/designer onay/yayın, /catalogs) + e2e + belgeler
