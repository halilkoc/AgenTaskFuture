# Yerel kabul raporu (otomatik)

**Bu rapor kullanıcı kabulü değildir.** GEÇTİ, maddenin otomatik kanıtla doğrulandığını gösterir; lab sonucu Pega kabulü değildir.

- Tarih: 2026-11-13T20:22:36 – 2026-11-13T20:27:33
- Kod özeti (src, tools, tests): `b766a0bc851c8f7b8f288321026e6a7f4cb54b82b52a3c87e763fd6a0280f87f`
- pytest çıkış kodu: **0**; koşunun çıkış kodu: **0**
- Yalıtım: değişiklik yok (.env, var/, kalıcı MongoDB sayıları)
- Paket: `agentask-company-test-0.2.1-20261113.zip` SHA-256 `5cf379642d5dc296c953481afe1024b73755b79ce7c8a033d66259cd16455d95`

| # | Madde | Sonuç | Test | Kanıt | Doğrulanan sonuç / not |
|---|---|---|---|---|---|
| 1 | Yanlış ve doğru parolayla giriş | **GEÇTİ** | 1 | test_company_candidate_flow.py | Giriş sayfasına yönlenir; yanlış parolada genel hata; doğru parolada tasarımcı. |
| 2 | Yeni akış, gerçek oturum, uygulamayı aç | **GEÇTİ** | 1 | test_company_candidate_flow.py | Prototip rozeti ve temsili düğmeler gizli; hedef giriş sayfası oturumda açıldı. |
| 3 | Hedefe giriş ve seçim ekranı | **GEÇTİ** | 1 | test_company_candidate_flow.py | Oturumda hedefe girildi; Kefil bölümündeki alan görünür. |
| 4 | Kefil › Şube sabit Konak tanımı | **GEÇTİ** | 2 | test_company_candidate_flow.py, test_new_designer_choice_mongo.py | Tanım ve kaydetme sonrası sayfadaki tüm alanlar başlangıçla aynı (Şube hâlâ Seçiniz). |
| 5 | Kaydet, yenile, yeniden aç | **GEÇTİ** | 1 | test_company_candidate_flow.py | Yenileme sonrası oturum sürer; 5 adım değerleriyle gelir; eksik yok. |
| 6 | Ekran tanıtma, onay, gerçek deneme | **GEÇTİ** | 1 | test_company_candidate_flow.py | BAŞARILI; sayfa farkı yalnız tanımlı dört alan (Kefil › Şube = Konak dahil). |
| 7 | Elle girişli yeni oturum testi başlar | **GEÇTİ** | 1 | test_company_candidate_flow.py | “Elle giriş bekleniyor”; ayrı doğrulama oturumu açılır. |
| 8 | Girişsiz devam reddedilir | **GEÇTİ** | 1 | test_company_candidate_flow.py | “giriş ekranında”; BAŞARILI yazılmaz, deneme başlamaz. |
| 9 | Giriş sonrası devam | **GEÇTİ** | 1 | test_company_candidate_flow.py | “Yeni oturum testi tamamlandı: BAŞARILI”; doğrulama oturumu kapandı. |
| 10 | Yayıncı onayı ve yayın | **GEÇTİ** | 1 | test_company_candidate_flow.py | Onay geçerli; mesajdaki yayın kimliği API'deki etkin yayınla aynı. |
| 11 | İşlem Asistanı ile çalıştırma | **GEÇTİ** | 1 | test_company_candidate_flow.py | Başarılı; onay kutusu yok; yalnız tanımlı alanlar değişti (Başvuran › Şube boş); destek no /runs ile aynı. |
| 12 | Onaylı işlem: her çalıştırmada tek not | **GEÇTİ** | 1 | test_new_designer_approved_action_mongo.py | Kaydetmede 0, deneme/yeni oturum/Asistan'da birer not; adımın aksiyon özeti güncel özetle aynı. |
| 13 | Yanıt kaybında mükerrer yok | **GEÇTİ** | 4 | test_new_designer_approved_action_mongo.py, test_action_definition_runtime.py | Yanıtı kaybolan çalıştırma Başarılı ve tek yeni not; sonuç doğrulanamazsa tekrar yok. |
| 14 | Çok ekranlı başvuru tasarımdan Asistan'a | **GEÇTİ** | 1 | test_wizard_acceptance_mongo.py | Kayıt bağlamı kontrolü geçiş tanımında; rota iki ekran; tutar yazıldı; her çalıştırmada tek geçiş. |
| 15 | Yanlış vaka ekranında durma | **GEÇTİ** | 1 | test_wizard_acceptance_mongo.py | C-2001-B açılınca Duraklatıldı; tutar boş; destek no görünür; doğru vakada yeniden çalıştı. |
| 16 | Çalışma geçmişi ve çıkış | **GEÇTİ** | 1 | test_wizard_acceptance_mongo.py | Aşama, neden, sonraki adım dolu; teknik ayrıntı kapalı; destek no aynı; çıkış girişe döner. |
| 17 | Aksiyon dosyası değişince yeniden onay | **GEÇTİ** | 4 | test_action_file_mongo.py, test_action_definition_runtime.py | Eski yayın 422 action_changed, manifest değişmedi; yeni özete bağlanıp yeniden test, yayın ve tek not. |
| 18 | Yayın geri ve ileri alma | **GEÇTİ** | 8 | test_release_activation_ui.py, test_release_activation.py | Yayıncı dışı 403; kısa gerekçe reddi; geri ve ileri alma; iki yayın korunur; iki etkinleştirme kaydı. |
| 19 | Okunan değer işleme ve bileşene | **GEÇTİ** | 3 | test_output_binding_mongo.py, test_executor.py::test_empty_prior_output_stops_without_writing | Okunan değer tek gönderimle kaydedildi; boş okumada adım durdu, kayıt yok. |
| 20 | Bağlantı ve seçimle geçiş | **GEÇTİ** | 7 | test_transition_triggers_mongo.py, test_transition_triggers.py | Hedef alan yazıldı; aynı adlı bağlantıda tıklama yok, sayfa aynı kaldı. |
| 21 | Kayıt bul, satırdan aç, bağlam | **GEÇTİ** | 7 | test_record_flow_mongo.py, test_record_runtime.py | Doğru kaydın detayı yazıldı; yalnız bulunan satır değişti; yinelenen/yok/yanlış kayıtta yazma yok. |
| 22 | Onay kutusu ve seçenek grubu | **GEÇTİ** | 26 | test_controls_flow_mongo.py, test_controls_runtime.py | Yalnız Başvuru değişti, Kefil aynı; ikinci çalıştırmada kutu ve radyoda 0 yeni tıklama. |
| 23 | Öneri alanı doğru/yok/iki eşleşme | **GEÇTİ** | 26 | test_controls_flow_mongo.py, test_controls_runtime.py | Tam eşleşme ve gerçek değer doğrulandı; seçim kaybolunca Belirsiz, iki eşleşmede Başarısız; tekrar yok. |
| 24 | Çoklu seçim küme farkı | **GEÇTİ** | 19 | test_multi_date_file_flow_mongo.py, test_multi_date_file_runtime.py | Alandaki küme birebir istenen küme; yalnız fark uygulandı; eksik/devre dışı üyede 0 değişiklik. |
| 25 | Tarih alanları | **GEÇTİ** | 19 | test_multi_date_file_flow_mongo.py, test_multi_date_file_runtime.py | type=date ISO yazıldı; 31.02 tasarımda reddedildi ve alana yazılmadı; çeviren uygulama başarısız. |
| 26 | Dosya yükleme | **GEÇTİ** | 37 | test_multi_date_file_flow_mongo.py, test_multi_date_file_runtime.py, test_artifacts.py | Ad/tür/boyut doğru, tek gönderim; içerik uyuşmayan dosya alınmadı; belirsizde tekrar yok. |
| 27 | Beklenen pencere ve isteğe bağlı modal | **GEÇTİ** | 18 | test_window_modal_flow_mongo.py, test_window_modal_runtime.py | Pencerede yazıldı, ana ekran doğrulandı, açık pencere yok; beklenmeyen/çift pencere ve farklı modal durdu. |
| 28 | Paket içeriği ve temiz kurulum | **GEÇTİ** | 1 | paket denetimi | Özetler uyuşuyor; yasak yol yok; wheel kaynakla aynı; temiz ortamda kurulum, --check-config, --doctor. |

## Paket denetimi

- yasak_yol: 0
- ozet_uyusmayan: 0
- wheel_kaynak_farki: 0
- venv: çıkış 0
- kurulum: çıkış 0
- check_config: çıkış 0
- doctor: çıkış 0

## Ön koşullar

- mongod: var
- gecici_port: bağlanabilir
- port_8000: boş (kullanılmaz)
- port_8100: boş (kullanılmaz)
- port_8101: boş (kullanılmaz)
- port_27017: dolu (kullanılmaz, dokunulmaz)
- chromium: 156.0.8078.4

## Size kalan insan kontrolleri

- Ekranların anlaşılırlığı, metinlerin ve akışın analist için uygunluğu.
- Görünür tarayıcıda (BROWSER_HEADLESS=false) pencerelerin açılışı ve elle giriş deneyimi.
- Windows'ta install.ps1, start.ps1, doctor.ps1, hash-admin.ps1 ve Windows wheel kurulumu.
- Gerçek Pega/SSO, kurumsal MongoDB/TLS, kurum modeli, S3 ve log aktarımı (MANUAL_ACCEPTANCE.md S0–S25).

### Maddeye özel notlar

- Madde 1: Ekranın anlaşılırlığı ve metinlerin yerindeliği insan değerlendirmesidir.
- Madde 2: Testler görünmez tarayıcıda çalışır; görünür pencerenin açılışı elle görülmedi.
- Madde 7: Testler görünmez tarayıcıda çalışır; görünür pencerenin açılışı elle görülmedi.
- Madde 16: Ekranın anlaşılırlığı ve metinlerin yerindeliği insan değerlendirmesidir.
- Madde 27: Testler görünmez tarayıcıda çalışır; görünür pencerenin açılışı elle görülmedi.
- Madde 28: Windows .ps1 betikleri ve Windows wheel kurulumu yalnız Windows'ta denenebilir.
