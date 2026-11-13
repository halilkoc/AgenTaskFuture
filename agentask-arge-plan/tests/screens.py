"""YALNIZ TEST: deney uygulamasının 'Başvuru — taraf bilgileri' ekranı için anlamsal ekran tanımı.

Tanım URL, DOM id veya frame sırası içermez; aynı ekran farklı adreste de tanınmalıdır. İşlemin kendi hedefi
(Kefil › Müşteri No) tanıma işaretlerinden biri DEĞİLDİR (döngüsel doğrulama yok)."""

from __future__ import annotations

from agentask.domain.screens import RegionDef, ScreenDef
from agentask.domain.targeting import TargetSpec

APPLICANT_NO = TargetSpec(kind="textbox", labels=["Müşteri No"], region="Başvuran")
GUARANTOR_NAME = TargetSpec(kind="textbox", labels=["Ad Soyad"], region="Kefil")
GUARANTOR_NO = TargetSpec(kind="textbox", labels=["Müşteri No"], region="Kefil")
# Benzer ama farklı "Kefil değişiklik talebi" ekranını ayıran kontrol: doğru ekranda bulunmaz.
CHANGE_REQUEST_NOTE = TargetSpec(kind="textbox", labels=["Talep Notu"], region="Kefil")

PARTIES_SCREEN = ScreenDef(
    screen_id="basvuru_taraflar",
    title="Başvuru — taraf bilgileri",
    regions=[
        RegionDef(region_id="basvuran", name="Başvuran"),
        RegionDef(region_id="kefil", name="Kefil"),
    ],
    markers=[APPLICANT_NO, GUARANTOR_NAME],
    absent_markers=[CHANGE_REQUEST_NOTE],
)

ASSERT_PARTIES = {"op": "assert_screen", "screen": PARTIES_SCREEN.model_dump(mode="json")}

# Not ekleme ekranı: işaret, adımların kullandığı "Not" alanı değil, ekranın kaydet düğmesidir.
NOTE_SCREEN = ScreenDef(
    screen_id="vaka_not_ekle",
    title="Vaka — not ekle",
    markers=[TargetSpec(kind="button", labels=["Kaydet"])],
    absent_markers=[TargetSpec(kind="textbox", labels=["Müşteri No"])],
)
