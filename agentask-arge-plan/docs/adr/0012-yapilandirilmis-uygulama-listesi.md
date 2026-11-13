# ADR 0012 — Yapılandırılmış otomasyon uygulamaları (AUTOMATION_APPLICATIONS_JSON)

Tarih: 2026-11-07 · Durum: kabul edildi (lab ve test ikameleriyle doğrulandı; gerçek Pega/SSO doğrulanmadı)

## Bağlam
İşlem Asistanı tek bir uygulama kimliğiyle (`CATALOG_APPLICATION_ID`) çalışıyordu. Kullanıcının birden fazla
uygulama arasından seçim yapabilmesi ve Akış Tasarımcısı prototipi ile İşlem Asistanı'nın aynı listeyi kullanması
gerekiyor. Liste dağıtıma bağlıdır; bu yüzden merkezi Settings'ten okunmalıdır (docs/05).

## Karar
1. **Ayar:** `AUTOMATION_APPLICATIONS_JSON` zorunlu bir Settings alanıdır. Değeri JSON listesidir ve her kayıt
   `id`, `name`, `base_url` alanlarını taşır. Boş liste `[]` geçerlidir; varsayılan veya üretim adresi
   eklenmez.
2. **Başlangıçta doğrulama:** Hata mesajı girdi değerini içermez. Doğrulanan durumlar:
   - bozuk JSON veya liste olmayan değer;
   - yinelenen `id` veya `id` deseni dışı değer;
   - boş ya da yalnız boşluktan oluşan `name`;
   - bilinmeyen alan;
   - `base_url`'de http(s) dışı şema, kimlik bilgisi veya `#` parçası.
3. **Güvenlik politikası korunur:** `base_url` origin'i `TARGET_ALLOWED_ORIGINS` içinde olmalıdır. Liste yeni
   bir URL erişimi açmaz.
4. **Katalog eşleşmesi:** Uygulama `id`'si katalogdaki `application_id` ile aynı anlamı taşır. Liste boş değilse
   `CATALOG_APPLICATION_ID` listedeki bir `id` olmalıdır. Mevcut yayınlar bu kimlikle kayıtlıdır; bu kural
   eşleşmeyi açık hale getirir. Eski yayınlar başka uygulamaya bağlanmaz.
5. **İşlem Asistanı gerçekten kapsamlanır:**
   - Her API isteği zorunlu `application_id` taşır (`/catalog` için sorgu parametresi, diğer uçlar için gövde).
   - Bilinmeyen kimlik `application_not_configured` (422) ile reddedilir.
   - Katalog, plan ve run o kimliğin etkin yayınından derlenir. Başka uygulamanın `release_id`'si kullanılırsa
     `release_superseded` döner.
   - Run'ın `binding` alanında `application_id` bulunur.
   - Run, oturumun o anki origin'i uygulamanın origin'i değilse başlamaz (`session_application_mismatch`, 409).
     Boş oturum da bu kapsama girer; oturum kilidi bırakılır ve run kaydı oluşmaz.
   - `AssistantService`'e kimlik verilmezse eski davranış sürer (`CATALOG_APPLICATION_ID`, origin şartı yok).
     Bu yol iç kullanım ve mevcut servis testleri içindir; API her zaman kimlik verir.
6. **Yetki ayrıdır:** Listede bulunmak yetki vermez; rol, yayın ve oturum kontrolleri değişmedi.
7. **Frontend'e allowlist:** İşlem Asistanı sayfasına `id`, `name` ve `base_url` gider (uygulamayı oturumda
   açmak için). Prototipe yalnız `id` ve `name` gider. Başka hiçbir Settings alanı aktarılmaz.

## Sonuçlar ve sınırlar
- Mevcut `.env` dosyalarına `AUTOMATION_APPLICATIONS_JSON` eklenmelidir; eklenmezse uygulama açık bir
  yapılandırma hatasıyla başlamaz (zorunlu alan, docs/05 tek kaynak kuralı).
- Katalog Tasarımcısı (`/designer`), Değişiklik/etki ekranı ve yayın tarafı hâlâ tek uygulama
  (`CATALOG_APPLICATION_ID`) ile çalışır. Çok uygulamalı yayın/tasarım bu kararın kapsamı dışındadır.
- Oturum origin kontrolü yalnız run başlangıcında yapılır. Çalışma sırasındaki ekran doğrulaması mevcut R3/R4
  kontrolleriyle sürer.
