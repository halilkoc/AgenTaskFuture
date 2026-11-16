# İlerleme ve devam noktası

Paket hazırlanma tarihi: 2026-11-05. Belgelerin varlığı implementasyon değildir; işaretli kutular aşağıdaki kayıttaki test kanıtına dayanır.

- [x] P0 İskelet/Settings (2026-11-05)
- [x] P1 Deney uygulaması/session (2026-11-05)
- [x] P2 Frame/DOM/resolver (2026-11-05)
- [x] P3 Adapter/runtime/reconciliation (2026-11-05) — COMPLETED (lab kapsamında)
- [x] P4 Designer (2026-11-05) — COMPLETED (yerel taslak, lab)
- [x] P5 Mongo yayın (2026-11-05) — COMPLETED (yerel geçici mongod ile doğrulandı; kurumsal Mongo BLOCKED)
- [x] P6 Assistant/LLM (2026-11-05) — COMPLETED (LLM_ENABLED=false yolu + sahte yerel model ile adapter); gerçek model BLOCKED
- [x] P7 Maintenance/observability (2026-11-05) — COMPLETED (lab kapsamında)
- [x] P8 Composition/gerçek Pega hazırlığı (2026-11-05) — PARTIAL (birleştirme + paketleme COMPLETED; uzak runner uygulanmadı; gerçek Pega doğrulaması BLOCKED)

## Durum özeti (2026-11-05)
| Aşama | Durum | Not |
|---|---|---|
| P0 | COMPLETED | Settings/.env, iskelet |
| P1 | COMPLETED | Deney uygulaması, browser oturumları |
| P2 | COMPLETED | Frame/envanter/çözümleyici/seçim (lab) |
| P3 | COMPLETED | Adapterler, komut motoru, uzlaştırma (lab aksiyonları) |
| P4 | COMPLETED | Katalog Tasarımcısı (yerel taslak). Denetim K1 (varsayılan ayarla yeni oturum testi 429) R2 ile düzeltildi; override'sız E2E geçti |
| P5 | COMPLETED | MongoDB yayın (yerel geçici mongod 8.0.34); R3 ile catalog_screens + manifest ekranları; kurumsal Mongo BLOCKED |
| P6 | PARTIAL | Asistan, kural yolu, LLM adapteri (sahte yerel sunucu); gerçek model BLOCKED. Denetim K2 R1 ile düzeltildi (şüphede model yok, hassas argüman reddi; tespit sezgisel); secret_ref çözümü yok |
| P7 | COMPLETED | Etki/onarım/metrikler (lab) |
| P8 | PARTIAL | Birleştirme + paketleme tamam; uzak runner yok; gerçek Pega/SSO doğrulaması BLOCKED |

## Sonraki somut adım
**Tek güncel devam noktası: [docs/STATUS.md](STATUS.md).** Bu dosya tarihçedir.
Denetim (docs/12_IMPLEMENTATION_AUDIT.md) sonrası düzeltmeler: docs/14_REMEDIATION_LOG.md. **Güncel durum (2026-11-06): R4 çok ekranlı işlemler COMPLETED (lab kapsamında).** Önceki tamamlanan aşamalar (R1, R2, R2B, yerel MongoDB otomatik başlatma, R3) tarihçe olarak geçerlidir; K5'in automation_runs kısmı, K3, K4, K6, K7 açık; /designer/targets ve /designer/runs henüz ortak oturum panelini kullanmıyor.
Yarın için başlangıç ve yeniden başlatma komutları: aşağıdaki "Devam noktası (2026-11-06)" bölümü.
Kurum test ortamı sağlandığında docs/12'deki doğrulama sırasını izle ve sonuçları docs/13'e yaz. Kurum gerektirmeyen
sıradaki işler: uzak runner lease/fencing uygulaması, MongoDB run deposu adapteri, SSE ilerleme, shadow DOM envanteri.

## Aşama kayıtları

### 2026-11-05 / P0 İskelet ve konfigürasyon
- **Değişen dosyalar:** pyproject.toml, requirements.lock, README.md (geliştirme bölümü), docs/05_CONFIGURATION.md
  (değer kümeleri), docs/adr/0001-p0-iskelet-ve-settings.md;
  src/agentask/{__main__.py, bootstrap.py}, config/{settings.py, errors.py}, domain/identity.py,
  application/{errors.py, ports/identity.py, ports/llm.py}, infrastructure/{logging.py, identity/dev.py,
  identity/unconfigured.py, llm/unavailable.py}, presentation/{app.py, errors.py, dependencies.py, pages.py,
  api/health.py, api/me.py, api/public_config.py, templates/*.html, static/app.{js,css}};
  tests/{conftest.py, unit/test_settings.py, unit/test_dev_identity.py, unit/test_architecture.py,
  integration/test_app.py, integration/test_cli.py}. `.env.example` ve `.gitignore` değişmedi.
- **Davranış:** typed/frozen Settings (zorunlu alanlar varsayılansız, tek kaynak .env.example); process env > dotenv;
  `--env-file`; dotenv'de bilinmeyen anahtar reddi; girdisiz redakte hata; LLM/production/dev-auth koşullu kuralları
  ve token bütçesi kontrolü. Composition root (IdentityPort, LLMPort). Dev kimliği yalnızca development + açık izin
  + loopback bind + loopback istemci. Endpoint'ler: /health/live, /health/ready, /api/me, /api/config/public
  (allowlist), rol kontrollü /, /assistant, /designer (Türkçe Jinja2). Error envelope + correlation id + güvenlik
  başlıkları. `agentask --check-config`; tek uvicorn worker; JSON stdout log.
- **Testler:** `.venv/bin/pytest -q` → 72 passed; `.venv/bin/ruff check src tests` → temiz;
  `.venv/bin/ruff format --check` → temiz; `.venv/bin/mypy` (strict) → 31 dosyada hata yok.
  T17/T18 karşılandı. Gerçek sunucu duman testi (port 8765, geçici env dosyası): ready 200, public config yalnız
  allowlist, operator ile /designer 403; ham .env.example ile `--check-config` exit 2 ve redakte mesaj.
- **Çalıştırılamayanlar:** Playwright/Mongo/LLM yok (P1/P5/P6 kapsamı). Gerçek SSO doğrulanmadı.
- **Bilinen sınırlamalar:** AUTH_MODE yalnız dev|unconfigured; LLM_ENABLED=true olsa bile LLM adapteri yok
  (açıkça unavailable raporlanır). Readiness henüz Mongo'yu kontrol etmiyor (P5). Relative DRAFT/ARTIFACT
  dizinleri çalışma dizinine göre çözülür; dizinler henüz oluşturulmuyor. Starlette TestClient'ın httpx
  deprecation uyarısı pytest'te filtrelendi. CSRF, cookie oturumu henüz yok (cookie auth eklenince zorunlu).

## Aşama kayıt şablonu
Tarih / aşama / değişen dosyalar / uygulanan davranış / çalıştırılan test komutları ve sonuçları / çalıştırılamayan testler ve nedeni / bilinen sınırlamalar / sonraki iş.

## Kurum bilgisi bekleyenler
- Gerçek Pega sürümü ve Traditional/Constellation UI; örnek DOM ve kontrol ailesi.
- SSO ve kullanıcı yetkisi servis sözleşmesi.
- Runner yerleşimi ve onay öncesi draft kalıcı yeri.
- On premise LLM endpoint/auth/model/context ve structured output desteği.
- İzinli test ortamı/verisi; DX API erişimi ve kullanılabilecek outcome okumaları.
Bu eksikler P0–P7 fixture geliştirmesini durdurmaz; gerçek entegrasyonun doğrulandığı iddia edilemez.

### 2026-11-05 / P0 yeniden doğrulama
- `.venv/bin/pytest -q` → 72 passed; ruff/format/mypy temiz; ham `.env.example` ile `agentask --check-config` → exit 2,
  redakte mesaj; gerçek sunucu: /health/ready 200, /api/me 200. Eksik bulunmadı.
- Not: varsayılan `.env` çalışma dizininden okunur, docs/05 "repo kökü" der; komutlar repo kökünden çalıştırılmalı.

### 2026-11-05 / P1 Deney uygulaması ve browser session
- **Plan:** docs/superpowers/plans/2026-11-05-p1-lab-and-browser-sessions.md. **Karar kaydı:** docs/adr/0002-p1-lab-ve-browser-session.md.
- **Sürümler:** Python 3.12.0, Playwright 1.64.1, Chromium 156.0.8078.4 (async API ile doğrulandı), python-multipart 0.0.33;
  pyproject.toml ve requirements.lock'ta sabit.
- **Değişen/yeni dosyalar:** `.env.example`, `.gitignore`, pyproject.toml, requirements.lock, README.md, docs/05, docs/09,
  docs/adr/0002; src/agentask/{bootstrap.py, domain/origins.py, config/settings.py, config/runtime_env.py,
  application/errors.py, application/ports/browser.py, application/services/browser_sessions.py,
  infrastructure/browser/playwright_factory.py, presentation/app.py, presentation/errors.py, presentation/api/sessions.py};
  src/agentask_lab/{__main__, app, server, state}.py + templates/ + static/; tests/{support_lab.py,
  integration/conftest.py, integration/lab/*, integration/browser/*, integration/test_sessions_api.py,
  unit/test_browser_sessions.py, unit/test_origins.py, unit/test_runtime_env.py, unit/test_settings.py (P1 ekleri),
  unit/test_architecture.py (lab bağımsızlığı)}.
- **Yeni ayarlar:** BROWSER_LAUNCH_TIMEOUT_MS, BROWSER_MAX_SESSIONS, BROWSER_MAX_SESSIONS_PER_USER,
  BROWSER_SESSION_IDLE_SECONDS, NAVIGATION_TIMEOUT_MS, LAB_PRIMARY_ORIGIN, LAB_SECONDARY_ORIGIN.
- **Deney uygulaması:** iç içe (2 seviye) + cross-origin (:8101) + sonradan eklenen frame; aynı isimli kontroller
  (Başvuran/Kefil); her yüklemede yeni id/name; native select + gecikmeli özel combobox; sayfalı ve kaydırdıkça yüklenen
  tablo; sunucu gecikmesi ve gecikmeli içerik; modal ve native uyarı; oturum düşürme (login'e yönlendirme, API 401);
  commit edilip yanıtı kaybolan not kaydı (commit `/__lab/state`'te görünür, sayfa "işlem sonucu bilinmiyor" der).
  Hepsi `/__lab/*` kontrol API'si ile testten tetiklenir.
- **Oturumlar:** kullanıcı başına ayrı BrowserContext; sahip olmayan 404; oturum başına tek işlem (ikincisi 409);
  limitler (429) eşzamanlı open'da da korunur; boşta kalan oturum kapanır, işlemdeki kapanmaz; lifespan kapanışında
  bütün context'ler ve browser süreci kapanır; browser koparsa yeniden başlar; başlatılamazsa 503; izinsiz origin'e
  giden bütün http(s) istekleri ve sunucu yönlendirmeleri engellenir.
- **Testler:** `.venv/bin/pytest -q` → 145 passed (~20 sn, gerçek headless Chromium dahil; `-m browser` 24 test).
  Lab testleri 3 ardışık koşuda 19/19, oturum testleri 3 koşuda 8/8. ruff check/format temiz, mypy strict 46 dosya
  temiz. Kritik eşzamanlı-open testi mutasyonla doğrulandı (rezervasyon kaldırılınca 2 test kırıldı).
- **Gerçek çalıştırma:** `agentask-lab` + `agentask` birlikte: lab login 200, :8101 cross frame 200, kontrol API PUT çalışıyor,
  girişsiz sayfa 303→login; ana uygulamada ayse oturum 201, ikinci 429, mehmet listesi boş, mehmet DELETE 404,
  ayse DELETE 204, publisher 403; SIGINT sonrası iki süreç kapandı ve kalan Playwright browser süreci 0.
- **Çalıştırılamayanlar / kapsam dışı:** gerçek Pega, SSO, MongoDB, LLM bağlanmadı. Firefox/WebKit ile test edilmedi
  (yalnız Chromium). Headed (BROWSER_HEADLESS=false) mod otomatik testte koşulmadı.
- **Bilinen sınırlamalar:** origin koruması istekleri `route.fetch` ile servis ediyor (tamponlama, cache/streaming farkı,
  WebSocket kontrol dışı) — gerçek Pega'da doğrulanmalı (ADR 0002). Kilit bellek içi, tek worker. POST /api/sessions
  idempotency key almıyor. Observe/navigate API'si P2'de. Lab yalnız Ar-Ge içindir; kontrol API'si CSRF korumasız.
- **Kararlar (ruling) ve ertelenenler:**
  - Setup: Ruling: klasör git deposu değil; worktree/commit adımları atlanır, ilerleme bu ledger + docs/10_PROGRESS.md ile izlenir — kullanıcı git istemedi, git init kapsam dışı — maliyet: commit geçmişi/BASE aralığı yok, review-package scripti kullanılamaz.
  - Task 2: Ruling: serve imzası serve(state, primary_origin, secondary_origin) oldu; Settings'i CLI okur — testler Settings olmadan boş portlarda başlatabilsin — maliyet: yok, CLI aynı Settings'i kullanır.
  - Task 2: Ruling: Scenario'ya reveal_delay_ms, combobox_delay_ms, client_timeout_ms eklendi — gecikmeli içerik/combobox/istemci zaman aşımı testten kontrol edilebilsin (plan bunları sabit bırakmıştı) — maliyet: yok.
  - Task 2: Ruling: ikincil origin /frames/cross giriş istemez (cookie'ler port ayırt etmez; "dış sistem" olarak kendi oturumu yok) — maliyet: cross-origin oturum kaybı senaryosu yok.
  - Task 2: Ruling: python-multipart==0.0.33 bağımlılığı eklendi (lab giriş formu) — maliyet: ek bağımlılık.
  - Task 3: Ruling: ServiceShuttingDown (503) hatası eklendi — kapanış sırasında yeni open/operation açıkça reddedilsin — maliyet: yok.
  - Task 4: Ruling: izinsiz origin engeli yalnızca document değil bütün http(s) isteklerine uygulanır (plan document diyordu) — docs/08 "credential/ham DOM dış servise taşınmaz" ile daha uyumlu, img/script ile veri sızması da kapanır — maliyet: izinli listede olmayan CDN/kaynaklar yüklenmez; gerçek Pega'da origin listesi buna göre doldurulmalı.
  - Task 4: Ruling: Playwright route yönlendirme adımlarını yakalamadığı (test kanıtı: HitCounter '/redirect' isabeti) için izinli istekler route.fetch(max_redirects=0)+fulfill ile servis edilir, Location politikaya göre denetlenir — güvenlik sınırı — maliyet: istekler tarayıcı yerine Playwright request context'i ile yapılır (yanıt tamponlanır; HTTP cache/streaming/SSE davranışı farklı olabilir; websocket bu yoldan geçmez). Gerçek Pega'da doğrulanmalı; ADR 0002'de.
  - Task 4: Ruling: Container'a browser_factory alanı eklendi (lifespan/test kaynak kontrolü için) — maliyet: yok.
  - Final: Ruling: POST /api/sessions idempotency key taşımıyor — docs/09'daki kural run/publish gibi dış etkili işlemler için kritik; oturum açma dış sisteme yazmaz ve limitle sınırlı — maliyet: ağ tekrarı ikinci oturum açmaya çalışır, limit 429 ile durdurur.
  - Final: minor (deferred): lab POST /login next="/\evil" biçimini reddetmiyor (yalnız loopback deney uygulaması).
  - Final: minor (deferred): lab kontrol API'si CSRF korumasız; aynı makinedeki başka bir sayfa senaryoyu değiştirebilir.
  - Final: minor (deferred): varsayılan .env çalışma dizininden okunuyor; docs/05 "repo kökü" diyor (README komutları repo kökünden çalıştırır).

### 2026-11-05 / P2 Frame takibi, anlamsal envanter, hedef çözümü, manuel seçim
- **Başlangıç doğrulaması:** P0/P1 suite 145 passed, ruff/mypy temiz.
- **Plan:** docs/superpowers/plans/2026-11-05-p2-frames-inventory-resolver.md. **Karar kaydı:** docs/adr/0003-p2-gozlem-ve-hedef-cozumu.md.
- **Yeni/değişen dosyalar:** src/agentask/domain/{frames,observation,targeting}.py; application/ports/{observation,browser}.py;
  application/services/{observation,browser_sessions}.py (peek); application/errors.py (CandidateStale, details);
  infrastructure/browser/{observer,inventory_js,picker_js,playwright_factory}.py; presentation/api/observation.py;
  presentation/{app,errors,pages}.py; templates/{target_lab,base,designer}.html; static/{target_lab.js,app.css};
  bootstrap.py; config/settings.py; .env.example; docs/05, docs/09, README; lab: sensitive/heavy sayfaları,
  tabloda satır başına "Aç", dropdowns'ta sekmeler, level1 frame yüksekliği, /__lab/autologin;
  testler: unit/test_frames.py, unit/test_targeting.py, integration/browser/{helpers,test_observer,test_resolution,
  test_picker}.py, integration/test_observation_api.py, e2e/test_target_lab_ui.py, test_app.py ve lab test ekleri.
- **Yeni ayarlar:** OBSERVE_TIMEOUT_MS (≥ FRAME_SCAN_TIMEOUT_MS), OBSERVE_MAX_FRAMES, PICKER_WAIT_MAX_MS.
  FRAME_SCAN_MAX_ELEMENTS artık uygulanıyor (frame başına).
- **Testler (gerçekten çalıştırıldı):** `.venv/bin/pytest -q` → 220 passed (~43 sn); `-m browser` → 58 passed.
  Dosya bazında: test_frames 5, test_targeting 29, test_observer 12, test_resolution 12, test_picker 7,
  test_observation_api 2, e2e 1. Browser testleri 3 ardışık koşuda kararlı (37/37). ruff/format/mypy strict temiz.
  Mutasyon kontrolleri: seçim modunda olay iptali kaldırılınca 2 picker testi kırıldı; seçim durdurmada bekleyeni
  uyandırma kaldırılınca ilgili test kırıldı.
- **Kullanıcının istediği 9 senaryo:** derin iç içe frame (test_deep_nested_frame_field_is_resolved), geç/yeniden
  yüklenen frame (test_late_frame_not_found_then_resolved, test_reloaded_frame_candidate_is_stale_and_re_resolves,
  test_frame_reload_invalidates_only_subtree), bağlamla ayrım (test_same_named_controls_distinguished_by_context,
  test_table_row_key_disambiguates), yetersiz bağlam ambiguous (test_insufficient_context_is_ambiguous), id değişimi
  sonrası yeniden bulma (test_resolved_again_after_ids_change, test_same_semantics_after_ids_change), kısmi tarama
  kapsamı (test_partial_scan_keeps_coverage, test_element_limit_reports_partial, test_frame_timeout_reports_timed_out,
  test_depth_and_frame_limits_report_not_scanned, test_inaccessible_frame_prevents_not_found), manuel seçimin işlem
  tetiklememesi (test_picking_submit_button_does_not_submit, test_picker_blocks_typing_and_select_changes),
  hassas değerler (test_sensitive_values_never_enter_snapshot_or_logs, test_sensitive_target_resolves_without_values),
  eski snapshot adayı reddi (test_new_snapshot_supersedes_old_candidates, test_rerender_detected_as_detached_or_changed,
  API 409 testi).
- **Gerçek çalıştırma:** agentask-lab + agentask (headless) ile curl: resolved (Kefil), ambiguous (2 aday), unresolved
  not_found, unresolved coverage_incomplete (4000 alan > 3000 limit, frame partial/element_limit), derin frame resolved,
  vurgu 200 ve yeni gözlem sonrası 409 candidate_stale; uygulama logunda etiket/HTML yok; kapanışta browser süreci 0.
- **Test edilmeyenler:** gerçek Pega/Constellation DOM'u, Shadow DOM, Firefox/WebKit, görünür (headed) modda insan
  etkileşimi (seçim/vurgu yalnız headless + Playwright fare olaylarıyla doğrulandı), çok büyük gerçek sayfalarda
  performans, OOPIF (farklı site) frame'ler — lab'daki iki origin aynı site (127.0.0.1) olduğundan aynı süreçtedir.
- **Kararlar (ruling) ve ertelenenler:**
  - Setup: Ruling: git deposu yok; commit adımları atlanır — maliyet: commit geçmişi yok.
  - Task 2: Ruling: FRAME_SCAN_MAX_ELEMENTS frame başına uygulanır; toplam frame sayısı OBSERVE_MAX_FRAMES ile sınırlanır — eşzamanlı taramada paylaşılan sayaç yarışını önler — maliyet: toplam kontrol sayısı frames×limit'e kadar çıkabilir.
  - Task 2: Ruling: textbox değerleri hiç toplanmaz (yalnız has_value); hassas select/combobox'ta seçili metin de yok — "hassas değer" tespiti hatalı olsa bile değer sızmaz — maliyet: P3'te ensure_value önce okuma adaptörü gerektirecek.
  - Task 2: Ruling: görünmeyen/devre dışı eşleşmeler de aday sayılır (gizli kopyayı tekil sanmamak için) — maliyet: gizli şablon kopyası olan ekranlarda ek bağlam gerekir.
  - Task 2: Ruling: frame başlığı iframe title/aria-label/name özniteliğinden; ana frame başlıksız — maliyet: başlıksız iframe'ler frame_title ile hedeflenemez.
  - Task 4: Ruling: Playwright 1.64 expose_binding 'handle' seçeneğini desteklemiyor; seçim katmanı eleman indeksini+anlamsal parmak izini gönderir, Python o frame'de elemanı yeniden alıp parmak izini doğrular — maliyet: tıklama ile eşleme arasında DOM değişirse seçim 'element_changed' ile reddedilir (yeniden seçim gerekir).
  - Task 4: Ruling: lab level1 iframe yüksekliği 260→340 (içerik görünür alana sığsın); testler tıklamadan önce scroll_into_view yapar — maliyet: yok.
  - Task 3: Ruling: hafif özeti tam olup adı içermeyen frame'ler resolve(summary_cleared=...) ile kapsam içinde tamam sayılır — iki aşamalı taramanın 'eksik kapsam' üretmemesi için — maliyet: özet adları kesilirse (partial) bu kural uygulanmaz.
  - Task 5: Ruling: lab'a /__lab/autologin (yalnız loopback, açık yönlendirme yok) eklendi — headless/API demolarında oturum tarayıcısı lab'a girebilsin — maliyet: lab'a özgü; ürün kodunda karşılığı yok.
  - Task 5: Ruling: deneme ekranı /designer/targets (designer yetkisi); e2e test gerçek HTTP sunucusu + ayrı UI tarayıcısıyla — maliyet: e2e ~3 sn.
  - Final: minor (deferred): Shadow DOM içindeki kontroller envantere girmiyor (querySelectorAll shadow root'a inmez).
  - Final: minor (deferred): sayfa betiği binding'i sahte token'la çağırarak uyarı logu üretebilir (log gürültüsü; seçim kabul edilmez).
  - Final: minor (deferred): seçim modu, frame yeni yüklenirken (domcontentloaded öncesi) kısa bir pencerede kurulmamış olabilir.

### 2026-11-05 / P3 Kontrol adapterleri, komut motoru, yürütme ve uzlaştırma — COMPLETED (lab kapsamında)
- **Plan:** docs/plans/2026-11-05-p3-controls-and-execution.md · **ADR:** docs/adr/0004-p3-komut-motoru-ve-yurutme.md
- **Yeni dosyalar:** domain/{commands,actions,runtime}.py; application/{controls.py, ports/controls.py, ports/runs.py,
  services/executor.py, services/runs.py}; infrastructure/{browser/driver.py, browser/driver_js.py,
  runs/local_file.py, approved_actions/lab.py}; presentation/api/runs.py; templates/run_lab.html; static/run_lab.js;
  testler: unit/{test_commands,test_runtime_states,test_run_repository,test_control_adapters}.py,
  integration/browser/{test_driver_adapters,test_executor}.py, integration/test_runs_api.py, e2e/{support,test_run_lab_ui}.py.
- **Değişen:** domain/observation.py (tag), inventory_js/observer (tag, native dialog kaydı), observation service
  (resolve_target), playwright_factory (driver), errors, bootstrap, app (açılış kurtarma, kapanışta run durdurma),
  pages (/designer/runs), settings + .env.example + docs/05, docs/09, README; lab: sekme geçişi, Kefil kaydet
  durumu, dialog=unknown_modal.
- **Yeni ayarlar:** RUN_DIRECTORY, APPROVED_ACTION_SET, OUTCOME_TIMEOUT_MS, RECONCILE_TIMEOUT_MS, TABLE_NO_PROGRESS_LIMIT.
- **Testler:** `.venv/bin/pytest -q` → 327 passed (~70 sn); ruff/format/mypy strict temiz. test_executor 17/17 üç
  ardışık koşuda. Mutasyon: belirsiz hedefte ilk aday seçilince ambiguous testi kırıldı.
- **İstenen 14 doğrulama:** textbox yaz/doğrula ve gereksiz değişiklik yok (test_textbox_write_verify_and_no_change,
  unit no-change), native/özel dropdown (test_native_and_custom_dropdown, test_card_application_reuses_adapters), sekme
  (test_tab_activation_verified), iş kimliğiyle kayıt (test_find_record_*), frame yeniden oluşunca yeniden çözüm
  (test_frame_recreated_before_write_is_safely_re_resolved), belirsiz hedefte dispatch yok
  (test_ambiguous_target_is_not_dispatched), bilinmeyen modal/native dialog'da durma, oturum kaybında duraklama
  (iki test), yanıt kaybında çift işlem yok (test_lost_response_reconciled_without_double_commit), dispatch sonrası
  kesinti (test_interruption_after_dispatch_keeps_outcome_unknown, test_restart_after_dispatch_keeps_outcome_unknown),
  çakışan işlem (test_conflicting_execution_on_same_session_rejected), iptal (test_cancel_prevents_next_step),
  ön yüz akışı (e2e/test_run_lab_ui.py).
- **Bilinen sınırlamalar:** onaylı aksiyonlar yalnız lab; uzlaştırma liste sayımına dayanır; SSE yok (yoklama);
  run kilidi tek worker; hassas alana yazma (SecretRef) yok; input tabanlı combobox desteklenmiyor.
- **Kararlar ve ertelenenler:**
  - Setup: Ruling: git yok; commit adımları atlanır. Plan konumu kullanıcı isteğiyle docs/plans/.
  - Task 3: Ruling: ObservedControl'a `tag` alanı eklendi (input tabanlı combobox'ı açıkça desteklenmez saymak için) — maliyet: yok, varsayılan "".
  - Task 3: Ruling: sayfalama 'sonraki' kontrolü, durum metni ve liste kanıtı P2 envanterinden değil, hedefin frame'inde ad/rol tam eşleşmesi + tekillik kontrolüyle bulunur (link/list P2 türleri değil) — maliyet: birden fazla eşleşmede AmbiguousControl ile durur.
  - Task 3: Ruling: page.on("dialog") dinleyicisi eklendi; Playwright'ın varsayılan otomatik kapatması devre dışı, native dialog açık kalır ve yürütme durur — maliyet: görünmez modda native dialog açan sayfa, insan kapatana kadar bloke kalır.
  - Task 4: Ruling: aksiyon ön koşulu `requires_fields` eklendi (gönderilecek alanın değeri parametreye eşit olmalı) — devamda boş/yanlış içerik gönderilmesin — maliyet: yok.
  - Task 4: Ruling: devamda (resume) önceki başarılı ensure/find_record adımları bağlamı yeniden kurmak için tekrar uygulanır (durumları değişmez); onaylı aksiyonlar asla yeniden gönderilmez — maliyet: kullanıcı ekranı farklı bir kayda getirmişse ensure o ekrana yazar; record context doğrulaması P5/P6 katalog bağlamıyla güçlendirilmeli.
  - Task 4: Ruling: ensure adımlarında (UI-yerel, retry-safe) dispatched/verifying durumları adapter doğruladıktan sonra yazılır; checkpoint sırası yalnız onaylı (sunucuya yazan) aksiyonlar için zorunlu — maliyet: ensure ortasında çöküşte adım pending görünür (güvenli tekrar).
  - Task 4: Ruling: tıklamadan önce click(trial=True) ile actionability doğrulanır; gerçek tıklama hatası belirsiz sonuç sayılır — maliyet: yok.
  - Task 4: Ruling: native dialog testi gezinmeyi wait_until=commit ile yapar (alert load'u bloke eder ve kasıtlı kapatılmaz) — maliyet: yok.
  - Final: minor (deferred): GET /api/runs/{id}/events (SSE) yok; ekran 500 ms yoklama yapıyor.
  - Final: minor (deferred): POST /api/sessions/{id}/navigate run sırasında 409 alır (beklenen); ekran bunu yalnız hata metni olarak gösterir.
  - Final: minor (deferred): run checkpoint dosyaları RUN_DIRECTORY'de saklama süresi olmadan birikir.

### 2026-11-05 / P4 Katalog Tasarımcısı — COMPLETED (yerel taslak deposu, lab ekranları)
- **Plan:** docs/plans/2026-11-05-p4-catalog-designer.md · **ADR:** docs/adr/0005-p4-katalog-tasarimcisi.md
- **Yeni:** domain/{catalog,authoring}.py; application/{ports/drafts.py, services/designer.py};
  infrastructure/drafts/local_file.py; presentation/api/drafts.py; templates/designer.html; static/designer.js;
  testler: unit/{test_catalog_domain,test_authoring,test_draft_repository}.py, integration/browser/test_designer.py,
  integration/test_drafts_api.py, e2e/test_designer_ui.py.
- **Değişen:** errors (Draft*, TargetNotUnique, EffectNotAcknowledged; Pydantic doğrulama → 422 girdisiz,
  geçersiz durum → 409, bilinmeyen adım → 404), bootstrap, app, pages (/designer), runs/designer list_* adları, docs/09.
- **Testler:** `.venv/bin/pytest -q` → 349 passed; ruff/mypy temiz. Ekran e2e: taslak → parametre → adım (kural
  önerisi) → adaylar (Kefil + Başvuran birlikte) → seçim → şablon → ayrı onaylar (etki eksikken reddedildi) →
  deneme (sistem doğrulaması) → sonuç onayı → yeni oturum testi → "incelemeye hazır".
- **Sınırlamalar:** element reuse önerisi yalnız yerel taslaklardan; prior_output/secret_ref derlemede desteklenmez
  (açık hata); ekran lab başlangıç ekranlarını sunar (gerçek uygulama için başlangıç ekranı tanımı P8).

### 2026-11-05 / P5 MongoDB, onay ve tutarlı yayımlama — COMPLETED (yerel mongod 8.0.34)
- **Plan:** docs/plans/2026-11-05-p5-mongo-publish.md · **ADR:** docs/adr/0006-p5-mongo-onay-yayin.md
- **Yeni:** domain/release.py; application/{ports/catalog.py, services/publishing.py}; infrastructure/mongo/catalog_store.py;
  presentation/api/catalogs.py; templates/catalogs.html; static/catalogs.js; testler: unit/test_publishing.py,
  integration/mongo/{conftest,test_mongo_catalog}.py, e2e/test_publish_ui.py, tests/{fake_catalog_store,support_mongo}.py.
- **Değişen:** domain/catalog.py (definition/from_definition, approval), errors, bootstrap (Mongo store, PublishService),
  app (ensure_schema, kapanışta close), health (catalog_mongo bileşeni), designer ekranı (Onayla/Yayımla), base.html,
  settings (+CATALOG_BACKEND, CATALOG_ENVIRONMENT), .env.example, docs/05, docs/09, README, pyproject (pymongo==4.19.0,
  mongo marker), requirements.lock. test_app'in P0 istemcisi CATALOG_BACKEND=disabled kullanır; Mongo erişilemezken
  readiness 503 ayrı testte doğrulanır (kapsam daraltılmadı, eklendi).
- **Testler:** `.venv/bin/pytest -q` → 372 passed; `-m mongo` gerçek mongod ile (şema validator reddi, unique/content
  conflict, CAS, revizyon/manifest sonrası hata → aktif değişmez, eşzamanlı yayında aktif manifest tam, stale onay
  yazmaz, erişilemeyen Mongo 503); e2e: ekrandan onay + yayın + /catalogs incelemesi. ruff/mypy temiz.
- **BLOCKED/bekleyen:** kurumsal MongoDB (TLS/CA, auth, replica set) doğrulanmadı. "Çalışan run eski release'e bağlı
  kalır": release'ler değişmez ve id ile okunur (test_old_release_pinned_and_immutable); run'ın release'e pinlenmesi P6'da.

### 2026-11-05 / P6 İşlem Asistanı ve sınırlı LLM — COMPLETED (model doğrulaması BLOCKED)
- **Plan:** docs/plans/2026-11-05-p6-assistant-llm.md · **ADR:** docs/adr/0007-p6-asistan-ve-sinirli-llm.md
- **Yeni:** domain/assistant.py; application/services/assistant.py; infrastructure/llm/httpx_llm.py;
  presentation/api/assistant.py; templates/assistant.html; static/assistant.js; testler: unit/test_assistant_domain.py,
  integration/test_llm_adapter.py (yerel sahte OpenAI uyumlu sunucu), integration/browser/test_assistant.py,
  e2e/test_assistant_ui.py (tasarla→onayla→yayımla→asistanla çalıştır, gerçek geçici mongod).
- **Değişen:** ports/llm.py (complete_json, LLMUnavailableError, LLMRejected), unavailable LLM, bootstrap (HttpxLLM,
  AssistantService), runtime (Run.binding), RunService.create(binding), RunOut.binding, errors (ReleaseSuperseded),
  pages (/assistant), settings + .env.example + docs/05 (CATALOG_APPLICATION_ID), docs/09, README. P0'daki
  "LLM etkin ama adapter yok" testi uygulanan davranışa güncellendi (etkin+yapılandırılmış → kullanılabilir, açılışta
  bağlantı yok, readiness bozulmaz).
- **Testler:** `.venv/bin/pytest -q` → 393 passed; ruff/mypy temiz. Kapsanan: kural eşleşmesi + baştaki sıfırlar,
  eksik parametre sorusu, eşit eşleşmede soru, prompt injection işlem kümesini genişletmez, model bilinmeyen
  işlem/argüman → red, uydurulmuş argüman düşürülür, model erişilemez → dış fallback yok, bütçe aşımında çağrı yok,
  json_schema → şemasız aynı uç geri dönüşü, bearer/basic auth, zaman aşımı, run yayına pinli, eski yayınla yeni run 409,
  veri değiştiren işlem etki onayı ister.
- **BLOCKED:** gerçek kurum içi model (endpoint/auth/context/structured output) doğrulanmadı; işlem bazında yetki filtresi
  kurum yetki modeli gerektirir.

### 2026-11-05 / P7 Değişiklik/etki, bakım ve çalışma takibi — COMPLETED (lab kapsamında)
- **Plan:** docs/plans/2026-11-05-p7-impact-maintenance.md · **ADR:** docs/adr/0008-p7-etki-ve-izleme.md
- **Yeni:** domain/{impact,metrics}.py; application/services/impact.py; presentation/api/changes.py;
  templates/{changes,runs}.html; static/{changes,runs}.js; testler: unit/test_impact_metrics.py,
  integration/browser/test_impact.py, e2e/test_changes_ui.py. Lab: `guarantor_customer_label` senaryosu.
- **Testler:** `.venv/bin/pytest -q` → 403 passed; ruff/mypy temiz. Kapsanan: dinamik id değişimi değişiklik sayılmaz,
  etiket değişimi bulunamadı + benzer etiket önerisi, aynı anlamsal hedefi kullanan işlemlere etki, adapter/aksiyon
  bağımlılığı, onarım taslağı etkin yayını değiştirmez, metriklerde teknik toparlanma iş başarısından ayrı; ekranlar e2e.

### 2026-11-05 / P8 Kontrollü birleştirme ve gerçek ortam hazırlığı — PARTIAL
- **Plan:** docs/plans/2026-11-05-p8-composition-and-readiness.md · **ADR:** docs/adr/0009-p8-kontrollu-birlestirme.md
- **Yeni:** domain/{composition,templating}.py; evaluate_condition komutu; StepRecord.when guard'ı; Executor guard ve
  koşul değerlendirme; AssistantService.composite_preview/execute; /api/assistant/composite/*; /assistant'ta bayraklı
  "Birleşik görev" bölümü; docs/12_RUNNER_AND_INTEGRATION_CHECKLIST.md; docs/13_PEGA_VALIDATION_LOG.md (boş şablon).
  Ayarlar: COMPOSITION_ENABLED (false), COMPOSITION_MAX_DEPTH, COMPOSITION_MAX_ITEMS.
- **Son inceleme bulgusu (düzeltildi):** şablonlarda `str.format_map` → Python format öznitelik erişimi ve derlemede
  yakalanmayan KeyError (500). Güvenli `templating` modülüyle değiştirildi; test_template_rendering_is_not_python_format
  ve test_loop_variable_cannot_use_format_attribute_access önce kırmızı, sonra yeşil.
- **Testler:** `.venv/bin/pytest -q` → 413 passed (~92 sn); `-m browser` 100, `-m mongo` 12 (gerçek geçici mongod);
  ruff/mypy strict (93 dosya) temiz. Gösterilmemiş birleşik görev (iki yayımlanmış işlem + koşul + sınırlı döngü)
  lab'da çalıştı; sağlanmayan koşulun dalı atlandı. Bayrak kapalıyken bileşik plan ve evaluate_condition reddedilir.
- **Paketleme:** `pip wheel .` → agentask-0.1.0 wheel; şablon/statik dosyalar dahil, .env yok; temiz venv'de kurulup
  `agentask --check-config` ve `agentask-lab --check-config` çalıştı.
- **Son duman testi:** agentask-lab + agentask + geçici mongod: /health/ready 200 (catalog_mongo available), bütün
  ekranlar 200, /api/catalogs/releases çalışıyor; süreçler kapatıldı, kalan tarayıcı yok.
- **PARTIAL/BLOCKED:** uzak runner (lease/fencing) yalnız sözleşme olarak belgelendi; gerçek Pega/SSO, kurumsal Mongo ve
  on-prem LLM doğrulamaları BLOCKED (kurum erişimi yok). Git deposu olmadığı için commit yok.

### 2026-11-05 / Düzeltme aşaması 1 — R1 (denetim K2) ve R2 (denetim K1)
- Ayrıntı: docs/14_REMEDIATION_LOG.md. Denetim raporu değiştirilmedi.
- **R1:** domain/sensitive.py (şüphe tespiti, değer taşımaz); asistan şüphede modeli çağırmaz, şüpheli değeri
  bağlamaz, açıklama ister; önizleme/yürütme/bileşik plan hassas argümanı kalıcılaştırmadan reddeder.
  Yeni testler: unit/test_sensitive.py (16), integration/test_assistant_sensitive.py (7, gerçek payload ikameyle).
- **R2:** geçici doğrulama oturumu (purpose=verification, BROWSER_MAX_VERIFICATION_SESSIONS_PER_USER=1, toplam
  kapasite içinde, her durumda kapanır, zaman aşımında run iptal edilir); varsayılan etkileşimli limit değişmedi.
  Yeni testler: unit/test_browser_sessions.py (+4), integration/browser/test_fresh_session_test.py (4);
  e2e/test_designer_ui.py override'sız.
- **Testler:** `.venv/bin/pytest -q -rs` → 444 passed, 0 skipped (exit 0); ruff/format/mypy temiz.
- **Açık kalan:** K3 (lease/fencing), K4 (artefakt deposu), K5 (Screen/automation_runs), K6 (aksiyonlar kodda),
  K7 (yetki modeli); çok sayfada eşzamanlı etkileşimli oturum (R2 sınırlaması).

### 2026-11-05 / Düzeltme aşaması 2 — R2B (sayfalar arası oturum)
- Ayrıntı: docs/14_REMEDIATION_LOG.md (R2B). Varsayılan oturum limitleri korundu (etkileşimli 1/kullanıcı).
- Doğrulama oturumu public uçlarda kullanılamaz (404); GET /api/sessions/overview ve /{id}; Designer/Assistant/Changes
  ortak oturum paneli (açık seçim, backend doğrulaması, kota görünümü, sessiz açma/gezinme yok).
- E2E override'ları (kullanıcı başına limit) kaldırıldı; yeni tests/e2e/test_cross_page_sessions.py varsayılan ayarlarla geçti.
- **Testler:** `.venv/bin/pytest -q -rs` → 449 passed, 0 skipped (exit 0); ruff/format/mypy temiz.

### 2026-11-06 / Düzeltme kaydı Aşama 3 — Yerel MongoDB otomatik başlatma
- Ayrıntı: docs/14_REMEDIATION_LOG.md (Aşama 3). Uygulama yalnız MONGO_URI ile bağlanır; LOCAL_MONGO_AUTOSTART
  (varsayılan false, yalnız development'ta true) ile sökülebilir tools/local_mongo başlatıcısı Compose'u yönetir.
- .env.example'daki kullanıcı eklemeleri korundu (yer tutucu MONGO_* satırları yorum bloğuna alındı; gerekçe kayıtta).
- **Testler:** `.venv/bin/pytest -q -rs` → 473 passed, 0 skipped (gerçek Docker 29.9.2 testleri dahil); ruff/format/mypy
  temiz; araç dosyaları kaldırılmışken uygulama ve Mongo testleri geçti.
- **Test edilmeyen:** yerel root auth ve backup/restore gerçek Docker ile; Windows/Podman.

### Devam noktası (2026-11-06, gün sonu)
**Tamamlananlar:**
- P0–P8 (P6/P8 PARTIAL, kurum erişimi BLOCKED).
- Denetim raporu: docs/12.
- Düzeltmeler: R1 (hassas veri), R2 (yeni oturum testi kotası), R2B (sayfalar arası ortak oturum paneli) ve Aşama 3
  (yerel MongoDB otomatik başlatma). Ayrıntılar docs/14'te.
- Son tam koşu: `.venv/bin/pytest -q -rs` → 473 passed, 0 skipped. ruff, format ve mypy temiz.

**Sonraki adım (öneri sırası):**
1. Denetim bulgularından K3–K7.
2. /designer/targets ve /designer/runs sayfalarını ortak oturum paneline geçirmek.
3. Kurum gerektirmeyen işler: MongoDB run deposu adapteri, SSE ilerleme, uzak runner lease/fencing, shadow DOM envanteri.
4. Yerel Mongo aracında backup/restore'u gerçek Docker testiyle doğrulamak.

**Yeniden başlatma (proje kökünde):**
```bash
.venv/bin/agentask --check-config        # yapılandırma doğrulaması
.venv/bin/agentask-lab                   # deney uygulaması: http://127.0.0.1:8100 (+ :8101)
.venv/bin/agentask                       # ana uygulama (ayrı terminal): http://127.0.0.1:8000
```
- Varsayılan `LOCAL_MONGO_AUTOSTART=false` ile uygulama `MONGO_URI`'deki mevcut Mongo'yu kullanır. Bu makinede
  Homebrew mongod 127.0.0.1:27017'de çalışıyor.
- Docker ile yönetilen yerel Mongo istenirse:
  - `.env`'de `APP_ENV=development` ve `LOCAL_MONGO_AUTOSTART=true` olmalı.
  - `LOCAL_MONGO_PORT` boş bir port olmalı (27017 doluysa ör. 27018) ve `MONGO_URI` aynı portu göstermeli.
  - Docker Desktop açık olmalı.
  - Komutlar:
    ```bash
    .venv/bin/python -m tools.local_mongo dev      # Mongo'yu hazırlar, ping sonrası uygulamayı başlatır
    .venv/bin/python -m tools.local_mongo status
    .venv/bin/python -m tools.local_mongo stop     # veriyi korur
    ```
- **Testler:**
  ```bash
  .venv/bin/pytest -q -rs                                   # tamamı
  .venv/bin/pytest -q -rs -m docker tests/integration/docker  # gerçek Docker (daemon yoksa BLOCKED/skip)
  .venv/bin/ruff check src tests tools && .venv/bin/ruff format --check src tests tools && .venv/bin/mypy
  ```

### 2026-11-06 / Düzeltme aşaması R3 — Ekran tanımı ve eski katalog geçişi — COMPLETED (lab kapsamında)
- **Ayrıntı:** docs/14_REMEDIATION_LOG.md "R3 (2026-11-06)" bölümü (değişen dosyalar, senaryo/test tablosu, kalan
  sınırlamalar, arayüz doğrulama adımları). ADR: docs/adr/0010-r3-ekran-tanimi-ve-gecis.md.
- **Davranış:**
  - Sürümlü ScreenDef (anlamsal işaretler, "olmamalı" işaretleri, işaretle kanıtlanan bölgeler) ve ortak karar
    çekirdeği (Designer/Assistant/Changes).
  - Plan assert_screen ile başlar; her sayfa adımından önce yeniden doğrulama yapılır; tanınmazsa yazma/tıklama
    olmadan durulur.
  - catalog_screens ve manifest.screens eklendi; onay hash'i screen_ref ile ekranı kapsar.
  - Eski yayın 409 migration_required ile reddedilir. Geçiş: taslak → ekran → yeni oturum testi → onay → r2.
    r1 korunur; otomatik geçiş yoktur.
- **U1–U3 düzeltildi:**
  - U1: taslak listesi yenilenir.
  - U2: alan bazlı Türkçe nedenler, değer yansıtılmaz.
  - U3: önizlemede bağlı değerler gösterilir, hassas değerler maskelenir.
- **Testler:**
  - `.venv/bin/pytest -q -rs` → 506 passed, 3 skipped (exit 0). Atlanan 3 test `-m docker`: BLOCKED, Docker daemon
    kapalı.
  - ruff, format ve mypy (102 dosya) temiz.
  - R3 tarayıcı/E2E grubu 3× kararlı; mutasyon kontrolünde 5 test düştü (testlerin koruması doğrulandı).
- **Yapılandırma:** yeni ortam ayarı yok; `.env`, `.env.example` ve `LOCAL_MONGO_AUTOSTART=false` değişmedi.
- **Sıradaki:**
  - Kullanıcının arayüz doğrulaması (docs/14 adımları).
  - K5'in kalan kısmı: Mongo automation_runs.
  - Çok ekranlı işlem / ekran geçişi tanımı.
  - "Olmamalı" işaretini gözlemle seçme.
  - K3, K4, K6.

### 2026-11-06 / Düzeltme aşaması R4 — Çok ekranlı işlemler ve kontrollü geçişler — COMPLETED (lab)
- **Ayrıntı:** docs/14_REMEDIATION_LOG.md "R4" bölümü (davranış, değişen dosyalar, durum/test tablosu, kalan
  sınırlamalar, arayüz doğrulama adımları). Plan: docs/plans/2026-11-06-r4-multi-screen.md. ADR 0011.
- **Davranış:**
  - catalog-v3: ekranlar, onaylı geçişler (kaynak/hedef/tetikleyici/tamamlanma) ve kayıt bağlamı. Tek ekranlı v2
    içeriği ve hash'i değişmez.
  - Geçiş tek tetiklenir, hedef sınırlı süre beklenir, yeniden tıklama yoktur.
  - Hata sınıfları: `TRANSITION_TIMEOUT`, `UNEXPECTED_SCREEN`, `RECORD_CONTEXT_MISMATCH`,
    `TRANSITION_NOT_COMPLETED`.
  - Resume geçiş ve aksiyonları yeniden oynatmaz.
  - Tasarımcı: ekran/geçiş/bağlam yönetimi, açık onaylı geçiş denemesi. Asistan: rota önizlemesi. Changes:
    ekran ve tetikleyici bağımlılığı.
- **Testler:**
  - `.venv/bin/pytest -q -rs` → 539 passed, 3 skipped (exit 0). Atlanan 3 test `-m docker`: BLOCKED, daemon
    kapalı.
  - ruff, format ve mypy (103 dosya) temiz.
  - R4/R3 tarayıcı/E2E grubu 3× kararlı; 3 mutasyonun 3'ü yakalandı.
- **Yapılandırma:** yeni ortam ayarı yok; `.env`, `.env.example` ve `LOCAL_MONGO_AUTOSTART=false` değişmedi.
- **Kullanıcı verisi:** `kefil_musteri_no` r1/r2 dokunulmadı.
- **Sıradaki:**
  - Kullanıcının R4 arayüz doğrulaması (docs/14 R4 adımları).
  - Dallanan/koşullu geçişler.
  - Tablo satırı kayıt bağlamı.
  - K5 automation_runs (Mongo), K3, K4, K6.

### 2026-11-07 / Akış Tasarımcısı prototipi (/prototype/designer) — PROTOTİP
- **Karar:** Kullanıcı R4 manuel kabulünü beklemeye aldı (tamamlanmadı; `teminat_gir` taslağı korunuyor). Öncelik:
  teknik yeterliği düşük analist için sade Akış Tasarımcısı prototipi.
- **Kapsam:** yalnız etkileşimli prototip, ayrı rota. Mevcut ekranlar, backend uçları, katalog sözleşmesi, `.env`,
  MongoDB, taslaklar ve yayınlar değişmedi. Durum yalnız tarayıcı belleğinde; sayfa yenilenince sıfırlanır.
  Hiçbir `/api` çağrısı, dış CDN/font yok. Mimari değişiklik olmadığı için ADR eklenmedi.
- **Çalışan (temsili uygulamada):** Alan doldur (alan seçme, öneri, üç değer kaynağı, alan yanında eksik/hata),
  Ekrana geç (beklenen ekranı kullanıcı belirtir; iş etkisi beyanı zorunlu; tek basış, otomatik tekrar yok),
  Akış çağır (seçili adımlardan yeniden kullanılabilir bileşen, başka akışta kullanım), adım/akış denemesi,
  hata/bekleme senaryoları, yalnız gösterim amaçlı yayın. Seçim yap / Düğmeye bas / Kayıt bul / Bilgi oku
  "Bu prototipte yok" olarak işaretli; sahte sonuç üretilmez.
- **Değişen dosyalar:** `src/agentask/presentation/pages.py` (rota), `templates/prototype_designer.html`,
  `static/prototype_designer.css`, `static/prototype_designer.js`, `tests/e2e/test_prototype_designer_ui.py`,
  `tests/integration/test_app.py` (rol testi), `docs/STATUS.md`.
- **Testler:**
  - `.venv/bin/pytest -q tests/e2e/test_prototype_designer_ui.py tests/integration/test_app.py
    tests/e2e/test_designer_ui.py` → 28 passed; prototip e2e (2 test) son değişiklikten sonra yeniden geçti.
  - ruff, format ve mypy (105 dosya) temiz. Geniş backend testleri değişiklik gerektirmediği için yeniden
    çalıştırılmadı.
  - Görsel inceleme 1440/1024/390 px: yatay taşma yok; sekme sırası görsel sırayla uyumlu.
- **Sıradaki:** kullanıcı denemesi ve geri bildirim. Gerçek sisteme entegrasyon başlatılmadı.

### 2026-11-07 / Akış Tasarımcısı prototipi — görsel tasarım ve sadeleştirme — PROTOTİP
- **Kapsam:** yalnız `/prototype/designer`. Backend, MongoDB, katalog sözleşmesi, mevcut tasarımcı, `.env` ve
  `.env.example` değişmedi; yeni bağımlılık ve yeni ortam ayarı yok. Font (sistem fontları), ikon (satır içi SVG)
  ve stiller yerel.
- **Görsel:** kullanıcının referans görselindeki koyu lacivert/turkuaz/mor dil. Turkuaz: ana işlemler ve seçili
  adım; mor: öneriler. Ölçülü gradient/ışık; sahte metrik veya grafik eklenmedi. Açık/koyu tema düğmesi
  (varsayılan sistem tercihi, seçim yalnız bellekte). Temsili uygulama her iki temada açık renkli pencere.
- **Sadeleştirme:**
  - Kart: kısa başlık + değer satırı + tek durum etiketi (Hazır / N eksik / N sorun).
  - Sağ panel: önce "1 Hangi alan?", "2 Değer nereden gelsin?". Ad, açıklama, not ve teknik bilgiler tek
    "Ayrıntılar" bölümünde (kapalı, düzenlenebilir). Adım adı artık zorunlu değil (boşsa öneri kullanılır).
  - Bölüm bağlamlı önerilen soru: "Müşterinin müşteri numarası nedir?", "Kefilin müşteri numarası nedir?";
    kullanıcı değiştirebilir. Parametre adı otomatik, kullanıcıdan istenmez.
  - Alan seçimi iki yol: "Önerilen alanlardan seç" (o ekranda yazılabilir ve akışta kullanılmamış alanlar) veya
    "Ekrandan kendim seçeyim" (önerilerde olmayan herhangi bir alan). Seçim temsili uygulamada iş eylemi yapmaz.
  - Kısa prototip bildirimi; desteklenmeyen bileşenler "Bu prototipte henüz yok" başlığı altında.
- **Değişen dosyalar:** `src/agentask/presentation/static/prototype_designer.css` (yeniden yazıldı),
  `static/prototype_designer.js`, `templates/prototype_designer.html`, `tests/e2e/test_prototype_designer_ui.py`,
  `docs/STATUS.md`, `docs/10_PROGRESS.md`.
- **Testler:**
  - `.venv/bin/pytest -q tests/e2e/test_prototype_designer_ui.py tests/integration/test_app.py
    tests/e2e/test_designer_ui.py` → 28 passed. E2E iki seçim yolunu, seçim sonrası alan/bölüm/tür/soru
    güncellemesini, Ayrıntılar'ı, temayı, deneme/yayın ayrımını, denemenin eskimesini ve bileşen akışını kapsar.
  - ruff, format ve mypy (105 dosya) temiz. Geniş backend testleri değişiklik olmadığı için çalıştırılmadı.
  - Görsel inceleme: açık 1440 ve 1024 px, koyu 1440 ve 390 px; yatay taşma yok. Klavye: sağ panelde sekme
    sırası görsel sırayla uyumlu, Esc diyaloğu kapatıp odağı geri verir.
  - Çalıştırılmayanlar: ekran okuyucu ile manuel deneme, Firefox/Safari, otomatik kontrast ölçüm aracı.
- **Sıradaki:** kullanıcı denemesi ve geri bildirim. Gerçek tarayıcı/model entegrasyonu başlatılmadı.

### 2026-11-07 / Vazgeç/geri dönüş + yapılandırılmış uygulama listesi — COMPLETED (lab/test ikameleri)
- **Kapsam:** prototipte vazgeçme ve geri dönüş; `AUTOMATION_APPLICATIONS_JSON` (ADR 0012); İşlem Asistanı'nda
  gerçek uygulama kapsamı; S3 kararı (ADR 0013, bağlantı yok).
- **Prototip (`/prototype/designer`, yalnız bellek):**
  - Akışlar görünümü, "Akışlara dön", "Sayfada sakla" (kalıcı kayıt olmadığı her yerde belirtiliyor).
  - Değişiklik varsa "Düzenlemeye devam et" / "Değişiklikleri bırak"; değişiklik yoksa onay sorulmuyor.
    Saklanmamış yeni akış bırakılırsa oluşturulmuyor.
  - Bileşen oluşturma iptali kaynak akışı değiştirmiyor; bir şey yazıldıysa aynı iki seçenek soruluyor.
  - Uygulama seçimi ekran seçiminden ayrı. Kayıp varsa değiştirmeden önce soruluyor; değişince önceki
    uygulamanın hedefleri, bileşen bağlantıları, deneme sonucu ve yayın gösterimi temizleniyor. Bileşenler
    uygulamaya bağlı.
  - Deneme durdurma: sonraki adımlar başlatılmıyor; tamamlanan adımlar geri alınmış gibi gösterilmiyor; basılmış
    ama doğrulanmamış düğme açıkça belirtiliyor.
  - `beforeunload` kayıp uyarısı: metni tarayıcı belirler; sayfayla etkileşim yoksa gösterilmeyebilir.
- **İşlem Asistanı:**
  - Uygulama seçimi ekran seçiminden ayrı. Her istek zorunlu `application_id` taşıyor ve sunucuda doğrulanıyor;
    bilinmeyen kimlik 422.
  - Katalog, plan ve run seçilen uygulamanın yayınından derleniyor; başka uygulamanın planı kullanılamıyor.
  - Run, oturum uygulamanın origin'inde değilse başlamıyor (409).
  - Çalışma sürerken uygulama değiştirilemiyor; değişince yorum ve plan temizleniyor.
  - Boş liste için açık boş durum gösteriliyor.
- **Değişen dosyalar:**
  - Kod: `src/agentask/domain/applications.py` (yeni), `config/settings.py`, `bootstrap.py`,
    `application/errors.py`, `application/services/assistant.py`, `application/services/runs.py`,
    `presentation/errors.py`, `presentation/api/assistant.py`, `presentation/pages.py`.
  - Arayüz: `templates/assistant.html`, `static/assistant.js`, `templates/prototype_designer.html`,
    `static/prototype_designer.js`, `static/prototype_designer.css`.
  - Örnek yapılandırma: `.env.example`.
  - Testler: `tests/unit/test_application_scope.py` (yeni), `tests/unit/test_settings.py`,
    `tests/integration/test_app.py`, `tests/e2e/test_prototype_designer_ui.py`,
    `tests/e2e/test_cross_page_sessions.py`, `tests/integration/browser/helpers.py`,
    `tests/integration/browser/conftest.py`, `tests/integration/test_sessions_api.py`.
  - Belgeler: `docs/05_CONFIGURATION.md`, `docs/adr/0012-*.md`, `docs/adr/0013-*.md`, `docs/STATUS.md`.
- **Testler:**
  - `.venv/bin/pytest -q -rs` → 570 passed, 3 skipped (Docker testleri BLOCKED, daemon kapalı).
  - ruff check, ruff format --check ve mypy (106 dosya) temiz.
  - Görsel inceleme: koyu 1440 px ve açık 390 px; yatay taşma yok.
- **Yapılandırma:** yeni zorunlu anahtar `AUTOMATION_APPLICATIONS_JSON`. `.env.example`'a temsili yerel örnek
  eklendi. Kullanıcının eklediği `nar`/`opera` satırı silinmedi; yorum satırı olarak gerçek ortam örneği
  bölümüne taşındı. Gerekçe: ikinci tanım yerel örneği eziyordu ve origin/katalog eşleşmesi olmadan örnek
  dosya doğrulamadan geçmiyordu. Gerçek `.env` okunmadı ve değiştirilmedi.
- **Sınırlar:**
  - Katalog Tasarımcısı, değişiklik/etki ve yayın hâlâ tek uygulama (`CATALOG_APPLICATION_ID`).
  - Prototip uygulama seçimi gerçek tarayıcı açmaz; ekranlar temsilidir.
  - Gerçek Pega/SSO yok; S3 bağlanmadı.

### 2026-11-07 / Tasarımcı → gerçek oturumdan alan seçimi; dinamik ekran ve pencere bağlamı — COMPLETED (lab)
- **Karar:** çok uygulamalı geliştirme beklemede. Tek uygulamada yeni Akış Tasarımcısı gerçek Playwright oturumuna
  bağlandı. Paralel motor yok; mevcut gözlem, çözümleme, picker, yürütücü ve uzlaştırma kullanıldı. ADR 0014.
- **Tasarımcı:**
  - "Alan seçme kaynağı": temsili ekranlar / gerçek oturum.
  - Oturum seç/aç, uygulamayı oturumda aç.
  - "Ekrandaki alanları listele" (gözlem) veya "Tarayıcıda kendim seçeyim" (picker; vazgeç, 120 sn sınırı,
    sayfa kapanınca durdurma).
  - Seçimden sonra semantik yeniden çözüm ve vurgulama; "Alanı yeniden bul (yazmadan)".
  - Eksik bilgi (etiket, bölüm, ekran) uydurulmuyor, açıklanıyor.
  - Kesinti kutusu (tarayıcı dialog'u, yeni pencere) yalnız açık kararla kapatıyor.
  - Gerçek adımlar temsili denemeye katılmıyor.
  - Durum sözcükleri: "Ekran bekleniyor", "Alan yeniden bulunuyor", "Açılan pencere bekleniyor", "Sonuç
    doğrulanıyor", "Müdahale gerekiyor" (İşlem Asistanı çalıştırma satırında da).
- **Çalışma zamanı:**
  - Etkileşim bağlamı (kapalı pencere, aktif modal arkası, kaplayan katman, inert, birden fazla aktif pencere).
  - Ekran işaretleri ve kayıt bağlamı için varlık kanıtı.
  - Ekran tanımlı pencere beklenen pencere sayılıyor.
  - Yeni pencere/sekme izleniyor ve duruluyor (`NEW_WINDOW`).
  - Engelli hedefte sınırlı bekleme, ardından `TARGET_BLOCKED`.
  - Picker'da odak/seçim temizliği ve IME/yapıştırma engeli.
  - Lab'a `/pages/popups` eklendi.
- **Değişen dosyalar:**
  - Kod: `domain/observation.py`, `domain/targeting.py`, `domain/screens.py`, `domain/actions.py`,
    `application/ports/observation.py`, `application/services/observation.py`, `application/services/executor.py`.
  - Tarayıcı ve API: `infrastructure/browser/{inventory_js,picker_js,observer}.py`, `presentation/api/observation.py`,
    `presentation/pages.py`.
  - Arayüz: `templates/prototype_designer.html`, `static/prototype_designer.{js,css}`, `static/assistant.js`.
  - Lab: `agentask_lab/app.py`, `agentask_lab/templates/popups.html`.
  - Testler: `tests/integration/browser/test_popups_dynamic.py` (yeni), `tests/e2e/test_prototype_real_session_ui.py`
    (yeni), `tests/unit/test_targeting.py`, `tests/integration/test_sessions_api.py`, `tests/integration/test_app.py`,
    `tests/e2e/test_prototype_designer_ui.py`.
  - Belgeler: `docs/adr/0014-*.md`, `docs/STATUS.md`.
- **Testler:**
  - `.venv/bin/pytest -q -rs` → 588 passed, 2 failed, 3 skipped (Docker BLOCKED).
  - İki başarısızlık yalnız `.env.example`'ı sınayan testler (`test_env_example_lists_both_configured_applications`,
    `test_process_environment_alone_is_sufficient`). Neden, dosyanın sonuna sonradan eklenen üç satır (125–127):
    önceki tanımları eziyor (ikinci uygulama düşüyor) ve tek tırnaklı `TARGET_ALLOWED_ORIGINS` doğrudan process
    env olarak verildiğinde JSON hatası veriyor. Kullanıcının değişikliği olduğu için geri alınmadı; kullanıcıya
    bildirildi.
  - ruff, format ve mypy (106 dosya) temiz.
  - Lab senaryoları:
    - yeniden çizilen element ve frame (mevcut);
    - ilgisiz DOM değişikliği;
    - gizli/görünür modalda aynı isimli alan;
    - aktif modal arkası;
    - beklenen ve beklenmeyen pencere;
    - iki etkin pencere;
    - kalıcı ve geçici katman;
    - yeni pencere;
    - tarayıcı onay penceresi;
    - modal içinde seçim;
    - yanıt kaybında mükerrer gönderim olmaması (mevcut);
    - iptal/zaman aşımı sonrası picker temizliği;
    - oturum sahipliği.
- **Sınırlar:**
  - Gerçek Pega/SSO denenmedi.
  - Beklenen yeni pencereye geçiş desteklenmiyor (yalnız durur).
  - Overlay tespiti sezgisel (ADR 0014).
  - Gerçek oturumdan seçilen adımların yürütmesi bu prototipten değil, mevcut Katalog Tasarımcısı/İşlem Asistanı
    yolundan.

### 2026-11-07 / Kalanların tamamlanması: .env.example, katman güvenilirliği, kimliğe bağlı kesinti kararları — COMPLETED (lab)
- **.env.example:**
  - Yinelenen dört anahtar (`MONGO_URI`, `CATALOG_BACKEND`, `LLM_ENABLED`, `BROWSER_HEADLESS`; değerleri aynıydı)
    tekilleştirildi.
  - Etkin uygulama örneği tek uygulamalı yerel lab. İki uygulamalı lab ve `nar`/`opera` örnekleri yorum satırı.
  - Gerçek `.env` okunmadı/değiştirilmedi.
- **Tırnak sorunu:**
  - dotenv okuma tırnağı kaldırır, doğrudan ortam değişkeni kaldırmaz.
  - Test yardımcısı örneği artık uygulamanın dotenv kurallarıyla okuyor.
  - `load_settings` çözülemeyen karmaşık değerde ham `SettingsError` yerine redakte `ConfigurationError` veriyor.
    Doğrulama gevşetilmedi.
  - Çok uygulamalı davranış testleri listeyi açıkça veriyor.
- **Katman:**
  - Boyuttan bağımsız örtme kuralı.
  - Eylem anında kaydırma + yeniden denetim (`TargetBlocked`); force/JS tıklaması yok (statik test).
  - Lab'a küçük katman (`?cover=1`, `labAddCover`) ve aldatıcı pencere (`?modal=decoy`) eklendi.
- **Beklenen pencere:** bölge adı + işaretin pencere içinde ve etkin olduğu güncel gözlemle doğrulanıyor.
  Sözleşme sınırı ADR 0014 ekinde.
- **Kesinti kararları:**
  - Kimliğe bağlı; eski/kısmi karar uygulanmıyor (409).
  - Karar kilidi var; ana sayfa korunuyor.
  - Arayüz kapsamı listeliyor.
  - Kapanmış oturumda 404.
- **Değişen dosyalar:**
  - Yapılandırma ve kod: `.env.example`, `src/agentask/config/settings.py`, `application/controls.py`,
    `application/errors.py`, `application/ports/observation.py`, `application/services/{observation,executor}.py`.
  - Tarayıcı ve API: `infrastructure/browser/{inventory_js,driver,observer}.py`, `presentation/api/observation.py`,
    `presentation/errors.py`.
  - Arayüz: `static/prototype_designer.js`.
  - Lab: `agentask_lab/{app.py,templates/popups.html}`.
  - Testler: `tests/conftest.py`, `tests/unit/{test_settings,test_targeting}.py`,
    `tests/integration/{test_app,test_sessions_api}.py`, `tests/integration/browser/test_popups_dynamic.py`,
    `tests/e2e/test_prototype_designer_ui.py`.
  - Belgeler: `docs/05_CONFIGURATION.md`, `docs/adr/0014-*.md`, `docs/STATUS.md`.
- **Testler:**
  - `.venv/bin/pytest -q -rs` → 600 passed, 3 skipped (Docker BLOCKED); başarısız test yok.
  - ruff, format ve mypy (106 dosya) temiz.
- **Sınırlar:**
  - Gerçek Pega/SSO denenmedi.
  - İsteğe bağlı/koşullu pencere sözleşmede yok.
  - Beklenen yeni pencereye geçiş yok.

### 2026-11-07 / Ürün deneyimi ana planı (A–G) — PARTIAL — GÜNCEL
- **Plan:** `docs/plans/2026-11-07-urun-deneyimi-ana-plan.md`.
- **Durum:**
  - A: DONE.
  - B: DONE.
  - C: PARTIAL.
  - D: PARTIAL.
  - E: TODO.
  - F: PARTIAL.
  - G: PARTIAL; kurum S3 bağlantısı BLOCKED.
  - Gerçek ortam kabul belgesi: DONE (`docs/15_REAL_ENV_ACCEPTANCE.md`); gerçek Pega/SSO kabulü BLOCKED.
- **Başlangıç doğrulaması:** git deposu yok (git işlemi yapılmadı); tam takım 600 passed, 3 skipped.
- **Yapılanlar:**
  - **Yeni tasarımcı:**
    - Tek uygulamada uygulama adı gösteriliyor.
    - "Taslağı kaydet": mevcut `/api/drafts`; hedef kaydetme anında yeniden çözülüyor, kod üretimli kimlikler,
      bağlamlı soru parametre başlığı.
    - Kayıtlı taslakları aç; düzenlenemeyen adımlı taslak salt okunur.
    - "Dene, onayla ve yayımla" → `/designer?draft=` (mevcut tasarımcıya derin bağlantı).
    - Düzeltme: "Sayfada sakla" düğmesi olay nesnesini sessiz mod sanıyordu.
  - **Asistan (ADR 0015):**
    - 5 bölümlü sade görünüm; hazır işlemler.
    - Model kullanımı politikaya taşındı (`use_model` yoksa `LLM_ENABLED` ve erişilebilirlik).
    - Teknik ayrıntılar katlanır.
    - Özet sonrası bilgi değişirse başlatma engellenir.
    - Durum sözcükleri; düğmeler "Başlat/Durdur".
  - **Depolama (ADR 0016):** port, yerel adaptör, servis, sahip kontrollü indirme; yeni ayar `ARTIFACT_MAX_BYTES`.
- **Değişen başlıca dosyalar:**
  - Yeni tasarımcı: `static/prototype_designer.{js,css}`, `templates/prototype_designer.html`, `static/designer.js`
    (derin bağlantı).
  - Asistan: `templates/assistant.html`, `static/assistant.js`, `api/assistant.py`.
  - Depolama: `domain/artifacts.py`, `ports/artifacts.py`, `services/artifacts.py`,
    `infrastructure/artifacts/local_file.py`, `api/artifacts.py`.
  - Çekirdek ve yapılandırma: `presentation/{app,errors}.py`, `bootstrap.py`, `config/settings.py`,
    `.env.example`, `docs/05_CONFIGURATION.md`.
  - Testler: `tests/unit/test_artifacts.py`, `tests/integration/test_drafts_persistence.py`,
    `tests/e2e/test_prototype_real_session_ui.py`, `tests/e2e/test_assistant_ui.py`; "Başlat" metni için
    `tests/e2e/{test_cross_page_sessions,test_r3_migration_ui,test_r4_multi_screen_ui}.py`.
  - Belgeler: `docs/adr/0015-*.md`, `docs/adr/0016-*.md`, `docs/15_REAL_ENV_ACCEPTANCE.md`, ana plan.
- **Testler:**
  - `.venv/bin/pytest -q -rs` → 614 passed, 3 skipped (Docker BLOCKED); başarısız test yok.
  - ruff, format ve mypy (112 dosya) temiz.
- **Kalanlar:**
  - C: önceki adım çıktısı, sonuç ve iş etkisi soruları, ekran tanımı.
  - D: yeni tasarımcı içinde gerçek deneme.
  - E: tamamı.
  - F: modelin akış ve bileşenlerden çok adımlı plan önermesi.
  - G: S3 adaptörü (BLOCKED), Mongo metadata, kanıt üreticisi.

### STATUS.md arşivi (2026-11-07 sadeleştirme öncesi; tarihsel)

> # Güncel durum (tek devam noktası) — 2026-11-07
>
> Tarihsel ayrıntılar: [docs/14_REMEDIATION_LOG.md](14_REMEDIATION_LOG.md) (R1–R4),
> [docs/10_PROGRESS.md](10_PROGRESS.md) (P0–P8 ve aşama kayıtları),
> [docs/12_IMPLEMENTATION_AUDIT.md](12_IMPLEMENTATION_AUDIT.md) (denetim).
>
> ## Şu anda çalışan özellikler (deney uygulamasında)
> - **Katalog Tasarımcısı:** modelsiz adım adım işlem hazırlama, hedef önerisi/seçimi, ayrı onaylar, deneme, yeni
>   oturum testi, hash'e bağlı onay ve yayın.
> - **Ekran tanımı (R3):** anlamsal tanıma işaretleri, "olmamalı" işaretleri ve bölgeler. Ekran tanınmazsa işlem
>   yapılmaz. Eski ekransız yayınlar için geçiş akışı.
> - **Çok ekranlı işlemler (R4):** onaylı geçişler, kayıt bağlamı (ör. Vaka No) ve devam ettirmede tekrar oynatmama.
> - **İşlem Asistanı:** kural tabanlı yorum (model kapalı), sunucuda derlenen plan, bağlı değer önizlemesi, yayına
>   pinlenmiş çalıştırma.
> - **Değişiklikler:** ekran ve eleman karşılaştırması, etki analizi, onarım taslağı.
> - **Yayın:** MongoDB'de değişmez revizyonlar ve manifest. Yerel Mongo `LOCAL_MONGO_AUTOSTART=false` ile mevcut
>   servisten kullanılıyor.
>
> ## Otomatik testlerle doğrulananlar
> - **Son tam koşu:** `.venv/bin/pytest -q -rs` → 539 passed, 3 skipped. Atlananlar Docker testleri (BLOCKED, daemon
>   kapalı).
> - **Geliştirme kontrolü:** `.venv/bin/python -m tools.dev_check` → BAŞARILI (lint, format, typecheck ve ilgili
>   testler: 445 passed).
> - **R4 senaryoları:**
>   - üç ekranlı akış, SPA ve iç içe frame;
>   - gecikmeli hedef (tek tetikleme), zaman aşımı, beklenmeyen ekran;
>   - yinelenen kanıt, eksik tarama, yanlış vaka;
>   - yanıtı kaybolan yazma (tekrar gönderim yok);
>   - devam ettirme;
>   - yalnız yasak işaret eklenmiş ekranın reddi;
>   - v2 regresyonu, MongoDB roundtrip ve arayüz uçtan uca akışı.
>
>   Ayrıntı: docs/14 R4 tablosu.
>
> ## Kullanıcının doğruladıkları (kullanıcı bildirimi)
> - **R3:**
>   - `kefil_musteri_no` r2 geçişi yayımlandı.
>   - Doğru ekranda 00456 yalnız Kefil alanına yazıldı.
>   - Benzer yanlış ekranda `SCREEN_NOT_RECOGNIZED` ile durdu; ret zorunlu işaretin yokluğundan geldi.
> - **R4 (kısmi):**
>   - `teminat_gir` taslağı oluşturuldu; üç parametre, iki ekran ve `teminata_gec` tanımlandı.
>   - Müşteri numarası yazma adımı denendi ve onaylandı; Devam geçişi denemesi geçti.
>   - **R4 manuel kabulü tamamlanmadı.**
>
> ## Açık sorunlar ve gerçek ortamda denenmeyenler
> - **Gerçek ortam (BLOCKED):** gerçek Pega/SSO, kurumsal MongoDB (TLS/kimlik doğrulama), kurum içi LLM ve Docker
>   testleri.
> - **Denetimden açık kalanlar:** K3 (lease/fencing, tek worker), K4 (kanıt deposu), K5 (`automation_runs` Mongo'da
>   değil), K6 (aksiyonlar kodda), K7 (yetki modeli).
> - **R4 sınırları:**
>   - doğrusal rota (dallanma yok);
>   - tetikleyici yalnız düğme veya sekme;
>   - zaman aşımında otomatik devam yok;
>   - kayıt bağlamı yalnız alan eşitliğine dayanıyor.
> - **Arayüz:**
>   - Katalog Tasarımcısı tek uzun sayfa ve karmaşık; sadeleştirme planı:
>     [docs/plans/2026-11-06-designer-simplification.md](plans/2026-11-06-designer-simplification.md).
>   - "Hedef Deneme" ve "İşlem Deneme" sayfaları ortak oturum panelini kullanmıyor.
>
> ## Ana plan ve kesin devam noktası (2026-11-07)
> - **Ana plan:** [docs/plans/2026-11-07-urun-deneyimi-ana-plan.md](plans/2026-11-07-urun-deneyimi-ana-plan.md).
> - **Durum:**
>   - A: DONE.
>   - B: DONE.
>   - C: PARTIAL.
>   - D: PARTIAL.
>   - E: TODO.
>   - F: PARTIAL.
>   - G: PARTIAL; kurum S3 bağlantısı BLOCKED.
> - **Son doğrulama:** `.venv/bin/pytest -q -rs` → 614 passed, 3 skipped (Docker BLOCKED); ruff, format ve mypy
>   temiz.
> - **Kesin sonraki adım:** Aşama D'nin kalanı. Yeni tasarımcıda kaydedilmiş taslağın gerçek adımlarını mevcut
>   `/api/drafts/{id}/steps/{step}/confirm|trial|confirm-outcome` uçlarına bağlamak: veri etkisi uyarısı,
>   sonuç doğrulaması, tanım değişince geçersizleşme. Ardından E (bileşen sürüm pinleme ADR'si ve catalog-v4
>   migrasyon planı).
> - **BLOCKED:** gerçek Pega/SSO kabulü (`docs/15_REAL_ENV_ACCEPTANCE.md`), kurum S3 bağlantısı, gerçek model
>   hizmetiyle test, runner yeri ve SSO yöntemi kararı.
> - **R4 manuel kabulü:** hâlâ beklemede ve tamamlanmadı.
>
> ## Güncel öncelik (2026-11-07)
> Çok uygulamalı katalog/yayın geliştirmesi **beklemede**. Tek uygulamada yeni Akış Tasarımcısı gerçek Playwright
> oturumundan alan seçmeye bağlandı; dinamik ekran ve pencere yönetimi eklendi (ADR 0014).
> - **Tamamlandı (lab):**
>   - Gerçek oturumdan seçim: ekrandaki alanlar veya picker.
>   - Seçim sonrası semantik yeniden çözüm.
>   - Etkileşim bağlamı: kapalı pencere, aktif modal arkası, kaplayan katman, birden fazla aktif pencere.
>   - Ekran tanımlı beklenen pencere.
>   - Yeni pencere/sekme ve tarayıcı dialog'unda durma; kapatma yalnız kullanıcının açık kararıyla.
>   - Picker temizliği ve sade durum metinleri.
> - **Kalanlar tamamlandı:**
>   - `.env.example` tekilleştirildi; etkin örnek tek uygulamalı lab.
>   - Tırnak/ortam değişkeni ayrımı ve redakte hata.
>   - Boyuttan bağımsız katman kuralı ve eylem anı kontrolü.
>   - Beklenen pencere açık doğrulaması.
>   - Kimliğe bağlı kesinti kararları.
> - **Testler:** 600 passed, 3 skipped (Docker); başarısız test yok.
> - **Desteklenmeyen:**
>   - Gerçek Pega/SSO denenmedi.
>   - Beklenen yeni pencereye geçiş (yalnız durur).
>   - İsteğe bağlı/koşullu pencere (sözleşmede adım bazlı beklenti yok; ADR 0014 eki).
>   - Gerçek seçilmiş adımların prototipten yürütülmesi (mevcut yürütücü yolu kullanılır).
>   - S3 yok.
>
> ## Son tamamlanan (2026-11-07)
> - **Prototip:** vazgeç/geri dönüş davranışları (Akışlar görünümü, kayıp onayı, bileşen iptali, dürüst durdurma,
>   kayıp uyarısı).
> - **`AUTOMATION_APPLICATIONS_JSON`:** merkezi Settings, başlangıç doğrulaması, ADR 0012.
> - **Uygulama kapsamı:** İşlem Asistanı ve prototip aynı listeyi kullanıyor. Asistan'da katalog, plan ve run
>   sunucuda uygulamaya göre kapsamlanıyor ve oturum origin'i kontrol ediliyor.
> - **S3 kararı:** belgelendi, bağlanmadı (ADR 0013): katalog/dosya metadatası MongoDB'de; ekran görüntüsü, kanıt ve
>   ek belgeler gerektiğinde kurum içi S3 uyumlu depoda. Önce mevcut artifact/storage yapıları incelenecek; paralel
>   depo kurulmayacak. Maskeleme, erişim ve saklama gerçek entegrasyonda ele alınacak.
> - **Testler:** 570 passed, 3 skipped (Docker). Ayrıntı: docs/10_PROGRESS.md.
> - **Önemli:** mevcut `.env` dosyalarına `AUTOMATION_APPLICATIONS_JSON` eklenmeli; yoksa uygulama yapılandırma
>   hatasıyla başlamaz.
>
> ## Şu anki tek görev
> **Akış Tasarımcısı prototipi** (2026-11-07 öncelik değişikliği): teknik yeterliği düşük analist için sade, yalnız
> etkileşimli prototip. Adres: `/prototype/designer` (designer rolü). Gerçek MongoDB, model, tarayıcı veya yürütücü
> kullanmaz; durum yalnız sayfa belleğindedir. 2026-11-07 ikinci tur: lacivert/turkuaz/mor görsel dil, açık/koyu
> tema, sadeleşmiş sağ panel ("Hangi alan?" / "Değer nereden gelsin?" + Ayrıntılar), iki yollu alan seçimi
> (önerilenler / ekrandan kendim). Ayrıntı: docs/10_PROGRESS.md 2026-11-07 kayıtları.
>
> **Beklemede:** R4 manuel kabulü kullanıcı kararıyla beklemeye alındı; **tamamlanmadı**.
> [docs/R4_ACCEPTANCE.md](R4_ACCEPTANCE.md) (5 madde) ve mevcut `teminat_gir` taslağı olduğu gibi korunuyor.
>
> ## Sonraki somut adım
> Kullanıcının uygulama listesi ve vazgeç/geri dönüş davranışlarını denemesi. Açık sınır: Katalog Tasarımcısı ve
> yayın tarafı hâlâ tek uygulama (`CATALOG_APPLICATION_ID`). Gerçek sisteme entegrasyon başlatılmadı.
> R4 kabulüne dönüldüğünde: kabul listesinin 1. maddesi (`teminat_gir` taslağına "Teminat tutarını yaz" adımı).

### 2026-11-07 / Ana plan devamı: STATUS sadeleştirme + Aşama D (yeni tasarımcıdan gerçek deneme) — PARTIAL — GÜNCEL
- **STATUS.md** tek ve güncel duruma indirildi; eski içerik bu belgede "STATUS.md arşivi" bölümünde.
- **D:**
  - Yeni tasarımcıda "Gerçek deneme ve yayın" paneli: ekranı tanıt, 4 onay, gerçek deneme (etki onayı),
    sonuç onayı, yeni oturum testi, onay ve yayın.
  - Yalnız mevcut uçlar kullanıldı.
  - Düzeltme: panel kimliği ekran okuyucu duyuru alanıyla (`pd-live`) çakışıyordu; `pd-runpanel` yapıldı.
- **Testler:** `.venv/bin/pytest -q -rs` → 617 passed (Docker testleri dahil). ruff, format ve mypy (112 dosya)
  temiz.
- **Kalan:**
  - D: yayının Mongo ile yeni tasarımcıdan e2e testi.
  - E: tamamı.
  - F: modelin akış/bileşenlerden plan önermesi.
  - G: S3 adaptörü (gerçek bağlantı BLOCKED), Mongo metadata, kanıt üreticisi.
  - C: önceki adım çıktısı; geçiş ve bileşen adımlarının kalıcılığı.

### 2026-11-07 / Belge tutarlılığı + Aşama D kabulü (MongoDB) — D DONE — GÜNCEL
- **Belgeler:** plan C ve ADR 0015, D'deki çalışan "Ekranı tanıt" ile uyumlu hale getirildi.
- **D kabulü:** `tests/e2e/test_new_designer_publish_mongo.py` (geçici mongod).
  - Akış: yeni tasarımcıdan taslak → ekran → onaylar → gerçek deneme → sonuç onayı → yeni oturum testi →
    yayıncı onayı → yayın → İşlem Asistanı'ndan hazır işlemle çalıştırma.
  - Sonuç "Başarılı/Tamamlandı"; kayıtta yeni değer görülüyor.
- **Oturum sınırı:** C, E, F ve G'nin kalanları başlatılmadı; kesin devam noktası STATUS.md'de.

### 2026-11-07 / Ana plan C, E, F, G — GÜNCEL
- **C (ADR 0017):** önceki adım çıktısının çalışma anı bağlaması (komut `value_from`, yürütücü, derleyici, devam);
  geçişin hedef ekrandan önce kaydı; parametre silme ucu; yeni tasarımcıda bilgi oku, gerçek düğmeyle ekrana geç,
  sonuç kontrolü, onaylı işlem, rota ekranlarının tanıtılması, düzenlenebilir yeniden açma.
- **E (ADR 0019):** catalog-v4 `call_operation` (revizyon + hash pinli), girdi/çıktı bağlama, yayın doğrulaması ve
  bileşen ekranlarının manifeste girmesi, sürüm etkisi ve açık yükseltme; asistan pinli bileşenleri değişmez
  revizyonundan derler.
- **F (ADR 0020):** model önerili doğrusal plan (≤5 işlem), kod denetimi, sunucuda yeniden derlenen özet/yürütme,
  asistan arayüzü; bağlayıcı sahte model sunucusuyla test edildi. Gerçek model kabulü BLOCKED.
- **G (ADR 0018):** async port, S3 SigV4 adaptörü (yeni bağımlılık yok), MongoDB metadata adaptörü, maskelemesi
  piksel düzeyinde doğrulanmış kanıt; `ARTIFACT_BACKEND`, `ARTIFACT_INDEX_BACKEND`, `S3_*` ayarları (.env.example
  ve docs/05). Kurum S3 kabulü BLOCKED.
- **Yeni testler:** `tests/unit/test_prior_output.py`, `test_components.py`, `test_component_publishing.py`,
  `test_object_store_contract.py`; `tests/integration/mongo/test_artifact_index_contract.py`,
  `tests/integration/browser/test_evidence.py`; `tests/e2e/test_new_designer_multi_screen_ui.py`,
  `test_new_designer_components_mongo.py`, `test_assistant_plan_ui.py`; ek testler `test_executor.py`,
  `test_designer.py`, `test_assistant.py`, `test_llm_adapter.py`, `test_settings.py`.
- **Değişen başlıca dosyalar:** `domain/commands.py`, `domain/catalog.py`, `domain/composition.py`,
  `domain/assistant.py`, `domain/runtime.py`, `domain/actions.py`, `application/services/{executor,designer,
  publishing,assistant,runs,artifacts}.py`, `application/ports/artifacts.py`, `infrastructure/artifacts/{local_file,
  s3,mongo_index}.py`, `infrastructure/browser/evidence.py`, `config/settings.py`, `bootstrap.py`,
  `presentation/api/{drafts,assistant,runs,artifacts}.py`, `presentation/static/{prototype_designer,assistant}.js`,
  `presentation/templates/assistant.html`, `.env.example`, docs/02, 05, 09, ADR 0017–0020.
- **Testler:** `.venv/bin/pytest -q -rs` → 667 passed (atlama yok; Docker/geçici MongoDB testleri dahil), ardından değişen 2 dosyada +1 test: 10 passed (toplam 668). ruff, format, mypy (102 dosya) ve JS sözdizimi temiz.

### 2026-11-07 / Akış Tasarımcısı responsive yerleşim düzeltmesi — DONE (lab, Chromium + Playwright WebKit)
- **Neden (ölçüldü):**
  1. Sol paneldeki `.pd-real` ızgarasının sütunu `auto`; oturum seçim kutusunun en uzun seçeneği (oturum + uzun
     adres) min-content genişliği dayatıyordu → panel içeriği 8–28 px taşıyor, sağ kenar kesiliyor, panelde yatay
     kaydırma çıkıyordu (1440/1280 dahil her genişlikte).
  2. ≤1180 px'te (1024, 820, %125/%150 zoom) sol panel `position: sticky` kalırken adım ayarları tam genişlikte
     alt satıra iniyordu; sticky öğenin sınırı ızgaranın tamamı olduğundan kaydırınca sol panel adım ayarlarının
     üzerine kayıyor, radyo/onay kontrollerini örtüyordu.
- **Düzeltme (yalnız CSS/şablon/arayüz JS):** `.pd-real` tek esnek sütun, seçim kutusu `width:100%`/ellipsis, uzun
  metinlerde `overflow-wrap:anywhere`; ≤1180 px'te sol panel sticky değil, akış içinde aç/kapa (bölümler sığdığı
  kadar yan yana), akış ve adım ayarları yan yana; ≤960 px'te tek kolon (adım ayarları akışın altında). Kapalı
  panelde kesinti rozeti görünür ve kesinti gelince panel açılır. Zoom/transform/overflow:hidden kullanılmadı.
- **Regresyon:** `tests/e2e/test_designer_layout_ui.py` + `tests/e2e/layout_probe.py` (örtüşme, panel içi taşma,
  kırpılma, örtülen kontrol, sayfa taşması; 1440/1280/1024/820/390, 1280@125/150, 1440@150; açık/koyu; aç/kapa ve
  durum korunması; Playwright WebKit — gerçek Safari değildir). Düzeltme öncesi aynı test 7 görünümde başarısızdı.
- **Testler:** `tests/e2e` → 23 passed.

### 2026-11-07 / Manuel kabul: yeni oturum testi başarısız (fresh_session_test_failed) — düzeltildi
- **Kanıt (taslak draft-zQLGwJmdL8Q, run-WwN5WYXkRp8g1g; taslak ve yayınlar değiştirilmedi):** ilk komut
  `assert_screen` `SESSION_EXPIRED` ile durdu (lab profilinde yol `/login` ile başlıyor = giriş ekranı); run
  `paused_session` → test süresi sonunda `cancelled_while_paused`. `ensure_value`/`assert_condition` hiç
  çalışmadı. Aynı taslağın gerçek adım denemesi (run-4b2jMpWUzop1Kw) kullanıcının girişli oturumunda geçmişti.
- **Neden:** yeni oturum testi bilinçli olarak yeni ve boş bir tarayıcı bağlamında çalışır (kullanıcı oturumu
  taşınmaz). Eski tasarımcı lab'da başlangıç adresini `/__lab/autologin?…&next=<ekran>` ile sarıyordu; yeni
  tasarımcı uygulama kök adresini olduğu gibi gönderiyordu → giriş ekranı. Kök adres hedef ekran da değildi.
- **Düzeltme:** yeni tasarımcı lab'da "Başlangıç ekranı (deney uygulamasındaki yol)" alır ve otomatik giriş
  adresini kurar (varsayılan: oturumda açık ekranın yolu). Doğrulama gevşetilmedi; test kapatılmadı. Sunucu,
  başarısız testin nedenini run kaydından çıkarır (`fresh_test_failure`: aşama, neden, sonraki adım; değer ve
  oturum bilgisi yok) ve arayüz kod yerine bunu gösterir. Gerçek uygulamada yeni oturuma giriş (SSO) yöntemi
  yok; bu durumda arayüz bunu açıkça söyler (BLOCKED).
- **Testler:** `test_designer.py::test_fresh_test_without_login_explains_cause` (hatayı yeniden üretir, sonra
  girişli adresle geçer), `test_prototype_real_session_ui.py` (arayüzde neden + sonraki adım), ilgili e2e'ler:
  9 passed; unit + ilgili entegrasyon: 459 passed.

### 2026-11-07 / Gün sonu — devam noktası (yeni geliştirme yok)
- **Taslak:** “Kefil müşteri numarası gir yaz.” (`draft-zQLGwJmdL8Q`), kullanıcının son gördüğü revizyon 11.
- **Başarılı:** alan seçimi, ekran tanımı, gerçek adım denemesi (00789 yalnız Kefil alanına yazıldı).
- **Başarısız:** yeni oturum testi `SESSION_EXPIRED` (girişsiz yeni oturum, başlangıç ekranında giriş sayfası).
- **Düzeltme:** lab otomatik giriş yolu; karar sunucuda (`fresh_test_entry`); HTML `no-store`, statik `no-cache`.
  Gerçek uygulamada otomatik giriş yok. Testler: ilgili entegrasyon + e2e 41 passed.
- **Açık:** kullanıcının çalışan ekranında hâlâ tam başlangıç adresi/SSO uyarısı görünüyor. Kayıtta taslak
  revizyon 12 ve 22:53'te başarılı bir yeni oturum testi (`run-x6iatXEy-Nt6Eg`) var; onay kaydı yok — yarın
  doğrulanacak.
- **Sonraki adım:** yeniden başlatıp çalışan sunucunun güncel kodu ve lab yapılandırmasını kullandığını
  doğrulamak; ardından mevcut taslakla yeni oturum testi, yayıncı onayı, yayın ve İşlem Asistanı'ndan çalıştırma.
- **Durum:** manuel yayın ve uçtan uca kabul **tamamlanmadı**. Taslak, onay ve yayınlar bu kayıtta değiştirilmedi.

### 2026-11-08 / H “Seçim yap” bileşeni (ADR 0021, catalog-v5)
- **Manuel kabul kaydı:** “Kefil müşteri numarası gir yaz.” uçtan uca yayımlandı ve Asistan'dan 00456 ile çalıştırıldı
  (kullanıcı bildirimi; yalnız tek alanlı lab senaryosu, Pega/SSO kabulü değildir).
- **Değişen dosyalar:** domain/{choices.py (yeni), catalog.py, commands.py, observation.py, assistant.py};
  application/{controls.py, ports/{controls,browser}.py, services/{executor,observation,assistant,designer,publishing}.py};
  infrastructure/browser/{driver,driver_js,inventory_js,observer}.py; presentation/{api/{drafts,observation,assistant}.py,
  static/{prototype_designer.js,.css,assistant.js}, templates/assistant.html}; config/settings.py, .env.example;
  agentask_lab/{app.py,state.py,static/lab.js,templates/selections*.html,selection_frame_*.html}; docs/{02,05,09,STATUS},
  ana plan, ADR 0021.
- **Testler:** 719 passed, 3 skipped (Docker BLOCKED); ruff, format, mypy temiz.
- **Sınır:** gerçek Pega doğrulanmadı; çoklu seçim, yazarak arama, shadow DOM, rolsüz özel liste desteklenmez.

### 2026-11-08 / I Yapılandırılmış loglama ve çalışma geçmişi (ADR 0022)
- **Değişen dosyalar:** application/observability.py (yeni), domain/{redaction,run_summary}.py (yeni), domain/runtime.py
  (`title`, `correlation_id`), infrastructure/logging.py, application/services/{executor,runs,designer,publishing,observation,assistant}.py,
  presentation/{app,errors,dependencies}.py, api/runs.py, static/{runs,assistant}.js, templates/{runs,assistant}.html, `__main__.py`,
  .env.example (yalnız açıklama), docs/{05,08,09,STATUS}, ADR 0022.
- **Davranış:** stdout JSON; correlation/actor/run/step bağlamı; alan izinli listesi; yabancı istisna mesajı yazılmaz; tek
  `http_request` ve tek `run_finished` kaydı; kullanıcı olayları `category=audit`; /runs ve Asistan'da neden, sonraki adım,
  destek numarası; yeni çalıştırmada eski sonuç temizlenir.
- **Testler:** son geçerli koşu (08, `caffeinate -i`) 769 passed, 3 skipped, pytest çıkış 0; ruff, format, mypy, dev_check çıkış 0. Aynı kodla önceki koşu (07) 2 failed, 767 passed, 3 skipped, çıkış 1; neden makinenin uykuya geçmesi (`07-diagnosis.md`). Gerçek süreç duman testi: bütün satırlar JSON, sorgu/gövde sırrı yok.
  Çıktı ve çıkış kodları: `var/verification/logging-2026-11-08/`.
- **Sınır:** kurum log altyapısı ve gerçek Pega/SSO ile doğrulanmadı; ayrı denetim deposu yok; run deposu yerel dosya.

### 2026-11-08 / I Loglama manuel kontrolleri (kullanıcı bildirimi; yalnız lab kabulü)
- Başarılı işlemde destek numarası İşlem Asistanı ve Çalışmalar ekranında aynı.
- Yanlış ekranda çalıştırmada işlem yapılmadan duruldu ve hata bilgisi gösterildi.
- Kurum log altyapısı, Pega/SSO veya ürünün tümünün kabulü değildir.

### 2026-11-08 / H “Seçim yap” manuel kabul hazırlığı
- Senaryo gerçek düğme adlarıyla otomatik prova edildi (geçici test; silindi). Prova iki hata buldu, düzeltildi:
  - `.card label` kuralı `hidden` özniteliğini eziyordu; etki onayı veri değiştirmeyen işlemde de görünüyordu (`app.css`: `[hidden]`).
  - Otomatik alan açıklaması işlem anlamı olarak kaydediliyor, plan metninde iç not görünüyordu (`prototype_designer.js`).
- **Testler:** prova çıkış 0; tam takım 769 passed, 3 skipped, pytest çıkış 0; ruff, format, mypy çıkış 0. Çıktılar:
  `var/verification/choice-manual-2026-11-08/`.
- **Durum:** kullanıcı manuel kabulü bekleniyor; prova kabul yerine geçmez.

### 2026-11-08 / Gün sonu kaydı
- **Tamamlandı:** loglama geliştirmesi (ADR 0022). Son bildirilen tam test sonucu 769 passed, 3 skipped; gün sonunda test çalıştırılmadı.
- **Kullanıcının bildirdiği manuel kabul (yalnız lab):** destek numarası Asistan ve Çalışmalar'da eşleşti; yanlış ekran senaryosu beklenen
  şekilde sonuçlandı. Gerçek Pega/SSO ve kurum log altyapısı doğrulanmadı.
- **Sonraki:** “Seçim yap” manuel kabulü, henüz yapılmadı (`/pages/selections`, “Kefil › Şube” = sabit “Konak”; ayrıntı STATUS).
- **Ertelendi:** OpenShift ve geniş kod temizliği. Veri, taslak, yayın ve `.env` değiştirilmedi.

### 2026-11-09 / Şirket testi aday sürümü (ADR 0023, docs/16, docs/17)
- **Yapılan:** AUTH_MODE=local_admin; elle hedef girişi ve yeni oturum testi bekleme (`/fresh-test/continue|cancel`); `Run.cancelled_by`; yeniden açma tutarlılığı;
  gerçek oturum etiketleri; zengin metin hedefinde açık durma; `APPROVED_ACTION_SET=file`; `agentask --doctor`; `tools/build_company_package.py`, `packaging/company/`.
- **Testler:** 805 passed, pytest çıkış 0; Docker testleri çalıştı (3 passed); ruff, format, mypy, JS, dev_check çıkış 0. Önceki deneme 1 failed (bilinçli gizlenen düğme; teşhis `attempt1-failed/DIAGNOSIS.md`).
- **Sınır:** Windows kurulum betikleri ve gerçek Pega/SSO, kurumsal Mongo, model, S3 doğrulanmadı.

### 2026-11-09 / Şirket sürümü S1–S9 (ADR 0024, catalog-v6, paket 0.2.0)
- **Yapılan:** K1 aksiyon pinleme, K3 yayın etkinleştirme, çıktı bağlama, bağlantı/seçim geçişi, Kayıt bul ve satır, onay kutusu, seçenek grubu, öneri alanı, çoklu seçim, tarih, dosya yükleme, tek beklenen yeni pencere, isteğe bağlı pencere.
- **Testler:** son koşu 916 passed, pytest çıkış 0; ruff, format, mypy, JS, dev_check çıkış 0; Docker 3 passed. İlk koşu 1 failed (`focused_window` sözleşme testi), teşhisle saklandı. Çıktılar: `var/verification/company-final-2026-11-09/`.
- **Sınır:** Windows betikleri, Pega/SSO ve kurum bağlantıları denenmedi; kullanıcı yerel kabulü yapılmadı.

### 2026-11-09 / Gün sonu: otomatik kabul çalışması (tamamlanmadı)
- **Yapılan:** 28 madde eşlemesi (`tools/local_acceptance/coverage.py`); e2e sonuç doğrulamaları; `test_wizard_acceptance_mongo`; `tools/local_acceptance` aracı. `src/` değişmedi, paket 0.2.0 geçerli (SHA-256 `e4000fc6fc2cd33207d0b6abc2993878c41ec087d50c66f1b7f57de516a89816`).
- **Test:** genişletilmiş koşu çıkış kodu üretmedi (`FF..F`, ardından `test_controls_flow_mongo` takılı). Başarılı sayılmaz. Kanıt: `acceptance-reports/2026-11-09-tamamlanmamis-kosu/DURUM.md`.
- **Yapılmadı:** araç hiç çalıştırılmadı, birim testleri ve `docs/18` yok, ruff 64 bulgu. 28 maddenin tamamı OTOMATİK DOĞRULANAMADI.
- **Manuel:** `docs/17` için kullanıcı sonucu bildirilmedi; hiçbir madde kabul edilmiş sayılmaz.
- **Devam:** `docs/STATUS.md` “Kesin devam noktası”.

### 2026-11-11 / test_company_candidate_flow teşhisi
- **Koşu:** yalnız bu test, `-x`, 600 sn sınır, geçici ortam; pytest çıkış **1**. Kanıt: `acceptance-reports/2026-11-11-company-candidate-teshis/`.
- **Bulgu:** elle girişten sonra yeni oturum testi başlamadı (“Beklenen başlangıç ekranı görünmüyor”); ürün işlemi güvenli biçimde başlatmadı. Önceki adımlar ve yeni sonuç doğrulamaları geçti. **Kaynak belirsiz** (test zamanlaması veya ekran işareti seçimi; kanıt yok).
- **Manuel:** kullanıcı “Kefil şubesi seçimi İşlem Asistanı'nda başarılı” bildirdi; kısmi lab kanıtı. 28 madde geçmiş sayılmaz.
- **Kod/paket:** ürün ve test kodu değişmedi; paket 0.2.0 aynı.
- **Yarın ilk adım:** bu testi ekran işaretleri ve doğrulama penceresi adresi kaydedilerek yeniden teşhis et.

### 2026-11-13 / Otomatik yerel kabul tamamlandı; aday 0.2.1
- **Ürün:** öneri alanında gerçek seçim geri gelmezse sonuç Belirsiz (`controls.py`). Regresyon testi eklendi; eski davranışla başarısız olduğu kanıtlandı.
- **Testler:** company_candidate, wizard, action_file ve controls testleri düzeltildi. Hepsi test kurgusu nedenliydi; teşhisler `acceptance-reports/2026-11-13-*` altında.
- **Araç:** `tools/local_acceptance` tamamlandı (yalıtım, gerçek adres reddi, süre sınırı, çıkış kodları, eksik sonuç raporu); birim testleri `tests/unit/test_local_acceptance_tool.py`. `docs/18` yazıldı.
- **Doğrulama:** tam regresyon 933 passed, bütün çıkışlar 0 (`var/verification/company-candidate-0.2.1-20261113/regression/`). Kabul koşusu 28/28 GEÇTİ, çıkış 0 (`acceptance-reports/20261113-202235/`). İlk kabul koşusu araç hatasıyla geçersiz sayıldı ve saklandı.
- **Paket:** `agentask-company-test-0.2.1-20261113.zip`, SHA-256 `5cf379642d5dc296c953481afe1024b73755b79ce7c8a033d66259cd16455d95`. 0.2.0 eski aday olarak işaretlendi.
- **Hata kaydı:** dar kapsamlı `ruff --fix` 27 `noqa` açıklamasını sildi; satırlar geri kondu, gerekçe metinlerinin çoğu kayboldu.
- **Doğrulanmadı:** Windows, gerçek Pega/SSO ve kurum bağlantıları.

### 2026-11-16 — Tarayıcı motoru seçimi (0.3.0, ADR 0025)
- **Ayar:** mevcut `BROWSER_ENGINE` genişletildi (varsayılan chromium; firefox desteklenir; webkit gerekçesiyle reddedilir). İkinci ayar veya paralel uyarlayıcı eklenmedi. Playwright 1.64.1 değişmedi.
- **Değişen ürün dosyaları:** `config/settings.py`, `diagnostics.py`, `infrastructure/browser/{blocked_frames.py (yeni), playwright_factory.py, observer.py, driver.py, inventory_js.py}`, `application/services/executor.py`, `agentask_lab/templates/optional_modal.html`, `presentation/app.py`, `pyproject.toml`, `.env.example`.
- **Paket/belge:** `packaging/company/{INSTALL.md, KNOWN_LIMITS.md, install.ps1}`, `docs/05`, `docs/18`, `docs/adr/0025-tarayici-motoru-secimi.md`.
- **Test/araç:** `tests/support_browser.py` (yeni), `tests/conftest.py`, 29 test dosyası, `tests/unit/test_browser_engine_settings.py` (yeni), `tests/integration/browser/test_browser_engine.py` (yeni), `tools/local_acceptance/{__main__,guard}.py`.
- **Kanıt:** Chromium 947 passed + Docker 3; Firefox entegrasyon 251 passed, e2e 38 passed; Firefox kabul 28/28 (`acceptance-reports/20261116-164525/`). WebKit doğrulanmadı.
- **Paket:** `agentask-company-test-0.3.0-20261116.zip`, SHA-256 `b91f750cb4c4ebf8efa558d7cf8154f7085d7327932754187fb425fecd52acad`.
- **Doğrulanmadı:** Windows'ta Firefox kurulumu, gerçek Pega/SSO.

### STATUS.md arşivi — 2026-11-09 aday sürüm devam noktası
## Devam noktası (2026-11-09) — şirket testi aday sürümü
**Hedef:** yerelde tek aday sürüm; gerçek şirket bağlantıları yalnız şirkette kabul edilir. Değerlendirme: `docs/16_COMPANY_TEST_READINESS.md`.

**Tamamlanan (lab):** geçici admin girişi (ADR 0023; kurumsal SSO **değil**), hedefe elle giriş ve yeni oturum testi bekleme akışı, iptal kaynağı ayrımı, yeniden açma ve etiket düzeltmeleri, `APPROVED_ACTION_SET=file`, `agentask --doctor`, Windows paketi.

**Son doğrulama:** `caffeinate -i` altında `pytest -q -rs` → 805 passed, pytest çıkış 0 (Docker testleri dahil; 3'ü çalıştı). ruff, format, mypy, JS, `tools.dev_check` çıkış 0. Çıktılar: `var/verification/company-candidate-2026-11-09/`; ilk başarısız koşu ve teşhisi `attempt1-failed/` altında.

**Paket:** `dist/agentask-company-test-0.1.0-20261109.zip`. Mac'te temiz sanal ortamda kurulum, `--check-config` ve `--doctor` denendi. **Windows'ta çalıştırılmadı** (PowerShell yok).

**Paket nihai değil.** Kod incelemesi ve son geliştirme planı: `docs/plans/2026-11-09-sirket-surumu-son-gelistirme-plani.md` (S1–S9; K1–K5 kararları bekleniyor, geliştirmeye başlanmadı).

**Sıradaki:** kullanıcının `docs/17_LOCAL_ACCEPTANCE.md` tek toplu yerel kabulü (henüz yapılmadı; “Seçim yap” ve R4 kabulü bunun içinde). Sonra paketle şirkette `MANUAL_ACCEPTANCE.md` Bölüm S.

**Yerelde açık kalanlar:** K3 lease/fencing, K7 işlem bazlı yetki, K5 run'ların Mongo'da olmaması, autocomplete/çoklu seçim/onay kutusu/radyo/dosya/takvim, dallanma; yeni tasarımcıda “Kayıt bul” yok. Hepsi `KNOWN_LIMITS.md`'de.

**Ertelendi (başlanmadı):** kurumsal SSO, OpenShift, kuyruk, çok kullanıcılı ölçekleme, runner ayrıştırma, kapasite testi, geniş kod temizliği. Eski `/designer` silinmedi (“Kayıt bul” için gerekli).

**Korunacaklar:** `var/` altındaki veriler, MongoDB yayınları, gerçek `.env`.

**Önceki gün sonu notu:** “Seçim yap” manuel kabulü yukarıdaki yerel kabule taşındı. 2026-11-08 test sonucu 769 passed, 3 skipped idi.
