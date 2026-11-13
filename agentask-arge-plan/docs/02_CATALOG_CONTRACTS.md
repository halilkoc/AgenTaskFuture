# Katalog, yayın ve plan sözleşmeleri

## Mantıksal veri modeli
| Varlık | Zorunlu içerik |
|---|---|
| Application | application_id, name, environment binding reference |
| Screen | screen_id, revision, recognition rules, logical regions |
| Element | element_id, semantic meaning, labels/roles, region/context, control behavior, matching constraints |
| Operation | operation_id, revision, intent phrases, typed parameters, preconditions, actions, effects, postconditions, retry/reconciliation policy, authorization reference |
| Release | release_id, application/environment, exact immutable definition revisions, schema/adapter requirements, content hash, test and approval references |
| Plan | plan_id, release_id/hash, typed arguments, supported operation references, compiler version, actor/session binding |

Tanımlar JSON Schema/Pydantic discriminated union olarak doğrulanır; unknown field/op/check reddedilir. Arbitrary Python/JS, eval, CSS/XPath veya serbest URL komutu kabul edilmez.
Element kimliği HTML id değildir. Fiziksel locator, koordinat ve frame sırası kalıcı hedef tanımı olamaz. Reference screenshot isteğe bağlı yardımcı kanıt, tek başına eşleştirme yetkisi değildir.

## Element eşleştirmesi
Örnek: element_id=working_branch; meaning=branch_code_selection; labels=[Şube,Çalışma Şubesi]; behavior=single_choice; logical_region=session_context; unique=true.
Adlar işaret/harf normalizasyonuyla karşılaştırılabilir; kayıt/şube kimlikleri metin olarak tutulur, baştaki sıfırlar korunur. Yakınlık eşleşmesi farklı iş kimliğini kabul ettiremez.
Mantıksal bölge ve ekran tanımları da somut gözlemlerle çözülmeli; açıklaması olmayan döngüsel 'screen doğruysa element doğru' doğrulaması kurma. Gerekli/opsiyonel kanıtlar açık olmalı.

## İşlem örneği (kavramsal)
operation=change_working_branch; parameter=branch_code:string; effect=session_context_change;
preconditions=authenticated + recognized_screen + authorized_branch;
action=ensure_choice(working_branch, branch_code);
postcondition=active_branch == branch_code;
on_uncertain=read_state_then_stop_if_unresolved.
Gerçek ekranda Uygula düğmesi gerekiyorsa bunun tanımı ve etkisi ayrıca eklenir; motor varsaymaz.

## Komut dili
MVP: read, ensure_value, ensure_choice, activate_tab, find_record, invoke_approved_action, assert_condition. 'invoke_approved_action' effect ve outcome check olmadan geçersizdir.
Kod tarafında kayıtlı kontrol adapterleri komutu fiziksel etkileşime çevirir. Genel sınırsız 'click any element' iş yeteneği sunma.
Sonraki faz: if(condition), call_operation, for_each(collection,max_items). Tip, veri akışı, kaynak kapsamı, çağrı döngüsü ve toplam adım bütçesi doğrulanır. Desteklenmeyen yapı reddedilir.
Plan derleme kontrolü niyetin matematiksel doğruluk kanıtı değildir. Belirsiz işlem/parametre kullanıcının açıklamasını gerektirir.

## MongoDB
catalog_screens, catalog_operations: application_id + entity_id + revision unique; sadece yayımlama servisi yazar.
catalog_releases: release_id unique; immutable tanım manifestosu, içerik hash'i ve test/onay referansları.
catalog_active_releases: application_id + environment unique; etkin release pointer.
automation_runs: run_id unique; actor/status/time/release indeksleri.
Mongo schema validation ve Pydantic doğrulaması birlikte; dangling reference ve şema uyumu release öncesi kontrol edilir. Ekrana ait sınırlı element listesi ekran dokümanında gömülebilir; bütün katalog tek sınırsız doküman olmaz.

## Tutarlı yayımlama
Önce tüm immutable revisions idempotent upsert/insert ile yazılır; aynı id+revision farklı hash ile yeniden yazılamaz. Ardından complete release manifest yazılır ve tüm referanslar doğrulanır. En son aktif pointer compare-and-set ile değiştirilir. Eksik yayın runtime tarafından okunamaz. Replica set varsa transaction opsiyoneldir; standalone Mongo'da da pointer-last yaklaşımı güvenli olmalıdır.
Onay kullanıcı kimliği + canonical content hash + test evidence hash + adapter/schema versions ile bağlıdır. Düzenleme onayı geçersiz kılar. Testten sonra değişen içerik yayımlanmaz. Approval durumu istemcinin gönderdiği boolean'dan alınmaz.
Runtime iş başında release'i pin eder. Eski release'e dönmek bitmiş işlemleri geri almaz. Süregelen run değişmez; açık revocation/kill durumu durdurabilir. Devamda güncel kullanıcı yetkisi yine kontrol edilir.

## Uygulama notu — R3 ekran tanımı (2026-11-06)
- `domain/screens.py`:
  - `ScreenDef`: screen_id, title, `regions` (RegionDef: region_id + ad), `markers` (1–10 TargetSpec, zorunlu, tekil
    çözülmeli), `absent_markers` (0–10 TargetSpec; benzer yanlış ekranı ayırır, tam kapsamla yok kanıtlanmalı).
  - Her bölge en az bir işaretle kanıtlanır.
  - Selector/XPath/id/frame sırası/URL/koordinat alanı yoktur (extra=forbid).
- Ortak karar çekirdeği: `judge` → recognized / not_recognized / ambiguous / incomplete.
  - Yürütme (assert_screen + her sayfa adımından önce yeniden doğrulama), Tasarımcı (kaydetmeden önce canlı
    doğrulama) ve Changes (analyze) aynı fonksiyonu kullanır.
  - Karar model değil, koddur.
- **Döngüsel doğrulama yok:**
  - İşaretlerin hepsi işlemin kendi hedefleri olamaz (`screen_markers_only_targets`).
  - Ekranın tanınması elemanı kanıtlamaz; eleman ayrıca bölge bağlamıyla çözülür.
  - Element bölgesi ekran bölgeleri içinde olmalıdır (`element_region_not_in_screen:<id>`).
- **Yayın:**
  - İşlem tanımı `screen_ref` = {screen_id, ekran içerik hash'i} taşır; böylece onay hash'i ekranı kapsar.
  - Ekran revizyonları `catalog_screens`'e (application_id + screen_id + revision unique, $jsonSchema) değişmez
    yazılır.
  - Manifest `screens` listesi kullanılan ekran revizyonlarını pinler ve manifest hash'ine girer.
  - SCHEMA_VERSION `catalog-v2`.
- **Eski (catalog-v1) yayın:**
  - Belgeler yerinde değiştirilmez; `screens` yoksa boş okunur.
  - Çalıştırma `migration_required` ile reddedilir.
  - Geçiş: yayından taslak → ekran tanımı → yeni oturum testi → hash-bağlı onay → yeni revizyon.
- Ekran bir işleme bağlıdır. Bir işlem içinde ekran değiştiren (gezinen) aksiyondan sonraki adımlar reddedilir; çok
  ekranlı işlem sonraki fazdır.

## Uygulama notu — R4 çok ekranlı işlemler (2026-11-06)
- **İşlem:**
  - `screen` (başlangıç) + `extra_screens`.
  - `transitions[]`: `transition_id`, `from_screen`, `to_screen`, `trigger` (`control`: onaylı düğme/sekme
    TargetSpec'i | `approved_action`: adımın onaylı aksiyonu), `timeout_ms` (500–60000), `completion[]`
    (ContextCheck: alan + değer şablonu).
  - `start_context[]`.
  - Adım alanları: `screen_id`, `transition_id`; yeni işlem `follow_transition`.
- **Statik rota:**
  - Adımlar ekranları sırayla izler; geçişin kaynağı o anki ekrandır.
  - Her geçiş tam bir adımda kullanılır ve tetikleyicisi adımın komutuyla uyumludur.
  - Yazma etkili geçişli aksiyonda uzlaştırma tanımlı olmalıdır.
  - Her ekranın işaretleri o ekrandaki hedeflerden ibaret olamaz (`…@screen_id`).
- **Sürüm:**
  - v2: tek ekran, kanonik içerik R3 ile aynı. v3: çok ekran.
  - Revizyon kendi `schema_version`'ını taşır.
  - Tanınmayan anahtar `unsupported_schema` ile okunmaz.

## Uygulama notu — önceki çıktı ve bileşenler (2026-11-07)
- **Önceki adım çıktısı (ADR 0017):** `ensure_value.value_from` / `assert_condition.value_equals.value_from`
  = `{step, max_length}`; yalnız önceki bir `read` komutuna başvurur. Değer derlemede yoktur; yürütücü kaynak okuma
  başarıyla bittiyse yerleştirir, aksi halde `PRIOR_OUTPUT_UNAVAILABLE` ile hiçbir işlem yapmadan durur.
- **catalog-v6 (ADR 0024):** adım alanları `action_hash`, `next_labels`, `end_text`, `in_found_row`, `checked`, `autocomplete`,
  `search_text`, `choice_set`, `date_format`, `file_types`; parametrede `multiple`, `file`; geçişte `window`, `window_origin` ve
  `window_return` tetikleyicisi; taslakta `optional_dialogs`. Yeni komutlar: `ensure_checked`, `ensure_choices`, `ensure_date`,
  `upload_file`, `return_window`, `register_optional_dialogs`; koşullar `checked_equals`, `choices_equal`. Alanlar yalnız doluysa
  yazılır: v1–v5 tanımları, hash'leri ve planları değişmez.
- **catalog-v5 (ADR 0021):** seçim adımı alanları `choice_value`, `choice_effect` (`ui_local|unknown`), `result_text`;
  parametrede `choices` (`[{label, value?}]`; yoksa liste çalışma anında doğrulanır). `ensure_choice` ve `choice_equals`
  için `choice_from` (önceki okuma çıktısı) ve `expected_value`; `ensure_choice.effect`; `text_present.anchor`. Alanlar
  yalnız doluysa yazılır: v1–v4 tanımları, hash'leri ve planları değişmez.
- **catalog-v4 (ADR 0019):** `op=call_operation` adımı `call` ile yayımlanmış bir işlemin belirli revizyonuna
  (içerik hash'i dahil) pinlenir. v1–v3 tanımları ve hash'leri değişmez.
