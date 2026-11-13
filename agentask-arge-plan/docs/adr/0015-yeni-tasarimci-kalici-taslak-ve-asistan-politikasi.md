# ADR 0015 — Yeni tasarımcının kalıcı taslak bağlantısı ve asistanda model politikası

Tarih: 2026-11-07 · Durum: kabul edildi (lab; gerçek Pega/SSO doğrulanmadı)

## Bağlam
Yeni Akış Tasarımcısı akışları tarayıcı belleğinde tutuyordu. Kalıcı taslak, deneme, onay ve yayın mevcut
tasarımcıda ve `/api/drafts` servisinde hazırdı: `LocalFileDraftRepository`, revizyon kontrolü, `select-target`
ile kaydetme anında yeniden çözüm, 4 onay, deneme, yeni oturum testi, onay ve yayın.

İşlem Asistanı'nda modeli kullanıp kullanmamaya çalışan bir onay kutusuyla karar veriyordu.

## Karar
1. **Paralel depo yok:** yeni tasarımcının "Taslağı kaydet" düğmesi mevcut `/api/drafts` uçlarını kullanır.
   Taslak adaptörü bugün `LocalFileDraftRepository`'dir (DRAFT_DIRECTORY). Port korunur; üretim deposu kararı
   ayrıca verilir.
2. **Kaydedilen adımlar:** yalnız gerçek oturumdan seçilmiş "Alan doldur" adımları kaydedilir.
   - "Her çalıştırmada sor" → `user_input` parametresi (bağlamlı soru başlıktır); sabit → şablon.
   - Teknik kimlikleri kod üretir: işlem kimliği (ad + kısa ek), parametre adı ve eleman kimliği.
   - Hedef, kaydetme anında `select-target` ile canlı ekranda yeniden çözülür; tekil değilse kaydedilmez.
   - Kaydedilmeyenler gerekçesiyle bildirilir: temsili adımlar, gerçek çıktı sözleşmesi olmadan "önceki adımın
     çıktısı", ekran geçişi ve bileşen adımları.
3. **Değişiklik:**
   - İlk farklılık noktasından sonraki taslak adımları silinip sırayla yeniden oluşturulur; eski deneme ve
     onaylar mevcut kurallarla geçersizleşir.
   - Soru metni değişirse aynı parametre güncellenir (servis aynı adı upsert eder).
   - Çakışmada 409 alınır ve hiçbir şey üzerine yazılmaz.
   - Yarım kalan adım temizlenir.
4. **Yeniden açma:**
   - Yeni tasarımcının düzenleyemediği adımları (geçiş, aksiyon, ekran tanımı vb.) içeren taslak salt okunur
     açılır.
   - Mevcut katalog veya yayın sessizce dönüştürülmez.
   - Kaydedilmiş taslağın uygulaması değiştirilemez.
5. **Deneme, onay ve yayın:** yeni tasarımcı taslağı mevcut tasarımcıda `/designer?draft=<id>` ile açar.
   Deneme, onay ve yayın oradaki mevcut politika ve değişmez yayın mekanizmasıyla yapılır; yeni onay katmanı
   eklenmedi. Eski tasarımcı korunur.
6. **Asistanda model politikası:**
   - `use_model` verilmezse kurum politikası (`LLM_ENABLED` ve model erişilebilirliği) karar verir; arayüzde
     onay kutusu yok.
   - Model önerisi yine onay ister ve yalnız yayındaki onaylı işlemlere referans verebilir.
   - Model kapalıyken kural tabanlı eşleşme ve hazır işlem listesi çalışır.
7. **Asistanda plan geçerliliği:** gösterilen özetten sonra bilgi değişirse özet geçersizleşir ve yeniden
   gösterilmeden başlatılamaz. Sunucu yine planı yayından yeniden derler; eski yayında `release_superseded`.

## Sonuçlar
- **Güncelleme (2026-11-07):** gerçek deneme, adım onayı, sonuç onayı, yeni oturum testi ve ekran tanımı
  ("Ekranı tanıt") yeni tasarımcının D panelinde yapılıyor.
- Henüz yeni tasarımcıda olmayanlar:
  - iş etkisi ve sonuç koşullarının sade tanımı;
  - ekran geçişlerinin kalıcı kaydı;
  - okuma çıktısına dayalı bağlama.
- Bileşenler (E) için sürüm pinleme yeni sözleşme alanı gerektirir; ayrı ADR ile yapılacak.
