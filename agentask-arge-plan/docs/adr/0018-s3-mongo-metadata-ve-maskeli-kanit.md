# ADR 0018 — S3 uyumlu nesne deposu, MongoDB dosya metadatası ve maskeli kanıt (Ana plan G)

Tarih: 2026-11-07 · Durum: kabul edildi (sahte S3 ve geçici MongoDB ile doğrulandı; **kurum S3 kabulü BLOCKED**)

## Bağlam
ADR 0016 portu ve yerel adaptörleri kurdu. Kalanlar: S3 adaptörü, MongoDB metadata adaptörü, yürütücünün kanıt
üretmesi. Port eşzamanlıydı; ağ G/Ç'si olan adaptörler için async'e çevrilmesi gerekiyordu.

## Karar
1. **Port async:** `ObjectStore` ve `ArtifactIndex` yöntemleri `async`. `ArtifactService` ve
   `GET /api/artifacts/{id}` buna göre güncellendi; davranış (telafi, sahiplik, bütünlük) değişmedi.
2. **S3 adaptörü** (`infrastructure/artifacts/s3.py`):
   - Yeni bağımlılık yok: AWS Signature V4 kodda; istekler mevcut `httpx` ile.
   - Yalnız PutObject/GetObject/DeleteObject/ListObjectsV2. Uç nokta ve kova yalnız Settings'ten; anahtarlar yalnız
     kod üretimli `art_…` kimlikleri (yol geçişi ve serbest anahtar reddedilir, istek gönderilmeden).
   - İçerik özeti (`x-amz-content-sha256`) imzaya girer; nesne yalnız tamamı yazılınca görünür.
   - TLS doğrulaması kapatılamaz; kurum CA'sı `S3_CA_BUNDLE`. Yönlendirme izlenmez. Hata mesajı ve loglarda kimlik
     bilgisi yok.
   - Liste yanıtı boyut ve sayfa sınırlı; devam belirteci olmadan kesilen liste hata sayılır.
3. **Ayarlar** (docs/05): `ARTIFACT_BACKEND=local|s3`, `ARTIFACT_INDEX_BACKEND=local|mongo`, `S3_*`.
   Varsayılan `local` (mevcut .env'ler bozulmaz). `s3` için uç nokta/kova/bölge/kimlik zorunlu; uç nokta https
   (yalnız loopback test deposu http); adreste kimlik bilgisi reddedilir.
4. **MongoDB metadata** (`artifact_index` koleksiyonu): `artifact_id` tekil; `retain_until` ve sahip dizinli.
   TTL dizini **kullanılmaz**: metadata'nın tek başına silinip öksüz nesne kalmaması için silme servisten
   (`purge_expired`) yapılır.
5. **Maskeli kanıt** (`infrastructure/browser/evidence.py`), varsayılan kapalı (`EVIDENCE_SCREENSHOTS_ENABLED`):
   - Yalnız başarısız, sonucu belirsiz veya müdahale bekleyen run için tek görünür alan görüntüsü.
   - Bütün form kontrolleri ve çerçeveler (değer içerebilecek her şey) maske rengiyle örtülür; hassaslık tahmin
     edilmez.
   - **Doğrulama:** görüntü çözülür (bağımlılıksız PNG çözücü) ve her kutunun iç pikselleri maske rengi mi diye
     kontrol edilir. Tek kutu bile tam örtülü değilse görüntü saklanmaz (`masking_verified` yalnız bu durumda
     `true`). Kanıt alınamaması run sonucunu değiştirmez.
   - Run kaydı yalnız `artifact_id` tutar (`Run.evidence`); içerik depodadır, sahip kontrollü uçtan okunur.

## Doğrulama
- `tests/unit/test_object_store_contract.py`: AWS'nin yayımladığı SigV4 "GET Object" örnek imzası; yerel ve S3
  (sahte S3: imza, özet ve sayfalama denetimli) adaptörleri aynı sözleşme testlerinden geçer; yanlış kimlik/sunucu
  hatası; sır sızmaması.
- `tests/integration/mongo/test_artifact_index_contract.py`: yerel ve MongoDB metadata aynı sözleşme.
- `tests/integration/browser/test_evidence.py`: parola alanı maskeli ve piksel düzeyinde doğrulanmış; maskesiz
  görüntü doğrulamayı geçemez; başarısız run kanıtı depoya yazılır.

## BLOCKED / sınırlar
- **Kurum S3 bağlantı kabulü:** gerçek uç nokta, kimlik, CA ve kova politikası yok. Sahte S3 gerçek S3 değildir;
  kurum deposunun (ör. MinIO/Ceph) imza ve liste davranışı gerçek ortamda doğrulanmalıdır.
- Gölge DOM içindeki ve çapraz origin çerçeve içindeki alanlar ayrıca listelenmez; çerçeveler bütünüyle maskelenir.
  Gölge DOM alanı maskelenmezse doğrulama bunu yakalayamaz (kutusu listelenmediği için) — gerçek Pega ekranında
  ayrıca incelenmelidir.
