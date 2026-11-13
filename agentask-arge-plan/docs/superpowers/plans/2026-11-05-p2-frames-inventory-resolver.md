# P2 — Frame takibi, anlamsal envanter, hedef çözümü ve manuel seçim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Oturumdaki sayfanın frame ağacını takip eden, bütçeli anlamsal kontrol envanteri çıkaran, yapılandırılmış hedef tanımını resolved/ambiguous/unresolved olarak çözen ve sayfaya etki etmeyen manuel seçim/vurgulama sağlayan katman.

**Architecture:** Saf domain (`domain/observation.py`, `domain/frames.py`, `domain/targeting.py`): gözlem veri modeli, frame epoch/lineage kuralları, isim normalizasyonu ve çözümleyici. Playwright yalnız `infrastructure/browser/observer.py` (FrameTracker olayları, sayfa içi JS envanteri, picker/highlight) içinde. `application/services/observation.py` oturum kilidi altında iki aşamalı (hafif özet → ilgili frame ayrıntısı → gerekirse genişletme) çözüm yapar. API ve `/designer/targets` deneme ekranı bunu kullanır.

**Tech Stack:** Python 3.12, FastAPI, Playwright 1.64.1 async (Chromium), pytest-asyncio. Mongo/LLM yok.

**Spec:** Kullanıcının P2 talebi; docs/03 (Frame ve envanter, Hedef çözümü), docs/02 (Element eşleştirmesi), docs/06 P2, docs/07 T01–T05, T22, T23.

## Global Constraints
- Kalıcı CSS/XPath, HTML id, frame sıra yolu veya koordinat hiçbir çıktıda kalıcı kimlik olmaz; candidate id = `c-<snapshot_revision>-<n>` (geçici, oturuma bağlı).
- İlk eşleşen seçilmez; model güven puanı yok. Kısmi kapsam "yok" sayılmaz.
- Textbox değerleri envantere alınmaz (yalnız `has_value`); hassas alanlarda seçili metin de yok. Ham HTML log/çıktıya yazılmaz.
- Seçim modunda sayfaya click/submit/input/change/keydown ulaşmaz.
- Ayarlar Settings'ten; yeni: `OBSERVE_TIMEOUT_MS`, `OBSERVE_MAX_FRAMES`, `PICKER_WAIT_MAX_MS` (.env.example + docs/05 + config testi). `FRAME_SCAN_MAX_ELEMENTS` frame başına sınırdır.
- P3 kapsamı (kontrol adapterleri, yürütme) eklenmez; tek yan etki vurgulama/seçim katmanı DOM elemanlarıdır.

## Review Focus
1. Frame yeniden yüklenince eski aday kabul edilmemeli; ama başka frame'deki aday da gereksiz yere geçersiz sayılmamalı (test: `test_frame_reload_invalidates_only_subtree`).
2. Tek eşleşme varken kapsam eksikse "resolved" dememeli (test: `test_single_match_with_incomplete_scope_is_unresolved`).
3. Engellenen origin'deki frame (chrome-error) çökertmemeli, `inaccessible` raporlanmalı (test: `test_blocked_frame_reported_inaccessible`).
4. Etiket alt dizesi farklı alanı eşlememeli ("Not" ≠ "Mevcut notlar") (test: `test_label_match_is_exact_after_normalization`).
5. Seçim modunda native select açılmamalı/değer değişmemeli ve önceden odaklı alana yazılmamalı (test: `test_picker_blocks_typing_and_select_changes`).

---

### Task 1: Domain — gözlem modeli, frame lineage, çözümleyici
**Files:** Create `src/agentask/domain/{observation,frames,targeting}.py`; Test `tests/unit/test_targeting.py`, `tests/unit/test_frames.py`.
**Produces:**
- `ControlKind` (textbox|button|select|combobox|tab|table); `ScanStatus` (complete|partial|inaccessible|timed_out|not_scanned); `ContextEntry(kind, name, key)`; `ObservedControl(candidate_id, frame_ref, kind, role, accessible_name, label, visible, enabled, sensitive, has_value, selected_text, options, contexts, frame_titles)`; `FrameObservation(frame_ref, parent_ref, title, origin, path, depth, epoch, lineage, status, reason, detail_scanned, control_count)`; `Snapshot(revision, created_at, frames, controls)` + `coverage(frame_refs)`.
- `frames.FrameRegistry`: `attach(key, parent_key) -> FrameInfo`, `navigated(key)`, `detached(key)`, `info(key)`, `lineage(ref) -> tuple[(ref, epoch)]`, `is_current(lineage) -> bool`.
- `targeting.normalize_name(s)`, `TargetSpec` (pydantic, extra=forbid: kind, labels≥1, region?, frame_title?, row_key?, require_visible=True, require_enabled=True), `resolve(spec, snapshot, scope_refs) -> Resolution(outcome, reason, snapshot_revision, candidate_id, candidates, coverage, explanation)`. Reason kodları: `unique_match`, `multiple_candidates`, `not_found`, `coverage_incomplete`, `evidence_missing`.
- [ ] Testler (RED→GREEN): normalizasyon (Türkçe İ/ı/Ş, `:`/`*`), exact eşleşme, bölge/frame/satır daraltma, ambiguous adayları listeler, kapsam eksikse unresolved, görünmezse evidence_missing, lineage epoch değişimi.

### Task 2: Observer — FrameTracker + bütçeli envanter (gerçek tarayıcı)
**Files:** Create `src/agentask/infrastructure/browser/{observer.py, inventory_js.py}`; Modify `playwright_factory.py` (handle.observer), `config/settings.py`, `.env.example`, docs/05; Lab: `/pages/sensitive`, `/pages/heavy` (scenario `heavy_rows`), paged tabloya satır başına "Aç" düğmesi, dropdowns sayfasına sekmeler. Test `tests/integration/browser/test_observer.py`.
**Produces:** `PageObserver.observe(scope: ObserveScope | None) -> Snapshot` (scope: frame_titles + only_names for light→detail), `light_scan() -> list[FrameObservation + names]`, `check_candidate(cid) -> str | None` (stale reason: snapshot_superseded|frame_changed|element_detached|element_changed), `element_handle(cid)`.
- [ ] Testler: derin frame alanı ve frame başlık zinciri, geç frame eklenmesi tracker'da görünür, frame reload yalnız alt ağacı geçersiz kılar, id'ler değişse de aynı anlamsal envanter, kısmi tarama (eleman limiti→partial, süre→timed_out, derinlik→not_scanned, engelli→inaccessible), hassas değerler snapshot/loglarda yok, tablo satırı bağlamı, sekme/combobox/select türleri.

### Task 3: Application servis + API (resolve/observe/highlight/picker)
**Files:** Create `src/agentask/application/ports/observation.py`, `application/services/observation.py`, `presentation/api/observation.py`; Modify `application/errors.py` (`CandidateStale` 409), `bootstrap.py`, `app.py`, docs/09. Test `tests/integration/browser/test_resolution.py`, `tests/integration/test_observation_api.py`.
**Produces:** `ObservationService(sessions, settings)`: `navigate`, `observe`, `resolve(spec)` (iki aşama + genişletme), `highlight(cid)`, `clear_highlight`, `start_picker`, `stop_picker`, `wait_pick(wait_ms)`. Endpoint'ler: `POST /api/sessions/{id}/navigate|observe|resolve`, `POST /api/sessions/{id}/candidates/{cid}/highlight`, `DELETE /api/sessions/{id}/highlight`, `POST /api/sessions/{id}/picker/start|stop`, `GET /api/sessions/{id}/picker/selection?wait_ms=`.
- [ ] Testler: kullanıcı talebindeki 9 gerçek tarayıcı senaryosu + API sahiplik/409.

### Task 4: Manuel seçim ve vurgulama (gerçek tarayıcı)
**Files:** Create `infrastructure/browser/picker_js.py`; Modify observer. Test `tests/integration/browser/test_picker.py`.
- [ ] Testler: Kaydet tıklaması commit üretmez, yazma/select değiştirmez, seçilen aday doğru, geç frame ve iç içe frame'de seçim, vurgu etiket/tür/bağlam gösterir, stale aday vurgusu 409.

### Task 5: Deneme ekranı, belgeler, doğrulama
**Files:** `presentation/templates/target_lab.html`, `static/target_lab.js`, `pages.py` (`/designer/targets`), ADR 0003, README, docs/10.
- [ ] Ekran HTTP testi; gerçek çalıştırma duman testi; tüm suite + ruff + mypy.
