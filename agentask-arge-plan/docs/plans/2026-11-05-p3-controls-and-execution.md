# P3 — Ortak kontrol adapterleri, sınırlı komut motoru ve yürütme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** P2 çözümleyicisini kullanan tekrar kullanılabilir kontrol adapterleri, tipli 7 komutlu motor, checkpoint'li run/step durum makinesi, teknik toparlanma, dispatch/uzlaştırma sınırı ve "İşlem Deneme" ekranı.

**Architecture:** Saf domain: komut birliği (`domain/commands.py`), onaylı aksiyon/engelleyici/uygulama profili şeması (`domain/actions.py`), run/step durum makineleri (`domain/runtime.py`). Uygulama: adapterler (`application/controls.py`, yalnız `ControlDriver` portuna bağlı), `Executor` (`application/services/executor.py`), `RunService` (`application/services/runs.py`: oluştur/iptal/devam/başlangıç kurtarma). Altyapı: Playwright sürücü (`infrastructure/browser/driver.py`), yerel dosya checkpoint deposu (`infrastructure/runs/local_file.py`), lab onaylı aksiyon seti (`infrastructure/approved_actions/lab.py`). Run, oturum kilidini (operation "run") baştan sona tutar.

**Tech Stack:** Python 3.12, FastAPI, Playwright 1.64.1 async, Pydantic v2. Mongo/LLM yok.

**Spec:** Kullanıcının P3 talebi; docs/02 (Komut dili), docs/03 (Run durumları, Yazma sınırı, Hata sınıfları, Hazır olma), docs/06 P3, docs/07 T05–T12, T25, T26.

## Global Constraints
- Komutlar: read, ensure_value, ensure_choice, activate_tab, find_record, invoke_approved_action, assert_condition (discriminated union, extra=forbid). Selector/JS/URL alanı yok.
- `invoke_approved_action` yalnız kayıtlı aksiyon kimliğiyle; aksiyon şeması hedef + etki + sonuç kontrolü (mutating ise uzlaştırma) zorunlu tutar. Bu aşamada yalnız lab aksiyonları (`APPROVED_ACTION_SET=lab`, production'da reddedilir).
- Hedef her adımda P2 ile çözülür; ambiguous → dispatch yok. Dispatch'ten hemen önce `check_candidate`; stale ise yeniden çözüm (retry-safe adımlarda).
- Mutating aksiyon: niyet + kayıt bağlamı + uzlaştırma tabanı checkpoint'e yazılır → `dispatched` checkpoint → tıklama → `verifying`. Belirsiz sonuç yalnız onaylı okumayla uzlaştırılır; non-idempotent aksiyon asla otomatik tekrar edilmez.
- Bekleme koşullu (DOM mutation / frame olayı) ve süre sınırlı; sabit sleep ana yöntem değil; force click yok.
- Bilinmeyen modal/native dialog kapatılmaz; run `paused_blocked`. Oturum kaybı → `paused_session`.
- Yeni ayarlar: `RUN_DIRECTORY`, `APPROVED_ACTION_SET`, `OUTCOME_TIMEOUT_MS`, `RECONCILE_TIMEOUT_MS`, `TABLE_NO_PROGRESS_LIMIT` (.env.example + docs/05 + config testi).
- Değerler loglanmaz; hassas hedefe ensure_value/read reddedilir (SecretRef P3 kapsamı dışı).

## Review Focus
1. Doğru değer zaten varken hiçbir sürücü çağrısı yapılmamalı (test: `test_ensure_value_no_change_makes_no_write`).
2. Yanıt kaybında uzlaştırma ikinci tıklama yapmamalı; lab commit sayısı 1 (test: `test_lost_response_reconciled_without_double_commit`).
3. Dispatch sonrası süreç kesilirse yeniden başlatmada adım `outcome_unknown` kalmalı, başarılı sayılmamalı (test: `test_restart_after_dispatch_keeps_outcome_unknown`).
4. Kısmi tablo taraması "kayıt yok" dememeli: limit/no-progress/son ayrı sonuçlar (test: `test_find_record_limit_vs_end`).
5. İptal edilen run'da sonraki adım hiç `prepared` olmamalı (test: `test_cancel_prevents_next_step`).

---

### Task 1: Domain — komutlar, onaylı aksiyonlar, durum makineleri
**Files:** Create `src/agentask/domain/{commands,actions,runtime}.py`; Test `tests/unit/test_commands.py`, `tests/unit/test_runtime_states.py`.
**Produces:** `Command` union (op discriminator) + `Condition` union (`value_equals`, `choice_equals`, `tab_active`, `text_present`); `TextMatch(mode: equals|prefix|contains, text)` + `render(params)`; `EvidenceSpec(kind: status_text|list_items, name)`; `ApprovedAction(action_id, title, target, effect: mutating|non_mutating, retry_safe, params, outcome: OutcomeSpec(evidence, success, failures: list[FailureRule(match, error_class, applied: False)], unknown), reconcile: ReconcileSpec | None)` (mutating ⇒ reconcile zorunlu); `KnownBlocker(blocker_id, dialog_name, text, button)`; `AppProfile(session_lost_path_prefixes, session_lost_texts)`; `ActionSet`. `RunStatus`, `StepState`, `transition_run/step` (geçersiz geçiş `IllegalTransition`), `Run`, `StepRecord` (Pydantic, JSON checkpoint).
- [ ] Testler: bilinmeyen op/alan/selector reddi, invoke kayıtsız aksiyon reddi, mutating aksiyonda reconcile zorunlu, plan adım limiti, durum geçiş tablosu (succeeded→dispatched yasak vb.).

### Task 2: Checkpoint deposu + RunService iskeleti
**Files:** Create `application/ports/runs.py`, `infrastructure/runs/local_file.py`, `application/services/runs.py` (kısmi); Test `tests/unit/test_run_repository.py`.
**Produces:** `RunRepository`: `save(run)`, `get(run_id)`, `list_for(owner)`, `find_by_request(owner, request_id)`; atomik yazma (tmp+fsync+replace); `recover_interrupted(repo) -> list[Run]`: running/cancel_requested run'larda dispatched/verifying adım → `outcome_unknown`, run → `outcome_unknown`; aksi → `paused_session(reason=process_restart)`.
- [ ] Testler: yaz/oku, bozuk dosya yok sayılır+loglanır, kurtarma kuralları, request_id aynı payload aynı run / farklı payload conflict.

### Task 3: Kontrol adapterleri (fake driver ile birim, Playwright sürücü ile gerçek)
**Files:** Create `application/ports/controls.py`, `application/controls.py`, `infrastructure/browser/{driver,driver_js}.py`; Modify factory/handle (`handle.driver`), observer (dialog takibi, `wait_for_change`, `open_dialogs`); lab: sekme JS, duplicates Kaydet durumu, `dialog=unknown_modal`. Test `tests/unit/test_control_adapters.py`, `tests/integration/browser/test_driver_adapters.py`.
**Produces:** `ControlAdapter.supports(control) -> bool`, `TextboxAdapter`, `NativeSelectAdapter`, `CustomComboboxAdapter` (input tabanlı combobox desteklenmez), `TabAdapter`, `TableAdapter.find(...) -> RecordSearch(outcome: found|not_found_at_end|limit_reached|no_progress|duplicate_key)`, `AdapterRegistry.for_control(control)` → adapter veya `ControlUnsupported`. Her ensure: `EnsureResult(changed: bool, verified: bool, observed: str | None)`.
- [ ] Testler (gerçek tarayıcı): textbox yaz+doğrula, aynı değerde yazma yok, native ve custom seçim, sekme aktif doğrulama, sayfalı + kaydırmalı tabloda iş kimliğiyle kayıt, limit/no-progress/son ayrımı, desteklenmeyen kontrol.

### Task 4: Executor + toparlanma + uzlaştırma
**Files:** Create `application/services/executor.py`, `infrastructure/approved_actions/lab.py`; complete `runs.py`. Test `tests/integration/browser/test_executor.py`.
**Produces:** `Executor.run(run, handle, cancel_flag)`; hata sınıfları FRAME_CHANGED, TARGET_NOT_READY, TARGET_AMBIGUOUS, CONTROL_UNSUPPORTED, RECORD_NOT_LOADED, SESSION_EXPIRED, KNOWN_OVERLAY, UNKNOWN_DIALOG, WRITE_RESULT_UNKNOWN, BUDGET_EXCEEDED, POLICY_DENIED. `RunService.create(owner, session_id, request_id, steps) / cancel / resume(owner, run_id, session_id) / get / list / start_recovery()`.
- [ ] Gerçek tarayıcı testleri: kullanıcı listesindeki 13 backend senaryosu + adapterin farklı örnek işlemlerde tekrar kullanımı.

### Task 5: API + "İşlem Deneme" ekranı + belgeler
**Files:** `presentation/api/runs.py`, `templates/run_lab.html`, `static/run_lab.js`, pages (`/designer/runs`), bootstrap/lifespan (kurtarma), docs/09, ADR 0004, README, docs/10. Test `tests/integration/test_runs_api.py`, `tests/e2e/test_run_lab_ui.py`.
- [ ] API sahiplik/409/422/202 testleri; e2e: formdan komut seçip hedefi P2 ile doğrulama, çalıştırma, adım durumları, iptal, başarılı/başarısız/belirsiz ayrımı.
