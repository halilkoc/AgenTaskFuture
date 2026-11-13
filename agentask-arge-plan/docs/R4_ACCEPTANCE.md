# R4 kullanıcı kabul listesi (teminat_gir taslağından devam)

Katalog Tasarımcısı'nda **Taslaklar** listesinden `teminat_gir` için **Aç**'a basın. Parametreler, iki ekran,
`teminata_gec` geçişi ve ilk iki adım sizde hazır; bunları yeniden yapmayın.

1. **Üçüncü adım:** Önce ilk iki adım kartında "İncelemeye hazır" yazdığını kontrol edin; yazmıyorsa o kartta
   **Sonucu onayla**'ya basın. Sonra **Deney ekranı**'nda "Başvuru sihirbazı — teminat ekranı"nı seçip **Ekranı aç**'a basın.
   - "Yapmak istediğiniz adım" alanına "Teminat tutarını yaz" yazıp **Adım ekle**'ye basın.
   - **Hedef adaylarını göster** → "Teminat Tutarı" satırında **Bu hedefi seç**.
   - "Değer/şablon" alanına `{tutar}` yazıp **Tanımı kaydet**'e basın.
   - Kartta "Beklenen ekran: Başvuru — teminat bilgileri" görünmeli.
   - Dört onay kutusunu işaretleyip **Onayla**; değerleri girip **Dene**. "sistem doğrulaması: BAŞARILI"
     görünmeli; ardından **Sonucu onayla**.
2. **Yeni oturum testi:** Son inceleme bölümünde "Başlangıç ekranı" olarak "Başvuru sihirbazı (çok ekran)"yı seçin.
   - Test değerlerini girip **Yeni oturum testi**'ne basın.
   - "İncelemeye hazır: bütün adımlar doğrulandı ve yeni oturum testi geçti." görünmeli.
3. **Onay ve yayın:** **Onayla (yayıncı)** → **Yayımla**. "Yayımlandı ve etkin: … teminat_gir r1" görünmeli.
4. **Asistandan çalıştırma:** İşlem Asistanı'nda "Teminat tutarını gir" yazıp **Yorumla**'ya basın; değerleri girip
   **Planı göster**.
   - Planda "Ekran rotası: Başvuru — müşteri seçimi → Başvuru — teminat bilgileri" görünmeli.
   - Panelden **Bu oturumu kullan** → "Başvuru sihirbazı (çok ekran)" → **Ekranı aç** → **Çalıştır**.
   - Sonuç "Başarılı" olmalı; teminat ekranında girdiğiniz tutar görünmeli.
5. **Yanlış vaka reddi:** Deney uygulaması denetim sayfasında `wizard_target` alanına `other_case` yazıp **Uygula**'ya
   basın.
   - Asistanda **Ekranı aç** → **Çalıştır**. Adım tablosunda `RECORD_CONTEXT_MISMATCH` görünmeli ve Teminat Tutarı
     boş kalmalı.
   - Sonra alanı `collateral` yapıp **Uygula**'ya basın.
