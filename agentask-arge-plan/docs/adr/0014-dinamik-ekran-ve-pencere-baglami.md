# ADR 0014 — Dinamik ekran, pencere bağlamı ve tasarımcıda gerçek oturumdan alan seçimi

Tarih: 2026-11-07 · Durum: kabul edildi (lab'da gerçek Chromium ile doğrulandı; gerçek Pega/SSO doğrulanmadı)

## Bağlam
Yeni Akış Tasarımcısı gerçek Playwright oturumundan alan seçmeye bağlanıyor. Mevcut yürütücünün yetenekleri:
- tanımsız sayfa içi pencerede ve native dialog'da durma;
- yeniden çözümleme;
- DOM değişimine bağlı sınırlı bekleme;
- belirsiz sonuçta uzlaştırma.

Eksik olanlar:
- hedef çözümleyici kapalı penceredeki kopyayı belirsizlik sayıyordu;
- açık modalın arkasındaki alanı ayırt etmiyordu;
- kaplayan katmanı tanımıyordu;
- ekran tanımında yer alan beklenen bir pencerenin içinde çalışılamıyordu;
- yeni pencere/sekme izlenmiyordu.

## Karar
1. **Etkileşim bağlamı (gözlem):** her kontrol için `interaction` alanı tutulur. Değerler:
   - `open`;
   - `inactive_dialog`: kapalı/gizli pencerenin içinde;
   - `behind_dialog`: açık modalın arkasında;
   - `overlay`: sayfanın en az yarısını kaplayan sabit/mutlak bir katmanın altında;
   - `inert`;
   - `dialog_ambiguous`: aynı belgede birbirini içermeyen birden fazla aktif modal.

   DOM'da bulunma, görünürlük (`visible`) ve etkileşime açıklık ayrı tutulur. Bu alan parmak izine girmez;
   pencere açılıp kapanması aday kimliğini değiştirmez.
2. **Çözüm kuralları (işlem hedefi, katı):**
   - `inactive_dialog` aday değildir.
   - Engellenmiş aday listede görünür ama kullanılamaz. Tek etkileşime açık aday varsa o seçilir; hiç yoksa
     `blocked` sonucu verilir.
   - `dialog_ambiguous` durumunda çözüm yapılmaz (`multiple_active_dialogs`).
   - Pencere dışındaki gizli kopyalar eskisi gibi belirsizlik sayılır.
3. **Varlık kanıtı (ekran işaretleri ve kayıt bağlamı):**
   - Ekranın kimliği ve kayıt bağlamı, üstünde pencere açık olsa da kanıtlanır (`presence=True`).
   - Pencere politikası yürütücünün engelleyici kontrolündedir.
   - Yasak işaretler engelli olsalar da görülmüş sayılır (güvenli taraf).
4. **Beklenen pencere:**
   - Etkin ekranın (veya doğrulanmakta olan ekranın) bölge olarak tanımladığı sayfa içi pencere beklenen
     penceredir ve yürütmeyi durdurmaz.
   - Diğer görünür pencereler eskisi gibi engelleyicidir; yalnız onaylı engelleyicide tanımlı düğmeye basılır.
   - Pencereler varsayılan olarak otomatik kapatılmaz.
5. **Yeni pencere/sekme:**
   - Bağlam düzeyinde izlenir; otomatik geçilmez ve kapatılmaz.
   - Açık yeni pencere varken sonraki adım başlatılmaz (`NEW_WINDOW`, paused_blocked).
   - Gönderim sonrası açılırsa sonuç `unknown` sayılır ve uzlaştırma kuralları uygulanır.
6. **Engelli hedef:**
   - Bekleme DOM değişimine bağlıdır ve `READINESS_TIMEOUT_MS` ile sınırlıdır.
   - Süre dolarsa `TARGET_BLOCKED` (paused_blocked) ile durulur; hiçbir şey yapılmaz.
7. **Kullanıcı kararı:**
   - `POST /api/sessions/{id}/interruptions` yalnız iki tanımlı kararı uygular: tarayıcı dialog'unu iptal ederek
     kapatmak ve açılan pencereleri kapatmak.
   - Sahiplik kontrollüdür ama oturum kilidi alınmaz. Native dialog açıkken sayfa betikleri durur ve süren bir
     işlem kilidi tutarak asılı kalabilir; kilit beklemek kilitlenme üretir.
   - Onaylama (accept) kararı yoktur.
8. **Picker:** seçim modunda sayfa kontrollerinden odak ve düzenleme seçimi sürekli kaldırılır. Kompozisyon,
   yapıştırma ve sürükleme olayları da engellenir; böylece modal açılırken otomatik odaklanan alana IME veya metin
   ekleme yoluyla da yazılamaz.
9. **Tasarımcı (gerçek oturum):**
   - Yalnız mevcut uçlar kullanılır: oturum, gezinme, gözlem, picker, çözümleme, vurgulama, kesintiler.
   - Seçimden sonra ve istendiğinde hedef güncel ekranda yeniden çözülür ("Alanı yeniden bul (yazmadan)").
   - Gözlenmeyen bilgi uydurulmaz: bölüm yoksa "gözlenmedi" denir; ekran tanımı gerçek yürütmede ayrıca
     doğrulanır.
   - Gerçek hedefli adımlar temsili denemede çalıştırılmaz; gerçek yürütme mevcut yürütücüdedir.
   - Model kullanılmaz.

## Sonuçlar
- Yeni ortam ayarı yok. Mevcut `READINESS_TIMEOUT_MS`, `PICKER_WAIT_MAX_MS`, `OUTCOME_TIMEOUT_MS` ve
  `RECONCILE_TIMEOUT_MS` kullanılır. Arayüzdeki tek seçim isteği 120 sn ile sınırlıdır; bu bir arayüz davranış
  sabitidir.
- Overlay tespiti sezgiseldir. Sayfanın yarısından küçük katmanlar engel sayılmaz; görünüm alanı dışındaki
  hedefte örtüşme denetlenmez. Eylem anında Playwright'ın kendi eyleme uygunluk kontrolleri de geçerlidir.
- İç içe pencere yığınında yalnız en içteki etkin sayılır. Birbirini içermeyen iki aktif pencere belirsizdir.
- Beklenen yeni pencere/sekmeye geçiş (onaylı geçişle başka sayfaya geçme) desteklenmez; yalnız durulur.

## Ek (2026-11-07) — güvenilirlik düzeltmeleri
1. **Katman kuralı boyuttan bağımsız:**
   - Hedefin merkezindeki nokta-isabet testinde en üstteki öğe hedefin kendisi, alt öğesi, atası veya kendi
     etiketi değilse hedef `overlay` (kapalı) sayılır; katman ne kadar küçük olursa olsun.
   - Görünüm alanı dışındaki hedef tarama sırasında denetlenmez. Sürücü yazma/seçme/tıklama/tıklama denemesinden
     hemen önce hedefi görünür alana kaydırır ve aynı kuralı yeniden uygular.
   - Kapalıysa `TargetBlocked` (bayat hedef türü) ile hiçbir eylem yapılmaz ve hedef yeniden çözülür. Engel
     sürerse sınırlı bekleme sonunda `TARGET_BLOCKED` ile durulur.
   - Veri değiştiren aksiyonda kontrol, gönderim kaydından önceki tıklama denemesinde yapılır.
   - Playwright'ın uygunluk kontrolleri aynen geçerlidir; force veya betikle tıklama yoktur (statik testle
     korunur).
2. **Beklenen pencere açıkça doğrulanır; bölge adı tek başına yetmez:**
   - Adımın beklenen ekranı (doğrulanmış etkin ekran veya o anda doğrulanan ekran) pencereyi bölge olarak
     tanımlamalıdır.
   - O bölgenin tanıma işareti güncel gözlemde bu pencerenin içinde ve etkileşime açık (en üstteki pencere)
     bulunmalıdır.
   - Aynı adlı aldatıcı pencere tanımsız sayılır.
   - **Sözleşme sınırı:** katalog adım bazında "bu pencere bu adımda isteğe bağlı/gelebilir" bilgisini taşımaz.
     Beklenti, adımın beklenen ekranı (R4 `screen_id`) ve o ekranın işaretleriyle ifade edilir. İsteğe bağlı veya
     koşullu pencere desteklenmez.
3. **Varlık kanıtı yalnız gözlemdir:** ekran işaretleri, kayıt bağlamı okuması ve beklenen pencere kanıtıyla
   sınırlıdır. İş eylemi hedefleri her zaman katı kuralla ve eylem anı kontrolüyle çözülür.
4. **Kesinti kararları kimliğe bağlı:**
   - Her native dialog ve yeni pencere bir kimlik alır; arayüz kararı bu kimliklerle gönderir.
   - Kimlik güncel değilse hiçbir şey kapatılmaz (`interruption_changed`, 409). Eski karar sonradan açılan
     pencereye uygulanmaz; kısmi uygulama yoktur.
   - Eşzamanlı/tekrarlanan kararlar gözlemcinin sayfaya dokunmayan karar kilidiyle sıralanır; yalnız biri
     etkili olur.
   - Sahiplik ve rol her çağrıda denetlenir; kapatılan oturumda uçlar "bulunamadı" döner.
   - Ana çalışma sayfası hiçbir durumda kapatılmaz.
   - Toplu kapatmanın kapsamı (pencere origin'leri) kullanıcıya gösterilir.
   - Onaylama kararı yoktur.
