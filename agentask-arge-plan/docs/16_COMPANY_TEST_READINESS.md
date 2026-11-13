# Şirket testi aday sürümü — hazırlık değerlendirmesi (2026-11-09)

Tek uygulama, tek kullanıcı, yerel çalıştırma içindir. **Yerelde geçmek, gerçek Pega/SSO/kurum bağlantısı kabulü değildir.**
Kanıt sütunundaki testler 2026-11-09 koşusunda çalıştırıldı (`var/verification/company-candidate-2026-11-09/`).

> **Güncel:** Bu değerlendirme 0.1.0 adayı içindir ve **o paket geçersizdir**. Geçerli paket `agentask-company-test-0.2.1-20261113.zip` (0.2.0 eski aday); S1–S9 kanıtı `var/verification/company-final-2026-11-09/`, plan ve durum `docs/STATUS.md`. Aşağıdaki “Kalan” sütunundaki autocomplete, Kayıt bul ve çıktıdan bileşen girdisi maddeleri 0.2.0'da lab düzeyinde kapatıldı.

## Aşama değerlendirmesi (etiket değil, kod ve test kanıtı)
| Aşama | Değerlendirme | Kanıt | Kalan |
|---|---|---|---|
| A hatalar | Doğrulandı | `test_popups_dynamic`, tam takım | — |
| B alan seçimi | Doğrulandı (lab) | `test_prototype_real_session_ui`, `test_picker` | Pega DOM'u |
| C kalıcı taslak | Doğrulandı; yeniden açma kusurları bu turda düzeltildi | `test_company_candidate_flow` | “Kayıt bul” yok |
| D deneme/yayın | Doğrulandı | `test_new_designer_publish_mongo`, aday akış | Kurumsal Mongo |
| E bileşen | Doğrulandı | `test_components`, `test_new_designer_components_mongo` | Çıktıdan bileşen girdisi yok |
| F Asistan/model | Asistan doğrulandı; model yalnız sahte sunucuyla | `test_assistant*`, `test_llm_adapter` | Gerçek model |
| G depolama | Yerel + sahte S3 | `test_object_store_contract`, `test_evidence` | Kurum S3 |
| H seçim | Doğrulandı (lab); kullanıcı manuel kabulü yok | `test_choice_runtime`, `test_new_designer_choice_mongo` | Autocomplete yok |
| I log/geçmiş | Doğrulandı; kullanıcı lab kontrolü yapıldı | `test_structured_logging`, `test_run_logging`, `test_logging_http` | Kurum log altyapısı |

## Kontrol listesi
| Yetenek | Çalışan davranış | Eksik / desteklenmeyen | Kabul kanıtı |
|---|---|---|---|
| Alan doldurma ve okuma | Anlamsal hedef, değer doğrulama, hassas alan reddi | `contenteditable`, onay kutusu, radyo, dosya, takvim | `test_executor::test_textbox_write…`, aday akış |
| Okuma çıktısını kullanma | Yalnız gerçek okuma; yoksa işlem yapmadan durur | Bileşen girdisi ve onaylı aksiyon parametresi çıktıdan alınamaz | `test_prior_output`, aday akış |
| Standart/özel liste | select, combobox, düğme+liste, açık liste, frame, etiket+değer | Yazarak arama, çoklu seçim, rolsüz liste | `test_choice_runtime` (24) |
| Onaylı işlem ve sonuç | Etki onayı, kanıt, uzlaştırma, kurum JSON dosyası | Arayüzden aksiyon tanımlama yok (K6 kısmi) | `test_new_designer_approved_action_mongo` (yeni), `test_executor::test_lost_response…` |
| Ekran geçişleri | Düğme/sekme, doğrusal rota, tek tetikleme | Dallanma; seçim/bağlantı tetikleyici | `test_multi_screen_runtime`, `test_new_designer_multi_screen_ui` |
| Sürümlü bileşen | Pinli revizyon, açık yükseltme | Bileşen içi düzenleme | `test_components`, `test_component_publishing`, Mongo e2e |
| Dinamik DOM, modal, pencere | Yeniden çözüm, kapsam raporu, modal arkası yok, otomatik kapatma yok | Shadow DOM, erişilemeyen dış frame | `test_popups_dynamic` (17), `test_observer`, `test_resolution` |
| Durdurma, devam, belirsiz sonuç | Tekrar göndermez; okuma/uzlaştırma; devam oynatmaz | Lease/fencing (K3) | `test_executor`, `test_run_logging`, `test_choice_runtime` |
| Taslak, onay, yayın, Asistan | Hash'e bağlı onay, değişmez yayın, pinli çalıştırma | Etkin yayını geri alma düğmesi yok | Aday akış, `test_publish_ui`, Mongo testleri |
| Log, geçmiş, erişim | JSON, korelasyon, redaksiyon, sahiplik | Ayrı denetim deposu yok | Log testleri, `test_admin_auth_http` |
| Geçici admin | Hash, süre, CSRF, sınırlama, dev'e düşmeme | Kurumsal SSO yok; tek admin | `test_admin_login`, `test_admin_auth_http`, aday akış |
| Elle hedef girişi | Bekleme, yeniden doğrulama, süre, vazgeçme, resume | SSO/MFA yerelde denenemez | `test_fresh_manual_login`, aday akış |

## Açık denetim maddeleri
| Madde | Durum | Not |
|---|---|---|
| K1 yeni oturum kotası | Kapandı | Doğrulama oturumu ayrı kota |
| K2 modele hassas veri | Kapandı (sezgisel tespit) | Eksiksiz DLP değildir |
| K3 lease/fencing | **Açık; büyük özellik** | Ayrı runner ile birlikte ele alınmalı |
| K4 kanıt deposu | Kapandı (yerel/sahte S3) | Kurum S3 şirkette |
| K5 Screen / automation_runs | Screen kapandı; **run'lar yerel dosyada** | Tek süreç için yeterli |
| K6 aksiyon kataloğu | Kısmi: kurum JSON dosyası | Arayüzden tanımlama büyük özellik |
| K7 politika/yetki | **Açık; büyük özellik** | Rol düzeyinde; işlem/kayıt kapsamı yok |

**R4 manuel kabulü:** otomatik testler geçiyor (`test_multi_screen_runtime`, `test_r4_multi_screen_ui`), kullanıcı kabulü hâlâ **yapılmadı**;
tek toplu yerel kabule alındı. Eski `/designer` silinmedi: `Kayıt bul` ve ayrıntılı tanımlar için hâlâ gerekli.

## Bu turda bulunup düzeltilenler
Süre aşımında “kullanıcı durdurdu” yazması; gerçek oturumda “Prototip” ve temsili öğeler; yeniden açılan taslakta kayıtlı adımların “eksik” görünmesi;
önceki akışın deneme değerleri/başlangıç yolunun taşınması; eski yayıncı onayının geçerli gibi görünmesi; gerçek oturumda kaydedilemeyecek kaynakların listelenmesi;
“Gerçek Pega değildir” sabit uyarısı; desteklenmeyen zengin metin alanının tasarımda açıklanmaması; yeni tasarımcıda onaylı işlem için uçtan uca test olmaması;
tarayıcı başlatma hatasında yabancı hata metninin loglanması.
