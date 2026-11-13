"""Seçim modu ve vurgulama için sabit sayfa betikleri.

Seçim modu her frame belgesine şeffaf bir katman koyar (alt iframe alanları clip-path ile boş bırakılır, böylece
o frame'in kendi katmanı olayı alır) ve pencere capture aşamasında fare/klavye/form olaylarını iptal eder.
Böylece sayfadaki kontrol click, focus, submit, input veya change almaz. Seçilen elemanın envanter sırasındaki indeksi ve
anlamsal parmak izi yalnız bir binding'e token ile bildirilir; token'sız/yanlış token'lı çağrılar Python tarafında yok sayılır.
"""

from agentask.infrastructure.browser.inventory_js import DESCRIBE

BINDING = "__agentaskPick"
_KEY = "Symbol.for('agentask.picker')"

PICKER_INSTALL = (
    "(token) => {"
    + DESCRIBE
    + """
  const KEY = """
    + _KEY
    + """;
  if (window[KEY]) window[KEY]();
  const doc = document;
  const root = doc.documentElement;
  const overlay = doc.createElement('div');
  overlay.setAttribute('data-agentask-ui', 'picker');
  overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483646;cursor:crosshair;background:rgba(31,95,191,0.06);';
  const hover = doc.createElement('div');
  hover.setAttribute('data-agentask-ui', 'picker-hover');
  hover.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483647;border:2px dashed #1f5fbf;display:none;';
  root.appendChild(overlay); root.appendChild(hover);
  if (doc.activeElement && doc.activeElement !== doc.body && doc.activeElement.blur) doc.activeElement.blur();

  function updateClip() {
    const w = innerWidth, h = innerHeight;
    let d = `M0 0 H${w} V${h} H0 Z`;
    doc.querySelectorAll('iframe,frame').forEach(f => {
      const r = f.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) d += ` M${r.left} ${r.top} h${r.width} v${r.height} h${-r.width} Z`;
    });
    overlay.style.clipPath = `path(evenodd, '${d}')`;
  }
  // Seçim modunda hiçbir sayfa kontrolü odakta kalmaz (ör. modal açılırken otomatik odak); böylece IME/metin
  // ekleme gibi tuş olayı üretmeyen girişler de alana ulaşamaz.
  function dropFocus() {
    const a = doc.activeElement;
    if (a && a !== doc.body && !a.closest('[data-agentask-ui]') && a.blur) a.blur();
    // Odak kalksa da düzenleme seçimi alanda kalabilir; seçim de temizlenir.
    const sel = doc.getSelection && doc.getSelection();
    if (sel && sel.rangeCount) sel.removeAllRanges();
  }
  dropFocus();
  updateClip();
  const timer = setInterval(() => { updateClip(); dropFocus(); }, 150);

  function targetAt(x, y) {
    const under = doc.elementsFromPoint(x, y).filter(e => !e.closest('[data-agentask-ui]'));
    const first = under[0];
    if (!first || first.tagName === 'IFRAME' || first.tagName === 'FRAME') return null;
    const control = first.closest(SELECTOR);
    if (control) return control;
    const label = first.closest('label');
    return label && label.control ? label.control : null;
  }
  const BLOCK = ['click','dblclick','auxclick','contextmenu','mousedown','mouseup','pointerdown','pointerup',
    'touchstart','touchend','submit','keydown','keypress','keyup','beforeinput','input','change','focusin','wheel',
    'compositionstart','compositionupdate','compositionend','paste','cut','drop','dragstart'];
  function block(e) {
    if (e.type === 'wheel') return;  // kaydırma serbest; sayfa olayı tetiklemez
    e.preventDefault(); e.stopImmediatePropagation();
    if (e.type === 'focusin' && e.target && e.target.blur && !e.target.closest('[data-agentask-ui]')) e.target.blur();
    if (e.type === 'click' && e.isTrusted) {
      const el = targetAt(e.clientX, e.clientY);
      const index = el ? candidates().indexOf(el) : -1;
      const fp = el && index >= 0 ? describe(el).fp : null;
      try { window["""
    + repr(BINDING)
    + """]({ token, index, fp }); } catch (err) {}
    }
  }
  function move(e) {
    e.stopImmediatePropagation();
    const el = targetAt(e.clientX, e.clientY);
    if (!el) { hover.style.display = 'none'; return; }
    const r = el.getBoundingClientRect();
    Object.assign(hover.style, { display: 'block', left: `${r.left - 2}px`, top: `${r.top - 2}px`,
      width: `${r.width + 4}px`, height: `${r.height + 4}px` });
  }
  BLOCK.forEach(t => window.addEventListener(t, block, { capture: true, passive: false }));
  ['mousemove','pointermove','mouseover','mouseout','pointerover','pointerout'].forEach(
    t => window.addEventListener(t, move, { capture: true }));
  window[KEY] = () => {
    clearInterval(timer);
    BLOCK.forEach(t => window.removeEventListener(t, block, { capture: true }));
    ['mousemove','pointermove','mouseover','mouseout','pointerover','pointerout'].forEach(
      t => window.removeEventListener(t, move, { capture: true }));
    overlay.remove(); hover.remove();
    delete window[KEY];
  };
  return true;
}"""
)

PICKER_UNINSTALL = "() => { const k = " + _KEY + "; if (window[k]) window[k](); return true; }"

HIGHLIGHT = """(arr, args) => {
  const [index, caption] = args;
  document.querySelectorAll('[data-agentask-ui=highlight]').forEach(n => n.remove());
  const el = arr[index];
  if (!el || !el.isConnected) return false;
  const r = el.getBoundingClientRect();
  const box = document.createElement('div');
  box.setAttribute('data-agentask-ui', 'highlight');
  box.style.cssText = 'position:absolute;pointer-events:none;z-index:2147483647;border:3px solid #f59e0b;' +
    'box-shadow:0 0 0 3px rgba(245,158,11,.35);border-radius:3px;';
  Object.assign(box.style, { left: `${r.left + scrollX - 4}px`, top: `${r.top + scrollY - 4}px`,
    width: `${r.width + 8}px`, height: `${r.height + 8}px` });
  const tag = document.createElement('div');
  tag.textContent = caption;
  tag.style.cssText = 'position:absolute;left:0;top:-1.9em;white-space:nowrap;background:#f59e0b;color:#111;' +
    'font:12px/1.6 system-ui,sans-serif;padding:0 .4em;border-radius:3px;';
  box.appendChild(tag);
  document.documentElement.appendChild(box);
  return true;
}"""

CLEAR_HIGHLIGHT = (
    "() => { document.querySelectorAll('[data-agentask-ui=highlight]').forEach(n => n.remove()); }"
)

# Seçilen indeksteki elemanı döndürür; parmak izi değiştiyse null (seçimden sonra ekran değişti).
ELEMENT_AT = (
    "(args) => {"
    + DESCRIBE
    + """
  const [index, fp] = args;
  const el = candidates()[index];
  return el && describe(el).fp === fp ? el : null;
}"""
)
