"""Maskelemesi doğrulanmış ekran kanıtı (ADR 0018). Varsayılan kapalı: EVIDENCE_SCREENSHOTS_ENABLED.

- Kanıt yalnız görünür alanın (viewport) tek görüntüsüdür; sürekli kayıt yoktur.
- Maskelenen: bütün form kontrolleri (input, textarea, select, contenteditable) ve bütün çerçeveler (iframe) —
  değer içerebilecek her şey. Hangi alanın hassas olduğu tahmin edilmez; muhafazakâr olarak hepsi örtülür.
- Doğrulama: maskeli görüntü çözülür; örtülecek her kutunun iç pikselleri maske rengiyle karşılaştırılır.
  Tek bir kutu bile tam örtülü değilse (ör. kapanan/kayan öğe, gölge DOM, ölçek farkı) görüntü KULLANILMAZ.
- Görüntü değerleri loglanmaz.
"""

from __future__ import annotations

import logging
import struct
import zlib
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

MASK_COLOR = (255, 0, 255)
MASK_SELECTOR = "input, textarea, select, [contenteditable]:not([contenteditable='false']), iframe"
_BOXES_JS = """(sel) => Array.from(document.querySelectorAll(sel)).map((el) => {
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  const hidden = s.visibility === 'hidden' || s.display === 'none';
  return { x: r.left, y: r.top, w: r.width, h: r.height, hidden };
}).filter((b) => !b.hidden && b.w >= 1 && b.h >= 1)"""


@dataclass(frozen=True, slots=True)
class MaskedCapture:
    png: bytes
    verified: bool
    reason: str
    boxes: int


def decode_png(data: bytes) -> tuple[int, int, int, list[bytes]]:
    """(genişlik, yükseklik, piksel başına bayt, satırlar). Yalnız 8 bit RGB/RGBA, taramasız PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("png_signature")
    pos, idat, header = 8, b"", None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
        pos += 12 + length
    if header is None:
        raise ValueError("png_header")
    width, height, depth, color, _, _, interlace = header
    if depth != 8 or color not in {2, 6} or interlace != 0:
        raise ValueError("png_format")
    bpp = 3 if color == 2 else 4
    raw = zlib.decompress(idat)
    stride = width * bpp
    rows: list[bytes] = []
    prev = bytearray(stride)
    for y in range(height):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 0xFF
            elif f == 2:
                line[i] = (line[i] + b) & 0xFF
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
            elif f != 0:
                raise ValueError("png_filter")
        rows.append(bytes(line))
        prev = line
    return width, height, bpp, rows


def boxes_masked(png: bytes, boxes: list[dict[str, float]]) -> tuple[bool, str]:
    """Her kutunun (görünür kısmının) iç pikselleri maske rengi mi? Kenarda 1 px yumuşatma payı bırakılır."""
    width, height, bpp, rows = decode_png(png)
    for box in boxes:
        x0, y0 = max(0, int(box["x"]) + 1), max(0, int(box["y"]) + 1)
        x1, y1 = min(width, int(box["x"] + box["w"]) - 1), min(height, int(box["y"] + box["h"]) - 1)
        if x1 <= x0 or y1 <= y0:
            continue  # görünür alan dışında: görüntüde yok
        for y in range(y0, y1):
            row = rows[y]
            for x in range(x0, x1):
                if tuple(row[x * bpp : x * bpp + 3]) != MASK_COLOR:
                    return False, "unmasked_pixels"
    return True, "verified"


async def capture_masked(page: Any) -> MaskedCapture:
    """Görünür alanın maskeli görüntüsü ve doğrulaması. `page` Playwright Page'dir."""
    mask = page.locator(MASK_SELECTOR)
    png: bytes = await page.screenshot(
        type="png",
        full_page=False,
        scale="css",
        animations="disabled",
        caret="hide",
        mask=[mask],
        mask_color="#FF00FF",
    )
    # Kutular görüntüden sonra ölçülür; arada değişen sayfa doğrulamayı bozar ve görüntü reddedilir.
    boxes: list[dict[str, float]] = await page.evaluate(_BOXES_JS, MASK_SELECTOR)
    try:
        verified, reason = boxes_masked(png, boxes)
    except (ValueError, zlib.error) as exc:
        verified, reason = False, f"decode_failed:{exc}"
    if not verified:
        logger.warning("evidence_mask_unverified reason=%s boxes=%d", reason, len(boxes))
    return MaskedCapture(png=png, verified=verified, reason=reason, boxes=len(boxes))
