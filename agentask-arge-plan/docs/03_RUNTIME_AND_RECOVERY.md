# Çalışma motoru ve kurtarma

## Frame ve envanter
Frame ağacını Playwright nesneleri üzerinden çıkar; ana sayfa JS'inin cross-origin frame DOM'una erişebildiğini varsayma. Her frame için parent ilişkisi, runtime handle/id, generation, navigation epoch, logical context ve inspect status tut.
Attach/navigate/detach ilgili cache'i geçersiz kılar. Envanter geçici snapshot revision taşır. Eylemden hemen önce hedef ve bağlam yeniden çözülür; eski element handle'a güvenilmez.
Kapsam sonuçları: complete, partial, inaccessible, timed_out. İncelenmemiş frame varken 'hedef kesin yok' sonucu verme. Görünmeyen/kapalı bölgeleri kontrollü kapsamla ayır; bütün DOM'u her adımdan sonra çıkarma.
Önce hafif frame özeti, sonra ilgili bölge, sonra bütçeli genişletme. Derinlik/süre/eleman bütçesi dolarsa açık limit sonucu üret. Araçlar uyumlu Playwright API sürümüne göre uygulanır.

## Hedef çözümü
Aday sıralama kanıt bazlı; tekil eşleşme, doğru uygulama/ekran/bölüm/kayıt bağlamı hard gate'tir. Birden fazla eşleşmeyi first()/nth() ile sessizce çözme. Model confidence değerini olasılık veya işlem izni sanma.
Manuel seçim yalnızca user'ın seçtiği gözlemi sağlar; iş anlamı ve etki onayı ayrıca gerekir. Selection overlay click'i sayfaya iletmemeli.
Tablo satırı record business key ile bağlanır; DOM row index'i iş kimliği değildir. Sayfalama/infinite scroll sonu, no-progress, duplicate key ve limit ayrı sonuçlar. Daha yüklenmeyen kayıt 'yok' sayılmaz.
Custom dropdown seçenekleri görünür metin + business code/label eşleştirmesiyle; native olmayan kontrol için select_option zorlanmaz. Bilinmeyen kontrol unsupported döndürür.

## Run durumları
created → validating → ready → running → verifying → completed.
Yan yollar: needs_clarification, paused_session, paused_ambiguous, outcome_unknown, failed, cancelled.
Adım durumları: pending, prepared, dispatched, verifying, succeeded, known_failed, outcome_unknown.
Persisted checkpoint sonrası resume'da kimlik, yetki, release, session ve record context yeniden doğrulanır. PC yeniden başlatıldığında eski browser nesneleri restore edilemez; resume fresh observation ister.

## Yazma sınırı
Dış etki öncesi action intent ve record context kaydedilir; sonra dispatch; sonra postcondition ve kanıt kaydedilir. Dispatch ile checkpoint arasında crash olursa belirsiz sonuç olarak ele alınır. Log yazmak exactly-once sağlamaz.
İstek kimliği aynı UI submission'ın iki run başlatmasını engeller; Pega tarafındaki etkiyi tekilleştirme garantisi değildir.
Read ve güvenli ensure adımları politika kapsamında tekrar edilebilir. Non-idempotent write timeout/5xx/session loss nedeniyle otomatik tekrar edilmez. Önce approved read reconciliation ile record state/action id/version araştırılır. 'Henüz görünmüyor' sonucu işlemin yapılmadığını kanıtlamaz. İşlemin gerçekleşmediği güvenilir şekilde kanıtlanamıyorsa outcome_unknown ve insan incelemesi.
Cancel: yeni adım başlatmayı durdurur, mevcut dispatch'i geri alamayabilir. Cancel after dispatch → reconcile; otomatik rollback yok. Rollback yalnızca ayrı tanımlı/onaylı compensation varsa.

## Hata sınıfları ve politikalar
FRAME_CHANGED: re-observe + re-resolve; TARGET_NOT_READY: bounded condition wait; TARGET_AMBIGUOUS: context narrow or stop;
CONTROL_UNSUPPORTED: stop; RECORD_NOT_LOADED: bounded table traversal; SESSION_EXPIRED: pause;
KNOWN_OVERLAY: catalog-approved handler; UNKNOWN_DIALOG: stop; BUSINESS_VALIDATION: kullanıcıya yapılandırılmış sonuç;
WRITE_RESULT_UNKNOWN: reconciliation; BUDGET_EXCEEDED: stop; POLICY_DENIED: reject.
Her recovery state machine için attempt/time budget ve no-progress guard vardır. Her hata mesajı için süreç kodu yazma. Popup metni eşleşti diye kapatma/Onay düğmesine basma.

## Hazır olma ve concurrency
Sabit sleep'i temel strateji yapma. Playwright actionability + uygulama/bölge hazır olma koşulları kullan; networkidle genel başarı kriteri değildir.
Session başına tek mutating execution; authoring ve runtime aynı session'da paralel çalışamaz. Kullanıcı bağlamı değiştirirse yeniden doğrula veya dur. Lease kaybından sonra yeni dispatch engellenir; başlamış dış etkinin geri alınabildiğini varsayma.
