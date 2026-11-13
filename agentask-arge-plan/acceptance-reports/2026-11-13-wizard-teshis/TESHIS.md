# test_wizard_acceptance_mongo teşhisi (2026-11-13)

**Önceki kayıt:** 2026-11-09 koşusunda yalnız ilerleme satırı (`FF..F`) var; hata izi yok.
**Koşu:** yalnız bu test, bir kez; `-x`, 600 sn sınır, geçici `--basetemp` ve geçici MongoDB (silindi). **pytest çıkış kodu: 1.** İz: `pytest.log`.

**Başarısız adım:** test satırı 126. `wizard_target=other_case` ile İşlem Asistanı'ndan ikinci çalıştırma (madde 15).
**Beklenen:** çalıştırma durur (Duraklatıldı veya Başarısız), tutar yazılmaz.
**Gerçekleşen:** sonuç rozeti “Başarılı”. Önceki adımlar geçti: tasarım, kaydetme, iki ekranın tanıtılması, gerçek deneme, yeni oturum testi, yayın, ilk başarılı Asistan çalıştırması ve geçiş sayıları.

**Neden: test kurgusu (kod okumasıyla kanıtlı).**
- Lab'da `other_case`, aynı türde teminat ekranını başka vaka numarasıyla açar (`Vaka No` = `C-2001-B`). Ekran işaretleri aynıdır, ekran tanınır.
- Ürün bu durumu yalnız geçişte bir kayıt bağlamı kontrolü tanımlıysa reddeder (`RECORD_CONTEXT_MISMATCH`). Bunu `tests/integration/browser/test_multi_screen_runtime.py::test_right_screen_type_wrong_case_is_rejected` doğruluyor.
- Bu e2e testi “Ekrana geç” adımında “Açılan ekranda kayıt doğrulansın mı?” kontrolünü tanımlamıyor. Bağlam koşulu olmadığı için ürün tanımlandığı gibi devam etti.
- `docs/17` madde 14'teki adımlar da bu kontrolü içermediği halde madde 15 durmayı bekliyor. Belgede de aynı tutarsızlık var.

**Sınır:** taslağın geçiş tanımı bu koşuda ayrıca kaydedilmedi. “Bağlam koşulu yok” sonucu test kodunun bu kutuyu hiç doldurmamasına dayanıyor.
