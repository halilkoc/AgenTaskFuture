"""Yalnız bu teşhis koşusu: yeni oturum testinde adres yolu ve ekran işaretleri kaydedilir. Ürün kodu değişmez."""
import asyncio, json, os, time
from urllib.parse import urlsplit
from agentask.application.services import designer as d
from agentask.application.services.observation import assess_screen

OUT = os.environ["DIAG_OUT"]
T0 = time.monotonic()

def rec(event, **kw):
    kw = {"t": round(time.monotonic() - T0, 2), "olay": event, **kw}
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(kw, ensure_ascii=False) + "\n")

def path_of(self, wait):
    try:
        return urlsplit(self._sessions.peek(wait.owner, wait.session_id).page.url).path
    except Exception as exc:
        return f"okunamadı: {type(exc).__name__}"

_cont = d.DesignerService.continue_fresh_test
async def continue_fresh_test(self, owner, draft_id):
    wait = self._fresh_waits.get(draft_id)
    if wait is not None:
        rec("devam_tiklandi", url_yolu=path_of(self, wait))
    return await _cont(self, owner, draft_id)
d.DesignerService.continue_fresh_test = continue_fresh_test

_login = d.DesignerService._login_page_open
async def _login_page_open(self, wait):
    r = await _login(self, wait)
    rec("giris_ekrani_kontrolu", giris_ekraninda=r, url_yolu=path_of(self, wait))
    return r
d.DesignerService._login_page_open = _login_page_open

async def _verdict(self, wait, draft):
    async with self._sessions.operation(wait.owner, wait.session_id, "observe", allow_verification=True) as h:
        v = await assess_screen(h.observer, self._start_screen(draft))
        return v, urlsplit(h.page.url).path

async def _later(self, wait, draft, delay):
    await asyncio.sleep(delay)
    try:
        v, p = await _verdict(self, wait, draft)
        rec(f"yeniden_kontrol_{delay}s", url_yolu=p, sonuc=v.to_dict())
    except Exception as exc:
        rec(f"yeniden_kontrol_{delay}s", hata=type(exc).__name__)

async def _screen_recognized(self, wait, draft):
    screen = self._start_screen(draft)
    v, p = await _verdict(self, wait, draft)  # ürünle aynı çağrı: assess_screen(observer, başlangıç ekranı)
    rec("ekran_kontrolu", url_yolu=p, beklenen_ekran=screen.screen_id,
        beklenen_isaretler=[m.model_dump(mode="json", exclude_none=True, exclude_defaults=True) for m in screen.markers],
        yok_olmasi_gereken=[m.model_dump(mode="json", exclude_none=True, exclude_defaults=True) for m in screen.absent_markers],
        sonuc=v.to_dict())
    if not v.recognized:
        for delay in (3, 8):
            asyncio.get_running_loop().create_task(_later(self, wait, draft, delay))
    return v.recognized
d.DesignerService._screen_recognized = _screen_recognized
