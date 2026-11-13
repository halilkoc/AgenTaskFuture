# Uygulama planı

Bu belge uygulanacak backlog'dur. P0'dan başla; uygulama kodu yazmak için her aşamada yeniden izin bekleme. Gerçek sistem erişimi gereken işleri ayrı blocked olarak işaretleyip bağımsız geliştirmeye devam et. Gerçek banka ortamında yazma denemesi yapma.

## P0 — İskelet ve konfigürasyon
- Mevcut repo/AGENTS talimatlarını incele; boşsa src layout, pyproject, test/lint/typecheck ve README oluştur.
- Settings + .env.example + gitignore; environment precedence, booleans, secret redaction ve conditional config tests.
- Dependency ports/composition root ve dev identity sınırlarını kur.
Çıkış: yalnız config ile açılan FastAPI; eksik ayarda açık hata; frontend'e secret sızmaz.

## P1 — Deney uygulaması ve browser session
- Local loopback fake Pega fixtures: nested/dynamic/cross-origin (iki yerel origin), duplicate labels, random id, select/combobox, virtual/paged table, delay/dialog/session loss, committed write+lost response.
- Async session lifecycle + owner check + tek session lock. Browser cleanup.
Çıkış: iki kullanıcı izole; fixture hata varyasyonları kontrol edilebilir. Fake uygulama gerçek Pega diye sunulmaz.

## P2 — Frame/DOM ve hedef çözümü
- FrameTracker generation/invalidation, inspect status, bounded partial scans.
- Semantic extractor, form/region/table context, sensitive field filtering.
- Resolver üçlü sonuç: resolved / ambiguous / unresolved (reason + coverage).
- Manual picker, non-dispatch highlight; trace evidence redaction.
Çıkış: id/frame sıra değişimi, duplicate ve re-render testleri; belirsiz durumda yazma yok.

## P3 — Ortak kontrol ve yürütme
- Input/native-select/custom-combobox/tab/table adapterleri; unsupported açık sonuç.
- State-based ensure, condition readiness, budgets/no-progress.
- Run/step state machine, checkpoint, cancellation, dispatch/reconcile sınırları.
Çıkış: lost response testinde çift yazma yok; kontrol uyarlayıcısı farklı örnek işlemlerde tekrar kullanılır.

## P4 — Katalog Tasarımcısı
- Intent/adım kartı, hedef seçim/onayı, parametre kaynakları ve ön/son koşul editörü.
- Yerel draft adapteri; alan/işlem reuse ve provenance.
- Deneme ile gözlem; bağımsız outcome check; yeni session doğrulaması.
Çıkış: JSON elle yazmadan modelsiz de katalog hazırlama tamamlanır; published DB'de onay öncesi kayıt yok.

## P5 — MongoDB ve yayın
- Typed repository + schema validation/index migration; bounded docs.
- Hash-bound approval, immutable revisions, complete release manifest, CAS active pointer.
- Eksik yayın, concurrent publish, stale approval ve content conflict tests.
Çıkış: Mongo adapter integration testi geçer; half release active olamaz; çalışan run eski release'e bağlı kalır.

## P6 — İşlem Asistanı ve sınırlı LLM
- Kural bazlı intent/parameter mapping; ambiguity clarification UI.
- Internal httpx LLMPort (none/basic/bearer); JSON schema output capability negotiation, şema ve enum validation; yoksa strict parse+reject. Şema çıktısının semantik doğruluk olmadığını koru.
- Katalog retrieval permission filtered, token/call budget, timeout; dış fallback yok.
- Plan compiler ile doğrulanmış MVP sequential capabilities execution; user-facing plan ve result.
Çıkış: LLM disabled temel akış; unknown operation/candidate, prompt injection ve token taşması reddi. Serbest model planı dispatch edilemez.

## P7 — Bakım ve gözlemlenebilirlik
- Semantic diff + dependency impact, ilgili regression test seçimi, repair draft.
- Run timeline, hata sınıfı, sürüm/evidence bilgileri, teknik tekrar vs iş başarısı metrikleri.
Çıkış: bir shared adapter/element değişikliğinin etkilediği işlemler bulunur; otomatik production repair yok.

## P8 — Kontrollü genişleme ve gerçek Pega doğrulama hazırlığı
- Koşul/call/bounded loop dilini ancak static validation ve tests ile ekle; phase öncesi özellik kapalı.
- Demonstration dışında tutulan görevlerle capability composition testi.
- Yerel/remote runner sözleşmesi ve integration checklist; gerçek Pega/SSO/API bilinmeyenleri listesi.
- Kurum ortamı sağlandığında kontrol ailesi bazında gerçek Pega sonuçlarını kaydet; gerekirse adapter ekle, fixture testini regression'a dönüştür.
Çıkış: paketlenebilir Ar-Ge uygulaması; test edilen/test edilmeyen sınırlar dürüst raporlanır. Bu aşama production onayı değildir.

## Teslimat
Kaynak kod + kilitli dependency/kurulum yönergeleri + .env.example + test fixture + otomatik testler + katalog örnekleri + API docs + progress raporu. Gerçek .env/credential teslim etme. Windows yerel browser ve Linux headless uyumluluğu erişilebilen platformlarda doğrulanır; test edilmeyen platform belirtilir.
