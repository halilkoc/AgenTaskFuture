# Mimari

## Katmanlar
| Katman | Sorumluluk |
|---|---|
| Presentation | HTTP/WebSocket, rol kontrollü sayfalar, giriş/çıkış DTO |
| Application | Katalog hazırlama/yayımlama, plan derleme, run yönetimi use case'leri |
| Domain | Katalog, işlem sözleşmesi, plan, durum makinesi ve kurallar |
| Infrastructure | Playwright, MongoDB, yerel draft, httpx LLM ve kurum entegrasyon adapterleri |

Domain Playwright/FastAPI/Mongo import etmez. Use case'ler portlarla çalışır. Composition root Settings ve adapterleri birleştirir.

## Ortak çekirdek
1. BrowserSessionManager: yaşam döngüsü, sahiplik, kullanıcı başına izole context, session lock.
2. FrameTracker: attach/navigate/detach, ağaç, generation ve kapsam/erişim durumu.
3. SemanticExtractor: etkileşimli kontrol, rol/label, bölüm/form/satır ilişkisi; hassas değer dışlama.
4. TargetResolver: alan tanımı + güncel envanter → tekil hedef veya açık belirsizlik.
5. ControlAdapterRegistry: native select, custom combobox, input, tab, table ve dialog davranışları.
6. PlanCompiler + PolicyValidator: yalnızca desteklenen komutlar ve yetkili katalogdan çalıştırılabilir plan.
7. Executor + OutcomeVerifier: ön/son koşullar, yazma sınırı, uzlaştırma ve checkpoint.
8. EvidenceRecorder: redakte edilmiş karar kanıtı, hata sınıfı ve sürüm bilgisi.

## Temel portlar
BrowserPort, DraftRepository, CatalogRepository, ReleaseRepository, RunRepository, PolicyPort, IdentityPort, LLMPort, ApplicationMetadataPort, SecretProvider, ArtifactStore.
LLMPort unavailable sonucu normal bir sonuçtur; otomatik dış servis fallback'i yoktur. ApplicationMetadataPort başlangıçta unavailable olabilir.

## Önerilen repo yapısı
- src/agentask/domain/{catalog,planning,runtime,policies}
- src/agentask/application/{dto,ports,use_cases}
- src/agentask/infrastructure/{browser,pega,mongo,drafts,llm,identity,artifacts}
- src/agentask/presentation/{api,templates,static}
- src/agentask/config/{settings,validation}
- tests/{unit,integration,e2e,fixtures}
- docs/adr/

## Asenkron çalışma
Playwright async API kullan; sync API'yi çalışan event loop içinde çağırma. Playwright nesneleri rastgele thread/process'lere taşınmaz. Aynı browser session üzerinde adımlar seri, farklı session'lar kapasite sınırında bağımsızdır.
Ar-Ge web/runner aynı process olabilir. Run sahipliği ve lease/fencing sözleşmesi ayrı tutulur. İlk çoklu worker desteği yoksa tek worker zorunluluğunu açıkça uygula; çok worker altında bellek içi kilidin yeterli olduğunu iddia etme.

## Veri akışı
Authoring: kullanıcı adımı → envanter → aday/manuel seçim → anlam/hedef onayı → deneme → sonuç onayı → yapılandırılmış taslak → test → onaylı içerik hash'i → Mongo yayını.
Runtime: prompt → yetkili yayın seçimi → kural/model önerisi → parametre/politika/plan doğrulama → hedef çözümü → yürütme → sonuç kontrolü.
Modelden gelen metin, DOM metni ve katalog verisi ayrı güven sınırlarıdır. Page içeriği komut veya yetki kaynağı olamaz.
