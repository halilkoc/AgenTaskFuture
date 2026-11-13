# ADR 0016 — Dosya ve kanıt depolama portu (yerel adaptör; S3 BLOCKED)

Tarih: 2026-11-07 · Durum: kabul edildi (yerel adaptörle doğrulandı; kurum S3 bağlantısı BLOCKED)

## Bağlam
ADR 0013'e göre katalog ve dosya metadatası MongoDB'de, ekran görüntüsü, kanıt ve ek belgeler kurum içi S3 uyumlu
depoda tutulacak. İnceleme sonucu:
- `ARTIFACT_DIRECTORY` ayarı vardı ama hiçbir kod kullanmıyordu;
- artifact portu yoktu (denetim K4);
- ekran görüntüsü kaydı varsayılan olarak kapalı (`EVIDENCE_SCREENSHOTS_ENABLED=false`).

## Karar
1. **Tek port, iki parça** (`application/ports/artifacts.py`):
   - `ObjectStore` (put/get/delete/list_keys): yerel dosya veya S3 uyumlu.
   - `ArtifactIndex`: metadata.
   - Yerel geliştirme adaptörleri `infrastructure/artifacts/local_file.py`'dedir (ARTIFACT_DIRECTORY): atomik
     yerleştirme ve yol geçişi koruması var.
2. **Metadata** (`ArtifactRef`):
   - sahip (erişim), tür, içerik türü (allowlist), boyut, sha256, oluşturma ve saklama sonu (`retain_until`),
     isteğe bağlı run kimliği;
   - katalog içine binary/base64 gömülmez.
3. **Tutarlılık:**
   - Önce nesne, sonra metadata yazılır. Metadata yazılamazsa nesne silinir (telafi); nesne yazılamazsa
     metadata oluşmaz.
   - Ortak transaction varmış gibi davranılmaz. Çökmeden kalan öksüz nesneler `cleanup_orphans` ile temizlenir.
   - Süresi dolanlar `purge_expired` ile silinir; süre `EVIDENCE_RETENTION_DAYS`.
4. **Okuma:**
   - Sahip kontrollüdür; başka kullanıcıya "bulunamadı" denir.
   - Metadata olup nesne yoksa veya sha256 uyuşmazsa "eksik/bozuk" hatası verilir; var gibi gösterilmez.
   - İmzalı bağlantı üretilmez; içerik yetkili uçtan (`GET /api/artifacts/{id}`) akıtılır. İçerik ve değerler
     loglanmaz.
5. **Ekran görüntüsü:** maskelemesi doğrulanmamış görüntü reddedilir. Tüm ekranların sürekli kaydı yoktur.
6. **Ayar:** yalnız `ARTIFACT_MAX_BYTES` (dosya başına üst sınır) eklendi; mevcut `ARTIFACT_DIRECTORY` ve
   `EVIDENCE_RETENTION_DAYS` kullanılır.

## BLOCKED / kalan
- **S3 uyumlu adaptör:** kurum uç noktası, kimlik/secret enjeksiyonu ve TLS CA bilgisi gerekir; istemci
  kütüphanesi ayrıca seçilecek. Gerçek bağlantı yok.
- **MongoDB metadata adaptörü:** henüz yazılmadı; geliştirmede JSON dizini kullanılır.
- **Üreticiye bağlama:** yürütücünün kanıt üretip bu servise yazması henüz bağlanmadı. Ekran görüntüsü
  maskelemesi doğrulanmış bir yakalayıcı gerekiyor.
