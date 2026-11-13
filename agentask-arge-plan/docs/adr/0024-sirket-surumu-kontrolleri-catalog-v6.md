# ADR 0024 — Şirket sürümü: aksiyon pinleme, yeni kontroller, pencere ve catalog-v6

**Durum:** Kabul edildi (2026-11-09; kullanıcı kararları K1–K5).

## Bağlam
Şirket testi için tek ve kapsamı tam bir sürüm gerekiyordu. Mevcut yürütücü korunarak onaylı aksiyon değişimi, yayın geri alma,
veri akışı, geçişler, kayıt, yeni kontroller ve pencere davranışları eklendi. Paralel yürütücü yazılmadı.

## Kararlar
- **K1 Aksiyon pinleme:** adım, aksiyonun davranış özetine (`action_hash`) ve uygulamaya bağlanır. Dosya değişirse eski yayın
  çalışmaz; yeniden test ve onay gerekir. Eski yayın ve kanıtı değişmez.
- **K2 Yeni pencere:** yalnız analistin tanımladığı tek pencere (`window=new`) etkin sayfa olur. Kaynak ekran, hedef adres, hedef
  ekran ve dönüş doğrulanır. Beklenmeyen veya birden fazla pencerede işlem durur. İç içe pencere yoktur.
- **K3 Geri alma:** yalnız yayıncı, zorunlu gerekçeyle; hedef yayın güncel aksiyonlarla uyumlu olmalı. Süren çalışmalar kendi
  planında kalır.
- **K4 Dosya:** kaynak yalnız yetkili depodur; yol parametresi yoktur. Sahiplik, boyut, tür (içerik imzası dahil), süre ve bütünlük
  gönderimden hemen önce doğrulanır. Sonuç belirsizse yeniden yükleme yapılmaz.
- **K5 Çoklu seçim:** “tam olarak bu küme”. Üyeler değişiklikten önce doğrulanır, yalnız fark uygulanır; kısmi veya belirsiz sonuç
  başarı değildir.
- **Öneri alanı:** arama yazmak ekranı değiştirdiği için her zaman korumalı gönderimdir. Tam eşleşme yoksa eski değer geri yazılır ve
  okunarak doğrulanır; “değişiklik olmadı” iddiası yalnız bu kapsamdadır, uygulamanın arka plandaki sorgularını kapsamaz.
- **Tarih:** beyan edilen biçim ve `type=date`. **Takvim açılır penceresi eklenmedi;** Pega DOM'u görülmeden tahminle yazılmaz.
- **İsteğe bağlı pencere:** yalnız veri değiştirmediği beyan edilen pencere; ad + metin tam eşleşmesiyle tanımlı düğme.
- **catalog-v6:** yeni alanlar yalnız doluysa kanonik içeriğe girer; v1–v5 tanımları ve hash'leri değişmez.

## Sonuçlar ve sınırlar
- Yeni pencerede duran çalışma sürdürülemez: pencere insan kararına bırakılır, kullanıcı kapatıp yeniden başlatır.
- İsteğe bağlı pencere tanımları birleşik planda bütün adımlar için geçerlidir.
- Tablo anahtarı yalnız ilk sütunda aranır. ARIA çoklu listede Ctrl gerektiren bileşen doğrulanmadı.
- Tüm kanıtlar lab ve geçici MongoDB içindir; Pega DOM'u şirkette doğrulanacaktır (`MANUAL_ACCEPTANCE.md`).
