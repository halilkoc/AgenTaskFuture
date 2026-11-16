# Bilinen sınırlar

**Doğrulanmadı (yalnız şirkette yapılabilir):** gerçek Pega ekranları, SSO/MFA ile elle giriş, kurumsal MongoDB ve TLS, kurum modeli,
kurum S3, Windows üzerinde kurulum ve çalışma, kurulu Edge/Chrome uyumu.

**Tarayıcı motoru:** `chromium` (varsayılan) ve `firefox`. Firefox yalnız macOS'ta deney uygulamasıyla denendi; Windows'ta Firefox
kurulumu, çevrimdışı tarayıcı klasörü ve Pega/SSO ile çalışması doğrulanmadı. Firefox'ta kurulu tarayıcı yolu (`BROWSER_EXECUTABLE_PATH`) desteklenmez.
`webkit` reddedilir: yönlendirme denetimini desteklemediği için izinli adres sınırı korunamıyor.

**Kimlik:** geçici tek admin; kurumsal SSO yok; işlem bazlı yetki yok; oturum bellektedir, uygulama yeniden başlayınca yeniden giriş gerekir.

**Lab'da doğrulanan, Pega'da henüz denenmeyen kontroller:** onay kutusu (görsel gizli giriş dahil), seçenek grubu, yazınca öneri açan alan,
çoklu seçim, tarih (metin, maskeli, `type=date`), dosya yükleme, tablo satırı, beklenen yeni pencere, isteğe bağlı pencere. Şirket kabulü: `MANUAL_ACCEPTANCE.md` S0, S20–S25.

**Desteklenmeyen (işlem yapılmadan durur):** yalnız takvimden seçim kabul eden tarih alanı (takvim açılır penceresi, Pega DOM'u görülmeden eklenmedi),
biçimlendirilebilir metin (`contenteditable`), shadow DOM, canvas, ARIA rolü olmayan özel listeler, grup adı olmayan seçenek grubu.
Ctrl ile çoklu seçim isteyen ARIA listeleri doğrulanmadı: sonuç küme olarak okunur, uymazsa işlem başarılı sayılmaz.

**Akış:** rota doğrusaldır; koşullu dallanma yoktur. Tablo anahtarı yalnız ilk sütunda aranır. Aynı anda tek beklenen yeni pencere desteklenir;
yeni pencerede duran çalışma sürdürülemez (pencereyi kapatıp yeniden başlatın). Yeni pencere içinde iç içe pencere yoktur.
Öneri alanında eşleşme yoksa eski metin geri yazılır; görünen metin ve alandaki gerçek değer önceki haliyle aynı değilse sonuç “Belirsiz” olur (0.2.1). “Değişiklik olmadı” bilgisi uygulamanın arka plandaki sorgularını kapsamaz.

Yeni pencere ve engelleyici pencere her adımın başında, yeni pencere ayrıca eylemden hemen önce denetlenir. Bir yazmadan sonra gecikmeyle
açılan pencere, sonraki eylemden önce açılmışsa işlemi durdurur; son adımdan sonra açılan pencere çalışmanın sonucunu değiştirmez.

**Dosya yükleme:** PDF, PNG, JPEG, düz metin; boyut `ARTIFACT_MAX_BYTES` ile sınırlı. Sonuç belirsizse dosya yeniden gönderilmez, kullanıcı uygulamada kontrol eder.

**Onaylı işlem:** yalnız kurum JSON dosyasından; arayüzden yeni aksiyon tanımlanmaz. Veri değiştiren aksiyonda uzlaştırma tanımı zorunludur.
Aksiyonun tanımı değişirse eski yayın çalışmaz; yeniden test ve onay gerekir.

**Çalışma modeli:** tek süreç, tek worker. Çok kullanıcılı çalıştırma, kuyruk, ayrı runner, lease/fencing, OpenShift kapsam dışıdır.
Çalışma kayıtları yerel dosyadadır; ayrı denetim deposu yoktur. Sırlar için `secret_ref` çözümü yoktur.

UI tıklamasıyla exactly-once garantisi verilmez: sonuç belirsizse işlem tekrarlanmaz, kullanıcı uygulamada kontrol eder.
