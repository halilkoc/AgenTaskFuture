# test_company_candidate_flow: ekran tanıma teşhisi (2026-11-13)

**Koşu:** yalnız bu test, bir kez; `-x`, 600 sn sınır, geçici `--basetemp` ve geçici MongoDB (sonradan silindi). Ürün kodu ve test değişmedi. Kayıtlar yalnız bu koşuya yüklenen tanı eklentisiyle alındı (`tani_eklentisi.py`); eklenti ürünün kendi kontrolüyle aynı çağrıyı yapar: `assess_screen`.
**pytest çıkış kodu:** 1. Hata önceki koşuyla aynı (satır 210, “Beklenen başlangıç ekranı görünmüyor”). Olay kaydı: `olaylar.jsonl`. Parola, hash veya oturum belirteci içermez.

**Beklenen başlangıç ekranı işaretleri (4):** Başvuran › Şube; Ürün › Ürün Tipi; **Zengin Metin** (bölümsüz textbox); Kefil › Ad Soyad.

| An | URL yolu | Görünen işaretler | Sonuç |
|---|---|---|---|
| Elle girişten önce | `/login` | 0/4 | tanınmadı (doğru) |
| Girişten sonra, “Giriş yaptım, devam et” | `/pages/selections` | 3/4; yalnız **Zengin Metin** yok | tanınmadı |
| +3 sn | `/pages/selections` | 3/4; Zengin Metin yok | tanınmadı |
| +8 sn | `/pages/selections` | 3/4; Zengin Metin yok | tanınmadı |

**Ayrılan ihtimaller:**
- **Yanlış sayfa: hayır.** Doğrulama penceresi doğru yolda (`/pages/selections`).
- **Geç yüklenme: hayır.** 3 ve 8 saniye sonra da aynı üç işaret var, aynı işaret yok.
- **Hatalı ekran işareti: evet.** “Zengin Metin”, testin yalnız tasarım oturumuna betikle eklediği `contenteditable` öğesidir. Test, desteklenmeyen hedef kontrolünden sonra adımı siliyor, öğeyi ise sayfada bırakıyor. “Ekranı tanıt” bu öğeyi gerekli işaret olarak önerdi ve test öneriyi onayladı. Yeni oturumda bu öğe olmadığından ekran tanınmadı.

**Neden:** test kurgusu. Tasarım sayfası, yeni oturumun göreceği sayfadan farklı bırakılıyor. Ürün güvenli davrandı: tanımlı ekran görünmediği için işlem başlatılmadı.
**Sınır:** “Giriş yaptım, devam et” anındaki doğrudan okuma `SessionNotFound` verdi (doğrulama oturumu kilitsiz okunamadı). URL yolu aynı tıklamanın içinde, 0,06 sn sonra yapılan ekran kontrolünde kaydedildi.

**Önerilen tek düzeltme (yalnız test kurulumu):** desteklenmeyen hedef kontrolünden hemen sonra, betikle eklenen “Zengin Metin” öğesini tasarım sayfasından kaldır; böylece ekran tanıtılırken sayfa yeni oturumdakiyle aynı olur. Testin başarı koşulları değişmez.
