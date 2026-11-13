# Kapsam, kararlar ve varsayımlar

## Ürün hedefi
Çalışan doğal dille talep verir. Sistem yalnızca onaylı katalog yetenekleriyle iş gerçekleştirir. Analist adım yazar, hedef seçer/doğrular ve sonucu tanımlar; sistem taslak oluşturur. Son kontrol ve onayla sürüm MongoDB'ye yayımlanır.
Öncelik: doğru hedef, doğrulanmış sonuç, daha az tekrar eden süreç kodu ve daha az güncelleme bakımı. En çok promptu cevaplama tek başarı ölçütü değildir.

## Kesinleşenler
- İlk hedef Pega web; DOM/HTML erişimi ve Playwright kullanılabilir.
- Tek uygulama, role göre ayrı sayfalar; iki sayfa ortak motor kullanır.
- Katalog MongoDB'de, sürümlü ve yayımlanmış içerik değişmezdir.
- Kalıcı selector saklanmaz. İş tanımı ile teknik yürütme ayrılır.
- İç içe/dinamik frame, tekrarlanan adlar, dinamik id, özel dropdown, sanal tablo, gecikme, oturum kesilmesi ve yanıt kaybı gerçek hedef uygulamada vardır.
- Model on premise, çağrı sayısı ve bağlamı sınırlı; yürütme kararını tek başına vermez.
- İlk kapsam parasal işlem ve ayrıca onay gerektiren yüksek etkili işlemleri kapsamaz. Parasal olmayan her işlem otomatik olarak güvenli sayılmaz; işlem bazında izin gerekir.

## Nihai olarak açık kalanlar
Runner PC veya OpenShift; SSO kurulumu; onay öncesi taslakların kalıcı konumu; gerçek Pega UI/sürüm ve DX API erişimi; kurumun kimlik/yetki entegrasyonu; gerçek model context ve vLLM sürümü.
Bunlar kapatılmış kararlar değildir. Portlarla izole et, kurum adına URL/realm/servis davranışı uydurma.

## Ar-Ge başlangıç varsayımları (değiştirilebilir)
- Yerel runner, görünür tarayıcı; gerçek uygulama yerine loopback test uygulaması.
- Taslak deposu yerel dosya adapteri; yayımlama gerçek MongoDB adapteri. İsteğe bağlı test repository, kalıcı Mongo yerine geçmiş gibi gösterilmez.
- Dev kimlik adapteri sadece APP_ENV=development + açık izin + loopback binding. Production'da eksik kimlik/politika adapteri startup/işlem reddi verir.
- UI FastAPI/Jinja2/sade JS; frontend değişimi domain'i etkilemez.
- Pega'daki iş kuralları/API metadatası varsa onaylı bağlantıyla okunur; yoksa katalog tanımı veya açık duruş gerekir.

## MVP ve sonrasının ayrımı
MVP: yönlendirilmiş katalog hazırlama, alan bulma, parametreli sıralı işlemler, güvenli okuma/kurtarma, Mongo yayın, yürütme ve kanıt.
MVP sonrası: koşullar, alt işlem ve sınırlı koleksiyon döngüsü; daha önce gösterilmeyen görev birleştirme. Bu yapılar motor tarafından desteklenmeden katalogda kabul edilmez.
PC/OpenShift üretim dağıtımı ve gerçek SSO bu pakette uydurma entegrasyonla tamamlanamaz. Hazır port ve net doğrulama listesi teslim edilir.
