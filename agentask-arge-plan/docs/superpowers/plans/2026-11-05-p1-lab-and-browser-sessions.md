# P1 — Deney uygulaması ve browser session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerçek Pega yerine loopback'te iki origin'li, senaryoları HTTP ile tetiklenebilen bir deney uygulaması ve kullanıcı başına izole, sahiplik/kilit kontrollü async Playwright oturum yöneticisi.

**Architecture:** Deney uygulaması ürün kodundan ayrı `src/agentask_lab` paketidir; aynı FastAPI uygulaması iki uvicorn sunucusuyla (birincil/ikincil origin) tek process'te, ortak `LabState` ile servis edilir. Oturum kuralları (sahiplik, tek işlem kilidi, limitler, boşta kalma) `application/services/browser_sessions.py` içinde framework'süz; Playwright yalnızca `infrastructure/browser/` içindeki `BrowserContextFactory` adapterindedir. FastAPI lifespan servisi kapatır ve bütün kaynakları temizler.

**Tech Stack:** Python 3.12.0, FastAPI 0.162, Playwright 1.64.1 (async, Chromium 156.0.8078.4), pytest-asyncio, httpx.

**Spec:** docs/06_IMPLEMENTATION_PLAN.md (P1), docs/03_RUNTIME_AND_RECOVERY.md, docs/07_ACCEPTANCE_TESTS.md (T12, T13), docs/08_SECURITY_AND_OPERATIONS.md, docs/05_CONFIGURATION.md, kullanıcının P1 talebi.

## Global Constraints
- Bütün ortam ayarları `agentask.config.Settings`'ten; yeni anahtarlar `.env.example`, docs/05 ve config testine birlikte eklenir.
- Deney uygulaması "gerçek Pega değildir" bandı taşır; yalnızca loopback'e bind olur; production'da lab ayarı reddedilir.
- Gerçek Pega/SSO/MongoDB/LLM bağlantısı yok. Kullanıcı metinleri Türkçe, kod kimlikleri İngilizce.
- Playwright async API; Playwright nesneleri oluşturulduğu event loop dışına taşınmaz.
- Başka kullanıcının oturumu 404 (varlık sızdırılmaz); aynı oturumda ikinci işlem beklemeden 409.
- Gerçek tarayıcı testleri varsayılan test koşusunun parçasıdır (`-m browser` ile ayrıca seçilebilir).

## Review Focus
1. Aynı anda iki `open` isteği limit kontrolünü birlikte geçmesin → slot await öncesi rezerve edilir (test: `test_concurrent_open_respects_limit`).
2. İşlem sürerken `close` → 409 busy; `shutdown` ise zorla kapatır ve browser süreci kalmaz (test: `test_shutdown_closes_contexts_and_browser`).
3. Yönlendirme/iframe/popup ile izinli olmayan origin'e gitme → document isteği engellenir (test: `test_navigation_outside_allowed_origins_is_blocked`).
4. Yanıtı kaybolan kayıt: sunucuda commit görünür, sayfa başarı göstermez, sonraki kayıt normal (test: `test_lost_response_commits_but_page_shows_unknown`).
5. Boşta kalan oturum süre aşımında kapanır, fakat işlemdeki oturum reaplenmez (test: `test_reap_skips_busy_sessions`).

---

### Task 1: Settings — lab ve browser oturum ayarları

**Files:** Modify `src/agentask/config/settings.py`, `.env.example`, `docs/05_CONFIGURATION.md`; Create `src/agentask/domain/origins.py`, `src/agentask/config/runtime_env.py`; Test `tests/unit/test_settings.py`, `tests/unit/test_origins.py`.

**Interfaces — Produces:**
- `agentask.domain.origins.normalize_origin(url: str) -> str` (ValueError), `OriginPolicy(allowed: Iterable[str]).allows(url: str) -> bool` (yalnızca http/https; `about:blank` izinli).
- Yeni zorunlu alanlar: `BROWSER_MAX_SESSIONS=4`, `BROWSER_MAX_SESSIONS_PER_USER=1`, `BROWSER_SESSION_IDLE_SECONDS=900`, `BROWSER_LAUNCH_TIMEOUT_MS=30000`, `NAVIGATION_TIMEOUT_MS=15000` (hepsi pozitif; per-user ≤ max).
- Opsiyonel: `LAB_PRIMARY_ORIGIN=http://127.0.0.1:8100`, `LAB_SECONDARY_ORIGIN=http://127.0.0.1:8101` (http + loopback + farklı; ikisi birlikte verilir; production'da reddedilir).
- `agentask.config.runtime_env.apply_playwright_environment(settings) -> None`: `PLAYWRIGHT_BROWSERS_PATH` doluysa process env'e yazar (driver bunu env'den okur).

- [ ] Tests: `test_lab_origins_must_be_loopback`, `test_lab_origins_rejected_in_production`, `test_lab_origins_must_differ`, `test_per_user_sessions_cannot_exceed_total`, origin policy (path/redirect/about:blank/javascript: reddi). Run → FAIL.
- [ ] Implement; `_normalize_origin` domain'e taşınır. Run unit tests → PASS.

### Task 2: Deney uygulaması (`agentask_lab`)

**Files:** Create `src/agentask_lab/{__init__,__main__,state,app,server}.py`, `templates/*.html`, `static/lab.{js,css}`; Modify `pyproject.toml` (`agentask-lab` script, package data, marker `browser`, playwright pin). Test `tests/integration/lab/{conftest,test_lab_scenarios}.py`.

**Interfaces — Produces:**
- `LabState` (bellek içi): `scenario: Scenario`, `commits: list[NoteCommit]`, `login(user) -> token`, `is_valid(token)`, `expire_sessions()`, `reset()`.
- `Scenario` (Pydantic, extra=forbid): `delay_ms:int 0..30000=0`, `dialog: none|modal|native = none`, `lose_next_commit_response: bool=False`, `lost_response_hang_ms: 100..60000 = 5000`, `late_frame_delay_ms: 0..30000 = 1500`, `table_rows: 0..5000 = 57`, `page_size: 1..200 = 10`, `scroll_batch: 1..200 = 15`.
- `create_lab_app(state: LabState, primary_origin: str, secondary_origin: str) -> FastAPI`; `async serve(settings: Settings, state: LabState) -> None` iki sunucuyu birlikte çalıştırır.
- Kontrol API (yalnızca loopback istemci): `GET /__lab/state`, `PUT /__lab/scenario` (kısmi güncelleme), `POST /__lab/sessions/expire`, `POST /__lab/reset`; insan için `/__lab` kontrol sayfası.
- Sayfalar (giriş gerekir; oturum geçersizse `/login?reason=expired`, lab-api için 401):
  `/pages/frames` (same-origin 2 seviye iç içe + ikincil origin `/frames/cross` + `late_frame_delay_ms` sonra JS ile eklenen `/frames/late`),
  `/pages/duplicates` (Başvuran/Kefil bölümlerinde aynı "Müşteri No", "Ad Soyad" ve iki "Kaydet"),
  `/pages/dropdowns` (native "Şube" select + `role=combobox` "Ürün Tipi"; seçenekler tıklamadan sonra gecikmeli oluşur),
  `/pages/table-paged?page=N`, `/pages/table-scroll` (`/lab-api/rows?offset&limit` ile kaydırdıkça yükleme; sonda "Tüm kayıtlar yüklendi"),
  `/pages/delayed` (içerik istemci tarafında `delay_ms` sonra görünür), `/pages/note-form` (C-1001 için not; `client_request_id` ile `POST /lab-api/cases/C-1001/notes`; 2000 ms istemci zaman aşımı "Yanıt alınamadı — işlem sonucu bilinmiyor").
- Her render'da yeni rastgele `id`/`name` (secrets.token_hex). Sunucu gecikmesi `delay_ms` sayfa ve lab-api isteklerine uygulanır (kontrol API hariç).

- [ ] Browser tests (lab sunucusu thread'de, boş portlarda; senaryo httpx ile): `test_ids_change_on_every_load`, `test_nested_cross_origin_and_late_frames`, `test_duplicate_labels_present`, `test_native_and_custom_dropdown`, `test_paged_table_covers_all_rows_once`, `test_scroll_table_loads_incrementally`, `test_server_delay_and_delayed_reveal`, `test_modal_and_native_dialog`, `test_session_expiry_redirects_to_login`, `test_lost_response_commits_but_page_shows_unknown`, `test_control_api_rejects_unknown_fields`, `test_lab_banner_says_not_real_pega`. Run → FAIL.
- [ ] Implement. Run → PASS.

### Task 3: Browser oturum servisi (framework'süz kurallar)

**Files:** Create `src/agentask/application/ports/browser.py`, `src/agentask/application/services/browser_sessions.py`; Modify `src/agentask/application/errors.py`. Test `tests/unit/test_browser_sessions.py` (sahte factory).

**Interfaces — Produces:**
- Port: `BrowserContextHandle` (Protocol): `async navigate(url: str) -> None`, `current_url: str`, `is_closed: bool`, `async close() -> None`. `BrowserContextFactory` (Protocol): `async create_context(owner_id: str) -> BrowserContextHandle`, `async shutdown() -> None`.
- Hatalar: `SessionNotFound` (404, `session_not_found`), `SessionBusy` (409, `session_busy`), `SessionLimitReached` (429, `session_limit_reached`), `NavigationNotAllowed` (403, `navigation_not_allowed`).
- `SessionLimits(max_sessions:int, max_per_user:int, idle_seconds:int)`; `SessionView(session_id, owner_id, created_at, last_used_at, busy_operation: str | None)`.
- `BrowserSessionService(factory, limits, clock=lambda: datetime.now(UTC))`: `async open(owner_id) -> SessionView`, `async close(owner_id, session_id) -> None`, `list(owner_id) -> list[SessionView]`, `operation(owner_id, session_id, name) -> AsyncContextManager[BrowserContextHandle]`, `async reap_idle() -> int`, `async shutdown() -> None`. Session id: `secrets.token_urlsafe(16)`.

- [ ] Tests: `test_open_and_close_releases_context`, `test_other_user_gets_not_found` (get/close/operation), `test_second_operation_is_rejected_while_first_runs`, `test_operation_released_after_exception`, `test_close_while_busy_is_rejected`, `test_per_user_and_total_limits`, `test_concurrent_open_respects_limit`, `test_factory_failure_releases_reservation`, `test_reap_idle_closes_expired`, `test_reap_skips_busy_sessions`, `test_shutdown_closes_all_and_rejects_new`. Run → FAIL.
- [ ] Implement. Run → PASS.

### Task 4: Playwright adapteri + API + lifespan

**Files:** Create `src/agentask/infrastructure/browser/{__init__,playwright_factory}.py`, `src/agentask/presentation/api/sessions.py`; Modify `bootstrap.py` (Container'a `sessions`), `presentation/app.py` (lifespan: periyodik reap, shutdown), `presentation/errors.py` (yeni status eşlemesi), `docs/09_API_CONTRACTS.md`. Test `tests/integration/browser/test_playwright_sessions.py`, `tests/integration/test_sessions_api.py`.

**Interfaces — Produces:**
- `PlaywrightContextFactory(settings: Settings)`: browser'ı ilk kullanımda tek sefer (lock) başlatır (engine/headless/executable/launch timeout), kopmuşsa yeniden başlatır; her oturuma yeni `BrowserContext` + tek page; context.route ile izinsiz origin'e document isteklerini abort eder; `navigate` önce `OriginPolicy` kontrolü yapar, `NAVIGATION_TIMEOUT_MS` kullanır. Handle ayrıca `.page` ve `.context` (yalnız infrastructure/test kullanımı).
- API: `POST /api/sessions` → 201 `SessionView`; `GET /api/sessions` → kendi oturumları; `DELETE /api/sessions/{id}` → 204. Yetki: USE_ASSISTANT veya DESIGN_CATALOG.

- [ ] Browser tests: `test_users_are_isolated_by_context` (A lab'a giriş yapar, B login'e düşer), `test_shutdown_closes_contexts_and_browser`, `test_navigation_outside_allowed_origins_is_blocked`, `test_concurrent_operations_on_real_session_conflict`, `test_browser_relaunches_after_disconnect`. API: `test_session_api_lifecycle_and_ownership` (gerçek tarayıcı), `test_session_api_requires_capability`. Run → FAIL.
- [ ] Implement. Run → PASS. Tüm suite + ruff + mypy.

### Task 5: Belgeler ve doğrulama
- [ ] ADR `docs/adr/0002-p1-lab-ve-browser-session.md`; README'ye çalıştırma komutları ve lab adresleri; `requirements.lock` yenile; docs/10_PROGRESS.md P1 kaydı.
- [ ] Gerçek çalıştırma duman testi: `agentask-lab` + `agentask` aynı anda, curl ile lab kontrol API ve `/api/sessions`.
