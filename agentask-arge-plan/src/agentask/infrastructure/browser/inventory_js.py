"""Sayfa içinde çalışan sabit, salt-okur envanter betikleri (kod üretimi/eval yok; sabit kaynak).

Betik DOM'u değiştirmez, olay tetiklemez ve hiçbir alan değeri döndürmez. Yalnız rol/ad/etiket/durum ve
mantıksal bağlam döner. `data-agentask-ui` taşıyan kendi katmanlarımız envantere alınmaz.
"""

DESCRIBE = r"""
const SELECTOR = [
  'input:not([type=hidden]):not([type=radio]):not([type=range]):not([type=color]):not([type=image])',
  'textarea', 'select', 'button', 'table', 'a[href]', '[role=link]',
  '[role=button]', '[role=textbox]', '[role=searchbox]', '[role=combobox]', '[role=listbox]', '[role=checkbox]', '[role=switch]', '[role=radiogroup]', 'fieldset', '[role=tab]', '[role=table]', '[role=grid]'
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
  if (role === 'combobox' || role === 'listbox') return 'combobox';
  if ((tag === 'button' || role === 'button') && (el.getAttribute('aria-haspopup') || '').toLowerCase() === 'listbox') return 'combobox';
  if (role === 'tab') return 'tab';
  if (role === 'checkbox' || role === 'switch' || (tag === 'input' && (el.type || '').toLowerCase() === 'checkbox')) return 'checkbox';
  if (role === 'radiogroup' || tag === 'fieldset') return 'radio_group';
  if (tag === 'input' && (el.type || '').toLowerCase() === 'file') return 'file';
  if (role === 'link' || (tag === 'a' && !role)) return 'link';
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
  if (kind === 'radio_group' && el.tagName === 'FIELDSET') {
    const legend = el.querySelector(':scope > legend');
    if (legend) return clean(legend.textContent);
  }
  if (kind === 'table') {
    const cap = el.querySelector(':scope > caption');
    if (cap) return clean(cap.textContent);
  }
  if (kind === 'button' || kind === 'tab' || kind === 'link') {
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
function labelVisible(el) {
  return !!(el.labels && Array.from(el.labels).some(isVisible));
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
// Etkileşim bağlamı: DOM'da bulunma, görünürlük ve etkileşime açıklık ayrı tutulur.
//   open             : etkileşime açık (görünürlük ayrıca 'visible' alanında)
//   inactive_dialog  : kapalı/gizli bir pencerenin içinde (aktif hedef olamaz)
//   behind_dialog    : açık modal pencerenin arkasında
//   overlay          : görünür ama merkezini başka bir öğe/katman kapatıyor (boyuttan bağımsız)
//   inert            : inert bir ata altında
//   dialog_ambiguous : aynı belgede birden fazla bağımsız aktif modal var (hangisinin etkin olduğu belirsiz)
const DIALOG_SEL = 'dialog, [role=dialog], [role=alertdialog]';
let __activeDialogs = null;
function activeDialogs() {
  if (__activeDialogs) return __activeDialogs;
  const open = Array.from(document.querySelectorAll(DIALOG_SEL)).filter(d => !d.closest('[data-agentask-ui]')
    && isVisible(d) && (d.tagName === 'DIALOG' ? d.matches(':modal') : d.getAttribute('aria-modal') === 'true'));
  // İç içe pencerelerde en içteki etkindir; birbirini içermeyen birden fazla en-iç pencere belirsizdir.
  __activeDialogs = open.filter(a => !open.some(b => b !== a && a.contains(b)));
  return __activeDialogs;
}
function overlayCovers(el) {
  // Hedefin merkezindeki nokta-isabet testi: en üstteki öğe hedefin kendisi, alt öğesi, atası (hedef
  // pointer-events:none ise tıklama atasına gider) veya kendi etiketi değilse hedef kapalıdır. Katmanın boyutu
  // ölçüt değildir: küçük bir katman da hedefi kapatabilir. Görünüm alanı dışındaki hedef burada denetlenmez;
  // sürücü eylemden hemen önce hedefi görünür alana kaydırıp aynı kontrolü yeniden yapar.
  const r = el.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  if (!(r.width > 0 && r.height > 0) || cx < 0 || cy < 0 || cx >= innerWidth || cy >= innerHeight) return false;
  const hit = document.elementsFromPoint(cx, cy).find(e => !e.closest('[data-agentask-ui]'));
  if (!hit || hit === el || el.contains(hit) || hit.contains(el)) return false;
  if (el.labels && Array.from(el.labels).some(l => l.contains(hit))) return false;
  // Merkez, hedefi kırpan bir kaydırma alanının dışındaysa (alandan büyük tablo gibi) o noktadaki öğe hedefi
  // kapatan katman değildir; görünüm alanı dışındaki hedef gibi burada denetlenmez.
  for (let a = el.parentElement; a && a !== document.documentElement; a = a.parentElement) {
    const s = getComputedStyle(a);
    if (/(auto|scroll|hidden|clip)/.test(s.overflowX + ' ' + s.overflowY)) {
      const c = a.getBoundingClientRect();
      if (cx < c.left || cx >= c.right || cy < c.top || cy >= c.bottom) return false;
    }
  }
  return true;
}
function interactionOf(el) {
  const owner = el.closest(DIALOG_SEL);
  if (owner && !isVisible(owner)) return 'inactive_dialog';
  if (el.closest('[inert]')) return 'inert';
  const active = activeDialogs();
  if (active.length > 1) return 'dialog_ambiguous';
  if (active.length === 1 && !active[0].contains(el)) return 'behind_dialog';
  if (isVisible(el) && overlayCovers(el)) return 'overlay';
  return 'open';
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
  } else if (kind === 'combobox' && !sensitive && el.tagName !== 'INPUT' && el.getAttribute('role') !== 'listbox') {
    selectedText = ownText(el);
  }
  const multiple = el.tagName === 'SELECT' ? el.multiple : el.getAttribute('aria-multiselectable') === 'true';
  const hasValue = (kind === 'textbox' || kind === 'combobox') && el.tagName !== 'DIV'
    ? Boolean(el.value) : false;
  const contexts = contextsOf(el);
  const item = {
    kind, role: (el.getAttribute('role') || el.tagName.toLowerCase()), tag: el.tagName.toLowerCase(), name, label,
    visible: isVisible(el) || ((kind === 'checkbox' || kind === 'file') && labelVisible(el)), enabled: isEnabled(el), sensitive, hasValue, selectedText, options, contexts, multiple,
    interaction: interactionOf(el),
  };
  // Parmak izi kimliği taşır; etkileşim durumu (ör. pencere açılıp kapanması) kimliği değiştirmez.
  item.fp = JSON.stringify([kind, item.role, name, label, contexts]);
  return item;
}
function candidates() {
  // Bir kontrole bağlı açılır liste ayrı aday değildir (açıkken etiket çakışması üretmesin).
  const unrelatedFieldset = (el) => el.tagName === 'FIELDSET' && !el.querySelector('input[type=radio]');
  const owned = (el) => unrelatedFieldset(el) || el.getAttribute('role') === 'listbox' && el.id && document.querySelector(`[aria-controls="${CSS.escape(el.id)}"],[aria-owns="${CSS.escape(el.id)}"]`);
  return Array.from(document.querySelectorAll(SELECTOR)).filter(el => !el.closest('[data-agentask-ui]') && !owned(el));
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

# Eylem anı kontrolü: sürücü hedefi görünür alana kaydırdıktan sonra aynı etkileşim kuralını uygular.
INTERACTION_AT = "(el) => {" + DESCRIBE + " return interactionOf(el); }"
