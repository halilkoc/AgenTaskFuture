"""Sayfa içinde çalışan sabit, salt-okur envanter betikleri (kod üretimi/eval yok; sabit kaynak).

Betik DOM'u değiştirmez, olay tetiklemez ve hiçbir alan değeri döndürmez. Yalnız rol/ad/etiket/durum ve
mantıksal bağlam döner. `data-agentask-ui` taşıyan kendi katmanlarımız envantere alınmaz.
"""

DESCRIBE = r"""
const SELECTOR = [
  'input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]):not([type=range]):not([type=color]):not([type=image])',
  'textarea', 'select', 'button', 'table',
  '[role=button]', '[role=textbox]', '[role=searchbox]', '[role=combobox]', '[role=tab]', '[role=table]', '[role=grid]'
].join(',');
const SENSITIVE_AUTOCOMPLETE = new Set(['current-password','new-password','one-time-code','cc-number','cc-csc','cc-exp']);
const SENSITIVE_NAME = /(parola|şifre|sifre|password|passwd|\bpin\b|cvv|cvc|otp|tek kullanımlık|güvenlik kodu|guvenlik kodu|gizli)/i;
const MAX_TEXT = 120;

function clean(text) {
  if (text == null) return null;
  const t = String(text).replace(/\s+/g, ' ').trim();
  return t ? t.slice(0, MAX_TEXT) : null;
}
function byIds(ids) {
  if (!ids) return null;
  const parts = ids.split(/\s+/).map(id => document.getElementById(id)).filter(Boolean).map(e => e.textContent);
  return clean(parts.join(' '));
}
function ownText(el) { return clean(el.innerText !== undefined ? el.innerText : el.textContent); }

function kindOf(el) {
  const role = (el.getAttribute('role') || '').toLowerCase();
  const tag = el.tagName.toLowerCase();
  if (role === 'combobox') return 'combobox';
  if (role === 'tab') return 'tab';
  if (role === 'table' || role === 'grid' || tag === 'table') return 'table';
  if (tag === 'select') return 'select';
  if (role === 'button' || tag === 'button') return 'button';
  if (tag === 'input' && ['button','submit','reset'].includes((el.type || '').toLowerCase())) return 'button';
  return 'textbox';
}
function labelOf(el) {
  const lb = byIds(el.getAttribute('aria-labelledby'));
  if (lb) return lb;
  if (el.labels && el.labels.length) {
    const clone = el.labels[0].cloneNode(true);
    clone.querySelectorAll('input,select,textarea,button').forEach(n => n.remove());
    return clean(clone.textContent);
  }
  return null;
}
function nameOf(el, kind, label) {
  const aria = clean(el.getAttribute('aria-label'));
  if (label && el.getAttribute('aria-labelledby')) return label;
  if (aria) return aria;
  if (label) return label;
  if (kind === 'table') {
    const cap = el.querySelector(':scope > caption');
    if (cap) return clean(cap.textContent);
  }
  if (kind === 'button' || kind === 'tab') {
    if (el.tagName === 'INPUT') return clean(el.value);
    const t = ownText(el);
    if (t) return t;
  }
  return clean(el.getAttribute('title')) || clean(el.getAttribute('placeholder'));
}
function isSensitive(el, label, name) {
  const type = (el.getAttribute('type') || '').toLowerCase();
  if (type === 'password') return true;
  if (el.getAttribute('data-sensitive') === 'true') return true;
  if (SENSITIVE_AUTOCOMPLETE.has((el.getAttribute('autocomplete') || '').toLowerCase())) return true;
  return SENSITIVE_NAME.test([label, name, el.getAttribute('name'), el.getAttribute('autocomplete')].join(' '));
}
function isVisible(el) {
  if (typeof el.checkVisibility === 'function' &&
      !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}
function isEnabled(el) {
  if (el.disabled) return false;
  if ((el.getAttribute('aria-disabled') || '') === 'true') return false;
  return !el.closest('fieldset[disabled]');
}
function regionName(node) {
  const lb = byIds(node.getAttribute('aria-labelledby'));
  if (lb) return lb;
  const aria = clean(node.getAttribute('aria-label'));
  if (aria) return aria;
  if (node.tagName === 'FIELDSET') {
    const legend = node.querySelector(':scope > legend');
    if (legend) return clean(legend.textContent);
  }
  const heading = node.querySelector(':scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > h5, :scope > h6');
  return heading ? clean(heading.textContent) : null;
}
function contextsOf(el) {
  const out = [];
  let node = el.parentElement, guard = 0;
  while (node && node !== document.body && guard++ < 40) {
    const tag = node.tagName;
    const role = (node.getAttribute('role') || '').toLowerCase();
    if (tag === 'TR' || role === 'row') {
      const table = node.closest('table,[role=table],[role=grid]');
      const keyCell = node.querySelector(':scope > th[scope=row]') || node.querySelector(':scope > td, :scope > th, :scope > [role=cell], :scope > [role=gridcell]');
      const tname = table ? (clean(table.getAttribute('aria-label')) || byIds(table.getAttribute('aria-labelledby')) ||
        (table.querySelector(':scope > caption') ? clean(table.querySelector(':scope > caption').textContent) : null)) : null;
      out.push({ kind: 'table_row', name: tname, key: keyCell && keyCell !== el && !keyCell.contains(el) ? clean(keyCell.textContent) : null });
    } else if (role === 'dialog' || role === 'alertdialog' || tag === 'DIALOG') {
      out.push({ kind: 'dialog', name: regionName(node), key: null });
    } else if (role === 'tabpanel') {
      out.push({ kind: 'tabpanel', name: regionName(node), key: null });
    } else if (tag === 'FIELDSET' || role === 'group') {
      const n = regionName(node); if (n) out.push({ kind: 'group', name: n, key: null });
    } else if (tag === 'FORM' || role === 'form') {
      const n = regionName(node); if (n) out.push({ kind: 'form', name: n, key: null });
    } else if (tag === 'SECTION' || tag === 'ASIDE' || role === 'region') {
      const n = regionName(node); if (n) out.push({ kind: 'region', name: n, key: null });
    }
    node = node.parentElement;
  }
  return out;
}
function describe(el) {
  const kind = kindOf(el);
  const label = labelOf(el);
  const name = nameOf(el, kind, label);
  const sensitive = isSensitive(el, label, name);
  let selectedText = null, options = [];
  if (kind === 'select' && !sensitive) {
    selectedText = el.selectedIndex >= 0 ? clean(el.options[el.selectedIndex].text) : null;
    options = Array.from(el.options).slice(0, 50).map(o => clean(o.text)).filter(Boolean);
  } else if (kind === 'combobox' && !sensitive && el.tagName !== 'INPUT') {
    selectedText = ownText(el);
  }
  const hasValue = (kind === 'textbox' || kind === 'combobox') && el.tagName !== 'DIV'
    ? Boolean(el.value) : false;
  const contexts = contextsOf(el);
  const item = {
    kind, role: (el.getAttribute('role') || el.tagName.toLowerCase()), tag: el.tagName.toLowerCase(), name, label,
    visible: isVisible(el), enabled: isEnabled(el), sensitive, hasValue, selectedText, options, contexts,
  };
  item.fp = JSON.stringify([kind, item.role, name, label, contexts]);
  return item;
}
function candidates() {
  return Array.from(document.querySelectorAll(SELECTOR)).filter(el => !el.closest('[data-agentask-ui]'));
}
"""

# Ayrıntılı tarama: { items, els, total } — els runtime element handle dizisi olarak Python'da tutulur.
DETAIL_SCAN = (
    "(opts) => {"
    + DESCRIBE
    + """
  const all = candidates();
  const els = all.slice(0, opts.maxElements);
  return { items: els.map(describe), els, total: all.length };
}"""
)

# Hafif özet: yalnız ad/etiket metinleri ve sayısı (bağlam ve durum yok).
LIGHT_SCAN = (
    "(opts) => {"
    + DESCRIBE
    + """
  const all = candidates();
  const els = all.slice(0, opts.maxElements);
  const names = [];
  for (const el of els) {
    const kind = kindOf(el); const label = labelOf(el); const name = nameOf(el, kind, label);
    if (label) names.push(label); if (name && name !== label) names.push(name);
  }
  return { names, total: all.length };
}"""
)

# Aday doğrulama: eleman hâlâ bağlı mı ve anlamsal parmak izi aynı mı?
FINGERPRINT_AT = (
    "(arr, index) => {"
    + DESCRIBE
    + """
  const el = arr[index];
  if (!el || !el.isConnected) return null;
  return describe(el).fp;
}"""
)

INDEX_OF = "(arr, el) => arr.indexOf(el)"
