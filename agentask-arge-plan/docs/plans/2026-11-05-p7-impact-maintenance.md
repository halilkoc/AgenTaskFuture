# P7 — Değişiklik/etki analizi, bakım ve çalışma takibi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.

**Goal:** Yeni gözlemi yayımlanmış işlemin anlamsal elemanlarıyla karşılaştırıp (dinamik id/zaman/kayıt verisi yok
sayılır) değişen/eksik/belirsiz elemanları göstermek; bağımlılık grafiğiyle etkilenen işlemleri ve yeniden test
listesini bulmak; onarım için yeni taslak açmak (aktif katalog değişmez); run zaman çizelgesi ve metrikleri göstermek.

**Architecture:** `domain/impact.py` (eleman durum sınıflandırması, yeniden adlandırma önerisi, bağımlılık grafiği,
regression seçimi, onarım taslağı), `application/services/impact.py`, `domain/metrics.py` (run metrikleri),
`/api/changes/*`, `/api/metrics/runs`, `/changes` ve `/runs` ekranları.

**Spec:** docs/04 (Değişiklik ekranı, /runs), docs/06 P7, docs/07 T24, docs/08 (Çalışma kaydı).

## Global Constraints
- Karşılaştırma anlamsaldır: label/role/region/kontrol davranışı; HTML id/sıra/zaman/kayıt değeri karşılaştırılmaz.
- Kapsam eksikse "eleman kayboldu" denmez (unknown). Yeniden adlandırma yalnız öneri; otomatik onarım yok.
- Onarım taslağı yeni taslaktır; etkin yayın değişmez. Teknik tekrar (recovery) ile iş başarısı ayrı sayılır.

## Review Focus
1. Dinamik id değişimi değişiklik sayılmamalı (`test_dynamic_ids_ignored`).
2. Etiket değişimi eleman+işlem etkisi olarak işaretlenmeli, onarım önerisi aynı bölge/tür (`test_label_change_detected`).
3. Ortak adapter/aksiyon değişikliği bütün kullanan işlemleri bulmalı (`test_shared_dependency_impact`).
4. Onarım taslağı aktif yayını değiştirmemeli (`test_repair_draft_does_not_touch_release`).
5. Metrikler teknik toparlanmayı başarıdan ayırmalı (`test_metrics_separate_recoveries`).
