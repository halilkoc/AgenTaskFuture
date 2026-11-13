# Tek toplu yerel kabul (lab)

Gerçek `.env` değişmez; admin kipi yalnız bu terminal için verilir. Lab sonucu Pega kabulü değildir. Mevcut `dev.user` taslakları admin
kullanıcısına görünmez; kayıplı değildir, normal `.venv/bin/agentask` ile yine görünür.

**Başlatma** (Mongo açık, proje klasöründe):
```
.venv/bin/agentask-lab                      # terminal 1
HASH=$(.venv/bin/agentask --hash-admin-password)   # terminal 2: en az 12 karakterli parola, iki kez
AUTH_MODE=local_admin DEV_AUTH_ENABLED=false ADMIN_USERNAME=admin ADMIN_PASSWORD_HASH="$HASH" .venv/bin/agentask
```
Adres: http://127.0.0.1:8000/prototype/designer

## Kabul alanıyla başlatma (mevcut verileri korumak için tercih edin)
Yukarıdaki komut `.env` ayarlarını kullandığından yayınlar `agentask_arge`'a, taslak ve kayıtlar `var/drafts`, `var/runs` altına yazılır. Aşağıdaki ayarlar `.env`'yi değiştirmez ve yalnız o terminalde geçerlidir; terminal kapanınca yeniden verilir. Kabul verileri (`agentask_kabul_20261109`, `var/kabul-20261109/`) kalıcıdır, kaldığınız yerden sürer.

Önce 8000, 8100, 8101 portlarını kontrol edin; doluysa ikinci kopyayı başlatmayın: `lsof -nP -iTCP:8000,8100,8101 -sTCP:LISTEN`

**Terminal 1**
```zsh
cd /Users/halilkoc/Documents/GitHub/AgenTaskFuture/agentask-arge-plan
.venv/bin/agentask-lab
```
**Terminal 2**
```zsh
cd /Users/halilkoc/Documents/GitHub/AgenTaskFuture/agentask-arge-plan
K=var/kabul-20261109; mkdir -p $K/drafts $K/runs $K/artifacts
HASH=$(.venv/bin/agentask --hash-admin-password)   # parola sorulur; hiçbir dosyaya yazmayın
export AUTH_MODE=local_admin DEV_AUTH_ENABLED=false ADMIN_USERNAME=admin ADMIN_PASSWORD_HASH="$HASH"
export MONGO_DATABASE=agentask_kabul_20261109 DRAFT_DIRECTORY=$K/drafts RUN_DIRECTORY=$K/runs ARTIFACT_DIRECTORY=$K/artifacts
.venv/bin/agentask
```
Taslaklar `admin` kullanıcısına aittir; kullanıcı adını değiştirmeyin. Parolayı her başlatmada yeniden belirleyebilirsiniz. Oturumlar bellektedir: yeniden giriş ve yeni tarayıcı oturumu gerekir. Deney uygulamasının durumu (not sayıları, `/__lab` senaryoları) da yeniden başlayınca sıfırlanır; kaydedilmiş taslak, yayın ve çalışma kayıtları korunur.

Madde 17 için ek olarak `APPROVED_ACTION_SET=file` ve `APPROVED_ACTIONS_FILE=$K/actions.json` gerekir; bu ayarlar yalnız o maddede verilir.

| # | Yapılacak | Beklenen |
|---|---|---|
| 1 | Yanlış parolayla, sonra doğru parolayla gir (`admin`) | Genel hata; sonra Akış Tasarımcısı |
| 2 | **Yeni akış**, ad `Kefil şubesini seç` → **Gerçek oturum** → **Yeni oturum aç** → **Uygulamayı oturumda aç** | “Prototip” etiketi ve temsili düğmeler yok; lab giriş sayfası açılır |
| 3 | Açılan pencerede `ayse` ile **Giriş yap** → **Seçim senaryoları** | `/pages/selections` |
| 4 | **Seçim yap** → **Ekrandaki alanları listele** → **Kefil › Şube** → **Sabit seçenek**: Konak → **Yalnız bu alanın seçimini değiştirir** | Pencerede Şube hâlâ “Seçiniz” |
| 5 | **Taslağı kaydet**; sayfayı yenile; **Kayıtlı taslakları göster** → **Aç** | Adım aynı, “eksik” yok; AgenTask oturumu sürüyor |
| 6 | **Ekranı tanıt** → **Bu işaretlerle ekranı tanıt**; dört kutu → **Onayla**; etki kutusu → **Gerçek dene** → **Sonucu onayla** | BAŞARILI; yalnız Kefil › Şube = Konak |
| 7 | Başlangıç yolu `/pages/selections`, **Girişi yeni pencerede elle yapacağım** → **Yeni oturum testi** | “Elle giriş bekleniyor”, yeni pencere |
| 8 | Giriş yapmadan **Giriş yaptım, devam et** | “giriş ekranında”; işlem yok |
| 9 | Yeni pencerede `ayse` ile gir → **Giriş yaptım, devam et** | “Yeni oturum testi tamamlandı: BAŞARILI” |
| 10 | **Onayla (yayıncı)** → **Yayımla** | “Yayımlandı ve etkin” |
| 11 | `/assistant` → **Bu oturumu kullan** → **Uygulamayı oturumda aç** → pencerede **Seçim senaryoları** → **Hazır işlemlerden seç** → **Kefil şubesini seç** → **Planı göster** → **Başlat** | “Başarılı”, Destek numarası; onay kutusu yok; Şube = Konak, Başvuran boş |
| 12 | Yeni akış, `/pages/note-form`: **Alan doldur** (Not, sabit metin) + **Onaylı işlem** “Vakaya not ekle” (aynı metin); deneme → test → yayın → Asistan'da onay kutusuyla **Başlat** | Her çalıştırmada tek not |
| 13 | `/__lab` → `lose_next_commit_response` açıp Asistan'dan yeniden çalıştır | “Başarılı”; tek yeni not (mükerrer yok) |
| 14 | **R4:** `/wizard/C-2001` üzerinde **Bilgi oku** (Vaka No), **Alan doldur** (Müşteri No), **Ekrana geç** (Devam, ekran adı `Teminat bilgileri`, “yalnız ekran…” kutusu; “Açılan ekranda kayıt doğrulansın mı?”: Beklenen değer **Sabit değer**, Alanın etiketi `Vaka No`, Bölüm `Vaka`, Sabit değer `C-2001`), **Alan doldur** (Teminat Tutarı). Kaydet; ilk ekranı tanıt; pencerede **Devam**'a bas, ikinci ekranı tanıt; test → yayın → Asistan | Rota iki ekran; tutar yazılır |
| 15 | `/__lab` → `wizard_target=other_case`, Asistan'dan çalıştır; sonra `collateral` yap | İşlem yapılmaz; neden ve Destek numarası |
| 16 | `/runs` → başarısız satır → **Ayrıntı**; **Çıkış** | Aşama, neden, sonraki adım; teknik ayrıntı kapalı; giriş ekranına döner |
| 17 | Mevcut bir onaylı işlemi yayımla; aksiyon dosyasında aynı id ile başarı metnini değiştir, yeniden başlat; Asistan'dan dene; taslağı aç, kaydet, yeniden test et | Eski yayın çalışmaz, neden açık; yeni test ve onay sonrası çalışır |
| 18 | `/catalogs` → önceki yayın → gerekçe yaz → **Bu yayını etkinleştir**; sonra ileri al | Etkin yayın değişir; kayıtlar ve geçmiş korunur; kısa gerekçe reddedilir |
| 19 | **Bilgi oku** çıktısını **Onaylı işlem** parametresine ve yayımlanmış bileşen girdisine bağla | Tek gönderim; boş okumada 0 gönderim |
| 20 | `/pages/transitions`: bağlantıyla geçiş; seçimle geçiş (“Bu seçim başka bir ekrana geçirir”) | Doğru ekran; aynı adlı iki bağlantıda durur |
| 21 | `/pages/records`: **Kayıt bul** (sayfalı, anahtar R-1005) → **Ekrana geç** satırdaki **Aç** (“Bulunan kaydın satırında”) → bağlam kontrolü | Doğru kayıt; bulunamayan anahtarda durur; yanlış kayıtta 0 yazma |
| 22 | `/pages/controls`: **İşaretle / kaldır** (Başvuru › Onaylıyorum); **Seçim yap** (Başvuru › Teslimat: Şube) | Yalnız Başvuru değişir (Kefil değil); ikinci çalıştırmada 0 tıklama |
| 23 | `/pages/controls`: **Seçim yap** → “Bu alan yazınca öneri açıyor” → Arama › Şehir → örnek arama `Ank` → her çalıştırmada sor. Asistan'da sırayla `Ankara Merkez`, `Yok`, `Çift Şube` | Yalnız ilki başarılı; diğerlerinde alan eski değerine döner, “seçenek” hatası görülür |
| 24 | `/pages/controls`: **Çoklu seçim** (Etiketler); Alfa+Gama; sonra Asistan'da farklı küme | Tam küme kalır; Beta kaldırılır; “Kapalı Seçenek” gerektiğinde hiçbir değişiklik yok |
| 25 | `/pages/controls`: **Alan doldur** → “Bu bir tarih alanı” (Başlangıç; `09.11.2026`); Bitiş alanına `31.02.2026` | Başlangıç doğru tarih; geçersiz tarih kaydedilemez/yazılmaz |
| 26 | `/pages/controls`: **Dosya yükle** (Belge, PDF, durum mesajı `Belge alındı`); Asistan'da PDF yükle, sonra PDF olmayan bir dosya dene | PDF tek kez gönderilir, Belge alındı; yanlış tür kabul edilmez |
| 27 | `/pages/windows`: **Ekrana geç** (Pencere Aç, “Bu düğme yeni pencere açıyor”), tarayıcıda düğmeye bas, **Bu pencerede tasarla**, Pencere Notu, **Ana pencereye dön**. `/pages/optional-modal?mode=info`: panelde pencere tanımı (Bilgilendirme, “Kaydınız işleniyor”, Tamam) | Pencerede yazılır, ana ekran doğrulanır; **İki Pencere** durur. Modal çıkınca Tamam'a basılır; `mode=other` durur; modal yoksa bekleme olmaz |
| 28 | Paketi ayrı klasöre aç; Mac'te temiz sanal ortam kur; `--check-config`, `--doctor`; içerikte `.env` ve `var/` ara | `.env`, `var/`, oturum yok; `HATA` yok. **Windows betikleri bu adımda denenmez** |
