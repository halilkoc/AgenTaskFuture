# Kullanıcı deneyimi ve katalog hazırlama

## Sayfalar
/assistant: prompt, yorumlanan iş/parametre özeti, eksik bilgi, çalıştırma, ilerleme, duraklatma/iptal ve sonuç.
/designer: uygulama/session, adım listesi, açıklama alanı, hedef seçimi, DOM/frame özeti, adaylar, değer kaynağı, deneme, başarı koşulu, review/publish.
/catalogs: yayımlanmış sürümler, etki ve test durumu; yetkiye göre düzenleme.
/runs: mevcut/önceki çalışmalar, adım sonuçları, redakte edilmiş hata kanıtı.
/changes: yeni gözlem ile katalog farkı, etkilenen işlemler ve yeniden test listesi.
Yalnızca frontend sekmesini gizlemek yetki kontrolü değildir.

## Designer adım durumu
intent_entered → target_proposed/target_selected → meaning_and_target_confirmed → trial_requested → observed → outcome_confirmed → ready_for_review.
Kullanıcının tek 'Evet' butonu hedef+anlam+etkiyi görünmez şekilde onaylamaz; kartta hepsi açık gösterilir. Adım onayı yayın onayı değildir. Deneme gerçek etki oluşturabilir; eylem öncesi etki türü gösterilir.
Görülmeyen ekran için model selector/alan uydurmaz. Sonraki ekran açıldıktan sonra o adım çözülür. Seçim overlay'i gerçek click/submit yapmaz.

## Adım kartı
Özgün açıklama (hassas değerler ayıklanmış), standart onaylı açıklama, yapılandırılmış işlem, hedef crop/etiket/tür/bölüm, parametre kaynağı, ön koşul, beklenen etki, başarı check'i.
Her önerinin provenance'ı: observed, rule_generated, model_suggested, human_verified. Modelin metni özgün niyetin yerine yazılmaz. 'İlerlet' → 'onayla' gibi anlam yükseltmesi reddedilir/açıklama ister.
Parametre kaynağı user_input, prior_output, approved_constant veya secret_ref; örnek branch/case değerleri katalogda sabitlenmez. Secret plaintext en başta UI/collector/model/log yolundan dışlanır.

## LLM kullanım şekli
Önce deterministik intent/candidate matching; gerekirse kullanıcıya görünür model desteği. İlgili katalog dilimi ve küçük DOM özeti gönder. Model kapalıyken manuel hedef seçimi + form doğrulama + yayın yolu çalışır.
Model sadece candidate ids / operation ids / typed parameter önerisi döndürür. Aynı modelin hedef önerisi ve açıklaması bağımsız kanıt değildir.

## Yeniden kullanım ve test
Mevcut screen/element/operation reuse önerisini göster; sessiz merge yapma. Akış kaydı ile tekrar kullanılabilir capability ayrı tutulur. Yeni oturum testi eski locator/snapshot olmadan yapılır.
Final review: amaç, kapsam, parametre, etki, adımlar, başarı/durma, test kanıtı ve açık eksikler. Eksik zorunlu check, belirsiz hedef veya başarısız zorunlu test yayın engelidir.

## Değişiklik ekranı
Dinamik id, timestamp ve record verisini normalize et. Label/role/region/control behavior ve outcome sözleşmesi değişikliklerini göster. Dependency graph ile etkilenen operation/release'leri bul. Önerilen repair yeni draft açar; aktif katalog kendiliğinden değişmez.
