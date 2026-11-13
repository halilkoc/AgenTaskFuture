"""Akış Tasarımcısı yerleşim ölçümü (yalnız test). Yatay taşmadan fazlasını ölçer:

- panel örtüşmesi (sol / orta / sağ kutularının kesişimi; sayfa kaydırılırken de),
- panel içi yatay taşma (scrollWidth > clientWidth),
- kırpılma: görünür metin/kontrolün kendi panelinin dışına taşması veya sayfanın solundan kesilmesi,
- erişilemeyen kontrol: düğme/alan merkezindeki en üst öğe kontrolün kendisi değil (başka panel örtüyor).
"""

from __future__ import annotations

from typing import Any

PROBE_JS = r"""
() => {
  const out = { overlaps: [], overflow: [], clipped: [], covered: [], doc: {} };
  const vis = (el) => { const s = getComputedStyle(el); const r = el.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0 && !el.closest('[hidden]'); };
  const de = document.documentElement;
  out.doc = { scrollWidth: de.scrollWidth, clientWidth: de.clientWidth };
  const panels = [...document.querySelectorAll('#pd-editor-view > .pd-panel')].filter(vis);
  const name = (el) => el.id || el.className.split(' ').find((c) => c.startsWith('pd-left') || c.startsWith('pd-right') || c.startsWith('pd-center')) || el.tagName;
  for (let i = 0; i < panels.length; i++) for (let j = i + 1; j < panels.length; j++) {
    const a = panels[i].getBoundingClientRect(), b = panels[j].getBoundingClientRect();
    const w = Math.min(a.right, b.right) - Math.max(a.left, b.left), h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (w > 1 && h > 1) out.overlaps.push(`${name(panels[i])}×${name(panels[j])} ${Math.round(w)}x${Math.round(h)}`);
  }
  for (const p of panels) {
    if (p.scrollWidth > p.clientWidth + 1) out.overflow.push(`${name(p)} ${p.scrollWidth}>${p.clientWidth}`);
    const pr = p.getBoundingClientRect();
    const items = p.querySelectorAll('button, input, select, textarea, a, label, p, h3, h4, li, .pd-badge, code');
    for (const el of items) {
      if (!vis(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.left < pr.left - 1 || r.right > pr.right + 1 || r.left < -1) {
        out.clipped.push(`${name(p)}:${el.tagName.toLowerCase()}#${el.id || ''} "${(el.textContent || el.value || '').trim().slice(0, 30)}" [${Math.round(r.left)},${Math.round(r.right)}] in [${Math.round(pr.left)},${Math.round(pr.right)}]`);
      }
      if (['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) {
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) continue;
        const top = document.elementFromPoint(cx, cy);
        if (top && top !== el && !el.contains(top) && !top.contains(el) && !(el.labels && [...el.labels].some((l) => l.contains(top)))) {
          out.covered.push(`${name(p)}:${el.tagName.toLowerCase()}#${el.id || ''} "${(el.textContent || '').trim().slice(0, 25)}" ← ${top.tagName.toLowerCase()}.${(top.className || '').toString().slice(0, 30)}`);
        }
      }
    }
  }
  return out;
}
"""  # noqa: E501


async def probe(page: Any, scroll_steps: int = 4) -> dict[str, list[str]]:
    """Sayfanın farklı kaydırma konumlarında ölçer (sticky paneller kaydırınca örtüşebilir)."""
    total: dict[str, list[str]] = {"overlaps": [], "overflow": [], "clipped": [], "covered": [], "page": []}
    height = await page.evaluate("document.documentElement.scrollHeight")
    view = await page.evaluate("innerHeight")
    for k in range(scroll_steps + 1):
        y = int(max(0, height - view) * k / scroll_steps)
        await page.evaluate(f"window.scrollTo(0, {y})")
        r = await page.evaluate(PROBE_JS)
        for key in ("overlaps", "overflow", "clipped", "covered"):
            for item in r[key]:
                tagged = f"@y={y} {item}"
                if not any(x.endswith(item) for x in total[key]):
                    total[key].append(tagged)
        if r["doc"]["scrollWidth"] > r["doc"]["clientWidth"] + 1 and not total["page"]:
            total["page"].append(f"sayfa yatay taşma {r['doc']['scrollWidth']}>{r['doc']['clientWidth']}")
    await page.evaluate("window.scrollTo(0, 0)")
    return total
