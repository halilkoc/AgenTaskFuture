# ADR 0013 — Katalog metadatası MongoDB'de, ekran görüntüsü/kanıt/ek belgeler S3 uyumlu depoda

Tarih: 2026-11-07 · Durum: kabul edildi (karar kaydı; **S3 bu aşamada bağlanmadı**)

## Bağlam
Katalog tanımları ve yayınlar MongoDB'dedir (ADR 0006). Ekran görüntüsü, test kanıtı ve ek belgeler gibi büyük
ikili içerikler için ayrı bir depo gerekecek. Bugün:
- yalnız yerel `ARTIFACT_DIRECTORY` ayarı ve `EVIDENCE_SCREENSHOTS_ENABLED` / `EVIDENCE_RETENTION_DAYS` var;
- ayrı bir artifact/storage portu henüz yok;
- denetimde K4 (kanıt deposu) açık.

## Karar
1. Katalog tanımları ve dosya metadatası (kimlik, içerik özeti, boyut, tür, ilişkili run/yayın) MongoDB'de kalır.
2. Ekran görüntüsü, test kanıtı ve ek belgeler gerektiğinde kurum içi S3 uyumlu depoda tutulur. Dış bulut deposu
   kullanılmaz.
3. Gerçek entegrasyondan önce mevcut artifact/storage yapıları incelenecek: `ARTIFACT_DIRECTORY`, kanıt ayarları
   ve K4 kapsamı. Depo tek bir port/adapter arkasına alınacak; paralel ikinci bir depolama sistemi kurulmayacak.
4. Hassas ekranların maskelenmesi, erişim yetkisi ve saklama süresi gerçek entegrasyon aşamasında ele alınacak.
   Mevcut saklama ayarı (`EVIDENCE_RETENTION_DAYS`) üst sınır olarak korunur.

## Sonuçlar
- Bu görevde S3 bağlantısı, ayarı veya bağımlılığı eklenmedi.
- S3 uç noktası ve kimlik bilgileri ileride merkezi Settings ve `.env` üzerinden eklenecek; sırlar frontend'e
  gitmeyecek.
