# Tamamlanmamış genişletilmiş test koşusu (2026-11-09)

**Sonuç yok; başarılı sayılmaz.** pytest çıkış kodu oluşmadı (19:12'de hâlâ çalışıyordu, kapatılmadı).

- Süreç: PID 95736, başlangıç yaklaşık 18:40. Son ilerleme 18:42, sonraki 30 dakikada ilerleme yok (CPU %0.1).
- İlerleme çıktısı `pytest-ilerleme.txt`: `FF..F`.
- Takıldığı test: `tests/e2e/test_controls_flow_mongo.py` (`test_checkbox_radio_autocomplete_from_design_to_assistant`). Nedeni belirlenmedi.
- Sırayla: wizard F, company_candidate F, approved_action geçti, release_activation geçti, action_file F.
- `--tb=short` hata ayrıntıları pytest bitince yazıldığı için bu üç başarısızlığın nedeni okunamadı. Ürün hatası mı, yeni test beklentisi mi olduğu bilinmiyor.
- Çalıştırılmayan: multi_date_file ve window_modal e2e testleri.
