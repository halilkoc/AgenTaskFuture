# Bilinen sınırlar

**Doğrulanmadı (yalnız şirkette yapılabilir):** gerçek Pega ekranları, SSO/MFA ile elle giriş, kurumsal MongoDB ve TLS, kurum modeli,
kurum S3, Windows üzerinde kurulum ve çalışma, kurulu Edge/Chrome uyumu.

**Kimlik:** geçici tek admin; kurumsal SSO yok; işlem bazlı yetki yok; oturum bellektedir, uygulama yeniden başlayınca yeniden giriş gerekir.

**Desteklenmeyen kontroller (işlem yapılmadan durur):** yazarak arama yapan kutular (autocomplete), çoklu seçim, biçimlendirilebilir metin
(`contenteditable`), onay kutusu ve radyo düğmesi, dosya yükleme, tarih seçici takvim, shadow DOM, canvas, ARIA rolü olmayan özel listeler.
Yeni tasarımcıda “Kayıt bul” yoktur (eski tasarımcıda `/designer` bulunur).

**Akış:** rota doğrusaldır; koşullu dallanma yoktur. Seçimle tetiklenen ekran geçişi onaylı geçiş olarak tanımlanamaz. Tablo satırı kayıt bağlamı yoktur.

**Onaylı işlem:** yalnız kurum JSON dosyasından; arayüzden yeni aksiyon tanımlanmaz. Veri değiştiren aksiyonda uzlaştırma tanımı zorunludur.

**Çalışma modeli:** tek süreç, tek worker. Çok kullanıcılı çalıştırma, kuyruk, ayrı runner, lease/fencing, OpenShift kapsam dışıdır.
Çalışma kayıtları yerel dosyadadır; ayrı denetim deposu yoktur. Sırlar için `secret_ref` çözümü yoktur.

UI tıklamasıyla exactly-once garantisi verilmez: sonuç belirsizse işlem tekrarlanmaz, kullanıcı uygulamada kontrol eder.
