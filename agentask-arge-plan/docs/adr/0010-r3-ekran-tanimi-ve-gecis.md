# ADR 0010 — R3: Sürümlü ekran tanımı, ortak ekran doğrulaması ve eski katalog geçişi

Tarih: 2026-11-06 · Durum: kabul edildi (lab kapsamında doğrulandı; gerçek Pega doğrulanmadı)

## Bağlam
- Denetim K5: katalog sözleşmesindeki Screen varlığı yoktu. İşlem yalnız kendi hedefini bularak çalışıyordu.
- Sonuç: benzer ama farklı bir ekranda (aynı adlı "Kefil › Müşteri No" alanı olan) yanlış yere yazma riski vardı.
- Ayrıca `kefil_musteri_no` r1 ekran tanımı olmadan yayımlanmıştı.

## Karar
1. **Ekran tanımı:**
   - `ScreenDef` anlamsal işaretlerden oluşur: zorunlu tekil işaretler, "olmamalı" işaretleri ve mantıksal bölgeler.
   - Kalıcı locator yoktur.
   - Her bölge bir işaretle kanıtlanır; yinelenen bölgede işaret tekil olamaz, sonuç `ambiguous` olur.
2. **Ortak karar çekirdeği:**
   - Tek kural kümesi (`domain/screens.judge`) kullanılır: tekil eşleşme zorunlu, yasak işaret görülürse yanlış
     ekran, kapsam eksikse kanıt yok.
   - Yürütücü, Tasarımcı ve Değişiklikler aynı fonksiyonu çağırır. Model kullanılmaz.
3. **Yürütme:**
   - Plan `assert_screen` ile başlar. Etkin ekran, sonraki her sayfa adımından (okuma, yazma, seçim, sekme, kayıt,
     onaylı aksiyon) önce güncel gözlemle yeniden doğrulanır.
   - Gezinme veya frame değişiminden sonra eski snapshot ve aday kimliği kullanılmaz.
   - Başarısızlıkta sürücü eylemi yapılmaz. Belirsizlikte `PAUSED_AMBIGUOUS`, diğer durumlarda `FAILED` +
     `SCREEN_NOT_RECOGNIZED` döner.
   - Devam ederken `assert_screen` yeniden çalışır (bağlam komutu olarak).
4. **Yayın:**
   - Ekran revizyonları `catalog_screens`'e yazılır.
   - İşlem tanımındaki `screen_ref` içerik hash'i sayesinde onay hash'i ekranı kapsar.
   - Manifest `screens` listesi ekran revizyonlarını pinler ve manifest hash'ine girer.
   - Şema sürümü `catalog-v2` olur.
5. **Eski yayın:**
   - Belgeler silinmez ve değiştirilmez; `ensure_schema` yalnız koleksiyon ve indeks ekler.
   - Ekransız işlem önizlenmez ve çalıştırılmaz (409 `migration_required`).
   - Geçiş insan eliyle yapılır: geçiş taslağı → ekran tanımı → yeni oturum testi → onay → yeni revizyon.
   - Otomatik geçiş veya otomatik yayın yoktur.

## Sonuçlar
- Ekran tanımı olmayan taslak onaylanamaz (`screen_missing`). Mevcut yerel taslakların ekran tanımı eklenmesi
  gerekir.
- Bir işlem tek bir ekrana bağlıdır. Ekran değiştiren aksiyondan sonraki adımlar reddedilir; çok ekranlı işlem
  ileride ele alınacak.
- Yeniden doğrulama her adımda gözlem maliyeti getirir; bu maliyet bilerek kabul edildi.
- Tanıma, gözlenen anlamsal kanıta dayanır. Gerçek Pega ekranlarında işaret seçiminin yeterliliği doğrulanmadı.
