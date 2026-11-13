# API sözleşmesi taslağı

Bütün private endpoint'ler identity/policy/ownership kontrolü yapar. Request/response Pydantic; OpenAPI güncel tutulur. Aşağıdaki yollar başlangıç sözleşmesidir; implementasyon değişirse bu belge güncellenir.

| Method/path | Amaç |
|---|---|
| GET /health/live, /health/ready | Sağlık |
| GET /api/me | Kimlik ve yetenekler; secret yok |
| GET /api/config/public | Allowlist public UI config |
| POST /api/sessions | İzole browser session (P1: 201; limit 429; yetki operator/designer) |
| GET /api/sessions | Yalnız kendi oturumları (P1) |
| DELETE /api/sessions/{id} | Sahibinin session'ını kapat (P1: 204; başkasının/yok 404; işlemdeyken 409) |
| POST /api/sessions/{id}/navigate | P2: izinli origin'e gezinme (iş etkisi yok); izinsiz 403 |
| POST /api/sessions/{id}/observe | Bütçeli observation; snapshot_revision/coverage (P2) |
| POST /api/sessions/{id}/choice-options | ADR 0021: `{target, open_list}` → `status` (ok, needs_open, unsupported, unresolved, failed), `options[{label, value, state, selected}]`; seçim yapmaz, özel liste yalnız `open_list=true` ile açılır |
| POST /api/sessions/{id}/resolve | P2: TargetSpec → resolved/ambiguous/unresolved + reason/coverage/snapshot_revision |
| POST /api/sessions/{id}/candidates/{cid}/highlight | P2: olaysız vurgu; stale aday 409 candidate_stale (details.reason) |
| DELETE /api/sessions/{id}/highlight | P2: vurguyu kaldır |
| POST /api/sessions/{id}/picker/start, /picker/stop | P2: manuel seçim modu (sayfaya olay iletilmez) |
| GET /api/sessions/{id}/picker/selection?wait_ms= | P2: seçimi bekle (≤ PICKER_WAIT_MAX_MS); aday + snapshot |
| POST /api/drafts | Yerel taslak başlat (P4: 201) |
| GET /api/drafts | P4: kendi taslakları |
| POST /api/drafts/{id}/parameters, POST /api/drafts/{id}/steps, PATCH/DELETE /api/drafts/{id}/steps/{step} | P4: expected_revision ile; çakışma 409 |
| POST /api/drafts/{id}/steps/{step}/confirm-outcome | P4: yalnız sistem doğrulaması başarılıysa |
| POST /api/drafts/{id}/fresh-test | P4: yeni oturumda bütün işlem; content hash'e bağlı |
| GET/PATCH /api/drafts/{id} | Versiyon kontrollü oku/düzenle |
| POST /api/drafts/{id}/steps/propose | Intent → öneri; dispatch yok |
| POST /api/drafts/{id}/steps/{step}/select-target | Geçici candidate + snapshot ref |
| POST /api/drafts/{id}/steps/{step}/confirm | Anlam/hedef/parametre/etki onayı |
| POST /api/drafts/{id}/steps/{step}/trial | Gerçek kontrollü deneme |
| POST /api/drafts/{id}/validate | Şema/referans ve test kapsamı |
| PUT /api/drafts/{id}/screen | R3: ekran tanımı (screen_id, title, marker_candidate_ids 1–10, regions, absent_markers). Adaylar güncel gözlemden anlamsal işarete çevrilir, aday kimliği saklanmaz; kaydetmeden önce canlı doğrulanır (tanınmazsa 409 screen_not_recognized, yalnız işlemin kendi hedefi işaretse 422 screen_markers_only_targets) |
| DELETE /api/drafts/{id}/screen?expected_revision= | R3: taslaktan ekran tanımını kaldırır (taslak onaya hazır olamaz) |
| POST /api/drafts/{id}/screen/verify | R3: taslaktaki ekranı güncel ekranda aynı çekirdekle doğrular; kaydetmez |
| GET /api/drafts/migrations | R3: etkin yayında ekran tanımı olmayan (geçiş gerektiren) işlemler; salt okunur; katalog kapalıysa 503 |
| POST /api/drafts/migrations | R3: eski yayımlanmış revizyondan geçiş taslağı (201). Yayın/revizyon/pointer değişmez; ekranı zaten olan işlemde 422 migration_not_required |
| POST /api/drafts/{id}/approve | İçerik/test hash'e bağlı server approval (P5: publisher; hazır değilse 409) |
| POST /api/drafts/{id}/publish | Publisher yetkisi, idempotent release (P5: request_id; stale_approval/publish_conflict/content_conflict 409; Mongo yok 503) |
| GET /api/catalogs/releases/{id} | P5: manifest + işlem özetleri |
| GET /api/catalogs/releases | Yetkili release listesi |
| POST /api/plans | Prompt+release → açıklama veya doğrulanacak plan (P6'da /api/assistant/* olarak uygulandı) |
| GET /api/assistant/catalog | P6: etkin yayındaki işlemler + model durumu |
| POST /api/assistant/interpret | P6: matched / needs_clarification / no_match; provenance rule_generated|model_suggested |
| GET /api/runs, /api/runs/{id} | ADR 0022: yanıtta `title` ve `summary` (`title`, `failed_stage`, `reason`, `next_step`, `correlation_id`); yalnız sahibine |
| POST /api/auth/login, /api/auth/logout | ADR 0023: yalnız AUTH_MODE=local_admin (aksi 404); giriş 401 `login_failed` / 429 `login_locked`; durum değiştiren istek `X-CSRF-Token` ister |
| POST /api/drafts/{id}/fresh-test[/continue,/cancel] | `manual_login`; yanıtta `fresh_wait`; gerçek uygulamada sunucu elle giriş kullanır |
| POST /api/assistant/preview | P6: sunucu tarafı derlenmiş plan + etki (`unknown` etki açık onay ister) |
| POST /api/assistant/parameter-options | ADR 0021: yayımlanmış seçim parametresinin açık ekrandaki güncel seçenekleri; seçim yapmaz |
| POST /api/assistant/execute | P6: 202 run (binding=release pin); etkin olmayan yayın 409; etki onayı yoksa 403 |
| GET /api/actions | P3: komut listesi ve onaylı aksiyonlar |
| POST /api/runs | Sunucuda yeniden validate edilmiş planı çalıştır (P3: 202; request_id idempotency; plan 422; oturum meşgul 409) |
| GET /api/runs | P3: kendi run'ları |
| GET /api/runs/{id} | Durum ve redakte adım sonuçları |
| POST /api/runs/{id}/cancel | İptal talebi |
| POST /api/runs/{id}/resume | Gerekli bağlam/yetki doğrulamasıyla devam |
| GET /api/runs/{id}/events | Yetkili SSE/WS progress (henüz yok; ekran yoklama yapar) |
| POST /api/catalogs/impact-analysis | Yeni observation ile anlamsal diff (P7: POST /api/changes/analyze olarak uygulandı) |
| GET /api/changes/operations, POST /api/changes/dependency-impact, POST /api/changes/repair | P7: etki ve onarım taslağı (etkin yayın değişmez) |
| GET /api/metrics/runs | P7: iş başarısı / teknik toparlanma / süre metrikleri |

Candidate id runtime scope'tadır: session/snapshot/generation ile bağlıdır. Stale candidate HTTP 409 üretir veya açık yeniden çözüm ister. Kullanıcıdan alınan selector çalıştırılmaz.
Long-running trial/run 202 + job/run id döndürür; browser işini HTTP timeout'a bağlama. session lease koşulları uygulanır.
Mutating create/run/publish request_id/idempotency key taşır. Aynı key farklı payload hash ile conflict. Draft update expected_revision/If-Match kullanır. Client approve=true göndermek yeterli değildir.
Error envelope: code, safe_message, correlation_id, retryable, details (redacted). Teknik retryable bayrağı belirsiz write'ı tekrar etme yetkisi değildir.
409: stale/ambiguous/conflict; 422: schema/unsupported plan; 403: policy; 503: etkin dependency unavailable. Outcome_unknown başarılı HTTP response içinde de açık run state olabilir.

P1 hata kodları: session_not_found 404, session_busy 409, session_limit_reached 429, navigation_not_allowed 403, service_shutting_down 503.

P8: POST /api/assistant/composite/preview, POST /api/assistant/composite/execute (COMPOSITION_ENABLED=false iken 422 composition_disabled).

## R3 notları (2026-11-06)
- Yayımlanmış ekransız (catalog-v1) işlem: `/api/assistant/preview`, `/execute`, `/composite/*` → 409 `migration_required`
  (details: operation_id, revision). Kontrol atlanmaz, run oluşturulmaz.
- `/api/assistant/preview` yanıtı: `screen` (screen_id, title), `bindings` (parametre başlığı + bağlı değer; hassas
  görünen/secret_ref değer `••••`), `steps` (ilk satır "Ekranı doğrula: …", şablonlar bağlı değerle doldurulmuş),
  `commands` (yanıttaki kopyada hassas değerler maskeli; yürütme planı sunucuda ayrıca derlenir).
- `/api/changes/analyze` yanıtı `screen` alanı içerir (aynı ekran çekirdeği; eski işlemde `migration_required`).
- 422 doğrulama hataları: `details.errors[] = {field, reason, message}` (Türkçe neden; girdi değeri yok) ve geriye dönük
  `details.fields`.

## R4 notları (2026-11-06)
- **Ekran uçları:**
  - `PUT /api/drafts/{id}/screen`: aynı `screen_id` ekranı günceller, ilgili adımlar yeniden onaya döner. Yeni
    kimlik ek ekran ekler; ilk ekran başlangıç ekranıdır.
  - `DELETE /api/drafts/{id}/screen?screen_id=`: başlangıç ekranı, ek ekranlar varken kaldırılamaz (422).
  - `POST /api/drafts/{id}/screen/verify`: `{session_id, screen_id?}`.
- **Geçiş uçları:**
  - `PUT /api/drafts/{id}/transitions`: `{transition_id, from_screen, to_screen, trigger_kind: control|approved_action,
    session_id?, trigger_candidate_id?, timeout_ms, completion[]}`. Tetikleyici adayı çözülür, tıklanmaz. Değişiklik,
    o geçişi kullanan adımları yeniden onaya döndürür.
  - `DELETE /api/drafts/{id}/transitions/{transition_id}?expected_revision=`.
  - `PUT /api/drafts/{id}/start-context`: `{checks[]}`.
- **Adım:** `PATCH /api/drafts/{id}/steps/{step}` `screen_id` ve `transition_id` kabul eder. Geçiş adımı denemesi
  `acknowledge_effect=true` ister (ekran değişir).
- **Asistan önizlemesi:** `navigation` (ekran etkisi, iş etkisinden ayrı), `route` (ekran başlıkları) ve geçiş
  satırları içerir.
- **Changes:**
  - `/api/changes/analyze` → `screens[]` (her ekranın kararı).
  - `/api/changes/dependency-impact` → `screen_ids[]`.
- **Run adım hata sınıfları:** `TRANSITION_TIMEOUT`, `UNEXPECTED_SCREEN`, `TRANSITION_NOT_COMPLETED`,
  `RECORD_CONTEXT_MISMATCH`.

## Ana plan C/E/F/G notları (2026-11-07)
- **C (ADR 0017):**
  - `PUT /api/drafts/{id}/transitions`: kaynak/hedef ekranın önceden tanımlı olması gerekmez; tetikleyici yine
    canlı ekranda tekil çözülür. Tanımsız uç `transition_unknown_screen` eksikliği olarak kalır.
  - `DELETE /api/drafts/{id}/parameters/{name}?expected_revision=` — kullanılan parametre 400
    (`parameter_in_use`).
  - `POST /api/drafts/{id}/parameters`: `prior_output` kaynağında `prior_step` (+ bileşen çıktısı için
    `prior_output`).
- **E (ADR 0019):**
  - `GET /api/drafts/{id}/components` — etkin yayındaki çağrılabilir işlemler ve sözleşme özetleri.
  - `PUT /api/drafts/{id}/steps/{step_id}/call` `{expected_revision, operation_id, revision, arguments}` — pinli
    çağrı; özet sunucuda çıkarılır. Döngü/eksik revizyon 400.
  - `GET /api/drafts/{id}/component-updates` — daha yeni revizyonlar ve etkisi (salt okunur).
- **F (ADR 0020):** `POST /api/assistant/plan/propose` `{application_id, prompt}`;
  `POST /api/assistant/plan/preview` `{application_id, release_id, steps}`;
  `POST /api/assistant/plan/execute` `{…, session_id, request_id, acknowledge_effect}` (202, RunOut).
- **G (ADR 0018):** `RunOut.evidence`: maskelemesi doğrulanmış kanıt kimlikleri; içerik
  `GET /api/artifacts/{id}` (sahip kontrollü).

## Şirket sürümü notları (2026-11-09, ADR 0024)
- `POST /api/catalogs/releases/{id}/activate` — yayıncı; `expected_active` ve zorunlu `reason`; uyumsuz aksiyonda reddedilir.
- `POST /api/artifacts/uploads` — ham gövde, `Content-Type`, `X-File-Name` (URL kodlu). Yanıt: `artifact_id`, `size_bytes`, `content_type`. Boyut okunurken sınırlanır; içerik beyan edilen türle uyuşmalı.
- `PUT /api/drafts/{id}/optional-dialogs` — `dialogs[]`: `dialog_name`, `text`, `button_label`, `confirm_no_data=true`.
- `PUT /api/drafts/{id}/transitions` — ek alanlar `window`, `window_origin`, `close`; `trigger_kind=window_return`.
- `POST /api/sessions/{id}/choice-options` — ek alanlar `search` (örnek arama), `multi` (çoklu alan).
- `POST /api/sessions/{id}/interruptions` — ek eylemler `design_new_window`, `design_main_window`; `GET` yanıtında `focused_window`.

