# Geri dönüş

1. Konsolda `Ctrl+C` ile uygulamayı durdurun. Süren çalışma varsa önce **Durdur** deyin; sonucu belirsiz işlemleri Pega'da kontrol edin.
2. Yeni sürüme geçerken eski klasörü silmeyin; ayrı klasöre açın. Geri dönmek için eski klasörde `start.ps1` çalıştırın.
3. `var\` ve `.env` kullanıcı verisidir; paket güncellemesi bunlara dokunmaz. Eski sürüme dönerken `var\` klasörünü yedekleyin
   (yeni sürümün yazdığı kayıtları eski sürüm okumayabilir).
4. Yayınlar MongoDB'de değişmezdir; arayüzde etkin yayını geri alma düğmesi **yoktur**. Bu yüzden teste ayrı `MONGO_DATABASE` kullanın.
   Testi tamamen geri almak için bu veritabanını yetkili kişi kaldırır.
5. Tamamen kaldırma: uygulamayı durdurun, klasörü silin, test veritabanını kaldırın. Sistem ayarı veya servis eklenmez.

Uygulama, Pega'da yapılmış işlemleri geri almaz.
