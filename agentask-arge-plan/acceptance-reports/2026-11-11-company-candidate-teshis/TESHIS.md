# test_company_candidate_flow teşhisi (2026-11-11)

**Koşu:** yalnız bu test; `-x`, 600 sn süre sınırı, geçici `--basetemp` ve geçici MongoDB (sonradan silindi). 23:00:32–23:01:28.
**pytest çıkış kodu:** 1 (`pytest-exit-code.txt`). Tam iz: `pytest.log` (parola/hash içermez).

**Beklenen:** elle girişten sonra “Giriş yaptım, devam et” → “Yeni oturum testi tamamlandı: BAŞARILI” (test satırı 210).
**Gerçekleşen:** “Beklenen başlangıç ekranı görünmüyor; işlem başlatılmadı. Pencerede doğru ekranı açıp yeniden deneyin.” 40 sn boyunca değişmedi.
Ürün, ekran tanınmadığı için işlemi başlatmadı. Bu güvenli davranıştır (`designer.py`, `_screen_recognized`).

**İlk hatadan önce geçen doğrulamalar:** giriş; temsili öğelerin gizli olması; tanımlama ve kaydetme sonrası sayfadaki alanların değişmemesi; 5 adımın yeniden açılması; gerçek denemede yalnız 4 tanımlı alanın değişmesi (Kefil › Şube = Konak dahil); girişsiz devamda “giriş ekranında” ve BAŞARILI yazılmaması.

**Kaynak: BELİRSİZ.** Kanıtlanamadı, çünkü taslağın ekran işaretleri ve doğrulama penceresinin adresi kaydedilmedi; geçici veriler test sonunda silindi. Olası iki neden:
1. Test kurgusu: `lab_login` girişten sonra sayfa geçişini beklemeden “Giriş yaptım, devam et”e basılıyor (zamanlama yarışı).
2. Ekran tanımı: 5. adım (Kefil › Şube) eklenince “Ekranı tanıt” farklı işaretler önermiş olabilir. Testin yalnız tasarım oturumuna betikle eklediği “Zengin Metin” öğesi de işaret olarak seçilmiş olabilir; bu öğe yeni oturumda yoktur.

Aynı test, bu genişletmeden önceki hâliyle 916 passed tam regresyonda geçiyordu. Ürün kodu (`src/`) değişmedi.
