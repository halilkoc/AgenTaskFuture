# test_action_file_mongo teşhisi (2026-11-13)

**Önceki kayıt:** yalnız ilerleme satırı (`FF..F`); hata izi yok.
**Koşu:** yalnız bu test, bir kez; `-x`, 600 sn sınır, geçici `--basetemp` ve geçici MongoDB (silindi). **pytest çıkış kodu: 1.** İz: `pytest.log`.

**Başarısız kontrol:** satır 216, `expect(ui.get_by_label("Tarayıcı oturumu")).to_have_value(sid)`. Yeniden test bloğunun ilk kontrolüdür; taslak yeniden açılıp “Gerçek oturum” seçildikten hemen sonra.
**Beklenen:** önceki blokta açılan oturum listede seçili olsun.
**Gerçekleşen:** oturum listede var (`O0G-jVi6 · …/pages/note-form`), ancak seçili değer “Seçin…” (boş).

**Önceden geçen kontroller:**
- Aksiyon dosyası değişince eski yayın 422 `action_changed` ile reddedildi; neden metni doğru; yayın manifesti değişmedi.
- Taslakta `action_changed` sorunu göründü; yayıncı onayı 409 verdi.
- Yeniden açılıp kaydedilince yeni özete bağlandı; adım hazır değil; özet güncel `fingerprint` ile aynı ve eskisinden farklı.

**Neden: test kurgusu (kod ve iz ile kanıtlı).**
- Tasarımcı seçili oturumu tarayıcının `localStorage` alanında hatırlar (`prototype_designer.js` satır 2869 ve 2881).
- Test bu blokta yeni bir Chromium başlatıyor (satır 210). Yeni tarayıcı profilinde `localStorage` boş olduğundan otomatik seçim olmaz.
- Aynı sayfanın yeniden yüklendiği `test_company_candidate_flow`'da bu kontrol geçiyor. Ürün tasarlandığı gibi davrandı; hiçbir işlem yapılmadı.
