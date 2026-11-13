# Katalog Tasarımcısı sadeleştirme planı (henüz uygulanmadı)

**Amaç:** Bugün tek uzun sayfada duran alanları beş aşamalı bir akışa yerleştirmek: İşlem bilgileri → Ekranlar →
Adımlar ve geçişler → Deneme → Yayın.

**Değişmeyecekler:**
- Backend uçları, doğrulamalar ve onay kuralları: ayrı onaylar, hash'e bağlı test ve onay, geçiş denemesi için açık
  onay, `screen_markers_only_targets` vb.
- Veri modeli ve mevcut taslaklar. `teminat_gir` gibi taslaklar olduğu gibi açılır.

**Kapsam:** yalnız `templates/designer.html` ve `static/designer.js` (sunum katmanı).

## 1. Aşama eşlemesi (mevcut alan → yeni yeri)
| Aşama | Gösterilecek alanlar (mevcut öğe) | İleri düzey (açılır bölüm) |
|---|---|---|
| 1. İşlem bilgileri | İşlem kimliği, Başlık, Açıklama (`.dz-create`); Parametreler: Ad, Başlık, Kaynak (`.dz-param`); taslak listesi ve geçiş gereken eski yayınlar (`.dz-drafts`, `.dz-migrations`) | Parametre "En fazla" uzunluk, Onaylı sabit değeri, niyet ifadeleri |
| 2. Ekranlar | Tarayıcı oturumu paneli + Deney ekranı / **Ekranı aç** (`.dz-nav`); Ekran kimliği, Ekran adı, **Ekrandaki kontrolleri listele** + işaret seçimi, **Ekran tanımını doğrula ve kaydet** (`.dz-screen-form`); ekran listesi + **Ekranı doğrula** (`.dz-screen`) | Ek bölgeler, "Bu ekranda olmamalı" işaretleri, Başlangıç kayıt bağlamı (`.dz-context-form`) |
| 3. Adımlar ve geçişler | **Adım ekle**; kartta: Komut, Değer/şablon, Hedef adayları / Tarayıcıda işaretle, Aksiyon, Geçiş seçimi; geçiş formu: kimlik, kaynak/hedef ekran, tetikleyici türü, **Tetikleyici adaylarını listele** (`.dz-transition-form`) | Eleman kimliği, Anlam metni, Başarı koşulu "Kontrol yok", Adımın ekranı (rota dışı seçim), geçiş bekleme süresi, tamamlanma koşulu, standart açıklama metni |
| 4. Deneme | Kartta dört ayrı onay (Anlam/Hedef/Etki/Parametre), deneme değerleri, veri değiştirir / ekran geçişini tetikler onayı, **Dene**, **Sonucu onayla** | Deneme çalıştırma kimliği ve hata sınıfı ayrıntısı |
| 5. Yayın | Başlangıç ekranı + test değerleri + **Yeni oturum testi** (`.dz-fresh`); eksikler listesi (`.dz-issues`); **Onayla (yayıncı)**, **Yayımla**, Yayınları incele | İçerik özeti (hash), onay kaydı ayrıntısı |

## 2. Tamamlananlar ve eksikler (mevcut `issues` kodlarından, backend değişmeden)
- **Aşama yanında rozet:** "Tamamlandı" ya da "N eksik". Hesap mevcut `draft.issues` kodlarının aşamalara
  eşlenmesiyle yapılır:
  - `no_steps`, `step_N_*`, `transition_*` → Adımlar ve geçişler;
  - `screen_missing`, `screen_markers_only_targets*`, `element_region_not_in_screen*`, `duplicate_screen_id` →
    Ekranlar;
  - `*_undeclared_param*` → İşlem bilgileri (parametre eksik);
  - `fresh_session_test_*` → Yayın;
  - `step_N_not_ready` → Deneme.
- **Türkçe açıklamalar:** her kod için tek cümle. Mevcut `ISSUE_TR` genişletilir; ham kod yalnız ileri düzey
  bölümde görünür. Örnek: "2. adımın denemesi onaylanmadı — Deneme aşamasında 'Sonucu onayla'ya basın."
- **Aşama kilidi yok:** kullanıcı istediği aşamaya geçebilir. Yalnız Yayın aşamasında, eksik varsa düğmeler
  açıklamayla pasif görünür. Backend yine son sözü söyler; ret iletisi aynen gösterilir.

## 3. Kısa yardım metinleri (soru işareti simgesi, tek-iki cümle)
- **Parametre:** "İşlem her çalıştığında kullanıcıdan istenen değer (ör. müşteri no). Adımda {ad} olarak
  kullanılır."
- **Ekran kimliği:** "Ekranı katalogda tanıtan kısa ad (küçük harf, rakam, _). Adres veya sayfa kodu değildir."
- **Tanıma işareti:** "Bu ekranda her zaman bulunan ve ekranı ayırt eden alan/düğme. İşlemin yazacağı alan tek
  başına yetmez."
- **Olmamalı işareti:** "Benzer ama yanlış ekranda bulunan kontrol; görülürse işlem durur."
- **Bölge:** "Ekrandaki adlandırılmış bölüm (ör. Kefil). Aynı adlı alanları ayırmaya yarar."
- **Kayıt bağlamı:** "Doğru kayıtta olduğunuzu kanıtlayan alan değeri (ör. Vaka No = {vaka_no})."
- **Geçiş:** "Bir düğmenin/aksiyonun hangi ekrandan hangi ekrana götürdüğü. Çalışırken yalnız bir kez tetiklenir."
- **Yeni oturum testi:** "İşlemi temiz bir tarayıcıda baştan sona çalıştırır; onay için zorunludur."
- **Onay:** "İçeriğin ve testin özetine bağlıdır; taslak değişirse yeniden gerekir."

## 4. Tek ekranlı işlemi kolay tutma
- Ekran sayısı 1 iken geçiş formu ve "Adımın ekranı" seçimi gizlenir. Yerlerine "Bu işlem tek ekranda çalışır" ve
  **Ekran ekle** bağlantısı görünür.
- Mevcut R3 akışı (adımlar → ekran tanımı → test) aynı sırayla da çalışmaya devam eder.

## 5. Uygulama adımları (sonraki görev)
1. `designer.html`: beş `<section data-stage>` ve üstte aşama gezinmesi; ileri düzey alanlar `<details>` içinde.
   Mevcut sınıf adları korunur.
2. `designer.js`: alanlar taşınır; aşama rozetleri (`issues` → aşama eşlemesi); `ISSUE_TR` genişletilir; yardım
   simgeleri eklenir. API çağrıları değişmez.
3. **Testler:**
   - Backend testleri değişmeden geçmeli.
   - E2E yardımcıları (`author_ready_draft`, `define_parties_screen`, R4 E2E) aşama gezinmesi için güncellenir;
     beklentiler gevşetilmez.
   - Yeni E2E: rozetler ve eksik açıklamaları; tek ekranlı işlemde geçiş alanlarının gizli olması.
4. **Kabul:** `.venv/bin/python -m tools.dev_check` BAŞARILI; kullanıcı, mevcut `teminat_gir` ve `kefil_musteri_no`
   taslaklarını yeni düzende açıp eksiklerin doğru aşamada göründüğünü doğrular.
