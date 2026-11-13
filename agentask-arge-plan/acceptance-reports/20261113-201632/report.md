# Yerel kabul raporu (otomatik)

**Bu rapor kullanıcı kabulü değildir.** GEÇTİ, maddenin otomatik kanıtla doğrulandığını gösterir; lab sonucu Pega kabulü değildir.

- Tarih: 2026-11-13T20:16:33 – 2026-11-13T20:21:45
- Kod özeti (src, tools, tests): `b9dab9923554bf793f69c78df729252c99cc53284482e256f1245282564b0f6d`
- pytest çıkış kodu: **1**; koşunun çıkış kodu: **1**
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
| 13 | Yanıt kaybında mükerrer yok | **KALDI** | 4 | test_new_designer_approved_action_mongo.py, test_action_definition_runtime.py | Yanıtı kaybolan çalıştırma Başarılı ve tek yeni not; sonuç doğrulanamazsa tekrar yok. |
| 14 | Çok ekranlı başvuru tasarımdan Asistan'a | **GEÇTİ** | 1 | test_wizard_acceptance_mongo.py | Kayıt bağlamı kontrolü geçiş tanımında; rota iki ekran; tutar yazıldı; her çalıştırmada tek geçiş. |
| 15 | Yanlış vaka ekranında durma | **GEÇTİ** | 1 | test_wizard_acceptance_mongo.py | C-2001-B açılınca Duraklatıldı; tutar boş; destek no görünür; doğru vakada yeniden çalıştı. |
| 16 | Çalışma geçmişi ve çıkış | **GEÇTİ** | 1 | test_wizard_acceptance_mongo.py | Aşama, neden, sonraki adım dolu; teknik ayrıntı kapalı; destek no aynı; çıkış girişe döner. |
| 17 | Aksiyon dosyası değişince yeniden onay | **KALDI** | 4 | test_action_file_mongo.py, test_action_definition_runtime.py | Eski yayın 422 action_changed, manifest değişmedi; yeni özete bağlanıp yeniden test, yayın ve tek not. |
| 18 | Yayın geri ve ileri alma | **GEÇTİ** | 8 | test_release_activation_ui.py, test_release_activation.py | Yayıncı dışı 403; kısa gerekçe reddi; geri ve ileri alma; iki yayın korunur; iki etkinleştirme kaydı. |
| 19 | Okunan değer işleme ve bileşene | **KALDI** | 3 | test_output_binding_mongo.py, test_executor.py::test_empty_prior_output_stops_without_writing | Okunan değer tek gönderimle kaydedildi; boş okumada adım durdu, kayıt yok. |
| 20 | Bağlantı ve seçimle geçiş | **KALDI** | 7 | test_transition_triggers_mongo.py, test_transition_triggers.py | Hedef alan yazıldı; aynı adlı bağlantıda tıklama yok, sayfa aynı kaldı. |
| 21 | Kayıt bul, satırdan aç, bağlam | **KALDI** | 7 | test_record_flow_mongo.py, test_record_runtime.py | Doğru kaydın detayı yazıldı; yalnız bulunan satır değişti; yinelenen/yok/yanlış kayıtta yazma yok. |
| 22 | Onay kutusu ve seçenek grubu | **KALDI** | 26 | test_controls_flow_mongo.py, test_controls_runtime.py | Yalnız Başvuru değişti, Kefil aynı; ikinci çalıştırmada kutu ve radyoda 0 yeni tıklama. |
| 23 | Öneri alanı doğru/yok/iki eşleşme | **KALDI** | 26 | test_controls_flow_mongo.py, test_controls_runtime.py | Tam eşleşme ve gerçek değer doğrulandı; seçim kaybolunca Belirsiz, iki eşleşmede Başarısız; tekrar yok. |
| 24 | Çoklu seçim küme farkı | **KALDI** | 19 | test_multi_date_file_flow_mongo.py, test_multi_date_file_runtime.py | Alandaki küme birebir istenen küme; yalnız fark uygulandı; eksik/devre dışı üyede 0 değişiklik. |
| 25 | Tarih alanları | **KALDI** | 19 | test_multi_date_file_flow_mongo.py, test_multi_date_file_runtime.py | type=date ISO yazıldı; 31.02 tasarımda reddedildi ve alana yazılmadı; çeviren uygulama başarısız. |
| 26 | Dosya yükleme | **KALDI** | 37 | test_multi_date_file_flow_mongo.py, test_multi_date_file_runtime.py, test_artifacts.py | Ad/tür/boyut doğru, tek gönderim; içerik uyuşmayan dosya alınmadı; belirsizde tekrar yok. |
| 27 | Beklenen pencere ve isteğe bağlı modal | **KALDI** | 18 | test_window_modal_flow_mongo.py, test_window_modal_runtime.py | Pencerede yazıldı, ana ekran doğrulandı, açık pencere yok; beklenmeyen/çift pencere ve farklı modal durdu. |
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

## Başarısız testler

- `tests/integration/browser/test_action_definition_runtime.py::test_definition_changed_after_planning_is_not_dispatched`
- `tests/integration/browser/test_action_definition_runtime.py::test_session_lost_text_pauses_before_action`
- `tests/integration/browser/test_action_definition_runtime.py::test_unknown_outcome_without_reconcile_is_safe_and_not_a_crash`
- `tests/integration/browser/test_controls_runtime.py::test_already_in_state_makes_no_click`
- `tests/integration/browser/test_controls_runtime.py::test_app_reverting_checkbox_is_single_send_and_never_success`
- `tests/integration/browser/test_controls_runtime.py::test_aria_checkbox`
- `tests/integration/browser/test_controls_runtime.py::test_aria_radiogroup`
- `tests/integration/browser/test_controls_runtime.py::test_autocomplete_already_selected_does_not_search`
- `tests/integration/browser/test_controls_runtime.py::test_autocomplete_delayed_redrawn_exact_pick`
- `tests/integration/browser/test_controls_runtime.py::test_autocomplete_label_right_value_wrong_is_not_success`
- `tests/integration/browser/test_controls_runtime.py::test_autocomplete_lost_selection_is_not_reported_as_restored`
- `tests/integration/browser/test_controls_runtime.py::test_autocomplete_no_exact_match_restores_and_says_so[Ankara]`
- `tests/integration/browser/test_controls_runtime.py::test_autocomplete_no_exact_match_restores_and_says_so[Yok B\xf6yle]`
- `tests/integration/browser/test_controls_runtime.py::test_autocomplete_no_exact_match_restores_and_says_so[\xc7ift \u015eube]`
- `tests/integration/browser/test_controls_runtime.py::test_autocomplete_plain_input_when_declared`
- `tests/integration/browser/test_controls_runtime.py::test_bad_radio_option_stops_without_change[K\u0131s\u0131tl\u0131-Kapal\u0131]`
- `tests/integration/browser/test_controls_runtime.py::test_bad_radio_option_stops_without_change[Teslimat-Posta]`
- `tests/integration/browser/test_controls_runtime.py::test_bad_radio_option_stops_without_change[Yinelenen-Ayn\u0131]`
- `tests/integration/browser/test_controls_runtime.py::test_checkbox_behind_modal_is_not_changed`
- `tests/integration/browser/test_controls_runtime.py::test_checkbox_same_label_is_separated_by_section`
- `tests/integration/browser/test_controls_runtime.py::test_checkbox_without_section_is_ambiguous_and_untouched`
- `tests/integration/browser/test_controls_runtime.py::test_combobox_input_without_declaration_is_rejected`
- `tests/integration/browser/test_controls_runtime.py::test_disabled_checkbox_is_not_changed`
- `tests/integration/browser/test_controls_runtime.py::test_hidden_checkbox_is_not_changed`
- `tests/integration/browser/test_controls_runtime.py::test_radio_groups_with_same_name_are_separated`
- `tests/integration/browser/test_controls_runtime.py::test_radio_second_time_makes_no_click`
- `tests/integration/browser/test_controls_runtime.py::test_uncheck_is_verified`
- `tests/integration/browser/test_controls_runtime.py::test_visually_hidden_input_goes_through_its_label`
- `tests/integration/browser/test_executor.py::test_empty_prior_output_stops_without_writing`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_another_users_file_is_not_sent`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_app_changing_the_date_is_failure`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_aria_multiselect_applies_only_the_difference`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_bad_member_stops_before_any_change[Kapal\u0131 Se\xe7enek]`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_bad_member_stops_before_any_change[Yok]`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_disallowed_type_is_not_sent`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_exact_set_replaces_current_selection`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_invalid_date_is_never_written[1.2.2026]`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_invalid_date_is_never_written[31.02.2026]`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_invalid_date_is_never_written[yar\u0131n]`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_native_date_is_written_iso_and_verified`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_readonly_calendar_field_is_not_forced`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_same_set_in_any_order_makes_no_change`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_single_select_command_still_rejects_multi`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_text_date_uses_declared_format`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_uncertain_upload_is_not_resent_on_resume`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_upload_sends_once_with_original_name`
- `tests/integration/browser/test_multi_date_file_runtime.py::test_visually_hidden_file_input_is_supported`
- `tests/integration/browser/test_record_runtime.py::test_duplicate_key_pauses`
- `tests/integration/browser/test_record_runtime.py::test_missing_record_writes_nothing`
- `tests/integration/browser/test_record_runtime.py::test_only_found_row_is_written`
- `tests/integration/browser/test_record_runtime.py::test_paged_search_with_custom_next_label`
- `tests/integration/browser/test_record_runtime.py::test_row_order_change_does_not_change_target`
- `tests/integration/browser/test_record_runtime.py::test_row_step_without_found_record_is_refused`
- `tests/integration/browser/test_transition_triggers.py::test_already_selected_does_not_claim_transition`
- `tests/integration/browser/test_transition_triggers.py::test_choice_that_does_not_navigate_times_out_without_reselecting`
- `tests/integration/browser/test_transition_triggers.py::test_choice_trigger_reaches_target_once`
- `tests/integration/browser/test_transition_triggers.py::test_duplicate_link_is_not_clicked`
- `tests/integration/browser/test_transition_triggers.py::test_link_trigger_reaches_target`
- `tests/integration/browser/test_window_modal_runtime.py::test_application_closes_window_itself`
- `tests/integration/browser/test_window_modal_runtime.py::test_declared_other_origin_is_accepted`
- `tests/integration/browser/test_window_modal_runtime.py::test_different_text_or_two_dialogs_stop[other]`
- `tests/integration/browser/test_window_modal_runtime.py::test_different_text_or_two_dialogs_stop[two]`
- `tests/integration/browser/test_window_modal_runtime.py::test_expected_window_is_used_and_main_screen_reverified`
- `tests/integration/browser/test_window_modal_runtime.py::test_extra_window_while_working_stops`
- `tests/integration/browser/test_window_modal_runtime.py::test_multiple_or_missing_window_stops[Pencere A\xe7maz]`
- `tests/integration/browser/test_window_modal_runtime.py::test_multiple_or_missing_window_stops[\u0130ki Pencere]`
- `tests/integration/browser/test_window_modal_runtime.py::test_optional_dialog_absent_causes_no_wait_or_failure`
- `tests/integration/browser/test_window_modal_runtime.py::test_optional_dialog_appears_and_defined_button_is_used`
- `tests/integration/browser/test_window_modal_runtime.py::test_undeclared_dialog_stops`
- `tests/integration/browser/test_window_modal_runtime.py::test_unexpected_window_still_stops_without_declaration`
- `tests/integration/browser/test_window_modal_runtime.py::test_window_closing_early_is_unknown_not_success`
- `tests/integration/browser/test_window_modal_runtime.py::test_window_not_closing_by_itself_stops`
- `tests/integration/browser/test_window_modal_runtime.py::test_wrong_origin_is_not_adopted`
- `tests/integration/browser/test_window_modal_runtime.py::test_wrong_screen_in_window_writes_nothing`

Teşhis ve ekran görüntüleri: `failures/`.
