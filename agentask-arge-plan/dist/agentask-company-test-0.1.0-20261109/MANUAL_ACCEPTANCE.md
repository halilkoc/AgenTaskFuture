# Tek toplu manuel kabul

Her maddeyi **Geçti / Kaldı / Yapılamadı** ve varsa Destek numarasıyla işaretleyin.

## Bölüm S — Şirket ortamı
Ön koşul: `doctor.ps1` HATA vermiyor; Pega test adresi ve test kaydı hazır.

| # | Adım | Beklenen |
|---|---|---|
| S1 | `/` adresini açın | Giriş ekranı. Yanlış parolada genel hata, 5 denemede kilit |
| S2 | Admin ile girin; **Çıkış** deyin; tekrar girin | Oturum kapanır, yeniden girilir |
| S3 | `/prototype/designer` → **Yeni akış** → **Gerçek oturum** → **Yeni oturum aç** → **Uygulamayı oturumda aç** | Pega açılır; girişi açılan pencerede **siz** yaparsınız (SSO/MFA dahil) |
| S4 | Gerçek bir metin alanı için **Alan doldur** → **Ekrandaki alanları listele** / **Tarayıcıda kendim seçeyim** | Alan tek bulunur; Pega'da değer değişmez |
| S5 | **Bilgi oku** ve sonraki **Alan doldur**da **Önceki adımın çıktısı** | Kaydedilir |
| S6 | Standart veya özel liste için **Seçim yap** | Seçenekler okunur. Yazarak arama yapan alanda açık “desteklenmiyor” |
| S7 | **Ekrana geç**; hedef ekranda **Ekranı tanıt** | Her ekran “tanıtıldı” |
| S8 | **Taslağı kaydet**; sayfayı yenileyin; **Kayıtlı taslakları göster** → **Aç** | Değerler, ekranlar ve onay durumları aynı |
| S9 | Dört onay → **Onayla** → **Gerçek dene** → **Sonucu onayla** | “Sistem doğrulaması: BAŞARILI” |
| S10 | **Yeni oturum testi** | “Elle giriş bekleniyor”; girişsiz **Giriş yaptım, devam et** işlem başlatmaz |
| S11 | Yeni pencerede girin, ekranı açın, **Giriş yaptım, devam et** | Test başarılı. **Vazgeç** de ayrıca denenir: sonuç yazılmaz |
| S12 | **Onayla (yayıncı)** → **Yayımla** | MongoDB'de etkin yayın |
| S13 | İşlem Asistanı → **Hazır işlemlerden seç** → **Planı göster** → **Başlat** | Başarılı; Pega'da doğru alan |
| S14 | Yanlış ekranda başlatın | İşlem yapılmaz; neden ve Destek numarası görünür |
| S15 | Beklenmeyen açılır pencere varken başlatın | Durur; pencere otomatik kapatılmaz |
| S16 | Çalışma sırasında **Durdur** | “kullanıcı tarafından durduruldu” |
| S17 | (Onaylı işlem dosyası varsa) test kaydında **Onaylı işlem** | Etki onayı ister; sonuç kanıtla doğrulanır; mükerrer kayıt yok |
| S18 | `/runs` ve konsol logları | Ad, durum, neden, Destek numarası; logda parola, cookie, alan değeri yok |
| S19 | (Açıksa) model ve S3 | Yalnız bu adımla kurum bağlantısı kabul edilir |

Kritik kural: bir madde kaldıysa işlem Pega'da tekrarlanmadan önce sonucu elle kontrol edin.
