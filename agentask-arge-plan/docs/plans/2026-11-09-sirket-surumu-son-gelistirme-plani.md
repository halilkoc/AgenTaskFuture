# Şirket sürümü — kod incelemesi ve son geliştirme planı (2026-11-09)

Durum: **yalnız inceleme ve plan.** Bu belge için kod yazılmadı, test çalıştırılmadı; `.env`, veriler ve yayınlara dokunulmadı.
Kapsam: tek uygulama, tek kullanıcı. OpenShift, çok kullanıcılı ölçekleme ve kurumsal SSO ertelendi.
Mevcut paket (`dist/agentask-company-test-0.1.0-20261109.zip`) **nihai değildir.**

---

## 1. `APPROVED_ACTION_SET=file` kod incelemesi

### 1.1 Şema
Yükleme `infrastructure/approved_actions/file.py`, şema `domain/actions.py`. Bilinmeyen alan reddedilir. Dosya yalnız açılışta okunur.

| Alan | Kural |
|---|---|
| `actions{}` | Anahtar `action_id` ile aynı olmalı |
| `target` | `TargetSpec`: tür yalnız `button`; `labels`, isteğe bağlı `region`, `frame_title`, `row_key` |
| `effect` | `mutating` veya `non_mutating` (kurum beyanı; sistem doğruluğunu sınamaz) |
| `retry_safe` | Yalnız `non_mutating` ile belirsizlikte tekrar sağlar |
| `params[]` | `name`, `title`, `max_length` |
| `outcome` | `evidence` (`status_text` veya `list_items`), `success`, `failures[]`, `unknown[]` |
| `reconcile` | `mutating` için zorunlu: `reload`, `evidence`, `match`, `expected_increase=1` |
| `requires_fields[]` | Basmadan önce alan değeri parametreye eşit olmalı |
| `blockers[]`, `profile` | Tanımlı pencere davranışı, giriş sayfası yol önekleri |

Sır içermeyen örnek:
```json
{"actions": {"kurum.not_kaydet": {
  "action_id": "kurum.not_kaydet", "title": "Notu kaydet",
  "target": {"kind": "button", "labels": ["Kaydet"], "region": "Notlar"},
  "effect": "mutating", "retry_safe": false,
  "params": [{"name": "metin", "title": "Not", "max_length": 500}],
  "requires_fields": [{"target": {"kind": "textbox", "labels": ["Not"]}, "param": "metin"}],
  "outcome": {"evidence": {"kind": "status_text"},
              "success": {"mode": "prefix", "text": "Kaydedildi"},
              "failures": [{"match": {"mode": "equals", "text": "Kayıt başarısız."},
                            "error_class": "BUSINESS_VALIDATION"}]},
  "reconcile": {"evidence": {"kind": "list_items", "name": "Mevcut notlar"},
                "match": {"mode": "contains", "text": "{metin}"}}}},
 "profile": {"session_lost_path_prefixes": ["/prweb/login"]}}
```

### 1.2 Sınırlar
| Sınır | Gerçek durum |
|---|---|
| Uygulama | Dosyada uygulama alanı yok; set süreç genelidir. Sınır, Asistan'ın `required_origin` kontrolü ve izinli origin politikasından gelir. |
| Ekran | Aksiyon ekrana bağlı değildir; bağ adımın rotasıyla kurulur. Plan `assert_screen` ile başlar, her sayfa adımından önce yeniden doğrulanır. Tek adım denemesi ekran yokken çalışabilir; yayın ekran ister. |
| Hedef | Her çalıştırmada anlamsal olarak çözülür; çoklu eşleşmede durur, modal arkasında tıklamaz. |

### 1.3 Sonuç ve uzlaştırma (`Executor._invoke`)
1. `requires_fields` denetlenir; alan değeri parametreye eşit değilse tıklanmaz.
2. Taban kanıt okunur, tıklamasız uygunluk denemesi yapılır.
3. Niyet yazılır, `DISPATCHED`, tek tıklama.
4. Yalnız tıklama sonrası **yeni** kanıt metni `success` / `failures` / `unknown` ile karşılaştırılır. `failures` “uygulanmadı” bilgisidir.
5. Belirsizlikte: `non_mutating + retry_safe` tekrar eder; aksi halde `reconcile` çalışır. Eşleşen öğe tam 1 artmışsa uygulandı, yoksa `OUTCOME_UNKNOWN`; yeniden gönderilmez.

### 1.4 Dosya değişince
Çalışan süreç etkilenmez; aşağıdakiler yeniden başlatma sonrasıdır.

| Değişiklik | Taslak ve onay | Eski yayın ve çalıştırma |
|---|---|---|
| Geçersiz dosya | Uygulama başlamaz | Uygulama başlamaz |
| Aksiyon silindi | `step_N_unknown_action`; onay/yayın engellenir | Yayın kaydı değişmez; çalıştırma `unknown_action` ile reddedilir |
| Parametre kümesi değişti | Taslak doğrulaması yakalamaz | Çalıştırma `params_mismatch` ile reddedilir |
| **Aynı id; hedef, etki, kanıt, uzlaştırma değişti** | **Algılanmaz:** hash yalnız `action_id` ve parametreleri kapsar; onay ve yeni oturum testi geçerli kalır | **Algılanmaz:** manifest aksiyon özeti tutmaz; sonraki çalıştırma yeni tanımı kullanır |

### 1.5 Reddetme
Yanlış dosya/anahtar/bilinmeyen alan → açılışta `ConfigurationError`. Taslak `PATCH` → `PlanInvalid: unknown_action`. Derleme ve `validate_plan` → `unknown_action` / `params_mismatch`. Yürütmede aksiyon yok → `POLICY_DENIED`. İçeriği değişmiş aksiyon → **reddedilmez.**

### 1.6 Kusurlar
| # | Kusur | Kanıt |
|---|---|---|
| A1 | Aynı id ile değiştirilmiş aksiyon algılanmıyor; `mutating`→`non_mutating` etki onayını sessizce kaldırır | `StepCard.definition`, `ManifestEntry` |
| A2 | Aksiyon uygulamaya bağlı değil | `ActionSet` şeması |
| A3 | `non_mutating + retry_safe=false + reconcile yok`: belirsiz sonuçta `assert` patlar; sonuç güvenli ama yazılım hatası görünür. **Paketteki örnek dosya bu biçimde** | `executor.py:1103`, `approved-actions.example.json` |
| A4 | Sonucu belirsiz çalışma, aksiyon silindikten sonra sürdürülürse `KeyError` | `executor.py:283` |
| A5 | `profile.session_lost_texts` tanımlı ama çalışma anında kullanılmıyor | `_session_lost` yalnız yol önekine bakar |

Paket engelleri (bu incelemede bulundu):
| # | Kusur | Kanıt |
|---|---|---|
| B1 | `/catalogs` yalnız `application_id=lab` sorguluyor; `pega_test` yayınları görünmez | `catalogs.js:22` |
| B2 | Eski `/designer` taslağı sabit `application_id: "lab"` ile açıyor | `designer.js:137` |
| B3 | API varsayılanları `"lab"` | `api/catalogs.py:76`, `api/drafts.py:150,194` |

### 1.7 Test kanıtı
- Dosya: `test_action_file_loads_and_rejects_bad_content`, `test_action_file_is_used_by_container`
- Şema: `test_mutating_action_requires_target_outcome_and_reconcile`, `test_non_mutating_action_may_skip_reconcile`
- Red: `test_plan_rejects_unknown_action_and_wrong_params`, `test_runs_api.py` (`unknown_action`)
- Etki ve sonuç: `test_compile_approved_action_step`, `test_mutating_operation_requires_acknowledgement`, `test_picker_selection_and_mutating_trial_requires_ack`, `test_lost_response_reconciled_without_double_commit`, `test_lost_response_on_mutating_transition_is_not_resent`, `test_approved_action_through_designer_and_assistant`
- Pencere: `test_known_modal_handled_by_defined_behaviour`, `test_unknown_modal_stops_without_closing`

**Testi yok:** dosya değişiminin taslak/onay/yayın etkisi, aynı id'de içerik değişimi, çalışma anı `POLICY_DENIED`, `file` kipiyle tarayıcıdan uçtan uca çalıştırma, A3 ve A4.

---

## 2. Eksiklerin ayrı ayrı değerlendirmesi

Ortak kural: her yeni kontrol, tanımlama sırasında hedefi değiştirmez; yürütmede güncel DOM'dan çözülür, sonuç ayrıca okunur, belirsizlikte durur. Kabul koşullarındaki “lab” maddeleri otomatik testle ölçülür.

### 2.1 Autocomplete
- **Mevcut:** `listbox_options`, `click_option`, `await_options_change`, `settle`, tam eşleşme (`pick_option`), etiket/değer doğrulama. `input[role=combobox]` açıkça reddedilir. **Risk:** rolü olmayan düz `input` autocomplete metin alanı sayılır; yazılır ve “doğrulanır”, öneri seçilmemiş olabilir.
- **Geliştirme:** `AutocompleteAdapter`; `ensure_choice` üzerine `search_text`. Yaz → öneri bekle → tam etiket eşleşmesi → seç → **kalıcı değeri** doğrula. Tasarımda açık “yazınca öneri çıkıyor” beyanı (`autocomplete=true`) ve düz input için uyarı. Tasarımcıda örnek arama ile seçenek okuma.
- **Bağımlılık:** S1 sözleşme kuralı; choice altyapısı.
- **Kabul:** lab: gecikmeli (≥800 ms) öneride doğru seçim ve `data-value` eşleşmesi; öneri yok / iki eşleşme / kısmi eşleşme / öneri seçilmeden blur durumlarında 0 değişiklik ve `BUSINESS_VALIDATION`; yeniden çizilen listede tek seçim. Şirket: en az 1 Pega autocomplete.

### 2.2 Checkbox
- **Mevcut:** Envanter `type=checkbox` dışlar; seçici “desteklenmiyor” der. `ControlKind`, durum okuma, komut yok. Etki beyanı (`ui_local`/`unknown`) ve belirsizlikte tekrar etmeme kalıbı yeniden kullanılabilir.
- **Geliştirme:** `ControlKind.CHECKBOX`, `role=checkbox` dahil envanter, `checked` durumu, `ensure_checked` komutu ve adaptör, derleme, “İşaretle / kaldır” bileşeni. Görsel olarak gizli input + label (Pega'da yaygın) için etiket üzerinden etkileşim, force yok.
- **Bağımlılık:** S1.
- **Kabul:** lab: işaretli ise 0 tıklama; aç/kapa doğrulanır; aynı etiket bölümle ayrılır; devre dışı/gizli/modal arkası 0 değişiklik; etki `unknown` iken tek gönderim; uygulama geri alırsa başarısız.

### 2.3 Radyo
- **Mevcut:** Checkbox ile aynı; ek altyapı yok.
- **Geliştirme:** `ControlKind.RADIO_GROUP`: `fieldset/legend` veya `role=radiogroup` grup adı + seçenek. Grup tek hedef olarak modellenir, tek radyo değil. `ensure_choice` yeniden kullanılır; adaptör ayrı. Seçenek okuma ve Asistan seçim listesi hazır kalıpla.
- **Bağımlılık:** S1; checkbox envanteri.
- **Kabul:** lab: aynı değerli iki grup ayrılır; grup adı yoksa açık “desteklenmiyor”; yinelenen/devre dışı seçenekte durur; seçilen radyo ve değer okunarak doğrulanır.

### 2.4 Çoklu seçim
- **Mevcut:** `multiple` algılanır ve `multi_select_not_supported` ile reddedilir; seçenek okuma hazır.
- **Geliştirme:** `ensure_choices` (hedef küme, “tam olarak bu küme”); native `select multiple` ve `aria-multiselectable`; fark hesabı (ekle/çıkar); küme doğrulama; parametre `list` türü (Asistan çoklu seçim), `choices_equal` koşulu. Tek seçim komutundan ayrı.
- **Bağımlılık:** S1; parametre modeli değişimi.
- **Kabul:** lab: mevcut küme korunarak yalnız fark uygulanır; eksik/devre dışı üyede **hiçbir** değişiklik yapılmadan durur; küme sırası sonucu etkilemez; aynı küme 0 değişiklik.

### 2.5 Tarih: native alan ve takvim ayrı
- **Mevcut:** `type=date` ve düz metin alanı `textbox` sayılır; test yok. Takvim popup desteği yok.
- **Geliştirme:** (a) **Native/maskeli:** `ControlKind.DATE` veya `textbox` üzerinde `date_format`; analistin beyan ettiği biçim; normalize edilmiş karşılaştırma. (b) **Takvim popup:** Önce yazarak giriş denenir ve doğrulanır; yalnız yazı kabul etmeyen bileşen için `role=grid` takvim adaptörü (ay gezinme sınırı dahil). (b) şirket DOM'u görülmeden kesinleşmez.
- **Bağımlılık:** S1. (b), şirket DOM kanıtı.
- **Kabul:** lab: `type=date` ve maskeli alanda biçim dönüşümü; geçersiz tarih (31.02) gönderilmez; uygulama farklı tarihe çevirirse başarısız; takvim bileşeninde ay geçişli seçim; devre dışı gün seçilmez.

### 2.6 Dosya yükleme
- **Mevcut:** `ArtifactService` (sahiplik, boyut, tür, sha256); envanter `type=file` dışlar; sürücüde `set_input_files` yok.
- **Geliştirme:** `ControlKind.FILE`, `set_input_files` ilkeli, `upload_file` komutu; **kaynak yalnız artifact deposu** (serbest dosya yolu yok); Asistan'da dosya parametresi ve yükleme ucu; tür/boyut politikası; hedef uygulamada yükleme sonucu kanıtı zorunlu; değerlere benzer şekilde ad loga yazılmaz. Yükleme veri etkisi sayılır (`unknown`/onaylı).
- **Bağımlılık:** S3 parametre türü; karar K4.
- **Kabul:** lab: izinli dosya tek yüklenir ve sonuç kanıtlanır; tür/boyut dışı dosya 0 gönderim; belirsiz sonuçta tekrar yok; başka kullanıcının dosyası kullanılamaz; yol parametresi yok.

### 2.7 Yeni tasarımcıda Kayıt bul
- **Mevcut:** `FindRecordCommand`, `TableAdapter` (none/paged/scroll, duplicate, limit, no-progress), `find_record` derlemesi, eski tasarımcı, `test_find_record_*`. Yeni tasarımcıda `supported: false`. `next_labels`, `end_text` katalogda yok; eski arayüz `paged` sabit.
- **Geliştirme:** Yeni tasarımcı düzenleyicisi (tablo seçimi, anahtar kaynağı: sabit/sor/önceki çıktı, gezinme türü), kalıcı kayıt ve yeniden açma; `StepCard.next_labels/end_text`; arama formu varsa önceki adımlarla kurulur; anahtar sütunu seçimi (bugün ilk hücre varsayılıyor).
- **Bağımlılık:** S3 (önceki çıktı).
- **Kabul:** lab: sayfalı ve kaydırmalı tabloda 1 eşleşme; yok → kesin “yok”; limit/ilerleme yok → “kesin değil”; yinelenen anahtar → durur; yeniden açma aynı tanımı gösterir. Şirket: Pega tablo gezintisi.

### 2.8 Tablo satırı hedefi
- **Mevcut:** `TargetSpec.row_key` çözümleyicide çalışır (`test_row_key_matches_exact_text…`); `table_row` bağlamı gözlenir. Dinamik değer yok; `ctx.records` yalnız niyet kaydında; UI yok.
- **Geliştirme:** `row_key_from` (Kayıt bul sonucuna veya parametreye bağlama); satır içi alan/düğme hedefi; “Satırdaki düğmeye bas” için ekran geçişi veya onaylı aksiyon bağlantısı; bulunan kaydın satırını kapsam olarak taşıma.
- **Bağımlılık:** 2.7, S4 (geçiş).
- **Kabul:** lab: aynı adlı düğmelerden yalnız doğru satırdakine basılır; satır kayboldu/yeniden sıralandı → yeniden çözülür ya da durur; satır bağlamsız tanım reddedilir.

### 2.9 Kayıt bağlamı
- **Mevcut:** `start_context`, `completion`, `ContextCheck` yalnız alan eşitliği; yeni tasarımcıda salt okunur (taslak düzenlenemez). `RECORD_CONTEXT_MISMATCH` testli.
- **Geliştirme:** Yeni tasarımcıda başlangıç ve geçiş bağlamı düzenleyicisi; tablo satırından bağlam; çok anahtarlı bağlam (mevcut en fazla 5 koşul yeterli).
- **Bağımlılık:** 2.7, 2.8.
- **Kabul:** lab: yanlış kayıtta 0 yazma; bağlam yeniden açılınca düzenlenebilir; bileşen çağrısında bağlam taşınır.

### 2.10 Önceki çıktıdan bileşen girdisi
- **Mevcut:** `_render(v, values)` statik; arayüz reddeder. `rebase_output_refs` düzleştirme var.
- **Geliştirme:** `CallSpec.arguments` için çıktı referansı; bileşen içi `{param}` kullanımını plan aşamasında `value_from`/`choice_from` referansına çeviren derleme; bileşen ekran bağlamı ve hassas çıktı kuralları.
- **Bağımlılık:** S1; `output_refs`.
- **Kabul:** lab: gerçek okuma bileşen içinde kullanılır; kaynak okuma başarısız → bileşen başlamaz; hassas çıktı reddedilir; 3 kat iç içe; pinli hash değişmez kuralı.

### 2.11 Önceki çıktıdan onaylı işlem parametresi
- **Mevcut:** `InvokeApprovedActionCommand.params: dict[str,str]`; yalnız sabit/sor. `requires_fields` alan-parametre eşitliği.
- **Geliştirme:** `params_from`; `_bound` çoklu referans (bugün `refs[0]`); `requires_fields` ve `reconcile` şablonlarında bağlanmış değer; önizlemede “çalışırken okunacak” gösterimi.
- **Bağımlılık:** 2.10 ile aynı çıktı bağlama çekirdeği.
- **Kabul:** lab: okunan değer gönderilir ve uzlaştırmada kullanılır; boş/uzun/hassas değerde 0 gönderim; yanıt kaybında mükerrer yok; ack metni etkiyi gösterir.

### 2.12 Seçimle ekran geçişi
- **Mevcut:** `ControlTrigger` yalnız `BUTTON/TAB`; `_await_transition` var; `choice_effect=unknown` ile sonraki ekran kontrolünde durur.
- **Geliştirme:** `ChoiceTrigger` + `ensure_choice.transition`; seçimden sonra hedef ekran ve kayıt bağlamı doğrulama; dispatch checkpoint; belirsizde yeniden seçmeme; tasarımcıda “Bu seçim ekranı değiştirir”.
- **Bağımlılık:** S1; 1.x etki modeli.
- **Kabul:** lab: doğru seçenek hedefe götürür; yanlış/gecikmeli/beklenmeyen ekran ayrı sonuç; tek seçim; zaten seçili ise geçiş beklenmez ve açıkça açıklanır.

### 2.13 Bağlantıyla ekran geçişi
- **Mevcut:** Envanter `a[href]` ve `role=link` taramaz; `ControlKind.LINK` yok.
- **Geliştirme:** `ControlKind.LINK`, envanter (ad + bölge; `href` kataloğa girmez), `ControlTrigger` genişletmesi, izinli origin kontrolü, yeni sekme açan bağlantı için 2.15 kuralı.
- **Bağımlılık:** S1. Buton/sekmeden ayrı ele alınır.
- **Kabul:** lab: aynı adlı iki bağlantı belirsiz; izinli olmayan hedef engellenir; tek tıklama; hedef ekran doğrulanır.

### 2.14 Etkin yayını geri alma
- **Mevcut:** Değişmez manifest, `compare_and_set_active` (CAS), `releases()` listesi, `manifest_hash`; **geri alma ucu ve arayüz yok**. B1 yüzünden `/catalogs` şirket uygulamasını göstermiyor.
- **Geliştirme:** `activate_release(release_id, expected_active)` (yayıncı yetkisi, CAS, gerekçe), manifest/şema/aksiyon özeti uyum kontrolü, ayrı audit olayı, `/catalogs` düğmesi ve onay, çalışan run'lar pin'de kalır.
- **Bağımlılık:** S1 aksiyon özeti (eski yayın aksiyonu değiştiyse engel).
- **Kabul:** Mongo: eski yayına dönüş yeni kayıt silmez; eşzamanlı iki işlemde tek kazanan; aksiyonu uyumsuz yayın reddedilir; yayıncı olmayan 403; süren run eski yayında kalır; ileri alma da aynı yolla.

### 2.15 Yeni pencere
- **Mevcut:** Algılar, yürütmeyi `PAUSED_BLOCKED` ile durdurur, otomatik geçmez; kullanıcı kararıyla kapatır (kimliğe bağlı); yeni pencereden yeni adıma geçiş yok.
- **Geliştirme:** Karar K2'ye bağlı. Önerilen: **beklenen pencere** tanımı (adımdan sonra açılması beklenen, ekran tanımı olan tek pencere; origin izinli); o pencereyi etkin sayfa yapma; bitince ana sayfaya kontrollü dönüş; adımdan bağımsız çıkan pencere hâlâ durdurur.
- **Bağımlılık:** S4 geçiş modeli; observer/driver'ın tek sayfa varsayımı (kapsamlı değişiklik).
- **Kabul:** lab: beklenen pencere doğrulanıp işlenir ve kapanışta ana ekrana dönülür; ikinci/beklenmeyen pencere durdurur; yanlış ekran 0 yazma; kapanan pencere belirsiz sonuç üretir.

### 2.16 İsteğe bağlı modal
- **Mevcut:** Ekran bölgesi olarak beklenen pencere (`_expected_dialog`), dosyadan `blockers` (ad+metin → tanımlı düğme); bilinmeyen pencere durur. Tasarımcıdan blocker tanımlanamaz; “bazen çıkan ama işi etkileyen” modal için adım yok.
- **Geliştirme:** Tasarımcıda “Bu pencere çıkarsa” tanımı (ad, metin, izinli düğme, etki beyanı); `blockers`'ın katalog/aksiyon özetine bağlanması; veri etkili modal yalnız onaylı akışta.
- **Bağımlılık:** S1 özet; 2.15 ile ortak engel modeli.
- **Kabul:** lab: tanımlı modal çıkınca tanımlı düğme ve akış sürer; çıkmazsa bekleme yok; aynı adlı farklı metin durur; iki modal durur; yanlış düğme tıklanmaz.

---

## 3. Son geliştirme planı

Her aşama sonunda: birim + tarayıcı + Mongo testleri, `caffeinate -i`, saklı çıktılar, kusur listesi. Sözleşme: alanlar yalnız doluysa yazılır; eski hash ve yayınlar değişmez (`catalog-v6`).

| Aşama | İş | Boyut | Bağımlı |
|---|---|---|---|
| **S1 Güven temeli** | A1 aksiyon özeti (taslak/onay/yeni oturum testi/manifest/run), A2 `application_id`, A3–A5, B1–B3, örnek dosya, dosya değişim testleri, `file` kipi uçtan uca | Orta | — |
| **S2 Yayın yönetimi** | 2.14 geri alma | Küçük | S1 |
| **S3 Veri akışı** | 2.11 aksiyon parametresi, 2.10 bileşen girdisi, ortak çoklu referans çekirdeği | Orta | S1 |
| **S4 Geçiş tetikleyicileri** | 2.13 bağlantı, 2.12 seçim | Orta | S1 |
| **S5 Kayıt** | 2.7 Kayıt bul, 2.8 satır, 2.9 bağlam | Büyük | S3, S4 |
| **S6 Kontroller I** | 2.2 checkbox, 2.3 radyo, 2.1 autocomplete | Büyük | S1 |
| **S7 Kontroller II** | 2.4 çoklu seçim, 2.5a tarih, 2.6 dosya | Büyük | S3, S6 |
| **S8 Pencere ve modal** | 2.16 isteğe bağlı modal, 2.15 beklenen pencere | Büyük | S4 |
| **S9 Bütünleşik sürüm** | Tam regresyon, Docker, paket yeniden üretimi, Windows ön kontrolü, belgeler | Orta | Tümü |

Sıra gerekçesi: S1 güvenlik ve paket engelidir. S3 ve S4, Kayıt bul'un önkoşuludur. Pencere modeli en riskli değişiklik olduğu için kontrol türlerinden sonra gelir ve kapsamı K2 kararına bağlıdır.

**2.5b takvim popup:** şirket DOM'u görülmeden tasarlanmaz (aşama S9'dan sonra veya şirket keşfinde).

### Kararlar (geliştirmeden önce gerekli)
| # | Karar | Öneri |
|---|---|---|
| K1 | Değişmiş aksiyonda eski yayın | **Çalıştırmayı reddet**, yeniden onay ve test iste |
| K2 | Yeni pencere | Yalnız tanımlı tek “beklenen pencere”; serbest geçiş yok |
| K3 | Geri alma yetkisi | Yayıncı rolü, gerekçe zorunlu |
| K4 | Dosya kaynağı | Yalnız artifact deposu; serbest yol yok |
| K5 | Çoklu seçim anlamı | “Tam olarak bu küme”; ayrı ekle/çıkar yok |

### Şirket bağlantısı olmadan doğrulanamayanlar
Pega DOM'unda: autocomplete, gizli input'lu checkbox/radyo, tarih bileşeni, tablo gezintisi, dosya yükleme, popup ve modal davranışı. SSO/MFA ile elle giriş ve `TARGET_ALLOWED_ORIGINS` kapsamı. Kurumsal MongoDB/TLS, kurum modeli, S3, log altyapısı. Windows kurulum betikleri ve kurulu Edge/Chrome uyumu.

Lab testi Pega uyumu kanıtı değildir. **Tek taşımada** Pega'ya özgü sapma çıkabilir; bu yüzden her adaptör belirsizlikte durur ve Bölüm S ilk olarak DOM uyum envanterini ister.

---

## 4. Toplu kabul listesinin genişletilmesi

Mevcut: `docs/17_LOCAL_ACCEPTANCE.md` (16 adım), `MANUAL_ACCEPTANCE.md` Bölüm S (19 adım). Öneri: aynı iki belge, aşağıdaki ekler; yeni belge açılmaz.

### Yerel (lab) ekleri
| # | Senaryo | Beklenen |
|---|---|---|
| L17 | Yayın sonrası aksiyon dosyasını değiştir, yeniden başlat | Eski işlem çalışmaz; neden açık; yeniden onay sonrası çalışır |
| L18 | `/catalogs`'tan önceki yayına dön, ileri al | Etkin yayın değişir; kayıtlar korunur; çift tıklamada tek sonuç |
| L19 | Okunan değer onaylı işleme ve bileşene | Tek gönderim; boş okumada 0 gönderim |
| L20 | Bağlantı ve seçimle ekran geçişi | Doğru ekran; yanlış seçimde durur |
| L21 | Kayıt bul → doğru satırda düğme → kayıt bağlamı | Yinelenen/yok ayrımı; yanlış kayıtta 0 yazma |
| L22 | Checkbox, radyo (bölümlerle aynı etiket) | Doğru grup; aynı durumda 0 tıklama |
| L23 | Autocomplete: doğru, öneri yok, iki eşleşme | Yalnız ilki başarılı; diğerleri 0 değişiklik |
| L24 | Çoklu seçim küme farkı | Yalnız fark uygulanır; eksik üyede hiç değişiklik yok |
| L25 | Native ve maskeli tarih | Biçim doğru; geçersiz gönderilmez |
| L26 | Dosya yükleme | İzinli tek yükleme; tür dışı 0 gönderim |
| L27 | Beklenen yeni pencere ve isteğe bağlı modal | Akış sürer; beklenmeyen durdurur |
| L28 | Paket: Mac'te temiz kurulum, `--doctor`, içerik denetimi | `.env` ve `var/` yok; `HATA` yok |

### Şirket ekleri (Bölüm S)
| # | Senaryo | Beklenen |
|---|---|---|
| S0 | Hedef Deneme ekranında 3 ana Pega ekranının kontrol envanteri | Her kontrol türü tanındı/desteklenmiyor olarak kaydedilir; değer alınmaz |
| S20 | Pega autocomplete, checkbox, radyo, tarih | Her tür için en az bir gerçek alan; sonuç Pega'da doğrulanır |
| S21 | Pega tablosunda Kayıt bul ve satırdan açma | Doğru kayıt; bağlam kontrolü |
| S22 | Pega dosya yükleme ve popup | Tek işlem; belirsizde tekrar yok |
| S23 | Kurum aksiyon dosyası değişimi ve yayın geri alma | Reddedilir; geri alma çalışır |
| S24 | SSO oturumu düşünce devam | Tamamlanmış adım tekrarlanmaz |
| S25 | Kurumsal Mongo/TLS, model, S3, log aktarımı | Yalnız bu adımla kabul edilir |

---

## 5. Uygulama kaydı (K1–K5 kararlarıyla)

Her aşamanın kanıtı aşağıdadır. Tam regresyon S9'dadır; aşama testleri `caffeinate -i` ile çalıştırıldı.

| Aşama | Durum | Kanıt |
|---|---|---|
| S1 Güven temeli | Tamamlandı (lab) | `test_action_pinning`, `test_action_definition_runtime`, `test_action_file_mongo` (dosya değişince eski yayın reddedilir, manifest değişmez) |
| S2 Yayın yönetimi | Tamamlandı (lab + geçici Mongo) | `test_release_activation`, `test_release_activation_ui` |
| S3 Veri akışı | Tamamlandı (lab + geçici Mongo) | `test_output_binding_mongo` (onaylı işlem parametresi ve bileşen girdisi, tasarımdan Asistan'a) |
| S4 Geçişler | Tamamlandı (lab + geçici Mongo) | `test_transition_triggers`, `test_transition_triggers_mongo` (bağlantı, seçim) |
| S5 Kayıt | Tamamlandı (lab + geçici Mongo); **kalan:** anahtar yalnız tablonun ilk sütununda aranır | `test_record_runtime`, `test_record_flow_mongo` |
| S6 Kontroller I | Tamamlandı (lab + geçici Mongo); **kalan:** Pega DOM'unda doğrulama (S20) | `test_controls_runtime` (24 senaryo), `test_controls_flow_mongo` (tasarım → yayın → Asistan) |
| S7 Kontroller II | Tamamlandı (lab + geçici Mongo); **kalan:** takvim açılır penceresi kurum DOM'u görülmeden desteklenmez; ARIA çoklu listede Ctrl gerektiren bileşen doğrulanmadı | `test_multi_date_file_runtime`, `test_artifacts` (yükleme), `test_multi_date_file_flow_mongo` |
| S8 Pencere ve modal | Tamamlandı (lab + geçici Mongo); **kalan:** Pega DOM'unda doğrulama (S22); yeni pencerede duran çalışma sürdürülemez | `test_window_modal_runtime` (16), `test_window_modal_flow_mongo` (2) |
| S9 Doğrulama ve paket | Tamamlandı: 916 passed, çıkış kodları 0; paket 0.2.0 | `var/verification/company-final-2026-11-09/` (`regression/`, `package/`); başarısız ilk koşu `regression-attempt1-failed/` |
