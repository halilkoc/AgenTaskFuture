# ADR 0023 — Geçici admin girişi ve hedef uygulamaya elle giriş

Tarih: 2026-11-09. Durum: kabul edildi (lab). Kurumsal SSO değildir; SSO ertelendi.

## Kararlar
1. **AUTH_MODE=local_admin:** mevcut `IdentityPort` üzerinden tek admin. Parola scrypt hash'i olarak `.env`'de durur
   (`agentask --hash-admin-password`). Varsayılan hesap yoktur; ayar eksikse uygulama başlamaz, dev kimliğine düşülmez.
2. **Oturum:** rastgele belirteç, bellekte yalnız özeti, süreli; cookie HttpOnly + SameSite=Strict; loopback dışında Secure zorunlu.
   Durum değiştiren istekler oturuma bağlı CSRF belirteci ister (`auth.js`). Hatalı giriş istemci başına sınırlıdır.
3. **Hedef oturumu ayrıdır:** kullanıcı Pega'ya otomasyon penceresinde elle girer; kimlik bilgisi AgenTask'a gelmez.
4. **Yeni oturum testi:** gerçek uygulamada ayrı doğrulama oturumu açılır; beklenen ekran yoksa bekler. **Giriş yaptım, devam et**
   giriş ve ekranı yeniden doğrular. Süre aşımı ve vazgeçme sonuç yazmaz. Test sırasında giriş düşerse yeni çalıştırma değil `resume`
   kullanılır; yapılmış adımlar tekrar oynatılmaz. Lab otomatik girişi yalnız `LAB_PRIMARY_ORIGIN` ile aynı origin'de geçerlidir.
5. **APPROVED_ACTION_SET=file:** kurum aksiyonları ve oturum kaybı profili tipli JSON'dan okunur; serbest kod ve seçici yoktur.
6. **İptal kaynağı:** `Run.cancelled_by` kullanıcı ve sistem süre aşımını ayırır; eski kayıtlarda “bilinmiyor” gösterilir.

## Sınırlar
Tek admin, tüm roller, işlem bazlı yetki yok. Oturumlar yeniden başlatmada düşer. Elle giriş `BROWSER_HEADLESS=false` ister.
Gerçek SSO/MFA akışı yalnız şirkette doğrulanabilir.
