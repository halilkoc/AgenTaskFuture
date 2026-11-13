# Test matrisi ve kabul

## Zorunlu davranışlar
| ID | Senaryo | Beklenen |
|---|---|---|
| T01 | Derin nested frame ve yeni frame | Doğru hedef, ağaç generation takibi |
| T02 | Aynı isimli iki kontrol | Bağlam yeterli değilse ambiguous; tıklama yok |
| T03 | Her reload'da id değişiyor | Kalıcı id/selector olmadan hedef yeniden bulunur |
| T04 | Frame scan yarıda kesiliyor | partial bilgisi; hedef yok diye kesin hüküm yok |
| T05 | Hedef onaydan sonra değişti | Dispatch öncesi yeniden doğrulama |
| T06 | Native ve custom dropdown | Aynı capability farklı adapter ile doğru seçim |
| T07 | Virtual/paged tablo | Business key, son/limit/no-progress ayrımı; yanlış satır yok |
| T08 | Gecikme/overlay | Koşullu bekleme; bilinmeyen modalda dur |
| T09 | Oturum kaybı | Pause; yeni oturumda record/branch/actor revalidate |
| T10 | Server commit, response loss | Duplicate mutation yok; reconciliation/unknown |
| T11 | Crash dispatch öncesi/sonrası | Checkpoint'e göre tekrar güvenliği |
| T12 | Aynı session'da iki run | İkinci mutating execution engellenir |
| T13 | Sahibi farklı run/session | Backend 403/404; veri sızmaz |
| T14 | Model bilinmeyen operation döndürüyor | Compiler reject, browser dispatch yok |
| T15 | Sayfa metninde talimat saldırısı | Policy/action boundary değişmez |
| T16 | Model kapalı/timeout | Dış fallback yok; manual/rule path veya açık unavailable |
| T17 | .env false/yanlış tip/eksik secret | False doğru, invalid startup rejection, secret redacted |
| T18 | Environment .env'yi override ediyor | Belgelenen precedence doğrulanır |
| T19 | Taslak onaysız/stale approval | Mongo published collection yazması yok |
| T20 | Yayın sırasında hata | Eksik release active olmaz |
| T21 | Yeni katalog yayını | Çalışan run pinned; yeni run yeni active release |
| T22 | UI seçim overlay'i | Gerçek click/submit tetiklenmez |
| T23 | Parola/body secret | Model payload/log/snapshot/artifact içinde yok |
| T24 | Semantic diff | Dinamik id farkı yok sayılır; control meaning change işaretlenir |
| T25 | Cancel after dispatch | Geri alındı iddiası yok; reconcile |
| T26 | Aynı request_id yeniden geldi | Aynı run veya conflict; ikinci dispatch başlatılmaz |

## Değerlendirme yöntemi
Unit: saf matching/plan/config/state. Integration: gerçek local browser fixtures, Mongo repository ve release crash paths. E2E: designer→fresh session test→approve→publish→assistant run.
Gerçek browser testi yerine yalnız Mock sayfa kullanarak P1/P2/P3'ü tamamlanmış sayma. Mongo adapter testini memory repo ile ikame etme. Erişim yoksa blocked açıkça yazılır.
Aynı task birden çok kez, farklı fixture seed ile; gösterilen task ve holdout task ayrı. Selector/no-model/model yardımını aynı test kümesinde karşılaştır.
Metrikler: full verified task success, wrong target/write, correct abstention, unnecessary stop, human correction count, authoring time, maintenance time, p50/p95 elapsed, scan/model time, tokens/calls.
Yayın kapıları: bilinen testlerde yanlış iş etkisi, yetki atlama, double write, secret leak ve incomplete release activation sıfır olmalı. Bu, istatistiksel olarak gerçek dünyada sıfır risk kanıtı değildir. Diğer başarı/gecikme hedefleri baseline sonrası kullanıcıyla sabitlenir; uydurma yüzde hedefleriyle tamamlandı deme.
