# ADR 0008 — P7 anlamsal değişiklik, bağımlılık etkisi, onarım taslağı ve run metrikleri

Tarih: 2026-11-05 · Durum: kabul

## Kararlar
1. **Karşılaştırma anlamsal:** yayımlanmış her eleman (TargetSpec) yeni gözleme P2 çözümleyicisiyle çözülür → unchanged,
   ambiguous, not_found, hidden_or_disabled, unknown (kapsam eksik). HTML id/sıra/zaman/kayıt değeri hiç karşılaştırılmaz.
   Yeniden adlandırma önerisi: aynı tür + aynı bölge + eski etiketle ortak kelime; yalnız öneri.
2. **Bağımlılık grafiği:** aynı anlamsal hedefi kullanan bütün işlemler, ortak adapter türü (kontrol türü) ve onaylı
   aksiyon kimliği üzerinden etkilenen işlemler bulunur; yeniden test olarak işlemin yeni oturum testi önerilir.
3. **Onarım:** yayımlanmış revizyondan yeni taslak; bozuk elemanı kullanan adımlar hedef seçimine döner, diğerleri
   yeniden onay ister; test/onay kanıtı taşınmaz. Etkin yayın değişmez; otomatik production onarımı yok.
4. **Metrikler:** iş başarısı (completed / terminal) ile teknik toparlanma (recoveries) ayrı; belirsiz sonuç, hata
   sınıfları, p50/p95 süre, işlem bazında durum. Kaynak run checkpoint'leri; dış telemetri yok.

## Sınırlamalar
Ekran tanıma (hangi ekranda olunduğu) yok; analiz kullanıcının açtığı ekranda yapılır. Gizli sekmedeki elemanlar
`hidden_or_disabled` görünebilir. Metrikler kullanıcının kendi run'larıyla sınırlı (kurumsal raporlama yok).
