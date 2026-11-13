# ADR 0009 — P8 kontrollü iş birleştirme ve güvenli şablonlar

Tarih: 2026-11-05 · Durum: kabul

## Kararlar
1. **Birleştirme bayrakla kapalı** (`COMPOSITION_ENABLED=false`). Düğümler yalnız `call_operation` (etkin yayındaki
   onaylı işlem), `if` (P3 koşul tipleri) ve `for_each` (açık, sınırlı öğe listesi). Serbest döngü/while/kod yok.
2. **Derleme zamanında düzleştirme:** bileşik plan, çağrılan işlemlerin değişmez revizyonlarından düz P3 komut
   listesine derlenir; statik sınırlar: derinlik, öğe sayısı, toplam adım (`RUN_MAX_STEPS`), bilinmeyen işlem,
   argüman uyumu. Koşul `evaluate_condition` adımıyla değerlendirilir (başarısız olmaz, sonucu kaydeder); bağlı
   adımlar `when` guard'ıyla açılır/atlanır. Çalışma zamanında yeni komut üretilmez.
3. **Güvenli şablon:** bütün metin şablonları yalnız `{ad}` yer tutucusu kabul eder; Python format dili (öznitelik/
   indeks erişimi) kullanılmaz. Önceki `str.format_map` kullanımı bu aşamanın son incelemesinde kaldırıldı.
4. **Runner/gerçek ortam:** uzak runner sözleşmesi ve gerçek Pega/SSO bilinmeyenleri docs/12'de; doğrulama kaydı
   şablonu docs/13 (boş, BLOCKED). Yerel deney sonuçları gerçek Pega uyumluluğu olarak raporlanmaz.
