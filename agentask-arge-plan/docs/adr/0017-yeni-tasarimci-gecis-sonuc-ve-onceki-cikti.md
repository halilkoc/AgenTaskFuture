# ADR 0017 — Yeni tasarımcıda ekran geçişi, sonuç koşulu ve önceki adım çıktısı (Ana plan C)

Tarih: 2026-11-07 · Durum: kabul edildi (lab; gerçek Pega/SSO doğrulanmadı)

## Bağlam
ADR 0015 ile yeni tasarımcı yalnız gerçek oturumdan seçilmiş "Alan doldur" adımlarını kalıcı taslağa yazıyordu.
Ekran geçişleri, sonuç koşulu, iş etkisi ve "önceki adımın çıktısı" kaydedilmiyordu. İnceleme:
- `ParameterDef(source=prior_output, prior_step)` sözleşmede vardı ama **çalışma anında hiç uygulanmıyordu**:
  `bind_arguments` bu parametreyi kullanıcıdan istiyordu (bağlama yoktu).
- `PUT /api/drafts/{id}/transitions` her iki ekranın da önceden tanımlı olmasını istiyordu. Yeni tasarımcıda
  analist geçişi kaynak ekrandayken tanımlar; hedef ekran o anda henüz açılmamıştır.

## Karar
1. **Önceki adım çıktısı (çalışma anı bağlaması):**
   - Komut sözleşmesine `OutputRef {step, max_length}` eklendi; yalnız `ensure_value.value_from` ve
     `assert_condition` içindeki `value_equals.value_from` için. Bağlam koşulları (`context`) başvuru taşıyamaz.
   - `validate_plan`: başvuru yalnız **daha önceki bir `read` komutuna** olabilir; sabit değer ile birlikte
     verilemez.
   - Derleyici: `prior_output` parametresi yalnız sonraki bir `ensure_value` adımının değer şablonunda tek başına
     (`{ad}`) kullanılabilir; kaynak adım `read` olmalıdır. Aksi `validation_issues` ile bildirilir ve derleme
     reddedilir. Bu parametre argüman olarak verilemez (`unexpected_argument`).
   - Yürütücü değeri yalnız kaynak okuma adımı **başarıyla** bittiyse kullanır. Okuma yoksa/başarısızsa, değer
     boşsa, hassas alandan okunduysa (`sensitive`) veya sınırı aşıyorsa adım **hiçbir sürücü eylemi yapmadan**
     `PRIOR_OUTPUT_UNAVAILABLE` ile durur. Devam (resume) bağlam kurulumunda aynı kural uygulanır.
   - Birleştirmede (P8) düzleştirilen alt planın başvuruları üst plan sırasına kaydırılır.
   - Tasarımcıda tek adım denemesi, bağlı olduğu okuma adımını (etkisiz) önce çalıştırır; değer tahmin edilmez.
2. **Ekran geçişi önce, hedef ekran sonra:**
   - `define_transition` artık ekranların tanımlı olmasını beklemez. Tetikleyici yine **o anda canlı ekranda tekil
     çözülmelidir**; tıklama yapılmaz.
   - Tanıtılmamış uç `transition_unknown_screen` (başlangıç yoksa `screen_missing`) eksikliği olarak kalır. Bu
     durumda taslak incelemeye/onaya hazır olamaz ve derlenemez; güvenlik sınırı değişmez.
   - `define_screen`: başlangıç ekranı yokken bir geçişin **hedefi** olan ekran tanıtılırsa başlangıç değil ek ekran
     olur.
   - Ekran kimliklerini kod üretir; kimlik uygulama genelinde mantıksal ekrandır: başlangıç, mevcut başlangıç
     kimliği veya "<akış adı> ekranı"ndan; hedefler analistin yazdığı addan (ilk adım bileşen çağrısıysa
     bileşenin başlangıç ekranı). Ad, ekran tanıtılınca başlık olur.
3. **Sonuç koşulu ve iş etkisi (sade arayüz):**
   - "Alan doldur": "Yazılan değeri alanda okuyarak doğrula (önerilen)" / "Ek kontrol yapma" → `success_check`
     `auto|none`. İş etkisi metni sabittir: yalnız alana yazar, kayıt yapmaz.
   - Veri değiştiren işlem yalnız ayrı "Onaylı işlem" adımıdır (`invoke_approved_action`); liste onaylı aksiyon
     kataloğundan (`/api/actions`) gelir, etkisi katalogdaki beyandan gösterilir, uydurulmaz. Parametreleri sabit
     veya "her çalıştırmada sor" olabilir; önceki çıktıdan alınamaz.
4. **Parametre temizliği:** `DELETE /api/drafts/{id}/parameters/{name}` eklendi; bir adım, geçiş veya bağlam
   koşulu kullanıyorsa reddedilir. Yeni tasarımcı kayıttan sonra kullanılmayan parametreleri kaldırır.
5. **Yeniden açma:** okuma, önceki çıktıya bağlı alan doldurma, kontrol tetikleyicili geçiş ve onaylı işlem
   adımları düzenlenebilir açılır. Ekran tanımının varlığı artık salt okunur nedeni değildir. Adıma özel
   `screen_id`, tamamlanma koşullu geçiş, aksiyon tetikleyicili geçiş ve başlangıç kayıt bağlamı hâlâ salt
   okunurdur.

## Sonuç ve sınırlar
- Yayımlanmış eski komutlar etkilenmez: yeni alanlar isteğe bağlıdır; mevcut `value` içeren komutların JSON'u ve
  hash'i değişmez.
- Okunan değer çalışma kaydında (run) tutulur; hassas alandan okunan değer bağlamada kullanılmaz. Hassas alan
  okumasının değerinin kayda yazılması mevcut davranıştır ve ayrıca ele alınmalıdır (bu ADR kapsamı dışında).
- Tasarım sırasında sistem geçiş düğmesine basmaz; sonraki ekranın alanları için analist düğmeye tarayıcıda
  kendisi basar. Gerçek deneme ayrı ve etki onaylıdır.
