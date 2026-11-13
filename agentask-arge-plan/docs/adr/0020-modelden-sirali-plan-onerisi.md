# ADR 0020 — Yayımlanmış işlemlerden modelle sıralı plan önerisi (Ana plan F)

Tarih: 2026-11-07 · Durum: kabul edildi (test ikameleriyle; **gerçek model kabulü BLOCKED**)

## Bağlam
İşlem Asistanı model ile yalnız tek işlem önerebiliyordu. Çok adımlı birleştirme (P8) deneysel ve
`COMPOSITION_ENABLED` arkasında; koşul/döngü içerir.

## Karar
1. `POST /api/assistant/plan/propose`: model, etkin yayındaki (geçiş gerektirmeyen) işlemlerden **en fazla 5
   adımlık doğrusal** bir sıra önerir. Koşul, döngü, yeni işlem veya serbest kod yoktur.
2. Kodla denetlenen:
   - şema tam eşleşme (`{"steps":[{"operation_id","arguments"}]}`); bilinmeyen işlem/argüman, uzunluk → red;
   - talepte geçmeyen argüman değeri atılır (uydurma engeli), eksik değer kullanıcıdan istenir;
   - hassas veri şüphesinde model çağrılmaz; bağlam bütçesi aşılırsa çağrılmaz; model kapalıysa açık durum;
   - ardışık işlemlerin ekran sırası (bir işlemin bittiği ekran = sonrakinin başladığı ekran); uyumsuzsa öneri
     `rejected` olur ve çalıştırılamaz.
   Güven puanı veya açıklama yürütme izni değildir.
3. Öneri kendiliğinden çalışmaz. `POST /api/assistant/plan/preview` ve `/plan/execute` planı sunucuda **yeniden**
   derler (her işlem etkin yayından, pinli bileşenleriyle; argüman ve hassas değer denetimi; ekran sırası).
   Veri değiştiren işlem varsa açık etki onayı gerekir; yayın değiştiyse `ReleaseSuperseded`.
   Run bağlaması: `{"kind": "sequence", "release_id", "operations": [{operation_id, revision}]}`.
4. Arayüz: model kullanılabilirse "Birden çok işlem öner (model)" düğmesi; eksik bilgiler adım adım istenir,
   özet gösterilmeden başlatılamaz, bilgi değişirse özet geçersizleşir (mevcut kural).
5. `MAX_PLAN_OPERATIONS=5` dağıtıma bağlı ayar değil, ürün sınırıdır (docs/05 dışında).

## Doğrulama
`tests/integration/browser/test_assistant.py` (öneri, uydurma argümanın atılması, gerçek yürütme, bilinmeyen
işlem, ekran sırası reddi, model kapalı, hassas talep), `tests/e2e/test_assistant_plan_ui.py` (arayüz; geçici
MongoDB, model test ikamesi).

## BLOCKED
Gerçek kurum modeliyle kabul yapılmadı: bağlayıcı (`HttpxLLM`) mevcut test ikameleriyle doğrulanır; gerçek modelin
bu şemaya uyumu, gecikme ve bütçe davranışı erişim sağlanınca ölçülmelidir.
