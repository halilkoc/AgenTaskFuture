# P4 — Katalog Tasarımcısı Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** JSON yazmadan, modelsiz yönlendirilmiş işlem (operation) taslağı hazırlama: niyet → hedef önerisi/seçimi →
anlam/hedef/etki/parametre onayı → deneme → bağımsız sonuç kontrolü → yeni oturum testi → incelemeye hazır.
Yayımlanmış koleksiyonlara hiçbir şey yazılmaz (P5).

**Architecture:** `domain/catalog.py` (taslak, adım kartı, eleman, parametre kaynağı, provenance, adım durum
makinesi, canonical içerik hash'i, operasyon derleyicisi), `domain/authoring.py` (kural tabanlı niyet → komut
önerisi ve aday sıralama), `application/ports/drafts.py` + `infrastructure/drafts/local_file.py` (revizyon
kontrollü yerel taslak deposu), `application/services/designer.py` (use case'ler; P2 gözlem, P3 RunService),
`presentation/api/drafts.py`, `/designer` ekranı.

**Spec:** docs/04 (Designer adım durumu, Adım kartı, Yeniden kullanım ve test), docs/02, docs/06 P4, docs/09
(drafts uçları), kullanıcı talimatı "Katalog hazırlamada" maddeleri.

## Global Constraints
- Katalogda selector/id/frame sırası/koordinat/URL yok; hedef = TargetSpec (anlamsal), eleman kimliği slug.
- Parametre kaynağı: user_input | prior_output | approved_constant | secret_ref; örnek değerler katalogda sabitlenmez
  (deneme değerleri yalnız deneme kaydında). Secret değeri hiçbir yerde tutulmaz (secret_ref yalnız ad).
- Adım onayı yayın onayı değildir; tek "Evet" ile anlam+hedef+etki birlikte onaylanmaz (ayrı alanlar).
- Provenance: observed, rule_generated, model_suggested, human_verified. P4'te model yok.
- Taslak düzenlemesi expected_revision ile; çakışma 409. İçerik değişince deneme/test kanıtı geçersiz.
- Deneme gerçek etki oluşturabilir; mutating adım denemesi açık onay ister.

## Review Focus
1. Test sonrası içerik değişirse "incelemeye hazır" düşmeli (test: `test_edit_after_fresh_test_invalidates_readiness`).
2. Belirsiz hedef seçimi onaylanamamalı (test: `test_ambiguous_target_cannot_be_confirmed`).
3. approved_constant hassas görünen değeri kabul etmemeli; secret_ref değer taşımamalı (test: `test_param_sources`).
4. Eşzamanlı iki düzenleme: ikincisi 409 (test: `test_revision_conflict`).
5. Yayımlanmış katalog depolarına yazma yok (test: `test_designer_never_writes_published`).

### Task 1: Domain (catalog + authoring) — unit
### Task 2: Yerel draft deposu + DesignerService (gerçek tarayıcı: öneri, seçim, deneme, yeni oturum testi)
### Task 3: API + /designer ekranı + e2e (JSON yazmadan uçtan uca hazırlama)
