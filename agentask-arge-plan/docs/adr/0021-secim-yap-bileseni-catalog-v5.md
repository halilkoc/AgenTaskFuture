# ADR 0021 — “Seçim yap” bileşeni ve catalog-v5

Tarih: 2026-11-08. Durum: kabul edildi (lab + geçici MongoDB). Gerçek Pega/SSO doğrulanmadı.

## Bağlam
`ensure_choice` komutu ve iki adaptör vardı; ama seçenekler gözlemdeki kısaltılmış listeden okunuyor, devre dışı ve
değer bilgisi yoktu, doğrulama başarısızsa seçim otomatik tekrarlanabiliyordu ve yeni tasarımcıda bileşen yoktu.
Mevcut yürütücü genişletildi; paralel yürütücü yazılmadı.

## Kararlar
1. **Eşleşme:** Görünen etiketin tam eşitliği; yalnız büyük/küçük harf ve boşluk farkı yok sayılır, Türkçe harfler
   ayrıdır (`choice_key`). Kısmi/bulanık eşleşme ve sıra numarası yoktur. Eksik, devre dışı, yinelenen, boş değerli
   (yer tutucu) seçenekte seçim yapılmaz.
2. **Etiket ve değer ayrıdır:** Kararlı görünen değer (`choice_value`, `ChoiceItem.value`) etiketle birlikte aynı
   seçeneği göstermelidir. Sıra numarası gibi görünen veya üretilmiş kimlik saklanmaz (`stable_value`). Özel listede
   gerçek değer yalnız uygulama `data-value`/`value` yayımlıyorsa doğrulanabilir.
3. **Tanımlama etkisizdir:** Seçenek okuma seçim yapmaz. Özel liste yalnız `open_list=true` (açık kullanıcı eylemi)
   ile açılır, okunur ve aynı yolla kapatılır.
4. **İş etkisi uydurulmaz:** Analist `choice_effect` beyan eder: `ui_local` veya `unknown` (“tetikleyebilir / emin
   değilim”). `unknown` deneme ve çalıştırmada açık onay ister ve `success_check=none` ile yayımlanamaz. Veri
   değiştirme iddiası yine yalnız onaylı aksiyon kataloğundadır.
5. **Belirsiz sonuç:** `unknown` seçimde gönderimden önce checkpoint yazılır; gönderimden sonraki her hata yalnız
   okumayla uzlaştırılır. Doğrulanamazsa `OUTCOME_UNKNOWN`; seçim yeniden yapılmaz. Devam ettirme de yeniden seçmez.
6. **Sonuç doğrulaması:** Seçimden sonra DOM durulması beklenir (`CHOICE_SETTLE_MS`), gerçek seçim okunur; isteğe
   bağlı durum mesajı (`result_text`) alanın bölümünde aranır.
7. **Çalışma anı doğrulaması:** Seçenekler her zaman güncel DOM'dan okunur. Sabit liste (`ParameterDef.choices`)
   yalnız Asistan sunumu ve ön kontroldür; kayda göre değişen listede `choices` saklanmaz.

## Geriye uyum (catalog-v5)
Yeni adım alanları ve `choices` yalnız doluysa kanonik içeriğe yazılır: eski tanımların hash'i ve derlenen planı
değişmez, şeması eski kalır (`test_old_choice_step_compiles_and_hashes_exactly_as_before`). Eski seçim adımları
`ui_local` davranışını korur. Yeni alan içeren tanım `catalog-v5` olur. Tek davranış değişikliği: eşleşme artık
Türkçe harf farkını ayrı sayar; aksansız yazılmış eski bir sabit seçenek durur (yanlış seçim yapmaz).

## Sınırlar
Çoklu seçim, yazarak arama yapan kutu, shadow DOM, erişilemeyen dış origin frame ve ARIA rolü olmayan özel listeler
desteklenmez; açıkça bildirilir. Seçimle tetiklenen ekran geçişi onaylı geçiş olarak modellenmez: `unknown` beyanıyla
sonraki adımın ekran doğrulaması durur. Durum mesajı önceden ekranda aynıysa ayırt edilemez.
