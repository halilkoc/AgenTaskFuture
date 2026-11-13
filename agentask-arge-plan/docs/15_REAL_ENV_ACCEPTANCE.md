# Gerçek ortam kabul belgesi (kısa)

Durum: **BLOCKED.** Kurum Pega/SSO erişimi olmadan bu kabul yapılmadı; lab'da geçen testler Pega uyumluluğu
değildir. Kurum adresi, kullanıcı ve iş kuralı bu belgede tahmin edilmez; `<...>` alanlarını kurum doldurur.

## 1. Hazırlık ve başlatma
- `.env`'de en az şu ayarlar:
  - `TARGET_ALLOWED_ORIGINS` / `TARGET_BASE_URL`;
  - `AUTOMATION_APPLICATIONS_JSON` (tek kayıt: `<uygulama id>`, `<ad>`, `<başlangıç adresi>`);
  - `CATALOG_APPLICATION_ID` (aynı id), `MONGO_URI` ve `MONGO_DATABASE`;
  - `BROWSER_HEADLESS=false` (seçim için pencere görünmeli).
- Kontrol ve başlatma: `.venv/bin/agentask --check-config` → `.venv/bin/agentask`.
- Rol: analist `designer`, yayıncı `publisher`, iş birimi `operator`. Gerçek SSO yöntemi henüz kesinleşmedi.

## 2. Yalnız gözlem ve alan seçme (veri yazılmaz)
- Sayfa: `/prototype/designer` → Yeni akış → Gerçek oturum → Yeni oturum aç → Uygulamayı oturumda aç.
- Girişi kullanıcı kendisi yapar ve test kaydının ekranına gider.
- "Ekrandaki alanları listele" ve "Tarayıcıda kendim seçeyim" ile bir alan seçin.
- **Beklenen:** alan bilgisi gelir, "Ekranda tek olarak bulundu" görünür, uygulamada hiçbir alan değişmez.
- **Kanıt:** seçilen alanın bilgisi (ekran görüntüsü kurum politikasına göre).

## 3. Test kaydında düşük etkili tek işlem
- Kurumun belirleyeceği `<test kaydı>` üzerinde yalnız bir metin alanına yazan bir adım hazırlayın ve
  "Taslağı kaydet" deyin.
- "Dene, onayla ve yayımla" ile mevcut tasarımcıda 4 onayı verip **Dene**'ye basın.
- **Beklenen:** "sistem doğrulaması: BAŞARILI" görünür ve kayıtta değer görülür.

## 4. Sonuç doğrulama ve pop-up kontrolü
- Uygulamada bir onay penceresi veya modal çıkan durumu deneyin.
- **Beklenen:** yürütme durur ve "Müdahale gerekiyor" görünür; pencere kendiliğinden kapatılmaz.
- Kapatma yalnız kullanıcının "Bu pencereyi iptal ederek kapat" kararıyla olur.

## 5. Uçtan uca katalogdan çalıştırma
- Yeni oturum testi → Onayla (yayıncı) → Yayımla.
- İşlem Asistanı'nda talebi yazın, eksik bilgiyi girin, özeti kontrol edip **Başlat**'a basın.
- **Beklenen:** "Tamamlandı" görünür ve kayıtta beklenen değer bulunur.

## 6. Ne zaman durulur ve ne raporlanır
- Şu durumlarda hemen durun ve işlem yapmayın:
  - "Belirsiz", "Müdahale gerekiyor" veya "Sonuç belirsiz" görülmesi;
  - SSO yeniden giriş istemesi;
  - beklenmeyen ekran veya pencere.
- Raporlanacaklar:
  - run kimliği, adım tablosu (hata sınıfları);
  - seçilen alanın bilgisi;
  - ekranın kurum politikasına uygun görüntüsü;
  - uygulamadaki kaydın son durumu.
