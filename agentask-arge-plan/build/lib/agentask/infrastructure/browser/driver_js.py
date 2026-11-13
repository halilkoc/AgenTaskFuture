"""Kontrol sürücüsünün sabit sayfa betikleri. Kod üretimi yok; hiçbiri olay tetiklemez (tıklama/yazma Playwright
eylemleriyle yapılır). Değer okuma hassas (password) alanlarda null döner."""

_NORM = "const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim().toLowerCase();"
_VISIBLE = """const isVisible = (el) => {
  if (typeof el.checkVisibility === 'function' && !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
  const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0;
};"""
_NAME = """const byIds = (ids) => ids ? ids.split(/\\s+/).map(i => document.getElementById(i)).filter(Boolean).map(e => e.textContent).join(' ') : '';
const nameOf = (el) => byIds(el.getAttribute('aria-labelledby')) || el.getAttribute('aria-label') || (() => {
  const h = el.querySelector(':scope > h1, :scope > h2, :scope > h3, :scope > h4'); return h ? h.textContent : '';
})();"""
_LISTBOX = """const listboxOf = (el) => {
  const id = el.getAttribute('aria-controls');
  if (id) { const lb = document.getElementById(id); if (lb) return lb; }
  const visible = Array.from(document.querySelectorAll('[role=listbox]')).filter(isVisible);
  return visible.length === 1 ? visible[0] : null;
};"""

STATE = (
    "(el) => {"
    + _VISIBLE
    + """
  const tag = el.tagName.toLowerCase();
  let value = null, selectedText = null;
  if (tag === 'input' || tag === 'textarea') value = (el.type || '').toLowerCase() === 'password' ? null : el.value;
  if (tag === 'select') { value = el.value; selectedText = el.selectedIndex >= 0 ? el.options[el.selectedIndex].text.trim() : null; }
  else if (tag !== 'input' && tag !== 'textarea') selectedText = (el.innerText || '').replace(/\\s+/g, ' ').trim();
  const flag = (n) => el.hasAttribute(n) ? el.getAttribute(n) === 'true' : null;
  const panelId = el.getAttribute('role') === 'tab' ? el.getAttribute('aria-controls') : null;
  const panel = panelId ? document.getElementById(panelId) : null;
  return { value, selectedText, expanded: flag('aria-expanded'), selected: flag('aria-selected'),
    panelVisible: panel ? isVisible(panel) : null, visible: isVisible(el),
    enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true' && !el.closest('fieldset[disabled]') };
}"""
)

LISTBOX_READY = (
    "(el) => {"
    + _VISIBLE
    + _LISTBOX
    + """
  const lb = listboxOf(el); return !!lb && lb.querySelectorAll('[role=option]').length > 0;
}"""
)

LISTBOX_OPTIONS = (
    "(el) => {"
    + _VISIBLE
    + _LISTBOX
    + """
  const lb = listboxOf(el); if (!lb) return [];
  return Array.from(lb.querySelectorAll('[role=option]')).filter(isVisible).map(o => o.textContent.replace(/\\s+/g, ' ').trim());
}"""
)

FIND_OPTION = (
    "(el, label) => {"
    + _VISIBLE
    + _LISTBOX
    + _NORM
    + """
  const lb = listboxOf(el); if (!lb) return null;
  const hits = Array.from(lb.querySelectorAll('[role=option]')).filter(o => isVisible(o) && norm(o.textContent) === norm(label));
  return hits.length === 1 ? hits[0] : null;
}"""
)

TABLE_KEYS = """(el, max) => {
  const rows = Array.from(el.querySelectorAll(':scope > tbody > tr, :scope > tr, [role=row]')).slice(0, max);
  return rows.map(r => { const c = r.querySelector(':scope > th[scope=row]') || r.querySelector(':scope > td, :scope > [role=cell], :scope > [role=gridcell]');
    return c ? c.textContent.replace(/\\s+/g, ' ').trim() : null; }).filter(k => k !== null);
}"""

NEXT_CONTROLS = (
    "(labels) => {"
    + _VISIBLE
    + _NORM
    + """
  const wanted = new Set(labels.map(norm));
  return Array.from(document.querySelectorAll('a[href], button, [role=link], [role=button]')).filter(e =>
    !e.closest('[data-agentask-ui]') && wanted.has(norm(e.getAttribute('aria-label') || e.textContent)) && isVisible(e)
    && !e.disabled && e.getAttribute('aria-disabled') !== 'true');
}"""
)

SCROLL_TO_END = """(el) => {
  let node = el.parentElement;
  while (node && node !== document.body) {
    const style = getComputedStyle(node);
    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) {
      node.scrollTop = node.scrollHeight; node.dispatchEvent(new Event('scroll')); return true;
    }
    node = node.parentElement;
  }
  return false;
}"""

TEXT_VISIBLE = (
    "(text) => {"
    + _VISIBLE
    + _NORM
    + """
  const wanted = norm(text); const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  let n = 0;
  while (walker.nextNode() && n++ < 20000) {
    const el = walker.currentNode;
    if (el.children.length === 0 && norm(el.textContent) === wanted && isVisible(el)) return true;
  }
  return false;
}"""
)

EVIDENCE_STATUS = """(el) => {
  const scope = (el && el.closest('form,[role=form],section,[role=region],[role=dialog]')) || document;
  return Array.from(scope.querySelectorAll('[role=status]')).map(s => s.textContent.replace(/\\s+/g, ' ').trim()).filter(Boolean);
}"""

EVIDENCE_LIST = (
    "(name) => {"
    + _NORM
    + _NAME
    + """
  const lists = Array.from(document.querySelectorAll('ul, ol, [role=list]')).filter(l => norm(nameOf(l)) === norm(name));
  if (lists.length !== 1) return { error: lists.length ? 'ambiguous' : 'missing', items: [] };
  return { error: null, items: Array.from(lists[0].querySelectorAll(':scope > li, :scope > [role=listitem]'))
    .map(i => i.textContent.replace(/\\s+/g, ' ').trim()) };
}"""
)

OPEN_DIALOGS = (
    "() => {"
    + _VISIBLE
    + _NAME
    + """
  return Array.from(document.querySelectorAll('[role=dialog], [role=alertdialog], dialog[open]'))
    .filter(d => !d.closest('[data-agentask-ui]') && isVisible(d))
    .map(d => ({ name: nameOf(d).replace(/\\s+/g, ' ').trim() || null,
                 text: (d.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 300) }));
}"""
)

DIALOG_BUTTONS = (
    "(args) => {"
    + _VISIBLE
    + _NAME
    + _NORM
    + """
  const [dialogName, label] = args;
  const dialogs = Array.from(document.querySelectorAll('[role=dialog], [role=alertdialog], dialog[open]'))
    .filter(d => isVisible(d) && norm(nameOf(d)) === norm(dialogName));
  return dialogs.flatMap(d => Array.from(d.querySelectorAll('button, [role=button]'))
    .filter(b => isVisible(b) && norm(b.textContent) === norm(label)));
}"""
)

MUTATION_WAIT = """(ms) => new Promise((resolve) => {
  const obs = new MutationObserver(() => { obs.disconnect(); clearTimeout(t); resolve(true); });
  obs.observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
  const t = setTimeout(() => { obs.disconnect(); resolve(false); }, ms);
})"""
