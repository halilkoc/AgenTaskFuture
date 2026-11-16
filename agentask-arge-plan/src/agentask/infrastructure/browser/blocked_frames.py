"""Gezinmesi engellenen veya başarısız olan alt çerçevelerin kaydı (tarayıcı motorundan bağımsız).

Chromium böyle bir çerçeveyi `chrome-error://` adresine taşır; Firefox ve WebKit taşımaz. Çerçeve boş kaldığı
halde "tarandı" sayılmasın diye engelleme, isteği kesen yerde kaydedilir. Kayıt zayıf başvuruludur.
"""

from __future__ import annotations

import contextlib
from weakref import WeakSet

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Request

_blocked: WeakSet[Frame] = WeakSet()


def note_navigation(request: Request, *, blocked: bool) -> None:
    """Alt çerçevenin belge isteği kesildiyse işaretler; sonra izinli belge yüklenirse işareti kaldırır."""
    if not request.is_navigation_request():
        return
    with contextlib.suppress(PlaywrightError):
        frame = request.frame
        if frame.parent_frame is None:
            return  # ana belge: sayfa önceki belgesinde kalır, o belge geçerlidir
        if blocked:
            _blocked.add(frame)
        else:
            _blocked.discard(frame)


def frame_unusable(frame: Frame) -> bool:
    return frame.is_detached() or frame.url.startswith("chrome-error://") or frame in _blocked
