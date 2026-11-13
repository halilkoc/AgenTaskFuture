# ADR 0007 — P6 İşlem Asistanı ve sınırlı LLM

Tarih: 2026-11-05 · Durum: kabul

## Kararlar
1. **Kural önce:** talep, etkin yayındaki işlemlerin başlık/niyet ifadeleriyle token örtüşmesiyle puanlanır. Eşit veya
   zayıf (1) eşleşmede seçim yapılmaz, kullanıcıya sorulur. Parametreler talepten birebir alınır (başlık çapası,
   tırnaklı metin, iş kimliği/sayı; baştaki sıfırlar korunur); bulunamayan sorulur, uzunluk aşımı geçersizdir.
2. **Model yalnız öneri:** kural eşleşmesi yoksa ve kullanıcı isterse kurum içi OpenAI uyumlu uca, sistem talimatı +
   kullanıcı talebi + izinli katalog dilimi (kimlik, başlık, niyet, parametre adları) gönderilir. DOM/sayfa metni,
   değerler, secret gönderilmez. Çıktı `{operation_id, arguments}` şemasıdır; enum/argüman/uzunluk doğrulanır; talepte
   geçmeyen argüman düşürülür (uydurma engeli). Model önerisi her zaman `needs_clarification` + kullanıcı onayı ister.
3. **Yetenek müzakeresi:** önce `response_format=json_schema`; uç 400 dönerse aynı uçta şemasız istem + sıkı JSON parse.
   Dış/yedek model yok. Token bütçesi muhafazakâr tahminle (3 karakter ≈ 1 token; kesin değil) kontrol edilir; aşımda
   çağrı yapılmaz. Çağrı sayısı `LLM_MAX_CALLS_PER_RUN` ile sınırlı.
4. **Sunucu planı:** önizleme ve yürütme, etkin yayının değişmez revizyonundan derlenir; istemcinin planı kabul edilmez.
   Etkin olmayan yayınla yeni run başlatılamaz (`release_superseded`); başlamış run `binding` ile yayına pinlidir.
5. **Etki onayı:** veri değiştiren işlem açık onay olmadan çalışmaz.

## Sınırlamalar
- Katalog erişimi yalnız `USE_ASSISTANT` yeteneğine göre; işlem bazında yetki referansı kurum yetki modeli
  gelince uygulanacak (BLOCKED: kurum bilgisi).
- Gerçek on-prem model ile doğrulama yapılmadı (BLOCKED); testler yerel sahte OpenAI uyumlu sunucu kullanır.
