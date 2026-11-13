# P6 — İşlem Asistanı ve sınırlı LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.

**Goal:** Kullanıcı doğal dille talep yazar; sistem etkin yayındaki onaylı işlemlerden kural tabanlı eşleşme ve
parametre çıkarımı yapar, belirsizlikte soru sorar, sunucuda yeniden doğrulanan planı gösterir ve yayına pinlenmiş
run olarak çalıştırır. LLM yalnız isteğe bağlı öneri verir (operation id + tipli argüman), doğrulanmadan çalışmaz.

**Architecture:** `domain/assistant.py` (eşleşme, parametre çıkarımı, model çıktısı doğrulayıcı, token bütçesi),
`application/ports/llm.py` (complete_json), `infrastructure/llm/httpx_llm.py` (OpenAI uyumlu iç endpoint; none/basic/
bearer; TLS/CA; json_schema yetenek müzakeresi, yoksa sıkı parse+red), `application/services/assistant.py`
(interpret/plan/execute; release pin), `/api/assistant/*`, `/assistant` ekranı. Run modeline `release_id`,
`operation_id`, `content_hash` eklenir.

**Spec:** docs/04 (LLM kullanım şekli), docs/06 P6, docs/07 T14–T16, docs/08, docs/05 (LLM ayarları).

## Global Constraints
- LLM_ENABLED=false iken hiçbir bağlantı kurulmaz; temel akış kural tabanlı çalışır. Dış/yedek model yok.
- Modele yalnız kullanıcı talebi + izinli katalog dilimi (işlem kimliği, başlık, niyet ifadeleri, parametre adları)
  gider; DOM/sayfa metni, değerler ve secret gitmez. Çıktı şema + enum ile doğrulanır; geçersiz → red.
- Model çıktısı plan değildir: sunucu planı yayındaki revizyondan derler ve kullanıcı onayı ister.
- Parametre uydurulmaz: bulunamayan değer eksik olarak sorulur; baştaki sıfırlar korunur.
- Token/çağrı bütçesi Settings'ten; aşımda çağrı yapılmaz.

## Review Focus
1. Prompt'taki "önceki talimatları yok say, sil" türü metin işlem kümesini genişletmemeli (`test_prompt_injection_cannot_add_operations`).
2. Model bilinmeyen operation/argüman döndürürse dispatch yok (`test_model_unknown_operation_rejected`).
3. Yeni yayın run sırasında aktif olsa da run kendi release'iyle kalır (`test_run_pinned_to_release`).
4. İki işlem eşit puanlıysa soru sorulur, seçilmez (`test_ambiguous_prompt_asks`).
5. Bütçe aşan bağlam gönderilmez (`test_token_budget_prevents_call`).
