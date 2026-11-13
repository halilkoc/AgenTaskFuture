"""docs/17'deki 28 maddenin otomatik kanıt eşlemesi. Rapor ve docs/18 bu listeden türetilir.

`baseline`: bu çalışmadan önceki kapsam (tam / kismi / yeni_test / insan). Otomatik sonuç kullanıcı
kabulü değildir; `human` alanı insan gözüyle kalan kontrolü söyler.
"""

from __future__ import annotations

from dataclasses import dataclass

E2E = "tests/e2e/"
RT = "tests/integration/browser/"
CANDIDATE = E2E + "test_company_candidate_flow.py"
ACTION_E2E = E2E + "test_new_designer_approved_action_mongo.py"
WIZARD = E2E + "test_wizard_acceptance_mongo.py"
ACTION_FILE = E2E + "test_action_file_mongo.py"
ROLLBACK = E2E + "test_release_activation_ui.py"
OUTPUT = E2E + "test_output_binding_mongo.py"
TRANS_E2E = E2E + "test_transition_triggers_mongo.py"
TRANS_RT = RT + "test_transition_triggers.py"
RECORD_E2E = E2E + "test_record_flow_mongo.py"
RECORD_RT = RT + "test_record_runtime.py"
CONTROLS_E2E = E2E + "test_controls_flow_mongo.py"
CONTROLS_RT = RT + "test_controls_runtime.py"
MULTI_E2E = E2E + "test_multi_date_file_flow_mongo.py"
MULTI_RT = RT + "test_multi_date_file_runtime.py"
WINDOW_E2E = E2E + "test_window_modal_flow_mongo.py"
WINDOW_RT = RT + "test_window_modal_runtime.py"
CHOICE_E2E = E2E + "test_new_designer_choice_mongo.py"
ACTION_RT = RT + "test_action_definition_runtime.py"
EMPTY_READ = RT + "test_executor.py::test_empty_prior_output_stops_without_writing"
PACKAGE = "package"
VISUAL = "Ekranın anlaşılırlığı ve metinlerin yerindeliği insan değerlendirmesidir."
HEADFUL = "Testler görünmez tarayıcıda çalışır; görünür pencerenin açılışı elle görülmedi."


@dataclass(frozen=True)
class Item:
    number: int
    title: str
    baseline: str
    tests: tuple[str, ...]
    verified: str
    human: str = ""


ITEMS: tuple[Item, ...] = (
    Item(1, "Yanlış ve doğru parolayla giriş", "tam", (CANDIDATE,),
         "Giriş sayfasına yönlenir; yanlış parolada genel hata; doğru parolada tasarımcı.", VISUAL),
    Item(2, "Yeni akış, gerçek oturum, uygulamayı aç", "tam", (CANDIDATE,),
         "Prototip rozeti ve temsili düğmeler gizli; hedef giriş sayfası oturumda açıldı.", HEADFUL),
    Item(3, "Hedefe giriş ve seçim ekranı", "tam", (CANDIDATE,),
         "Oturumda hedefe girildi; Kefil bölümündeki alan görünür."),
    Item(4, "Kefil › Şube sabit Konak tanımı", "kismi", (CANDIDATE, CHOICE_E2E),
         "Tanım ve kaydetme sonrası sayfadaki tüm alanlar başlangıçla aynı (Şube hâlâ Seçiniz)."),
    Item(5, "Kaydet, yenile, yeniden aç", "tam", (CANDIDATE,),
         "Yenileme sonrası oturum sürer; 5 adım değerleriyle gelir; eksik yok."),
    Item(6, "Ekran tanıtma, onay, gerçek deneme", "kismi", (CANDIDATE,),
         "BAŞARILI; sayfa farkı yalnız tanımlı dört alan (Kefil › Şube = Konak dahil)."),
    Item(7, "Elle girişli yeni oturum testi başlar", "tam", (CANDIDATE,),
         "“Elle giriş bekleniyor”; ayrı doğrulama oturumu açılır.", HEADFUL),
    Item(8, "Girişsiz devam reddedilir", "kismi", (CANDIDATE,),
         "“giriş ekranında”; BAŞARILI yazılmaz, deneme başlamaz."),
    Item(9, "Giriş sonrası devam", "tam", (CANDIDATE,),
         "“Yeni oturum testi tamamlandı: BAŞARILI”; doğrulama oturumu kapandı."),
    Item(10, "Yayıncı onayı ve yayın", "kismi", (CANDIDATE,),
         "Onay geçerli; mesajdaki yayın kimliği API'deki etkin yayınla aynı."),
    Item(11, "İşlem Asistanı ile çalıştırma", "kismi", (CANDIDATE,),
         "Başarılı; onay kutusu yok; yalnız tanımlı alanlar değişti (Başvuran › Şube boş); destek no /runs ile aynı."),
    Item(12, "Onaylı işlem: her çalıştırmada tek not", "kismi", (ACTION_E2E,),
         "Kaydetmede 0, deneme/yeni oturum/Asistan'da birer not; adımın aksiyon özeti güncel özetle aynı."),
    Item(13, "Yanıt kaybında mükerrer yok", "kismi", (ACTION_E2E, ACTION_RT),
         "Yanıtı kaybolan çalıştırma Başarılı ve tek yeni not; sonuç doğrulanamazsa tekrar yok."),
    Item(14, "Çok ekranlı başvuru tasarımdan Asistan'a", "yeni_test", (WIZARD,),
         "Kayıt bağlamı kontrolü geçiş tanımında; rota iki ekran; tutar yazıldı; her çalıştırmada tek geçiş."),
    Item(15, "Yanlış vaka ekranında durma", "yeni_test", (WIZARD,),
         "C-2001-B açılınca Duraklatıldı; tutar boş; destek no görünür; doğru vakada yeniden çalıştı."),
    Item(16, "Çalışma geçmişi ve çıkış", "kismi", (WIZARD,),
         "Aşama, neden, sonraki adım dolu; teknik ayrıntı kapalı; destek no aynı; çıkış girişe döner.", VISUAL),
    Item(17, "Aksiyon dosyası değişince yeniden onay", "kismi", (ACTION_FILE, ACTION_RT),
         "Eski yayın 422 action_changed, manifest değişmedi; yeni özete bağlanıp yeniden test, yayın ve tek not."),
    Item(18, "Yayın geri ve ileri alma", "kismi", (ROLLBACK, "tests/unit/test_release_activation.py"),
         "Yayıncı dışı 403; kısa gerekçe reddi; geri ve ileri alma; iki yayın korunur; iki etkinleştirme kaydı."),
    Item(19, "Okunan değer işleme ve bileşene", "tam", (OUTPUT, EMPTY_READ),
         "Okunan değer tek gönderimle kaydedildi; boş okumada adım durdu, kayıt yok."),
    Item(20, "Bağlantı ve seçimle geçiş", "tam", (TRANS_E2E, TRANS_RT),
         "Hedef alan yazıldı; aynı adlı bağlantıda tıklama yok, sayfa aynı kaldı."),
    Item(21, "Kayıt bul, satırdan aç, bağlam", "tam", (RECORD_E2E, RECORD_RT),
         "Doğru kaydın detayı yazıldı; yalnız bulunan satır değişti; yinelenen/yok/yanlış kayıtta yazma yok."),
    Item(22, "Onay kutusu ve seçenek grubu", "kismi", (CONTROLS_E2E, CONTROLS_RT),
         "Yalnız Başvuru değişti, Kefil aynı; ikinci çalıştırmada kutu ve radyoda 0 yeni tıklama."),
    Item(23, "Öneri alanı doğru/yok/iki eşleşme", "kismi", (CONTROLS_E2E, CONTROLS_RT),
         "Tam eşleşme ve gerçek değer doğrulandı; seçim kaybolunca Belirsiz, iki eşleşmede Başarısız; tekrar yok."),
    Item(24, "Çoklu seçim küme farkı", "tam", (MULTI_E2E, MULTI_RT),
         "Alandaki küme birebir istenen küme; yalnız fark uygulandı; eksik/devre dışı üyede 0 değişiklik."),
    Item(25, "Tarih alanları", "kismi", (MULTI_E2E, MULTI_RT),
         "type=date ISO yazıldı; 31.02 tasarımda reddedildi ve alana yazılmadı; çeviren uygulama başarısız."),
    Item(26, "Dosya yükleme", "kismi", (MULTI_E2E, MULTI_RT, "tests/unit/test_artifacts.py"),
         "Ad/tür/boyut doğru, tek gönderim; içerik uyuşmayan dosya alınmadı; belirsizde tekrar yok."),
    Item(27, "Beklenen pencere ve isteğe bağlı modal", "tam", (WINDOW_E2E, WINDOW_RT),
         "Pencerede yazıldı, ana ekran doğrulandı, açık pencere yok; beklenmeyen/çift pencere ve farklı modal durdu.",
         HEADFUL),
    Item(28, "Paket içeriği ve temiz kurulum", "kismi", (PACKAGE,),
         "Özetler uyuşuyor; yasak yol yok; wheel kaynakla aynı; temiz ortamda kurulum, --check-config, --doctor.",
         "Windows .ps1 betikleri ve Windows wheel kurulumu yalnız Windows'ta denenebilir."),
)  # fmt: skip

HUMAN_CHECKS = (
    "Ekranların anlaşılırlığı, metinlerin ve akışın analist için uygunluğu.",
    "Görünür tarayıcıda (BROWSER_HEADLESS=false) pencerelerin açılışı ve elle giriş deneyimi.",
    "Windows'ta install.ps1, start.ps1, doctor.ps1, hash-admin.ps1 ve Windows wheel kurulumu.",
    "Gerçek Pega/SSO, kurumsal MongoDB/TLS, kurum modeli, S3 ve log aktarımı (MANUAL_ACCEPTANCE.md S0–S25).",
)
