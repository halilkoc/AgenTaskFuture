# P8 — Kontrollü iş birleştirme ve gerçek Pega doğrulamasına hazırlık Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.

**Goal:** Koşul (if), işlem çağrısı (call_operation) ve sınırlı döngüyü (for_each) yalnız özellik bayrağıyla açık,
statik doğrulamalı ve derleme zamanında düzleştirilmiş olarak eklemek; gösterilmemiş bir birleşik görevi yayımlanmış
işlemlerden çalıştırmak; runner sözleşmesi + gerçek Pega/SSO entegrasyon kontrol listesi; paketlenebilir uygulama.

**Architecture:** `domain/composition.py` (düğüm birliği, statik doğrulama: bayrak, derinlik, öğe sınırı, adım bütçesi,
bilinmeyen işlem; düzleştirme + guard), `evaluate_condition` komutu (asla başarısız olmaz, sonucu kaydeder),
`StepRecord.when` guard'ı (koşul sağlanmazsa adım atlanır), `AssistantService.composite_*`, `/api/assistant/composite/*`.

**Spec:** docs/02 (Sonraki faz: if/call_operation/for_each; tip/veri akışı/kapsam/döngü/bütçe doğrulaması), docs/06 P8.

## Global Constraints
- `COMPOSITION_ENABLED=false` varsayılan; kapalıyken bileşik plan ve evaluate_condition reddedilir.
- Döngü yalnız açık, sınırlı öğe listesi (`COMPOSITION_MAX_ITEMS`); derinlik `COMPOSITION_MAX_DEPTH`; düzleştirilmiş
  adım sayısı `RUN_MAX_STEPS`. Çağrılan işlemler aynı etkin yayından; çağrı döngüsü reddedilir.
- Çalışma zamanında koşul yalnız önceden derlenmiş guard'ı açıp kapatır; yeni komut üretmez.

### Task 1: Domain composition + guard (unit) · Task 2: Executor guard + bileşik çalıştırma (browser) + API
### Task 3: Runner sözleşmesi + Pega/SSO kontrol listesi + doğrulama kaydı şablonu + paketleme + son inceleme
