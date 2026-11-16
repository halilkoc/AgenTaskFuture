# Yerel kabulün otomasyonu ve şirket kabul yaklaşımı

Bu belge `docs/17_LOCAL_ACCEPTANCE.md` içindeki 28 maddenin otomatik kanıtla nasıl değerlendirildiğini ve gerçek
ortamda (elle SSO girişinden sonra) uygulanacak kabul yaklaşımını anlatır.

**Otomatik sonuç kullanıcı kabulü değildir.** Lab'da geçmek Pega, SSO, Windows veya kurum bağlantılarının kabulü değildir.

## 1. Tek komut

```
.venv/bin/python -m tools.local_acceptance            # tam koşu (madde 28 dahil)
.venv/bin/python -m tools.local_acceptance --skip-package --timeout-s 1800
.venv/bin/python -m tools.local_acceptance --browser-engine firefox   # veya kabukta BROWSER_ENGINE=firefox
```

- **Tarayıcı motoru (0.3.0):** `chromium` (varsayılan) veya `firefox`. Seçim hem testin arayüz tarayıcısına hem uygulamanın
  hedef tarayıcısına uygulanır (`AGENTASK_TEST_BROWSER_ENGINE` test değişkeni → `BROWSER_ENGINE` ayarı). `guard.py` her
  tarayıcı başlatmasını taraf (arayüz/hedef) ve motor adıyla sayar; başka motor başlatılmak istenirse o test hata alır.
  Koşu sonunda `browser-launches.json` denetlenir: iki taraf da seçili motorla en az bir kez açılmamışsa veya başka motor
  açılmışsa çıkış kodu 1 olur. Ön koşul denetimi yalnız seçili motoru dener; indirme yapmaz. `webkit` reddedilir (ADR 0025).
- **macOS'ta Firefox:** bu Mac'te Firefox gerçek kullanıcı dizininde “Could not find profile folder” ile kapanıyor (neden
  belirlenemedi). Testler Firefox'u geçici bir kullanıcı diziniyle (`CFFIXED_USER_HOME`) başlatır; Playwright tarayıcı
  dosyalarının yeri değişmez. Bu yalnız test ortamı önlemidir, ürün ayarı değildir.

- **Rapor:** `acceptance-reports/<zaman>/`. İçerik: `report.md`, `report.json`, `junit.xml`, `pytest.log`, `pytest-exit-code.txt`, `exit-code.txt`, `paket-*.log`. Başarısız test varsa `failures/<test>/tani.json` ve ekran görüntüleri de yazılır.
- **Mac uykusu:** koşu uykuya karşı `caffeinate -i` ile kendini yeniden başlatır. Otomatik tekrar yoktur.
- **Kod kaynağı:** `tools/local_acceptance/`. Madde eşlemesi `coverage.py`, yalıtım kuralları `safety.py`, pytest eklentisi `guard.py`, madde 28 denetimi `package_check.py`. Aracın kendi testleri: `tests/unit/test_local_acceptance_tool.py`.

### Çıkış kodları

| Kod | Anlam |
|---|---|
| 0 | 28 maddenin hepsi GEÇTİ |
| 1 | En az bir test veya madde başarısız (KALDI), pytest sıfırdan farklı döndü ya da seçili motor dışında tarayıcı açıldı |
| 2 | Başarısız yok, ama OTOMATİK DOĞRULANAMADI madde var |
| 3 | Ön koşul eksik (mongod, seçili tarayıcı motoru), geçersiz/desteklenmeyen motor, kabukta yerel olmayan adres var veya başka bir koşu sürüyor |
| 4 | Yalıtım ihlali: koşu sırasında `.env`, `var/` veya kalıcı MongoDB sayıları değişti |
| 5 | Süre sınırı aşıldı; koşu kesildi, sonuçsuz maddeler OTOMATİK DOĞRULANAMADI |

pytest'in kendi çıkış kodu ayrıca `pytest-exit-code.txt` dosyasında ve raporda tutulur.

### Yalıtım ve güvenlik

- **Gerçek adres reddi:** `TARGET_*`, `LAB_*`, `MONGO_URI`, `AUTOMATION_APPLICATIONS_JSON`, `LLM_BASE_URL` veya `S3_ENDPOINT_URL` yerel olmayan bir adres içeriyorsa koşu hiç başlamaz (çıkış 3). Değer yazılmaz, yalnız anahtar adı yazılır.
- **Ortam:** pytest yalnız `PATH`, `HOME`, dil ve geçici dizin değişkenleriyle çalışır; diğer ayarlar aktarılmaz. Her uygulama örneği `guard.py` tarafından denetlenir. Hedef adresi yerel değilse, MongoDB yerel değilse veya çalışma/taslak/dosya dizini geçici alanın dışındaysa örnek kurulmaz.
- **Geçici kaynaklar:** MongoDB her test için geçici `mongod` ve rastgele port kullanır. Lab ve uygulama rastgele port kullanır; 8000, 8100, 8101 ve 27017'ye dokunulmaz. Dizinler `--basetemp` altındadır ve koşu sonunda silinir.
- **Kalıcı veri kanıtı:** koşudan önce ve sonra `.env` özeti, `var/` dosya listesi (boyut ve zaman) ve kalıcı MongoDB'deki koleksiyon sayıları yalnız okunarak karşılaştırılır.
- **Süre:** pytest için toplam sınır varsayılan 3600 sn. Süre dolarsa yalnız aracın başlattığı süreç grubu sonlandırılır. Takılan testte 600 sn sonra bütün iş parçacıklarının yığını `pytest.log`'a yazılır.
- **Hassas veri:** çıktılar parola, scrypt hash, oturum çerezi ve bağlantı sırlarından arındırılır. Trace ve ağ kaydı alınmaz. Ekran görüntüsü yalnız başarısız testte ve lab sayfalarından alınır.

## 2. Kapsam eşlemesi (28 madde)

“Önceki kapsam” bu çalışmadan önceki durumdur. Ayrıntı ve doğrulanan somut sonuç: `tools/local_acceptance/coverage.py`.

| # | Madde | Önceki kapsam | Otomatik kanıt (test) | İnsan kontrolü |
|---|---|---|---|---|
| 1 | Yanlış/doğru parolayla giriş | tam | `test_company_candidate_flow` | ekranın anlaşılırlığı |
| 2 | Yeni akış, gerçek oturum, uygulamayı aç | tam | `test_company_candidate_flow` | görünür pencere |
| 3 | Hedefe giriş, seçim ekranı | tam | `test_company_candidate_flow` | — |
| 4 | Kefil › Şube = Konak tanımı | kısmi | `test_company_candidate_flow`, `test_new_designer_choice_mongo` | — |
| 5 | Kaydet, yenile, yeniden aç | tam | `test_company_candidate_flow` | — |
| 6 | Ekran tanıtma, onay, gerçek deneme | kısmi | `test_company_candidate_flow` | — |
| 7 | Elle girişli yeni oturum testi | tam | `test_company_candidate_flow` | görünür pencere |
| 8 | Girişsiz devam reddi | kısmi | `test_company_candidate_flow` | — |
| 9 | Giriş sonrası devam | tam | `test_company_candidate_flow` | — |
| 10 | Yayıncı onayı, yayın | kısmi | `test_company_candidate_flow` | — |
| 11 | İşlem Asistanı | kısmi | `test_company_candidate_flow` | — |
| 12 | Onaylı işlem, tek not | kısmi | `test_new_designer_approved_action_mongo` | — |
| 13 | Yanıt kaybında mükerrer yok | kısmi | `test_new_designer_approved_action_mongo`, `test_action_definition_runtime` | — |
| 14 | Çok ekranlı başvuru | yeni test | `test_wizard_acceptance_mongo` | — |
| 15 | Yanlış vakada durma | yeni test | `test_wizard_acceptance_mongo` | — |
| 16 | Geçmiş ve çıkış | kısmi | `test_wizard_acceptance_mongo` | ekranın anlaşılırlığı |
| 17 | Aksiyon dosyası değişince yeniden onay | kısmi | `test_action_file_mongo`, `test_action_definition_runtime` | — |
| 18 | Yayın geri/ileri alma | kısmi | `test_release_activation_ui`, `test_release_activation` | — |
| 19 | Okunan değer işleme ve bileşene | tam | `test_output_binding_mongo`, `test_empty_prior_output_stops_without_writing` | — |
| 20 | Bağlantı ve seçimle geçiş | tam | `test_transition_triggers_mongo`, `test_transition_triggers` | — |
| 21 | Kayıt bul, satırdan aç, bağlam | tam | `test_record_flow_mongo`, `test_record_runtime` | — |
| 22 | Onay kutusu, seçenek grubu | kısmi | `test_controls_flow_mongo`, `test_controls_runtime` | — |
| 23 | Öneri alanı | kısmi | `test_controls_flow_mongo`, `test_controls_runtime` | — |
| 24 | Çoklu seçim | tam | `test_multi_date_file_flow_mongo`, `test_multi_date_file_runtime` | — |
| 25 | Tarih | kısmi | `test_multi_date_file_flow_mongo`, `test_multi_date_file_runtime` | — |
| 26 | Dosya yükleme | kısmi | `test_multi_date_file_flow_mongo`, `test_multi_date_file_runtime`, `test_artifacts` | — |
| 27 | Beklenen pencere, isteğe bağlı modal | tam | `test_window_modal_flow_mongo`, `test_window_modal_runtime` | görünür pencere |
| 28 | Paket ve temiz kurulum | kısmi | paket denetimi (`package_check.py`) | Windows betikleri |

**Sonuç doğrulamaları:** başarı yalnız mesajdan okunmaz. Testler şunları da kontrol eder:
- Değişen alanların birebir kümesi; hedef dışı alanlar ve aynı adlı başka bölümler değişmemelidir.
- Gönderim, tıklama ve arama sayıları.
- Etkin yayının API'deki kimliği.
- Adımın aksiyon özeti.
- Destek numarasının Asistan ile `/runs` arasında aynı olması.
- Yanlış ekran, yinelenen hedef ve belirsiz sonuçta yeniden işlem yapılmaması.

**Kısmi manuel lab kanıtı (kullanıcı bildirimi):** “Kefil şubesi seçimi İşlem Asistanı'nda başarılı.” Bu bildirim madde 2–11'e karşılık gelir, ama madde madde kabul sayılmaz.

## 3. Gerçek ortamda elle SSO sonrası kabul yaklaşımı

**Durum: tasarım. Gerçek Pega DOM'u olmadan hazır veya doğrulanmış değildir.** Bu makineden şirket bağlantısı kurulmadı ve işlem yapılmadı.

**İlkeler**
1. **Giriş insandadır.** Kabul koşusu bir AgenTask tarayıcı oturumu açar, hedef uygulamayı izinli adreste gösterir ve durur. Kullanıcı SSO/MFA girişini kendisi yapar. Parola, çerez veya belirteç kaydedilmez. Bu, yeni oturum testindeki “Girişi yeni pencerede elle yapacağım → Giriş yaptım, devam et” akışıyla aynıdır.
2. **Yalnız açıkça seçilmiş test kayıtları.** Koşu, kurumun ayırdığı test kayıtlarının listesini (vaka/kayıt numaraları) parametre olarak alır. Her işlem, “Açılan ekranda kayıt doğrulansın mı?” başlangıç ve geçiş bağlamıyla o kayda bağlanır. Liste dışı veya bağlamı uymayan kayıtta işlem yapılmaz.
3. **Yalnız yayımlanmış ve onaylı işlemler.** Kabul, katalogdaki yayımlanmış işlemleri İşlem Asistanı yoluyla çalıştırır. Veri değiştiren adımlar yalnız kurum aksiyon dosyasındaki uzlaştırmalı aksiyonlardır; belirsiz sonuçta tekrar yoktur.
4. **Sonuç ikinci bir okumayla doğrulanır.** Her işlemden sonra Bilgi oku veya uzlaştırma okumasıyla hedef alanın ve kaydın durumu okunur. Hedef dışı alanların değişmediği, aynı ekranın önce ve sonraki alan listesi karşılaştırılarak kanıtlanır.
5. **Ön koşul ve durdurma.** İzinli adres listesi (`TARGET_ALLOWED_ORIGINS`), test kayıtları listesi ve elle giriş onayı olmadan koşu başlamaz. Beklenmeyen pencere, oturum düşmesi veya bağlam uyuşmazlığında koşu durur ve insan kararı bekler.
6. **Kanıt.** Destek numaraları, çalışma kayıtları ve sır içermeyen teşhis saklanır. Ekran görüntüsü kurum politikası izin verirse ve maskeleme doğrulanırsa alınır (`EVIDENCE_SCREENSHOTS_ENABLED`).

**Önerilen adımlar (şirkette)**
1. `MANUAL_ACCEPTANCE.md` S0: üç ana ekranın kontrol envanteri. Desteklenmeyen kontrol türleri belirlenir.
2. Seçilmiş 1–3 test kaydı için `docs/17`'ye benzer akışlar tasarlanır (S20–S22), bağlam kontrolü zorunludur.
3. Elle SSO sonrası Asistan'dan çalıştırılır; sonuçlar Pega'da da elle kontrol edilir.
4. Otomatik tekrar koşusu ancak bu ilk kabul başarılı olduktan sonra, aynı test kayıtlarıyla ve kurumun onayıyla değerlendirilir.

**Bu makinede doğrulanmayanlar:**
- Windows kurulum betikleri ve Windows wheel kurulumu.
- Gerçek Pega DOM'u ve SSO/MFA.
- Kurumsal MongoDB/TLS, kurum modeli, S3 ve log aktarımı.
- Kurulu Edge/Chrome.

## 4. Son koşu (2026-11-13)
**Sonuç:** 28/28 GEÇTİ; araç çıkış kodu 0, pytest çıkış 0 (114 passed). Yalıtım: kalıcı veride değişiklik yok. Paket 0.2.1 madde 28 denetiminden geçti.
- Rapor: `acceptance-reports/20261113-202235/report.md`.
- Geçersiz önceki koşu: `acceptance-reports/20261113-201632/GECERSIZ_KOSU.md`. Neden, aracın `__aexit__` sarmalayıcısının argümansız çağrıyı kabul etmemesiydi.

