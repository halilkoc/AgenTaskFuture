# Uygulama denetimi — gereksinim/kanıt (2026-11-05)

Kapsam: CLAUDE.md, docs/00–11, docs/plans, mevcut kod ve testler. Bu denetimde uygulama kodu, test beklentileri ve
docs/10 kutuları **değiştirilmedi**. (Not: `docs/12_RUNNER_AND_INTEGRATION_CHECKLIST.md` aynı numarayı taşıyan ayrı bir belgedir.)

Durum anahtarı: **PASS** (kod + o davranışı doğrulayan, bu denetimde çalıştırılmış test) · **PARTIAL** (bir kısmı
var/doğrulanmış) · **FAIL** (gereksinim karşılanmıyor) · **BLOCKED** (kurum erişimi/bilgisi gerekli) · **NOT_TESTED**
(kod var, davranışı doğrulayan test yok).

---

## 0. Önce: kritik eksikler

| # | Bulgu | Kanıt | Etki |
|---|---|---|---|
| K1 | **Varsayılan yapılandırmayla Katalog Tasarımcısı'nın "Yeni oturum testi" çalışmaz.** `.env.example` `BROWSER_MAX_SESSIONS_PER_USER=1`; ekran bir oturum açık tutarken `DesignerService.fresh_session_test` ikinci oturum açar → `session_limit_reached` (429). E2E testleri bunu `BROWSER_MAX_SESSIONS_PER_USER=2/3` ile geçiyor. | `.env.example:33`; `application/services/designer.py::fresh_session_test` (`self._sessions.open`); `tests/e2e/test_designer_ui.py` fixture override | Yayına giden zorunlu adım varsayılan ayarla manuel olarak tamamlanamaz (geçici çözüm: değeri 2 yapmak). **FAIL** |
| K2 | **Asistan, kullanıcı talebini modele redaksiyonsuz gönderir.** docs/08: "Parola ve secret değerleri model… 'a girmez". Talepte parola yazılırsa (model yolu açıkken) olduğu gibi iç modele gider. `redact_intent` yalnız tasarımcıda kullanılıyor. | `application/services/assistant.py::_model_suggestion` (`json.dumps({"talep": prompt …})`); grep: assistant'ta `redact` yok | Model kapalıyken etkisi yok; açılınca secret sızma riski. **FAIL** |
| K3 | **Run lease/fencing yok; `SESSION_LEASE_SECONDS` hiç kullanılmıyor.** docs/01/03: "Run sahipliği ve lease/fencing sözleşmesi ayrı tutulur", "Lease kaybından sonra yeni dispatch engellenir". Yalnız bellek içi oturum kilidi (tek worker) var. | `config/settings.py` dışında `session_lease_seconds` referansı yok; `fencing` grep sonuçsuz | Tek worker Ar-Ge için yeterli; çok worker/uzak runner güvenli değil. **FAIL** (belgelenmiş sınırlama) |
| K4 | **Kanıt/artefakt deposu yok.** `ARTIFACT_DIRECTORY`, `EVIDENCE_RETENTION_DAYS` kullanılmıyor; `EVIDENCE_SCREENSHOTS_ENABLED` yalnız public config'te gösteriliyor, işlevi yok. ArtifactStore portu yok. | grep: `ArtifactStore` yok; Settings kullanım taraması | Ayar, var olmayan bir özelliği açıp kapatıyormuş gibi görünür. **FAIL** |
| K5 | **Katalog sözleşmesindeki Screen varlığı ve `catalog_screens`/`automation_runs` koleksiyonları yok.** Ekran tanıma kuralları ve mantıksal bölgeler modellenmedi; run'lar yerel dosyada. | grep sonuçsuz; `infrastructure/mongo/catalog_store.py` yalnız 3 koleksiyon | Etki analizi "hangi ekrandayım" bilmez; run'lar Mongo'da değil. **FAIL/PARTIAL** |
| K6 | **Onaylı aksiyonlar katalogda değil, kodda (yalnız lab seti).** Tasarımcı yeni veri değiştiren aksiyon tanımlayamaz; gerçek uygulama için aksiyon eklemek kod değişikliği ister. | `infrastructure/approved_actions/lab.py`; `APPROVED_ACTION_SET` yalnız `none|lab` | Gerçek Pega yolunda katalogla genişleyemez. **PARTIAL** |
| K7 | **Yetki/politika modeli yalnız rol yeteneği.** PolicyPort, işlem bazında yetki referansı ve uygulama/kayıt kapsam kontrolü yok; gerçek kimlik adapteri yok (AUTH_MODE dev|unconfigured). | grep: `PolicyPort` yok; `domain/identity.py` | Production'a hazır değil (BLOCKED: kurum kimlik/yetki sözleşmesi). |

İkincil eksikler: SSE/WS ilerleme yok (yoklama); run durum makinesinde `validating/ready/verifying/needs_clarification`
yok; iş audit olayları (AuditPort) yok; SecretProvider/`secret_ref` çözümü yok; `prior_output` derlenmiyor; tasarımcıda
hedef görüntü kırpması yok; eleman yeniden kullanım önerisi yalnız yerel taslaklardan; metriklerde hazırlama süresi/
insan düzeltme sayısı/token-çağrı sayısı yok; fixture seed/holdout değerlendirmesi yok; `APP_BASE_URL`, `RUNNER_MODE`,
`DRAFT_BACKEND`, `SESSION_SIGNING_KEY`, `DEV_AUTH_ENABLED`, `LLM_CONTEXT_TOKENS`, `LLM_CONTEXT_RESERVE_TOKENS`
yalnız başlangıç doğrulamasında kullanılıyor (çalışma zamanında etkisiz).

Taslak/sahte izi taraması: `src/` altında TODO/FIXME yok; `pass`/`NotImplementedError` yalnız istisna sınıfı gövdeleri ve
`ControlAdapter.supports` soyut metodu. Production kodu `tests/` içindeki sahte depoları (FakeCatalogStore, ScriptedLLM)
import etmiyor. `UnavailableLLM` bilinçli "kapalı" adapteridir (sabit başarı döndürmez, hata fırlatır).

---

## 1. Test çalıştırma sonuçları (bu denetimde)

| Grup | Komut | Exit | Sonuç |
|---|---|---|---|
| Unit | `.venv/bin/pytest -q -rs tests/unit` | 0 | 263 passed, 0 skipped |
| Gerçek tarayıcı entegrasyon | `.venv/bin/pytest -q -rs tests/integration/browser tests/integration/lab` | 0 | 95 passed, 0 skipped |
| API + LLM adapter entegrasyon | `.venv/bin/pytest -q -rs tests/integration/test_{app,cli,sessions_api,observation_api,runs_api,drafts_api,llm_adapter}.py` | 0 | 40 passed |
| MongoDB entegrasyon | `.venv/bin/pytest -q -rs tests/integration/mongo` | 0 | 9 passed (geçici yerel mongod 8.0.34) |
| Ön yüz E2E | `.venv/bin/pytest -q -rs tests/e2e` | 0 | 6 passed (Chromium headless; 3'ü geçici mongod ile) |
| Tamamı | `.venv/bin/pytest -q -rs` | 0 | 413 passed, 0 skipped (`-m browser` 100, `-m mongo` 12 test) |
| Lint | `.venv/bin/ruff check src tests` / `ruff format --check` | 0 / 0 | temiz / 153 dosya formatlı |
| Tip | `.venv/bin/mypy` (strict) | 0 | 93 kaynak dosya, hata yok |

**Test ikamesiyle çalışan ve PASS sayılmayan entegrasyonlar:** LLM adapteri yalnız yerel sahte OpenAI uyumlu sunucuyla
(`tests/integration/test_llm_adapter.py`) ve asistan model yolu `ScriptedLLM` ile test edildi; Pega yerine yerel deney
uygulaması; yayın birim testleri `FakeCatalogStore` ile (Mongo davranışı ayrıca gerçek mongod ile test edildi).
**Çalıştırılamayanlar:** gerçek on-prem model, gerçek Pega/SSO, kurumsal MongoDB (TLS/auth/replica set), headed modda
insan etkileşimi, Firefox/WebKit, uzak runner — erişim/altyapı yok.

---

## 2. Gereksinim–kanıt tablosu

Sütun "Çalıştırıldı": bu denetimdeki koşuda (bölüm 1) çalıştı mı.

### P0 — İskelet ve yapılandırma
| Gereksinim | Uygulama | Test | Çalıştırıldı | Ön yüz | Durum | Eksik/sınırlama |
|---|---|---|---|---|---|---|
| Tek typed Settings, process env > .env, --env-file | `config/settings.py::Settings, load_settings` | `unit/test_settings.py::test_process_environment_overrides_dotenv`, `test_default_env_file…`, `test_explicit_env_file_must_exist` | Evet | — | PASS | Varsayılan .env cwd'den (docs/05 "repo kökü") |
| Boolean/tip/limit doğrulama, sessiz default yok | `Settings` alan tipleri | `test_false_booleans_are_really_false`, `test_invalid_values_are_rejected_not_defaulted` | Evet | — | PASS | — |
| Bilinmeyen dotenv anahtarı red, ilgisiz env yok sayılır | `extra="forbid"` | `test_unknown_key_in_dotenv_is_rejected`, `test_unrelated_process_env_is_ignored` | Evet | — | PASS | — |
| Secret redaksiyonu (repr, hata mesajı) | `config/errors.py::ConfigurationError` | `test_validation_errors_never_echo_input_values`, `test_secrets_are_masked_in_repr_and_dump`, `integration/test_cli.py` | Evet | — | PASS | — |
| Koşullu LLM/production kuralları | `Settings._cross_field_rules` | `test_llm_enabled_requires_complete_config`, `test_production_rejects_unsafe_modes` | Evet | — | PASS | — |
| Settings dışında env okunmaz | ruff banned-api; `unit/test_architecture.py::test_only_settings_layer_touches_environment` | aynı | Evet | — | PASS | `config/runtime_env.py` PLAYWRIGHT_BROWSERS_PATH'i env'e **yazar** (belgelenmiş istisna) |
| Frontend'e secret sızmaz | `api/public_config.py` allowlist | `integration/test_app.py::test_public_config_is_allowlisted_and_secret_free` | Evet | Her sayfa | PASS | — |
| Dev identity sınırları | `infrastructure/identity/dev.py`, Settings kuralları | `test_dev_identity.py`, `test_dev_auth_requires_loopback_binding`, `test_non_loopback_client_is_refused…` | Evet | — | PASS | Gerçek kimlik adapteri yok → BLOCKED |
| Kullanılmayan ayar olmaması (her ayarın etkisi) | — | Settings kullanım taraması | Evet (tarama) | — | FAIL | 10 ayar çalışma zamanında etkisiz (bkz. bölüm 0) |

### P1 — Deney uygulaması ve browser session
| Gereksinim | Uygulama | Test | Çalıştırıldı | Ön yüz | Durum | Eksik |
|---|---|---|---|---|---|---|
| İç içe/geç/cross-origin frame, duplicate, rastgele id, select/combobox, sayfalı/kaydırmalı tablo, gecikme, dialog, oturum kaybı, commit+yanıt kaybı | `agentask_lab/*` | `integration/lab/test_lab_scenarios.py` (21) | Evet | :8100 sayfaları, `/__lab` | PASS | İki origin aynı site (OOPIF değil) |
| Senaryolar testten tetiklenebilir | `/__lab/scenario|reset|sessions/expire|state` (yalnız loopback) | `test_control_api_*`, `test_lab_control_security.py` | Evet | `/__lab` paneli | PASS | Kontrol API'sinde CSRF yok (yalnız lab) |
| Kullanıcı başına izole context, sahiplik, tek işlem kilidi, limitler, temizlik | `application/services/browser_sessions.py::BrowserSessionService`, `infrastructure/browser/playwright_factory.py` | `unit/test_browser_sessions.py` (15), `browser/test_playwright_sessions.py` | Evet | `/api/sessions` (ekranlarda "Oturum aç") | PASS | Kilit bellek içi, tek worker |
| İzinli origin dışına gezinme/yönlendirme engeli | `PlaywrightContextFactory._guard` | `test_navigation_outside_allowed_origins_is_blocked` | Evet | — | PASS | route.fetch: cache/streaming farkı, WebSocket kontrol dışı |

### P2 — Frame/DOM ve hedef çözümü
| Gereksinim | Uygulama | Test | Çalıştırıldı | Ön yüz | Durum | Eksik |
|---|---|---|---|---|---|---|
| Frame ağacı, generation/epoch, alt ağaç geçersizleştirme | `domain/frames.py::FrameRegistry`, `observer.py::PageObserver` | `unit/test_frames.py`, `browser/test_observer.py::test_frame_reload_invalidates_only_subtree`, `test_late_frame_is_tracked` | Evet | `/designer/targets` | PASS | — |
| Kapsam raporu (partial/timed_out/inaccessible/not_scanned) | `PageObserver._scan_frames` | `test_element_limit_reports_partial`, `test_frame_timeout_reports_timed_out`, `test_depth_and_frame_limits…`, `test_blocked_frame_reported_inaccessible` | Evet | Hedef Deneme gözlem listesi | PASS | — |
| Anlamsal envanter (rol/ad/etiket/bağlam/görünürlük/etkinlik) | `inventory_js.py::DESCRIBE` | `test_inventory_records_kind_context_and_state`, `test_same_semantics_after_ids_change` | Evet | Hedef Deneme tablo | PASS | Shadow DOM, contenteditable yok |
| Hassas değer envanter/log dışı | `isSensitive`, değer hiç toplanmaz | `test_sensitive_values_never_enter_snapshot_or_logs`, `test_sensitive_target_resolves_without_values` | Evet | `/pages/sensitive` | PASS | Sezgisel tespit |
| resolved/ambiguous/unresolved + gerekçe/kapsam/revision; ilk eşleşen yok | `domain/targeting.py::resolve` | `unit/test_targeting.py` (29), `browser/test_resolution.py` (12) | Evet | Hedef Deneme "Ara" | PASS | — |
| Bütçeli iki aşamalı tarama | `observation.py::resolve_target` | `test_partial_scan_keeps_coverage`, `test_summary_cleared_*` | Evet | — | PASS | — |
| Manuel seçim gerçek click/submit/değer değişikliği üretmez | `picker_js.py`, `PageObserver.start_picker/on_binding` | `browser/test_picker.py` (7; mutasyonla doğrulandı), e2e | Evet | Hedef Deneme "Seçimi başlat" | PASS | Headed insan etkileşimi test edilmedi; frame yüklenirken kısa kurulumsuz pencere |
| Eski snapshot adayı reddi | `PageObserver.check_candidate` | `test_new_snapshot_supersedes_old_candidates`, `test_rerender_detected…`, API 409 | Evet | "Vurgula" eski aday → hata | PASS | — |

### P3 — Kontrol adapterleri ve yürütme
| Gereksinim | Uygulama | Test | Çalıştırıldı | Ön yüz | Durum | Eksik |
|---|---|---|---|---|---|---|
| Textbox/native/custom combobox/tab/table adapterleri; gereksiz işlem yok; sonrası doğrulama; unsupported | `application/controls.py`, `infrastructure/browser/driver.py` | `unit/test_control_adapters.py` (15), `browser/test_driver_adapters.py` (7) | Evet | `/designer/runs` örnekleri | PASS | Input tabanlı combobox, hassas alana yazma yok |
| İş anahtarıyla kayıt, son/limit/no-progress/duplicate ayrımı | `TableAdapter.find_record` | `test_find_record_*` (unit+browser), `test_executor.py::test_find_record_by_business_key` | Evet | "Kayıt bul" örneği | PASS | Sanal (recycling) liste yok |
| 7 tipli komut, invoke yalnız onaylı aksiyon (hedef/etki/sonuç) | `domain/commands.py`, `domain/actions.py::ApprovedAction` | `unit/test_commands.py` | Evet | Komut seçimi | PARTIAL | Aksiyonlar kodda (lab) — K6 |
| Run/step durum makineleri | `domain/runtime.py` | `unit/test_runtime_states.py` | Evet | Adım tablosu | PARTIAL | validating/ready/verifying/needs_clarification run durumları yok |
| Checkpoint portu + yerel dosya, yeniden başlatma kurtarması | `ports/runs.py`, `infrastructure/runs/local_file.py`, `runs.py::recover_interrupted` | `unit/test_run_repository.py`, `test_restart_after_dispatch_keeps_outcome_unknown`, `test_runs_api.py::test_startup_recovers…` | Evet | `/runs` | PASS | Mongo run deposu yok |
| Toparlanma: frame değişimi, hazır olmayan hedef, bilinen/bilinmeyen pencere, oturum kaybı, belirsiz hedef | `executor.py::_gate/_resolve/_run_step` | `test_executor.py` (17; mutasyonla doğrulandı) | Evet | Lab senaryoları | PASS | Blocker tanımları kodda |
| Dispatch öncesi niyet, sonrası doğrulama, yanıt kaybı uzlaştırma, körlemesine tekrar yok | `Executor._invoke/_reconcile` | `test_lost_response_reconciled_without_double_commit`, `test_interruption_after_dispatch…` | Evet | Senaryo 7–8 | PASS | Uzlaştırma lab liste sayımına dayanır |
| Çakışan işlem engeli, iptal, sahiplik | `RunService.create/cancel`, oturum kilidi | `test_conflicting_execution…`, `test_cancel_prevents_next_step`, `test_runs_api.py` | Evet | "İptal et" | PASS | — |
| Lease/fencing | — | — | — | — | FAIL | K3 |
| İşlem Deneme ön yüzü | `run_lab.html/js` | `e2e/test_run_lab_ui.py` | Evet | `/designer/runs` | PASS | Çakışma ekrandan denenemez |

### P4 — Katalog Tasarımcısı
| Gereksinim | Uygulama | Test | Çalıştırıldı | Ön yüz | Durum | Eksik |
|---|---|---|---|---|---|---|
| Adım kartı durumları, ayrı onaylar | `domain/catalog.py::StepCard.move, Confirmation` | `unit/test_catalog_domain.py::test_step_flow_requires_order` | Evet | `/designer` kartı | PASS | — |
| Niyet → öneri, adaylar (ilk seçilmez), işaretleme, tekillik | `domain/authoring.py`, `DesignerService.propose_targets/select_target` | `unit/test_authoring.py`, `browser/test_designer.py` | Evet | "Hedef adaylarını göster", "Tarayıcıda işaretle" | PASS | Hedef görüntü kırpması yok |
| Parametre kaynakları, secret değer tutulmaz | `ParameterDef` | `test_param_sources` | Evet | Parametre formu | PARTIAL | prior_output/secret_ref derlenmiyor; ekranda yalnız user_input/approved_constant |
| Deneme (mutating için etki onayı) + bağımsız sistem doğrulaması | `DesignerService.trial_step/confirm_outcome` | `test_picker_selection_and_mutating_trial_requires_ack`, e2e | Evet | "Dene", "Sonucu onayla" | PASS | — |
| Yeni oturum testi, content hash'e bağlı | `fresh_session_test`, `OperationDraft.record_fresh_test` | `test_guided_authoring…`, `test_edit_after_fresh_test_invalidates_readiness` | Evet | "Yeni oturum testi" | PARTIAL | **K1**: varsayılan ayarla 429 |
| Revizyon kontrolü, sahiplik | `LocalFileDraftRepository.update` | `test_draft_repository.py::test_revision_conflict`, `test_drafts_api.py` | Evet | — | PASS | — |
| Eleman/işlem reuse + provenance | `propose_targets` (reuse), `StepCard.provenance` | browser testinde dolaylı | Evet | Reuse satırı | PARTIAL | Yayımlanmış katalogdan reuse yok; işlem reuse yok |
| Onay öncesi yayın koleksiyonuna yazma yok | Taslaklar yalnız DraftRepository | `test_publish_without_approval_rejected`, `test_stale_approval_never_writes` (Mongo) | Evet | — | PASS | — |

### P5 — MongoDB ve yayın
| Gereksinim | Uygulama | Test | Çalıştırıldı | Ön yüz | Durum | Eksik |
|---|---|---|---|---|---|---|
| Typed repo + $jsonSchema + index migration | `infrastructure/mongo/catalog_store.py::ensure_schema` | `mongo/test_mongo_catalog.py::test_schema_validation_rejects…` | Evet (gerçek mongod) | — | PASS | Kurumsal Mongo BLOCKED |
| Hash-bağlı onay, istemci boolean'ı yok, düzenleme onayı bozar | `PublishService.approve/_valid_approval` | `test_stale_approval_rejected` (unit+Mongo) | Evet | "Onayla (yayıncı)" | PASS | Tasarlayan = onaylayan engellenmiyor (kurum kararı) |
| Değişmez revizyon, content conflict | `put_revision` | `test_same_revision_different_hash_conflicts` (unit+Mongo) | Evet | — | PASS | — |
| Tam manifest, CAS pointer, eksik yayın aktif olamaz, eşzamanlı yayın | `PublishService.publish`, `compare_and_set_active` | `test_failure_mid_publish_never_activates`, `test_concurrent_publish_one_wins`, `test_cas_rejects_stale_expected` | Evet | "Yayımla" | PASS | — |
| Çalışan run eski release'e bağlı | `Run.binding`, değişmez manifest | `test_old_release_pinned_and_immutable`, `browser/test_assistant.py::test_run_pinned_to_release` | Evet | `/runs` "yayın" sütunu | PASS | — |
| catalog_screens, automation_runs | — | — | — | — | FAIL | K5 |
| /catalogs inceleme | `catalogs.html/js` | `e2e/test_publish_ui.py` | Evet | `/catalogs` | PASS | — |

### P6 — İşlem Asistanı ve sınırlı LLM
| Gereksinim | Uygulama | Test | Çalıştırıldı | Ön yüz | Durum | Eksik |
|---|---|---|---|---|---|---|
| Kural tabanlı eşleşme, belirsizlik sorusu, parametre uydurmama | `domain/assistant.py::interpret_rules` | `unit/test_assistant_domain.py` | Evet | `/assistant` "Yorumla" | PASS | — |
| LLM kapalı temel akış | `UnavailableLLM`, `AssistantService.interpret` | `e2e/test_assistant_ui.py` ("model: kapalı") | Evet | `/assistant` | PASS | — |
| httpx LLMPort (none/basic/bearer), json_schema müzakeresi, sıkı parse, dış fallback yok | `infrastructure/llm/httpx_llm.py` | `integration/test_llm_adapter.py` (sahte yerel sunucu) | Evet (ikame) | — | PARTIAL | Gerçek model BLOCKED |
| Bilinmeyen işlem/argüman reddi, model önerisi otomatik çalışmaz | `validate_model_choice`, `_model_suggestion` | `test_model_unknown_operation_rejected`, `test_model_suggestion_validated…` (ScriptedLLM) | Evet (ikame) | Kutucuk "modelden öneri iste" | PASS (kural mantığı) | — |
| Token/çağrı bütçesi | `check_budget`, `max_calls` | `test_token_budget_prevents_*` | Evet | — | PASS | Tokenizer yok (tahmin) |
| Prompt injection işlem kümesini genişletmez | Seçim yalnız katalog enum'ı | `test_prompt_injection_cannot_add_operations` | Evet | — | PASS | Sayfa metni enjeksiyonu (T15) özel test yok → NOT_TESTED |
| Model girdisinde secret yok | — | yok | — | — | FAIL | **K2** |
| Katalog erişimi yetkiye göre filtreli | yalnız USE_ASSISTANT | — | — | — | PARTIAL/BLOCKED | İşlem bazında yetki modeli yok |
| Sunucu derlenmiş plan, etki onayı, pin | `preview/execute` | `test_mutating_operation_requires_acknowledgement`, `test_run_pinned_to_release` | Evet | "Planı göster", "Çalıştır" | PASS | — |

### P7 — Bakım ve gözlemlenebilirlik
| Gereksinim | Uygulama | Test | Çalıştırıldı | Ön yüz | Durum | Eksik |
|---|---|---|---|---|---|---|
| Anlamsal diff (dinamik id yok sayılır, etiket değişimi) | `domain/impact.py::classify_elements` | `unit/test_impact_metrics.py`, `browser/test_impact.py` | Evet | `/changes` | PASS | Ekran tanıma yok |
| Bağımlılık etkisi (eleman/adapter/aksiyon), regression seçimi | `impact_of` | `test_shared_dependency_impact`, `test_dependency_impact_by_adapter_and_action` | Evet | "Etkilenen işlemleri bul" | PASS | Regression testleri otomatik çalıştırılmaz (yalnız liste) |
| Onarım taslağı, aktif katalog değişmez | `repair_draft`, `ImpactService.repair` | `test_repair_draft_*`, `test_label_change_detected_and_repair_draft` | Evet | "Onarım taslağı oluştur" | PASS | — |
| Run timeline, hata sınıfı, metrikler (teknik tekrar vs iş başarısı) | `domain/metrics.py::run_metrics`, `/runs` | `test_metrics_separate_recoveries`, `e2e/test_changes_ui.py` | Evet | `/runs` | PARTIAL | Hazırlama/bakım süresi, insan düzeltme, token/çağrı metrikleri yok; release/adapter sürümü run'da yok |
| Kanıt/artefakt, saklama süresi, audit olayları | — | — | — | — | FAIL | K4; AuditPort yok |

### P8 — Kontrollü genişleme ve gerçek ortam hazırlığı
| Gereksinim | Uygulama | Test | Çalıştırıldı | Ön yüz | Durum | Eksik |
|---|---|---|---|---|---|---|
| if/call/bounded loop, statik doğrulama, bayrak kapalı | `domain/composition.py`, `EvaluateConditionCommand`, `StepRecord.when` | `unit/test_composition.py`, `browser/test_composition_run.py`, `test_app.py::test_composite_*` | Evet | `/assistant` "Birleşik görev" (bayrak açıkken; yalnız sıralı çağrı) | PASS | Koşul/döngü yalnız API'den |
| Gösterilmemiş görev kompozisyonu testi | aynı | `test_composite_task_runs_with_guards` | Evet | — | PASS | Tek senaryo; holdout değerlendirme seti yok |
| Yerel/uzak runner sözleşmesi | docs/12_RUNNER_AND_INTEGRATION_CHECKLIST.md | — | — | — | PARTIAL | Uzak runner yalnız belge |
| Gerçek Pega/SSO bilinmeyenleri ve doğrulama kaydı | docs/12 checklist, docs/13 şablon | — | — | — | BLOCKED | Kurum erişimi yok |
| Paketlenebilir uygulama | pyproject, wheel | Önceki oturumda temiz venv kurulumu (bu denetimde tekrar edilmedi) | Hayır (bu denetimde) | — | NOT_TESTED (bu denetimde) | — |

---

## 3. Kritik davranış kontrolleri

| Soru | Cevap | Kanıt (bu denetimde çalıştı) |
|---|---|---|
| Aynı isimli belirsiz hedefte işlem yapılmıyor mu? | Evet, yapılmıyor | `test_ambiguous_target_is_not_dispatched` (alanlar boş kalıyor), `test_insufficient_context_is_ambiguous`, e2e "Belirsiz hedef" |
| Frame yeniden oluşunca eski aday reddediliyor / yeniden çözülüyor mu? | Evet | `test_frame_reload_invalidates_only_subtree`, `test_reloaded_frame_candidate_is_stale_and_re_resolves`, `test_frame_recreated_before_write_is_safely_re_resolved` |
| Manuel seçim gerçek click/submit tetikliyor mu? | Hayır (otomatik testte) | `test_picking_submit_button_does_not_submit` (commit yok), `test_picker_blocks_typing_and_select_changes`; headed insan testi yok |
| Standart ve özel dropdown çalışıyor mu? | Evet | `test_native_and_custom_dropdown` (sayfa değeri okunarak), `test_card_application_reuses_adapters` |
| Tabloda doğru kayıt iş kimliğiyle bulunuyor mu? | Evet | `test_find_record_paged_by_business_key`, `test_find_record_scroll_by_business_key`, limit/son ayrımı |
| Commit + yanıt kaybında çift yazma engelleniyor mu? | Evet (lab) | `test_lost_response_reconciled_without_double_commit` (commit listesi tek), `test_interruption_after_dispatch…` |
| Aynı session'da çakışan işler engelleniyor mu? | Evet (tek süreç) | `test_conflicting_execution_on_same_session_rejected`, `unit/test_browser_sessions.py` |
| Başka kullanıcı draft/run/session'a erişebiliyor mu? | Hayır (404) | `test_drafts_api_rules`, `test_runs_api_flow`, `test_session_api_lifecycle_and_ownership`, `test_observation_api_flow` |
| Onaysız/onay sonrası değişmiş katalog yayımlanabiliyor mu? | Hayır | `test_publish_without_approval_rejected`, `test_stale_approval_rejected` (Mongo dahil), e2e "Onay yok" |
| Kısmi yayın etkin olabiliyor mu? | Hayır | `test_failure_mid_publish_never_activates` (unit + gerçek mongod) |
| Çalışan run katalog sürümüne bağlı kalıyor mu? | Evet | `test_run_pinned_to_release` (yeni yayından sonra eski binding; eski yayınla yeni run 409) |
| Modelden bilinmeyen işlem gelince dispatch engelleniyor mu? | Evet | `test_model_unknown_operation_rejected`, `test_model_suggestion_validated…` (ikame model) |
| LLM kapalıyken temel uygulama çalışıyor mu? | Evet | `e2e/test_assistant_ui.py` (model: kapalı, run Başarılı) |
| .env değerleri merkezi Settings'ten mi? | Evet (okuma); 10 ayar etkisiz | `test_only_settings_layer_touches_environment`; Settings kullanım taraması |
| Secret log/model girdisi/frontend'e sızıyor mu? | Log: hayır; frontend: hayır; **model girdisi: talep redakte edilmiyor (K2)** | `test_sensitive_values_never_enter_snapshot_or_logs`, `test_public_config_is_allowlisted_and_secret_free`; assistant kodu |
| Kalıcı katalogda CSS/XPath/sabit frame yolu var mı? | Hayır | `TargetSpec`/`StepCard` extra=forbid (`test_target_spec_rejects_selectors…`, `test_step_card_rejects_selectors`), `test_publish_and_read_back` (Mongo'daki tanımda aday/`#` yok); frame yalnız iframe başlığı ile |

---

## 4. Entegrasyon ayrımı

- **Yerel deney uygulamasında doğrulananlar:** P1–P4, P6 (kural yolu), P7, P8 akışlarının tamamı (gerçek Chromium, headless).
- **Gerçek MongoDB ile doğrulananlar:** yerel geçici `mongod 8.0.34` (standalone, auth/TLS yok): şema validator,
  unique/conflict, CAS, eksik/eşzamanlı yayın, stale onay, ekrandan onay+yayın+asistan+değişiklik E2E'leri.
- **Gerçek on-prem modelle doğrulananlar:** **yok** (yalnız sahte yerel OpenAI uyumlu sunucu ve ScriptedLLM).
- **Gerçek Pega/SSO ile doğrulananlar:** **yok**.
- **Henüz doğrulanmayanlar:** kurumsal Mongo (TLS/CA/auth/replica set), on-prem model, Pega/Constellation DOM ve kontrol
  aileleri, SSO yönlendirmeleri ve origin listesi, gerçek kayıt kimliğiyle uzlaştırma, headed modda insan seçimi,
  Firefox/WebKit, OOPIF frame'ler, uzak runner, çok worker.

---

## 5. Manuel kabul kılavuzu

**Ortak hazırlık**
1. `cd agentask-arge-plan && cp .env.example .env`; `.env`'de `SESSION_SIGNING_KEY` için ≥32 karakter rastgele değer yazın.
2. **K1 nedeniyle** tasarımcı yeni oturum testi için `.env`'de `BROWSER_MAX_SESSIONS_PER_USER=2` yapın (yapmazsanız Senaryo 13 adım 9 "Açık tarayıcı oturumu sınırına ulaşıldı" hatası verir — bu bir FAIL bulgusudur).
3. Yayın senaryoları için: `mkdir -p var/mongo && mongod --dbpath ./var/mongo --port 27017 --bind_ip 127.0.0.1`.
4. Ayrı terminallerde: `.venv/bin/agentask-lab` ve `.venv/bin/agentask`. Tarayıcı penceresi görünür açılır (`BROWSER_HEADLESS=false`).
5. Lab kontrol paneli: http://127.0.0.1:8100/__lab · Kayıtlar: http://127.0.0.1:8100/__lab/state · Run dosyaları: `var/runs/` · Taslaklar: `var/drafts/`.

| # | Senaryo | Başlangıç | Adres ve adımlar | Örnek veri | Beklenen | Başarısızlık belirtisi | Kanıt |
|---|---|---|---|---|---|---|---|
| 1 | Sağlık | Hazırlık | http://127.0.0.1:8000/health/ready | — | `ready`; `catalog_mongo: available` | 503 / `unavailable` (Mongo çalışmıyor) | JSON yanıt |
| 2 | Belirsiz vs tekil hedef | — | `/designer/targets` → Oturum aç → Adres: `http://127.0.0.1:8100/login` → Git → açılan pencerede giriş → Adres `http://127.0.0.1:8100/pages/duplicates` → Git → Hedef ara: Tür Metin, Etiket `Müşteri No` → Ara; sonra Bölüm `Kefil` → Ara | Kullanıcı adı `deneme` | İlk: `ambiguous` + 2 aday (Başvuran, Kefil); ikinci: `resolved`, pencerede Kefil alanı turuncu vurgulu | İlk aramada `resolved` | Sonuç kutusu, vurgu |
| 3 | Eski aday reddi | Senaryo 2 sonrası | "Ekranı gözlemle" → sonra önceki sonuçtaki "Vurgula" | — | Hata: "Seçilen aday artık geçerli değil… (snapshot_superseded)" | Eski aday vurgulanır | Hata satırı |
| 4 | Manuel seçim işlem tetiklemez | Pencerede `/pages/note-form` açık | `/designer/targets` → "Seçimi başlat" → pencerede Not alanına yazmayı deneyin, sonra "Kaydet"e tıklayın | `deneme` | Yazı girmez; "Seçilen: Kaydet · düğme"; not kaydı oluşmaz | Not listesinde yeni not / sayfada "Kaydedildi" | http://127.0.0.1:8100/__lab/state `commits: []` |
| 5 | Standart/özel dropdown + sekme | — | `/designer/runs` → Oturum aç → Deney ekranı "Açılır listeler ve sekmeler" → Deney ekranını aç → Örnek senaryo "Kart başvurusu" → Çalıştır | Şube Konak, Ürün Ticari Kart, Teslimat adresi | Rozet **Başarılı**; pencerede Şube Konak, Ürün Tipi Ticari Kart, Teslimat sekmesi açık | Başarısız/Duraklatıldı | Adım tablosu (adapter: native_select, custom_combobox, tab, textbox) |
| 6 | Gereksiz değişiklik yok | Senaryo 5 sonrası | Aynı planı tekrar Çalıştır | — | Başarılı; ilgili adım sonuçlarında `"changed": false` | `changed: true` | Adım tablosu |
| 7 | İş kimliğiyle kayıt | — | Deney ekranı "Sayfalı tablo" aç → Örnek "Kayıt bul" → Çalıştır | Anahtar B-1027 | Başarılı, `pages_visited: 3`; pencere "Sayfa 3 / 6" | Yanlış sayfa / FAILED | Adım sonucu |
| 8 | Belirsiz hedefte işlem yok | — | Deney ekranı "Aynı isimli alanlar" → Örnek "Belirsiz hedef" → Çalıştır | `1` | **Duraklatıldı**, "Bilinen başarısızlık", TARGET_AMBIGUOUS; iki Müşteri No alanı boş | Bir alana `1` yazılması | Adım tablosu, pencere |
| 9 | Yanıt kaybı → uzlaştırma, çift yazma yok | — | Lab paneli: `lose_next_commit_response` işaretle, `client_timeout_ms` 800, `lost_response_hang_ms` 6000 → Uygula → `/designer/runs` Not ekleme ekranını aç → Örnek "Vakaya not ekle" → Çalıştır | "Müşteri arandı" | Başarılı; sonuçta `verified_by: reconciliation`, toparlanmada WRITE_RESULT_UNKNOWN | İki not / Belirsiz | `/__lab/state` commits tek kayıt; sayfada "Mevcut notlar"da bir kez |
| 10 | Belirsiz sonuç korunur | Senaryo 9 hazırlığı | Çalıştır'a bastıktan hemen sonra lab panelinde "Oturumları sonlandır" | — | **Belirsiz**, adım "Sonuç belirsiz"; sonra "Deney ekranını aç" + "Devam et" → Başarılı | Belirsizken otomatik yeniden gönderim (2 commit) | `/__lab/state` toplam commit artışı 1 |
| 11 | Bilinmeyen pencere | — | Lab: `dialog` = `unknown_modal` → Not ekleme ekranını aç → "Vakaya not ekle" → Çalıştır | — | **Duraklatıldı**, UNKNOWN_DIALOG; pencerede "Onay Gerekli" açık kalır | Pencere kendiliğinden kapanır / not kaydı | `/__lab/state` |
| 12 | Bilinen uyarı | — | Lab: `dialog` = `modal` → aynı akış | — | Başarılı; toparlanma `KNOWN_OVERLAY:lab.case_updated_notice` | Duraklatıldı | Adım tablosu |
| 13 | Oturum kaybında duraklama | Not ekleme ekranı açık | Lab "Oturumları sonlandır" → "Vakaya not ekle" → Çalıştır → sonra "Deney ekranını aç" → "Devam et" | — | Önce **Duraklatıldı** (SESSION_EXPIRED), devamda Başarılı; tek not | Not kaydı ilk çalıştırmada | `/__lab/state` |
| 14 | İptal | — | Lab: `table_rows` 40, `page_size` 10; Sayfalı tablo ekranını aç; lab `delay_ms` 600 → Örnek "Kayıt bul" + formdan Oku/Tablo/`Başvurular` adımı ekle → Çalıştır → hemen "İptal et" | — | **İptal edildi**; ikinci adım "Atlandı (iptal)" | İkinci adımın çalışması | Adım tablosu |
| 15 | Katalog hazırlama (JSON'suz) | Hazırlık 2–3 | `/designer` → Oturum aç → Deney ekranı Başvuran/Kefil → Ekranı aç → Taslak: kimlik `kefil_musteri_no`, başlık "Kefil müşteri numarasını gir" → Parametre `musteri_no` / Müşteri No → Adım "Kefil müşteri numarasını yaz" → Hedef adaylarını göster → Kefil satırında "Bu hedefi seç" → şablon `{musteri_no}` → Tanımı kaydet → 4 onay kutusu → Onayla → deneme değeri → Dene → Sonucu onayla → Başlangıç ekranı Başvuran/Kefil, test değeri → Yeni oturum testi | `00123`, `00999` | Kart "İncelemeye hazır"; inceleme "İncelemeye hazır: bütün adımlar doğrulandı" | Etki kutusu boşken onaylanması; varsayılan ayarla oturum sınırı hatası (K1) | `var/drafts/draft-*.json` (deneme değerleri yok) |
| 16 | Onay/yayın, onay sonrası değişiklik | Senaryo 15 | "Yayımla" (önce) → "Onayla (yayıncı)" → yeni bir adım ekle → "Yayımla" → adımı sil + yeni oturum testi + Onayla → Yayımla | — | İlk: "Onay yok veya içerik…"; değişiklik sonrası yine red; son: "Yayımlandı ve etkin: rel-…" | Onaysız/eski onayla yayın | `/catalogs` → Ayrıntı (ETKİN, onaylayan, hash) |
| 17 | Asistan (LLM kapalı) | Senaryo 16 yayını | `/assistant` → "Kefil müşteri numarasını gir" → Yorumla → Müşteri No `00456` → Planı göster → Oturum aç → ekranı aç → Çalıştır | — | "Açıklama gerekli", eksik parametre; plan etkisi "yalnız ekran"; **Başarılı**, "yayın rel-…" | Parametre uydurulması | `/runs` (işlem/yayın sütunu) |
| 18 | Run sürüm bağı | Senaryo 17 | Senaryo 15–16 ile yeni revizyon yayımla → `/runs` | — | Eski run eski `release_id` ile görünür | Eski run yeni yayını gösterir | `/runs`, `/catalogs` |
| 19 | Değişiklik/etki ve onarım | Senaryo 16 | Lab `guarantor_customer_label` = `Müşteri Numarası` → Uygula → `/changes` → Oturum aç → Ekranı aç → Ekranla karşılaştır → Onarım taslağı oluştur | — | Eleman "Bulunamadı", öneri "Müşteri Numarası", etkilenen `kefil_musteri_no r1`; onarım taslağı açıldı | Etkin yayının değişmesi | `/catalogs` aynı etkin yayın; `/designer` yeni taslak |
| 20 | Hassas alan | — | `/designer/targets` → pencere `/pages/sensitive`, alanlara değer yazın → Ekranı gözlemle | `Gizli-123` | Parola/kod alanları "Hassas: evet"; hiçbir değer görünmez | Değer metninin ekranda/logda görünmesi | Gözlem tablosu; uygulama terminal logu |
| 21 | Sahiplik (API ile; ekrandan kullanıcı değiştirilemez) | Senaryo 17'den bir run kimliği | `curl -H "X-Dev-User: baska" -H "X-Dev-Roles: operator" http://127.0.0.1:8000/api/runs/<run_id>` | — | 404 `run_not_found` | 200 | curl çıktısı |
