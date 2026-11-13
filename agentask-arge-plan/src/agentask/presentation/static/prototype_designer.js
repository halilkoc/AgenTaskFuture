/*
 * Akış Tasarımcısı — PROTOTİP.
 * Hiçbir API'ye, gerçek tarayıcıya, modele, MongoDB'ye veya yürütücüye bağlanmaz.
 * Bütün durum bu sayfanın belleğindedir; sayfa yenilenince sıfırlanır.
 * Kataloga ait sözleşme veya backend davranışı değildir.
 */
"use strict";
(function () {
  // ===================================================================
  // Yardımcılar
  // ===================================================================
  const SVG_NS = "http://www.w3.org/2000/svg";
  const byId = (id) => document.getElementById(id);

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    let value;
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === undefined || v === null || v === false) continue;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k === "value") value = v;
        else if (k === "dataset") Object.assign(el.dataset, v);
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else if (v === true) el.setAttribute(k, "");
        else el.setAttribute(k, String(v));
      }
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    if (value !== undefined) el.value = value;
    return el;
  }

  function icon(name, extra) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "pd-ico" + (extra ? " " + extra : ""));
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", "#i-" + name);
    svg.append(use);
    return svg;
  }

  let seq = 0;
  const uid = (p) => `${p}${++seq}`;
  const lower = (s) => String(s || "").toLocaleLowerCase("tr-TR");
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clone = (o) => JSON.parse(JSON.stringify(o));

  function slug(s) {
    const map = { ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u" };
    return lower(s).replace(/[çğıöşü]/g, (c) => map[c]).replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  }

  function announce(msg) {
    const live = byId("pd-live");
    live.textContent = "";
    setTimeout(() => { live.textContent = msg; }, 30);
  }

  function toast(msg, opts = {}) {
    const box = byId("pd-toasts");
    const kids = [h("p", { text: msg })];
    if (opts.action) {
      kids.push(h("button", {
        type: "button", class: "pd-btn pd-btn--ghost",
        onclick: () => { opts.action.run(); t.remove(); },
      }, opts.action.label));
    }
    const t = h("div", { class: "pd-toast" + (opts.error ? " pd-toast--error" : "") }, kids);
    box.append(t);
    setTimeout(() => t.remove(), opts.action ? 8000 : 4500);
  }

  // ===================================================================
  // Temsili uygulama (Prototip). Gerçek Pega ekranı değildir.
  // ===================================================================
  const SCREENS = {
    musteri: {
      title: "Müşteri Bilgileri",
      sections: [
        { name: "Müşteri", owner: "Müşterinin", fields: [
          { key: "m_no", label: "Müşteri No", noun: "müşteri numarası", kind: "text", maxLength: 10, digits: true },
          { key: "m_ad", label: "Ad Soyad", noun: "adı soyadı", kind: "text", maxLength: 60 },
          { key: "m_tip", label: "Müşteri Tipi", noun: "müşteri tipi", kind: "select", options: ["Bireysel", "Kurumsal"] },
        ] },
        { name: "Kefil", owner: "Kefilin", fields: [
          { key: "k_no", label: "Müşteri No", noun: "müşteri numarası", kind: "text", maxLength: 10, digits: true },
          { key: "k_ad", label: "Ad Soyad", noun: "adı soyadı", kind: "readonly" },
        ] },
      ],
      buttons: [
        { key: "b_devam", label: "Devam", goes: "teminat" },
        { key: "b_kaydet_m", label: "Kaydet", goes: null },
      ],
    },
    teminat: {
      title: "Teminat",
      sections: [
        { name: "Teminat", owner: "Teminatın", fields: [
          { key: "t_tur", label: "Teminat Türü", noun: "türü", kind: "select", options: ["İpotek", "Kefalet", "Mevduat rehni"] },
          { key: "t_tutar", label: "Teminat Tutarı", noun: "tutarı", kind: "amount", maxLength: 15 },
          { key: "t_para", label: "Para Birimi", noun: "para birimi", kind: "select", options: ["TL", "USD", "EUR"] },
          { key: "t_aciklama", label: "Açıklama", noun: "açıklaması", kind: "textarea", maxLength: 200 },
        ] },
      ],
      buttons: [
        { key: "b_geri", label: "Geri", goes: "musteri" },
        { key: "b_kaydet_t", label: "Kaydet", goes: null },
      ],
    },
  };
  const KIND_TEXT = {
    textbox: "Metin alanı", combobox: "Özel açılır liste", button: "Düğme", tab: "Sekme", table: "Tablo", link: "Bağlantı", checkbox: "Onay kutusu", radio_group: "Seçenek grubu", file: "Dosya alanı",
    text: "Metin alanı", amount: "Tutar alanı", select: "Seçim kutusu",
    textarea: "Uzun metin alanı", readonly: "Salt okunur alan",
  };
  const screenTitle = (k) => (SCREENS[k] ? SCREENS[k].title : "bilinmeyen");

  function allFields() {
    const out = [];
    for (const [screen, s] of Object.entries(SCREENS)) {
      for (const sec of s.sections) for (const f of sec.fields) out.push({ ...f, screen, section: sec.name, owner: sec.owner });
    }
    return out;
  }
  function allButtons() {
    const out = [];
    for (const [screen, s] of Object.entries(SCREENS)) for (const b of s.buttons) out.push({ ...b, screen });
    return out;
  }

  // ===================================================================
  // Bileşen kataloğu (soldaki liste)
  // ===================================================================
  const COMPONENTS = [
    { type: "fill", name: "Alan doldur", desc: "Bir alana değer yazar.", icon: "fill", supported: true },
    { type: "goto", name: "Ekrana geç", desc: "Düğmeye basıp yeni ekranın açıldığını doğrular.", icon: "goto", supported: true },
    { type: "back", name: "Ana pencereye dön", desc: "Beklenen yeni pencereden çıkar ve ana ekranı doğrular; canlı oturum gerekir.", icon: "goto", supported: true, realOnly: true },
    { type: "call", name: "Akış çağır", desc: "Kaydettiğiniz bir bileşeni çalıştırır.", icon: "call", supported: true },
    { type: "choose", name: "Seçim yap", desc: "Açılır listeden seçenek seçer; canlı oturum gerekir.", icon: "select", supported: true, realOnly: true },
    { type: "check", name: "İşaretle / kaldır", desc: "Onay kutusunu istenen duruma getirir; canlı oturum gerekir.", icon: "select", supported: true, realOnly: true },
    { type: "multi", name: "Çoklu seçim", desc: "Listede tam olarak istenen seçenekleri bırakır; canlı oturum gerekir.", icon: "select", supported: true, realOnly: true },
    { type: "upload", name: "Dosya yükle", desc: "Yetkili depodaki dosyayı alana yükler; canlı oturum gerekir.", icon: "fill", supported: true, realOnly: true },
    { type: "read", name: "Bilgi oku", desc: "Ekrandan değer okur; canlı tarayıcı oturumu gerekir.", icon: "read", supported: true, realOnly: true },
    { type: "action", name: "Onaylı işlem", desc: "Kaydet/gönder gibi veri değiştiren, kurumca onaylı işlem; canlı oturum gerekir.", icon: "press", supported: true, realOnly: true },
    { type: "find", name: "Kayıt bul", desc: "Tabloda iş anahtarıyla kaydı bulur; canlı oturum gerekir.", icon: "find", supported: true, realOnly: true },
  ];
  const TYPE_META = {
    fill: { name: "Alan doldur", icon: "fill" },
    goto: { name: "Ekrana geç", icon: "goto" },
    back: { name: "Ana pencereye dön", icon: "goto" },
    call: { name: "Akış çağır", icon: "call" },
    read: { name: "Bilgi oku", icon: "read" },
    choose: { name: "Seçim yap", icon: "select" },
    check: { name: "İşaretle / kaldır", icon: "select" },
    multi: { name: "Çoklu seçim", icon: "select" },
    upload: { name: "Dosya yükle", icon: "fill" },
    find: { name: "Kayıt bul", icon: "find" },
    action: { name: "Onaylı işlem", icon: "press" },
  };

  // ===================================================================
  // Durum (yalnız bellekte)
  // ===================================================================
  // Uygulama listesi sunucudan (AUTOMATION_APPLICATIONS_JSON; yalnız id ve ad). İşlem Asistanı ile aynı kaynak.
  // Prototip seçilen uygulamaya bağlanmaz; ekranlar temsilidir.
  const APPS = (() => {
    try { return JSON.parse(byId("pd-apps").textContent || "[]"); } catch (_) { return []; }
  })();
  const appName = (id) => (APPS.find((a) => a.id === id) || {}).name || "";
  function newFlow(name = "") {
    return {
      id: uid("f"), name, applicationId: APPS.length === 1 ? APPS[0].id : "",
      startScreen: "musteri", steps: [], lastTrial: null, published: [],
    };
  }
  const state = {
    view: "list", // "list" (Akışlar) | "editor"
    flows: [], // sayfada saklanan akışlar (yalnız bellek)
    editing: null, // { flow: çalışma kopyası, baseline, isNew }
    components: [],
    selectedStepId: null,
    checked: new Set(),
    lastAsk: {},
    changingTarget: new Set(), // yalnız arayüz durumu; imzaya girmez
    source: "mock", // alan seçme kaynağı: "mock" (temsili ekranlar) | "real" (gerçek tarayıcı oturumu)
    openDetails: new Set(),
  };
  const flow = () => state.editing.flow;
  // Değişiklik takibi yalnız kullanıcının düzenlediği içerik üzerinden; deneme sonucu değişiklik sayılmaz.
  const editable = (f) => JSON.stringify({ name: f.name, app: f.applicationId, start: f.startScreen, steps: f.steps });
  const isDirty = () => !!state.editing && editable(state.editing.flow) !== state.editing.baseline;
  const findStep = (id) => flow().steps.find((s) => s.id === id);
  const findComp = (id) => state.components.find((c) => c.id === id);

  function newBinding() {
    return { source: null, fixedValue: "", question: "", questionSuggested: true, previousRef: "" };
  }
  function newStep(type) {
    const base = { id: uid("s"), type, note: "" };
    if (type === "fill") {
      return { ...base, target: null, name: "", description: "", suggested: { name: false, description: false }, binding: newBinding(), successCheck: "auto" };
    }
    if (type === "read") return { ...base, target: null, name: "", description: "", suggested: { name: false, description: false } };
    if (type === "find") {
      return { ...base, target: null, name: "", description: "", suggested: { name: false, description: false }, binding: newBinding(), navigation: "none", nextLabel: "Sonraki", endText: "" };
    }
    if (type === "choose") {
      return { ...base, target: null, name: "", description: "", suggested: { name: false, description: false }, binding: newBinding(),
        choiceValue: null, effect: "", successCheck: "auto", resultText: "", askDynamic: false, askChoices: null, changesScreen: false, expectName: "", autocomplete: false, searchText: "" };
    }
    if (type === "multi") return { ...base, target: null, name: "", description: "", suggested: { name: false, description: false }, source: "fixed", fixedSet: [], question: "", askChoices: null, effect: "", successCheck: "auto", resultText: "" };
    if (type === "upload") return { ...base, target: null, name: "", description: "", suggested: { name: false, description: false }, question: "", fileTypes: [], resultText: "" };
    if (type === "check") return { ...base, target: null, name: "", description: "", suggested: { name: false, description: false }, checked: null, effect: "", successCheck: "auto", resultText: "" };
    if (type === "action") return { ...base, actionId: "", bindings: {} };
    if (type === "goto") return { ...base, button: null, expectScreen: "", expectName: "", confirmNoData: false, newWindow: false, windowOrigin: "" };
    if (type === "back") return { ...base, closeWindow: true, expectName: "" };
    return { ...base, componentId: "", bindings: {} };
  }

  // Temsili model önerisi: kurallı; gözlemden bilinemeyen iş etkisini yazmaz.
  // Bölüm bağlamını içeren ad ve soru: "Kefilin müşteri numarası nedir?". Temsili öneridir; kullanıcı değiştirebilir.
  const capFirst = (t) => t.charAt(0).toLocaleUpperCase("tr-TR") + t.slice(1);
  function suggestFor(field) {
    const phrase = field.owner && field.noun ? `${field.owner} ${field.noun}` : `${field.section} ${lower(field.label)}`;
    const name = capFirst(phrase);
    const limits = [];
    if (field.digits) limits.push("yalnız rakam");
    if (field.maxLength) limits.push(`en fazla ${field.maxLength} karakter`);
    const desc = `${screenTitle(field.screen)} ekranındaki ${field.section} bölümünde bulunan “${field.label}” ` +
      `${lower(KIND_TEXT[field.kind])}.` + (limits.length ? ` Ekranda gözlenen sınır: ${limits.join(", ")}.` : "");
    return { name, description: desc, question: `${name} nedir?` };
  }

  // Gerçek oturumda gözlenen kontrol → anlamsal hedef. Gözlenmeyen bilgi uydurulmaz (null bırakılır).
  function realTargetFrom(c) {
    const ctx = (c.contexts || []).filter((x) => x.kind !== "table_row" && x.name);
    const dialog = (ctx.find((x) => x.kind === "dialog") || {}).name || null;
    return {
      source: "real", kind: c.kind, label: c.label || c.accessible_name || null,
      section: ctx.length ? ctx[0].name : null, dialog, frames: c.frame_titles || [],
      sensitive: !!c.sensitive, interaction: c.interaction || "open", tag: c.tag || "",
      rowKey: ((c.contexts || []).find((x) => x.kind === "table_row" && x.key) || {}).key || null,
      screen: null, fieldKey: null, maxLength: null, digits: false, check: null,
    };
  }
  function realSpec(t) {
    const spec = { kind: t.kind, labels: [t.label] };
    if (t.section) spec.region = t.section;
    if (t.frames && t.frames.length) spec.frame_title = t.frames[t.frames.length - 1];
    if (t.rowKey) spec.row_key = t.rowKey;  // tasarımda bulunduğu satırla tekil çözülür
    return spec;
  }
  function suggestForReal(t) {
    const label = t.label || "etiketsiz alan";
    const name = capFirst(t.section ? `${t.section} ${lower(label)}` : label);
    const notes = [];
    if (t.frames.length) notes.push(`Çerçeve: ${t.frames.join(" › ")}.`);
    if (t.dialog) notes.push(`Pencere: ${t.dialog}.`);
    if (!t.section) notes.push("Bölüm bilgisi gözlenmedi.");
    notes.push("Ekran tanımı gerçek yürütmede ayrıca doğrulanır.");
    return {
      name,
      description: `Gerçek oturumda seçildi: ${t.section ? `${t.section} bölümündeki ` : ""}“${label}” ${lower(KIND_TEXT[t.kind] || t.kind)}. ${notes.join(" ")}`,
      question: t.section ? `${t.section} bölümündeki “${label}” nedir?` : `“${label}” nedir?`,
    };
  }
  function applyRealTarget(step, control) {
    step.target = realTargetFrom(control);
    const sug = suggestForReal(step.target);
    if (!step.name.trim() || step.suggested.name) { step.name = sug.name; step.suggested.name = true; }
    if (!step.description.trim() || step.suggested.description) { step.description = sug.description; step.suggested.description = true; }
    if (!step.binding.question.trim() || step.binding.questionSuggested) { step.binding.question = sug.question; step.binding.questionSuggested = true; }
  }

  function applyTarget(step, field) {
    step.target = {
      screen: field.screen, section: field.section, label: field.label, fieldKey: field.key,
      kind: field.kind, maxLength: field.maxLength || null, digits: !!field.digits,
      owner: field.owner || "", noun: field.noun || "",
    };
    const sug = suggestFor(field);
    if (!step.name.trim() || step.suggested.name) { step.name = sug.name; step.suggested.name = true; }
    if (!step.description.trim() || step.suggested.description) { step.description = sug.description; step.suggested.description = true; }
    if (!step.binding.question.trim() || step.binding.questionSuggested) {
      step.binding.question = sug.question; step.binding.questionSuggested = true;
    }
  }

  // ===================================================================
  // Değer kaynakları ve çıktılar
  // ===================================================================
  function outputsOf(step, index) {
    const out = [];
    if (step.type === "fill" && step.target) {
      out.push({ ref: step.id, label: `${index + 1}. adım: ${step.name || step.target.label}`, meta: step.target });
    }
    if (step.type === "read" && step.target && step.target.source === "real") {
      out.push({ ref: step.id, label: `${index + 1}. adım (okunan): ${step.name || step.target.label}`, meta: step.target, read: true });
    }
    if (step.type === "call" && step.published) {
      for (const o of step.published.outputs) out.push({ ref: `${step.id}/${o.name}`, label: `${index + 1}. adım (${step.published.title}): ${o.title}`, meta: { label: o.title }, read: true });
      return out;
    }
    if (step.type === "call") {
      const c = findComp(step.componentId);
      if (c) for (const inp of c.inputs) out.push({ ref: `${step.id}/${inp.key}`, label: `${index + 1}. adım (${c.name}): ${inp.name}`, meta: inp });
    }
    return out;
  }
  function outputsBefore(steps, index) {
    return steps.slice(0, index).flatMap((s, i) => outputsOf(s, i));
  }
  function refLabel(steps, ref) {
    for (let i = 0; i < steps.length; i++) {
      const o = outputsOf(steps[i], i).find((x) => x.ref === ref);
      if (o) return o.label;
    }
    return "";
  }

  function valueProblem(meta, v) {
    if (!meta) return "";
    if (meta.digits && !/^\d+$/.test(v)) return `“${meta.label}” alanı yalnız rakam kabul ediyor.`;
    if (meta.kind === "amount" && !/^\d+([.,]\d{1,2})?$/.test(v)) return "Tutar bir sayı olmalı (ör. 15000 veya 15000,50).";
    if (meta.maxLength && v.length > meta.maxLength) return `En fazla ${meta.maxLength} karakter yazılabilir; şu an ${v.length}.`;
    return "";
  }

  function bindingIssues(b, meta, outputs, steps, prefix, add) {
    if (!b.source) { add(prefix + "source", "Değerin nereden geleceğini seçin.", "missing"); return; }
    if (b.source === "fixed") {
      if (!b.fixedValue.trim()) add(prefix + "fixed", "Her seferinde yazılacak değeri girin.", "missing");
      else { const p = valueProblem(meta, b.fixedValue.trim()); if (p) add(prefix + "fixed", p, "error"); }
    } else if (b.source === "ask") {
      if (!b.question.trim()) add(prefix + "question", "Çalıştırırken kişiye sorulacak soruyu yazın.", "missing");
    } else if (b.source === "previous") {
      if (!b.previousRef) add(prefix + "previous", "Hangi önceki adımın değerini kullanacağınızı seçin.", "missing");
      else if (!outputs.some((o) => o.ref === b.previousRef)) {
        const exists = steps.some((s, i) => outputsOf(s, i).some((o) => o.ref === b.previousRef));
        add(prefix + "previous", exists
          ? "Seçtiğiniz kaynak adım artık bu adımdan sonra geliyor. Adımları yeniden sıralayın veya başka bir kaynak seçin."
          : "Seçtiğiniz kaynak adım silinmiş. Başka bir kaynak seçin.", "error");
      }
    }
  }

  // ===================================================================
  // Doğrulama: her adımın eksikleri ve akış ekran yolu
  // ===================================================================
  function targetIssues(field, screen, add, key) {
    if (field.kind === "select") add(key, "Bu bir seçim kutusu; “Alan doldur” metin alanlarında çalışır. Metin, tutar veya uzun metin alanı seçin.", "error");
    else if (field.kind === "readonly") add(key, "Bu alan salt okunur; buraya değer yazılamaz.", "error");
    if (field.screen !== screen) {
      add(key, `Bu alan “${screenTitle(field.screen)}” ekranında; akış bu adıma geldiğinde “${screenTitle(screen)}” ekranında olacak. Önüne bir “Ekrana geç” adımı ekleyin.`, "error");
    }
  }

  // Gerçek oturumdan seçilen alan: ekran bağlamı burada uydurulmaz (Katalog Tasarımcısı ekran tanımıyla doğrular).
  function realTargetIssues(t, add) {
    if (!t.label) add("target", "Alanın etiketi okunamadı; anlamsal olarak tanımlanamaz. Etiketi olan bir alan seçin.", "error");
    if (t.sensitive) add("target", "Hassas bir alan (ör. parola) seçildi; buraya değer yazılmaz.", "error");
    if (t.tag && t.kind === "textbox" && !["input", "textarea"].includes(t.tag)) add("target", "Bu biçimlendirilebilir bir metin kutusu; desteklenmiyor. Rastgele işlem yapılmaz; standart bir alan seçin.", "error");
    if (t.kind === "select" || t.kind === "combobox") add("target", "Bu bir seçim alanı; bunun için “Seçim yap” bileşenini kullanın.", "error");
    else if (t.kind !== "textbox") add("target", `Bu bir ${lower(KIND_TEXT[t.kind] || t.kind)}; “Alan doldur” yalnız metin alanlarında çalışır.`, "error");
    const c = t.check;
    if (!c) add("target", "Alanın ekranda tek olduğu henüz doğrulanmadı; “Alanı yeniden bul” deyin.");
    else if (c.outcome === "ambiguous") add("target", `Ekranda bu tanıma uyan ${c.count} alan var; yanlış alana yazmamak için durduruldu. Bölümü belli olan bir alan seçin.`, "error");
    else if (c.outcome !== "resolved" && c.outcome !== "saved") add("target", c.reason === "blocked" || c.reason === "multiple_active_dialogs" ? `Müdahale gerekiyor: ${c.explanation}` : `Alan şu an doğrulanamadı: ${c.explanation}`, c.reason === "blocked" ? "error" : "missing");
  }

  // Gerçek oturumdan okunacak alan: hassas alan okunup başka alana aktarılmaz; tekillik doğrulanmalı.
  function realReadIssues(t, add) {
    if (!t.label) add("target", "Alanın etiketi okunamadı; etiketi olan bir alan seçin.", "error");
    if (t.sensitive) add("target", "Hassas bir alan (ör. parola) okunup başka bir alana aktarılmaz.", "error");
    if (!["textbox", "select", "combobox"].includes(t.kind)) add("target", `Bu bir ${lower(KIND_TEXT[t.kind] || t.kind)}; “Bilgi oku” metin alanı veya liste değerini okur.`, "error");
    const c = t.check;
    if (!c) add("target", "Alanın ekranda tek olduğu henüz doğrulanmadı; “Alanı yeniden bul” deyin.");
    else if (c.outcome === "ambiguous") add("target", `Ekranda bu tanıma uyan ${c.count} alan var; yanlış alandan okumamak için durduruldu.`, "error");
    else if (c.outcome !== "resolved" && c.outcome !== "saved") add("target", `Alan şu an doğrulanamadı: ${c.explanation}`, "missing");
  }
  const dateValid = (text, format) => {
    const v = (text || "").trim();
    const parts = { "DD.MM.YYYY": /^(\d{2})\.(\d{2})\.(\d{4})$/, "DD/MM/YYYY": /^(\d{2})\/(\d{2})\/(\d{4})$/, "MM/DD/YYYY": /^(\d{2})\/(\d{2})\/(\d{4})$/, "YYYY-MM-DD": /^(\d{4})-(\d{2})-(\d{2})$/ }[format];
    const m = parts && v.match(parts);
    if (!m) return false;
    const [y, mo, d] = format === "YYYY-MM-DD" ? [m[1], m[2], m[3]] : format === "MM/DD/YYYY" ? [m[3], m[1], m[2]] : [m[3], m[2], m[1]];
    const dt = new Date(Date.UTC(+y, +mo - 1, +d));
    return dt.getUTCFullYear() === +y && dt.getUTCMonth() === +mo - 1 && dt.getUTCDate() === +d;
  };
  const choiceKinds = (s) => (s.autocomplete ? ["textbox", "combobox"] : ["select", "combobox", "radio_group"]);
  // Seçim alanı: tür, tekillik ve seçenek durumu. Desteklenmeyen tür açıkça söylenir; rastgele tıklanmaz.
  function realChooseIssues(s, add) {
    const t = s.target;
    if (!t.label) add("target", "Alanın etiketi okunamadı; etiketi olan bir seçim alanı seçin.", "error");
    if (t.sensitive) add("target", "Hassas bir alan seçildi; seçim adımı kurulamaz.", "error");
    if (!choiceKinds(s).includes(t.kind)) add("target", `Bu bir ${lower(KIND_TEXT[t.kind] || t.kind)}; ${s.autocomplete ? "yazınca öneri açan alan yalnız metin girişinde çalışır" : "“Seçim yap” yalnız açılır liste, seçim kutusu veya seçenek grubunda çalışır"}.`, "error");
    const c = t.check;
    if (!c) add("target", "Alanın ekranda tek olduğu henüz doğrulanmadı; “Alanı yeniden bul” deyin.");
    else if (c.outcome === "ambiguous") add("target", `Ekranda bu tanıma uyan ${c.count} alan var; yanlış alanda seçim yapmamak için durduruldu. Bölümü belli olan bir alan seçin.`, "error");
    else if (c.outcome !== "resolved" && c.outcome !== "saved") add("target", c.reason === "blocked" || c.reason === "multiple_active_dialogs" ? `Müdahale gerekiyor: ${c.explanation}` : `Alan şu an doğrulanamadı: ${c.explanation}`, c.reason === "blocked" ? "error" : "missing");
    const info = choiceInfo(s);
    if (info && info.status === "unsupported") add("target", info.message, "error");
  }

  function checkTargetIssues(s, add) {
    const t = s.target;
    if (!t.label) add("target", "Kutunun etiketi okunamadı; etiketi olan bir onay kutusu seçin.", "error");
    if (t.sensitive) add("target", "Hassas bir alan seçildi; bu adım kurulamaz.", "error");
    if (t.kind !== "checkbox") add("target", `Bu bir ${lower(KIND_TEXT[t.kind] || t.kind)}; “İşaretle / kaldır” yalnız onay kutusunda çalışır.`, "error");
    const c = t.check;
    if (!c) add("target", "Kutunun ekranda tek olduğu henüz doğrulanmadı; “Alanı yeniden bul” deyin.");
    else if (c.outcome === "ambiguous") add("target", `Ekranda bu tanıma uyan ${c.count} kutu var; yanlış kutuyu değiştirmemek için durduruldu. Bölümü belli olan bir kutu seçin.`, "error");
    else if (c.outcome !== "resolved" && c.outcome !== "saved") add("target", `Kutu şu an doğrulanamadı: ${c.explanation}`, c.reason === "blocked" ? "error" : "missing");
  }

  function realButtonIssues(t, add) {
    if (!t.label) add("button", "Düğmenin adı okunamadı; adı olan bir düğme seçin.", "error");
    if (!["button", "tab", "link"].includes(t.kind)) add("button", "Geçiş için bir düğme, sekme veya bağlantı seçin.", "error");
    const c = t.check;
    if (!c) add("button", "Düğmenin ekranda tek olduğu henüz doğrulanmadı; “Düğmeyi yeniden bul” deyin.");
    else if (c.outcome === "ambiguous") add("button", `Ekranda bu tanıma uyan ${c.count} düğme var; yanlış düğmeye basmamak için durduruldu.`, "error");
    else if (c.outcome !== "resolved" && c.outcome !== "saved") add("button", `Düğme şu an doğrulanamadı: ${c.explanation}`, "missing");
  }
  const isRealGoto = (s) => s.type === "goto" && s.button && s.button.source === "real";

  // Bileşenin içindeki adımları verilen ekrandan başlayarak yürütür; iç eksikleri döndürür.
  function walkInner(steps, screen) {
    const problems = [];
    steps.forEach((s, i) => {
      if (s.type === "fill" && s.target && s.target.source !== "real" && s.target.screen !== screen) {
        problems.push(`Bileşenin ${i + 1}. adımı “${screenTitle(s.target.screen)}” ekranında çalışıyor; akış bu noktada “${screenTitle(screen)}” ekranında.`);
      }
      if (s.type === "goto" && s.button) {
        if (s.button.screen !== screen) problems.push(`Bileşenin ${i + 1}. adımındaki düğme “${screenTitle(s.button.screen)}” ekranında; akış bu noktada “${screenTitle(screen)}” ekranında.`);
        screen = s.expectScreen || screen;
      }
    });
    return { problems, screen };
  }

  function analyze(f) {
    const result = new Map();
    let screen = f.startScreen;
    f.steps.forEach((s, i) => {
      const issues = [];
      const add = (field, msg, level = "missing") => issues.push({ field, msg, level });
      const screenBefore = screen;
      const outputs = outputsBefore(f.steps, i);
      if (s.type === "fill") {
        if (!s.target) add("target", "Değerin yazılacağı alanı seçin: önerilenlerden birini seçin veya “Ekrandan kendim seçeyim” deyin.");
        else if (s.target.source === "real") realTargetIssues(s.target, add);
        else targetIssues(s.target, screen, add, "target");
        bindingIssues(s.binding, s.target, outputs, f.steps, "", add);
        if (s.isDate && s.binding.source === "fixed" && s.binding.fixedValue.trim() && !dateValid(s.binding.fixedValue, s.dateFormat)) add("fixed", `Geçerli bir tarih yazın (${s.dateFormat}).`, "error");
        if (s.target && s.target.source === "real" && s.binding.source === "previous" && s.binding.previousRef
          && !outputs.some((o) => o.ref === s.binding.previousRef && o.read)) {
          add("previous", "Gerçek oturumda önceki adım çıktısı yalnız önceki bir “Bilgi oku” adımının gerçek okuma çıktısı olabilir.", "error");
        }
      } else if (s.type === "read") {
        if (!s.target) add("target", "Okunacak alanı gerçek oturumdan seçin.");
        else if (s.target.source !== "real") add("target", "“Bilgi oku” yalnız gerçek oturumda çalışır; temsili çıktı üretilmez.", "error");
        else realReadIssues(s.target, add);
      } else if (s.type === "find") {
        if (!s.target) add("target", "Kaydın aranacağı tabloyu gerçek oturumdan seçin.");
        else if (s.target.kind !== "table") add("target", "“Kayıt bul” yalnız tabloda çalışır.", "error");
        bindingIssues(s.binding, null, outputs, f.steps, "", add);
        if (s.binding.source === "previous" && s.binding.previousRef && !outputs.some((o) => o.ref === s.binding.previousRef && o.read)) add("previous", "Önceki çıktı yalnız “Bilgi oku” adımından gelebilir.", "error");
        if (s.navigation === "paged" && !s.nextLabel.trim()) add("nav", "Sonraki sayfa düğmesinin adını yazın.");
      } else if (s.type === "choose") {
        if (!s.target) add("target", "Seçim alanını gerçek oturumdan seçin.");
        else if (s.target.source !== "real") add("target", "“Seçim yap” yalnız gerçek oturumda çalışır.", "error");
        else realChooseIssues(s, add);
        bindingIssues(s.binding, null, outputs, f.steps, "", add);
        if (s.binding.source === "previous" && s.binding.previousRef && !outputs.some((o) => o.ref === s.binding.previousRef && o.read)) {
          add("previous", "Önceki adım çıktısı yalnız önceki bir “Bilgi oku” adımının gerçek okuma çıktısı olabilir.", "error");
        }
        if (s.binding.source === "ask" && !s.askDynamic && !askList(s)) add("question", "Geçerli seçenekleri okuyun veya “Seçenekler kayda göre değişebilir” kutusunu işaretleyin.");
        if (!s.effect) add("effect", "Bu seçimin ne yaptığını belirtin. Sistem iş etkisini ekrana bakarak bilemez.");
        if (/[{}]/.test(s.resultText)) add("result", "Durum mesajı { } içeremez.", "error");
        if (s.changesScreen && !s.expectName.trim()) add("expect", "Seçimden sonra açılacak ekranın adını yazın.");
      } else if (s.type === "multi") {
        if (!s.target) add("target", "Çoklu seçim alanını gerçek oturumdan seçin.");
        else if (s.target.source !== "real") add("target", "“Çoklu seçim” yalnız gerçek oturumda çalışır.", "error");
        else realChooseIssues(s, add);
        if (s.source === "fixed" && !s.fixedSet.length) add("set", "En az bir seçenek işaretleyin.");
        if (s.source === "ask" && !s.question.trim()) add("set", "Kullanıcıya sorulacak metni yazın.");
        if (!s.effect) add("effect", "Bu seçimin ne yaptığını belirtin. Sistem iş etkisini ekrana bakarak bilemez.");
      } else if (s.type === "upload") {
        if (!s.target) add("target", "Dosya alanını gerçek oturumdan seçin.");
        else if (s.target.source !== "real") add("target", "“Dosya yükle” yalnız gerçek oturumda çalışır.", "error");
        else if (s.target.kind !== "file") add("target", `Bu bir ${lower(KIND_TEXT[s.target.kind] || s.target.kind)}; “Dosya yükle” yalnız dosya alanında çalışır.`, "error");
        else if (!s.target.label) add("target", "Alanın etiketi okunamadı.", "error");
        if (!s.question.trim()) add("question", "Kullanıcıya hangi dosyanın sorulacağını yazın.");
        if (!s.resultText.trim()) add("result", "Yüklemenin başarılı olduğunu gösteren ekran mesajını yazın; kanıt olmadan yükleme başarılı sayılmaz.");
      } else if (s.type === "back") {
        const before = f.steps.slice(0, i);
        const opened = before.filter((x) => x.type === "goto" && x.newWindow).length - before.filter((x) => x.type === "back").length;
        if (opened !== 1) add("back", "Bu adımdan önce yeni pencere açan bir “Ekrana geç” adımı olmalı.", "error");
      } else if (s.type === "check") {
        if (!s.target) add("target", "Onay kutusunu gerçek oturumdan seçin.");
        else if (s.target.source !== "real") add("target", "“İşaretle / kaldır” yalnız gerçek oturumda çalışır.", "error");
        else checkTargetIssues(s, add);
        if (s.checked === null) add("wanted", "Kutunun son durumunu seçin.");
        if (!s.effect) add("effect", "Bu değişikliğin ne yaptığını belirtin. Sistem iş etkisini ekrana bakarak bilemez.");
        if (/[{}]/.test(s.resultText)) add("result", "Durum mesajı { } içeremez.", "error");
      } else if (s.type === "action") {
        const act = (real.actions || []).find((x) => x.action_id === s.actionId);
        if (!s.actionId) add("action", "Çalıştırılacak onaylı işlemi seçin.");
        else if (!act) add("action", "Bu onaylı işlem katalogda bulunamadı.", "error");
        else {
          for (const prm of act.params) {
            const b = s.bindings[prm.name] || newBinding();
            bindingIssues(b, { label: prm.title, maxLength: prm.max_length }, outputs, f.steps, `input:${prm.name}:`, add);
          }
        }
      } else if (isRealGoto(s)) {
        realButtonIssues(s.button, add);
        if (!s.expectName.trim()) add("expect", "Düğmeye basınca açılacak ekranın adını yazın.");
        if (!s.confirmNoData) add("confirm", "Sistem düğmenin iş etkisini ekrana bakarak bilemez. Yalnız ekran değiştirdiğinden eminseniz işaretleyin; veri kaydeden düğmeler için “Onaylı işlem” kullanın.");
      } else if (s.type === "goto") {
        if (!s.button) add("button", "Basılacak düğmeyi seçin: “Ekrandan düğme seç”.");
        else if (s.button.screen !== screen) {
          add("button", `Bu düğme “${screenTitle(s.button.screen)}” ekranında; akış bu adıma geldiğinde “${screenTitle(screen)}” ekranında olacak.`, "error");
        }
        if (!s.expectScreen) add("expect", "Düğmeye basınca hangi ekranın açılması gerektiğini seçin.");
        else if (s.button && s.expectScreen === s.button.screen) add("expect", "Beklenen ekran, düğmenin bulunduğu ekranla aynı olamaz.", "error");
        if (!s.confirmNoData) {
          add("confirm", "Sistem düğmenin iş etkisini ekrana bakarak bilemez. Yalnız ekran değiştirdiğinden eminseniz işaretleyin; emin değilseniz bu adımı kullanmayın.");
        }
        screen = s.expectScreen || screen;
      } else if (s.type === "call" && (state.source === "real" || s.published)) {
        if (!s.published) add("component", "Çağrılacak yayımlanmış bileşeni seçin.");
        else for (const inp of s.published.inputs) {
          const b = s.bindings[inp.name] || newBinding();
          bindingIssues(b, { label: inp.title, maxLength: inp.max_length }, outputs, f.steps, `input:${inp.name}:`, add);
        }
      } else if (s.type === "call") {
        const c = findComp(s.componentId);
        if (!c) add("component", "Çağrılacak bileşeni seçin.");
        else if (c.applicationId !== f.applicationId) {
          add("component", "Bu bileşen başka bir uygulamaya ait; bu akışta kullanılamaz.", "error");
        } else {
          const walked = walkInner(c.steps, screen);
          walked.problems.forEach((p) => add("component", p, "error"));
          screen = walked.screen;
          for (const inp of c.inputs) {
            bindingIssues(s.bindings[inp.key] || newBinding(), inp, outputs, f.steps, `input:${inp.key}:`, add);
          }
        }
      }
      if (s.inFoundRow && !f.steps.slice(0, i).some((x) => x.type === "find")) add("row", "Satırda çalışmak için önce bir “Kayıt bul” adımı ekleyin.", "error");
      const rowTarget = s.type === "goto" ? s.button : s.target;
      if (rowTarget && rowTarget.rowKey && !s.inFoundRow && ["fill", "read", "choose", "check", "goto"].includes(s.type)) add("row", "Bu kontrol bir tablo satırında. Önce “Kayıt bul” ekleyip “Bulunan kaydın satırında” seçeneğini işaretleyin; satır bağlamsız kaydedilmez.", "error");
      result.set(s.id, { issues, index: i, screenBefore, screenAfter: screen });
    });
    return result;
  }

  function flowIssues(f, analysis) {
    const list = [];
    if (!f.name.trim()) list.push({ msg: "Akışa bir ad verin.", focus: "pd-flow-name" });
    if (!f.applicationId) {
      list.push({ msg: APPS.length ? "Akış için uygulama seçin." : "Yapılandırılmış uygulama yok.", focus: "pd-flow-app", blockTrial: true });
    }
    if (!f.steps.length) list.push({ msg: "Akışa en az bir adım ekleyin." });
    for (const s of f.steps) {
      const a = analysis.get(s.id);
      if (a.issues.length) list.push({ msg: `${a.index + 1}. adımda ${a.issues.length} eksik var.`, stepId: s.id });
    }
    return list;
  }

  // ===================================================================
  // Özetler: adımın ne yapacağını tek cümlede anlatır
  // ===================================================================
  function bindingPhrase(b, steps) {
    if (b.source === "fixed") return b.fixedValue.trim() ? `sabit “${b.fixedValue.trim()}” değerini` : "sabit bir değeri (henüz girilmedi)";
    if (b.source === "ask") return "her çalıştırmada sorulan değeri";
    if (b.source === "previous") {
      const l = refLabel(steps, b.previousRef);
      return l ? `${l.split(":")[0]} değerini` : "önceki bir adımın değerini (henüz seçilmedi)";
    }
    return "bir değeri (kaynağı henüz seçilmedi)";
  }
  // İş etkisi uydurulmaz: onaylı işlem kataloğundaki beyan gösterilir.
  const effectText = (act) => act.effect === "mutating" ? "İş etkisi: veri değiştirir (kayıt yapar); sonuç kanıtla doğrulanır, belirsizse tekrar gönderilmez."
    : "İş etkisi: veri değiştirmez (katalog beyanı).";
  const targetTitle = (t) => `${t.section ? `${t.section} › ` : ""}${t.label || "(etiketsiz)"}${t.source === "real" ? " · gerçek oturum" : ""}`;
  // Kart için kısa özet: ne (başlık) + değer/sonuç (alt satır). Tam cümle düzenleyicide.
  function cardText(s) {
    if (s.type === "fill") {
      const title = s.target ? targetTitle(s.target) : "Alan seçilmedi";
      const b = s.binding;
      const detail = b.source === "fixed" ? (b.fixedValue.trim() ? `Sabit değer: “${b.fixedValue.trim()}”` : "Sabit değer girilmedi")
        : b.source === "ask" ? `Sorulur: ${b.question.trim() || "soru yazılmadı"}`
          : b.source === "previous" ? `Önceki adımdan: ${(refLabel(flow().steps, b.previousRef) || "seçilmedi").split(":")[0]}`
            : "Değer kaynağı seçilmedi";
      return { title, detail };
    }
    if (s.type === "read") {
      return { title: s.target ? targetTitle(s.target) : "Alan seçilmedi", detail: s.name ? `Çıktı: ${s.name}` : "Okunan değer sonraki adımlarda kullanılabilir" };
    }
    if (s.type === "find") {
      const b = s.binding;
      return { title: s.target ? `“${s.target.label}” tablosu` : "Tablo seçilmedi", detail: b.source === "fixed" ? `Anahtar: “${b.fixedValue.trim()}”` : b.source === "ask" ? `Sorulur: ${b.question.trim() || "soru yazılmadı"}` : b.source === "previous" ? "Anahtar önceki adımdan" : "Anahtar kaynağı seçilmedi" };
    }
    if (s.type === "choose") {
      const b = s.binding;
      const detail = b.source === "fixed" ? (b.fixedValue ? `Sabit seçenek: “${b.fixedValue}”` : "Seçenek seçilmedi")
        : b.source === "ask" ? `Sorulur: ${b.question.trim() || "soru yazılmadı"}`
          : b.source === "previous" ? `Önceki adımdan: ${(refLabel(flow().steps, b.previousRef) || "seçilmedi").split(":")[0]}`
            : "Seçenek kaynağı belirlenmedi";
      return { title: s.target ? targetTitle(s.target) : "Alan seçilmedi", detail };
    }
    if (s.type === "multi") return { title: s.target ? targetTitle(s.target) : "Alan seçilmedi", detail: s.source === "ask" ? `Sorulur: ${s.question.trim() || "soru yazılmadı"}` : s.fixedSet.length ? `Küme: ${s.fixedSet.join(", ")}` : "Seçenek seçilmedi" };
    if (s.type === "upload") return { title: s.target ? targetTitle(s.target) : "Alan seçilmedi", detail: `Sorulur: ${s.question.trim() || "soru yazılmadı"}` };
    if (s.type === "back") return { title: "Ana pencereye dön", detail: s.closeWindow ? "Pencereyi sistem kapatır" : "Pencereyi uygulama kapatır" };
    if (s.type === "check") return { title: s.target ? targetTitle(s.target) : "Kutu seçilmedi", detail: s.checked === null ? "Son durum seçilmedi" : s.checked ? "İşaretli olacak" : "İşaretsiz olacak" };
    if (s.type === "action") {
      const act = (real.actions || []).find((x) => x.action_id === s.actionId);
      return { title: act ? act.title : "Onaylı işlem seçilmedi", detail: act ? effectText(act) : "Veri değiştiren işlemler yalnız onaylı katalogdan" };
    }
    if (s.type === "goto") {
      return {
        title: s.button ? `“${s.button.label}” düğmesi` : "Düğme seçilmedi",
        detail: isRealGoto(s) ? (s.expectName.trim() ? `Açılacak ekran: ${s.expectName.trim()}` : "Açılacak ekran yazılmadı")
          : s.expectScreen ? `Açılacak ekran: ${screenTitle(s.expectScreen)}` : "Açılacak ekran seçilmedi",
      };
    }
    if (s.published) return { title: `“${s.published.title}” bileşeni`, detail: `Sürüm ${s.published.revision} · ${s.published.steps} adım` };
    const c = findComp(s.componentId);
    return c ? { title: `“${c.name}” bileşeni`, detail: `${c.steps.length} adım çalışır` } : { title: "Bileşen seçilmedi", detail: "Akış çağır" };
  }

  function summarize(s, steps) {
    if (s.type === "fill") {
      if (!s.target && !s.binding.source) return "Alanı ve değerin kaynağını seçtiğinizde adımın özeti burada görünür.";
      const where = !s.target ? "henüz seçilmemiş bir alana"
        : s.target.section ? `${s.target.section} bölümündeki “${s.target.label || "etiketsiz"}” alanına` : `“${s.target.label || "etiketsiz"}” alanına`;
      return `${where} ${bindingPhrase(s.binding, steps)} yaz.`.replace(/^./, (c) => c.toLocaleUpperCase("tr-TR"));
    }
    if (s.type === "read") {
      if (!s.target) return "Okunacak alanı seçtiğinizde adımın özeti burada görünür.";
      return `${s.target.section ? `${s.target.section} bölümündeki ` : ""}“${s.target.label || "etiketsiz"}” alanının değerini oku (yazmaz, kaydetmez).`;
    }
    if (s.type === "find") {
      if (!s.target) return "Tabloyu seçtiğinizde adımın özeti burada görünür.";
      return `“${s.target.label}” tablosunda ${bindingPhrase(s.binding, steps)} anahtar olarak ara. Kayıt yoksa veya birden fazla ise durur; kaydı açmaz.`;
    }
    if (s.type === "back") return `Yeni pencereden çıkıp ana pencereye dön ve önceki ekranın açık olduğunu doğrula.${s.closeWindow ? " Pencereyi sistem kapatır." : " Pencereyi uygulamanın kapatması beklenir."}`;
    if (s.type === "multi") return s.target ? `“${s.target.label}” listesinde tam olarak ${s.source === "ask" ? "her çalıştırmada seçilen" : "belirtilen"} seçenekleri bırak; üyelerden biri yoksa hiçbir değişiklik yapmaz.` : "Alanı seçtiğinizde adımın özeti burada görünür.";
    if (s.type === "upload") return s.target ? `“${s.target.label}” alanına kullanıcının yüklediği dosyayı gönder ve “${s.resultText.trim() || "…"}” mesajıyla doğrula; sonuç belirsizse yeniden göndermez.` : "Alanı seçtiğinizde adımın özeti burada görünür.";
    if (s.type === "check") {
      if (!s.target) return "Onay kutusunu seçtiğinizde adımın özeti burada görünür.";
      const final = s.checked === null ? "henüz belirlenmemiş duruma" : s.checked ? "işaretli duruma" : "işaretsiz duruma";
      return `${s.target.section ? `${s.target.section} bölümündeki ` : ""}“${s.target.label || "etiketsiz"}” kutusunu ${final} getir; zaten o durumdaysa dokunmaz.${s.effect === "unknown" ? " Kayıt veya ekran değişikliği tetikleyebilir; açık onay ister." : ""}`;
    }
    if (s.type === "choose") {
      if (!s.target) return "Seçim alanını seçtiğinizde adımın özeti burada görünür.";
      const where = `${s.target.section ? `${s.target.section} bölümündeki ` : ""}“${s.target.label || "etiketsiz"}” listesinde`;
      const b = s.binding;
      const what = b.source === "fixed" ? (b.fixedValue ? `“${b.fixedValue}” seçeneğini` : "henüz belirlenmemiş bir seçeneği")
        : b.source === "ask" ? "her çalıştırmada sorulan seçeneği"
          : b.source === "previous" ? `${(refLabel(steps, b.previousRef) || "önceki bir adımın").split(":")[0]} değerini` : "kaynağı belirlenmemiş bir seçeneği";
      const effect = s.effect === "unknown" ? " Kayıt veya ekran değişikliği tetikleyebilir; açık onay ister."
        : s.effect === "ui_local" ? " Yalnız bu alanın seçimini değiştirir." : "";
      return `${where} ${what} seç.${effect}`;
    }
    if (s.type === "action") {
      const act = (real.actions || []).find((x) => x.action_id === s.actionId);
      return act ? `Onaylı işlemi çalıştır: ${act.title}. ${effectText(act)}` : "Henüz seçilmemiş bir onaylı işlemi çalıştır.";
    }
    if (isRealGoto(s)) {
      return `“${s.button.label}” düğmesine bir kez bas ve ${s.expectName.trim() ? `“${s.expectName.trim()}”` : "henüz adı yazılmamış"} ekranının açıldığını doğrula.`;
    }
    if (s.type === "goto") {
      const btn = s.button ? `“${s.button.label}” düğmesine bas` : "Henüz seçilmemiş bir düğmeye bas";
      const exp = s.expectScreen ? ` ve “${screenTitle(s.expectScreen)}” ekranının açıldığını doğrula.` : "; beklenen ekran henüz seçilmedi.";
      return btn + exp;
    }
    if (s.published) return `Yayımlanmış “${s.published.title}” bileşenini sürüm ${s.published.revision} ile çalıştır. ${s.published.effect === "mutating" ? "Veri değiştiren onaylı işlem içerir." : "Yalnız alanlara yazar/okur."}`;
    const c = findComp(s.componentId);
    return c ? `“${c.name}” bileşenini çalıştır (${c.steps.length} adım).` : "Henüz seçilmemiş bir bileşeni çalıştır.";
  }

  // ===================================================================
  // Değişiklik takibi: deneme sonucu yalnız aynı içerik için geçerli
  // ===================================================================
  function signature(f) {
    const usedComps = f.steps.filter((s) => s.type === "call").map((s) => findComp(s.componentId)).filter(Boolean);
    return JSON.stringify({ app: f.applicationId, start: f.startScreen, steps: f.steps.map(({ note, ...rest }) => rest), comps: usedComps });
  }

  // ===================================================================
  // Çizim: tüm paneller
  // ===================================================================
  function renderAll() {
    byId("pd-home").hidden = state.view !== "list";
    byId("pd-editor-view").hidden = state.view !== "editor";
    if (state.view === "list") { renderHome(); return; }
    renderFlowBar();
    renderComponents();
    renderLibrary();
    renderSteps();
    renderEditor();
  }

  function refreshDerived() {
    // Metin yazarken düzenleyiciyi yeniden çizmeden özet/eksikleri günceller (odak korunur).
    renderFlowBar(true);
    renderSteps();
    updateEditorDerived();
  }

  // ---------- Akışlar (başlangıç görünümü) ----------
  function trialBadge(f) {
    const t = f.lastTrial;
    if (!t) return h("span", { class: "pd-badge pd-badge--muted" }, "Denenmedi");
    if (t.sig !== signature(f)) return h("span", { class: "pd-badge pd-badge--warn" }, "Deneme eskidi");
    return t.ok ? h("span", { class: "pd-badge pd-badge--ok" }, "Deneme başarılı") : h("span", { class: "pd-badge pd-badge--danger" }, "Deneme başarısız");
  }
  function renderHome() {
    const warn = byId("pd-home-apps");
    warn.hidden = APPS.length > 0;
    warn.textContent = APPS.length ? "" : "Yapılandırılmış uygulama yok (AUTOMATION_APPLICATIONS_JSON boş). Akış bir uygulamaya bağlı olduğundan yeni akış oluşturulamaz; yöneticinize başvurun.";
    const newBtn = byId("pd-new-flow");
    newBtn.setAttribute("aria-disabled", APPS.length ? "false" : "true");
    byId("pd-flow-list-empty").hidden = state.flows.length > 0;
    byId("pd-flow-list").replaceChildren(...state.flows.map((f) => h("li", { class: "pd-flowitem" },
      h("div", { class: "pd-flowitem__main" },
        h("p", { class: "pd-flowitem__name" }, f.name.trim() || "Adsız akış"),
        h("p", { class: "pd-flowitem__meta" }, `${appName(f.applicationId) || "Uygulama seçilmedi"} · ${f.steps.length} adım`)),
      trialBadge(f),
      h("button", {
        type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", dataset: { flowId: f.id },
        "aria-label": `“${f.name.trim() || "Adsız akış"}” akışını düzenle`,
        onclick: () => openEditor(f.id),
      }, "Düzenle"))));
  }

  function openEditor(flowId) {
    const stored = state.flows.find((f) => f.id === flowId);
    const working = clone(stored);
    state.editing = { flow: working, baseline: editable(working), isNew: false };
    enterEditor();
  }
  function startNewFlow() {
    if (!APPS.length) { toast("Yapılandırılmış uygulama olmadığı için yeni akış oluşturulamaz."); return; }
    const f = newFlow();
    state.editing = { flow: f, baseline: editable(f), isNew: true };
    enterEditor();
    announce("Yeni akış düzenleniyor. Saklamadan dönerseniz akış oluşturulmaz.");
  }
  function enterEditor() {
    state.view = "editor";
    state.selectedStepId = null; state.checked.clear(); state.changingTarget.clear(); state.openDetails.clear();
    renderAll();
    byId("pd-flow-name").focus();
  }
  function closeEditor() {
    if (real.pick) cancelRealPick("Akışlara dönüldü; seçim modu kapatıldı.");
    const id = state.editing ? state.editing.flow.id : null;
    state.editing = null;
    state.view = "list";
    state.selectedStepId = null; state.checked.clear(); state.changingTarget.clear();
    renderAll();
    const edit = id && document.querySelector(`[data-flow-id="${id}"]`);
    (edit || byId("pd-new-flow")).focus();
  }
  async function goBack() {
    const e = state.editing;
    if (isDirty()) {
      const discard = await confirmDiscard({
        title: "Saklanmamış değişiklikler var",
        text: e.isNew
          ? "Bu yeni akış henüz saklanmadı. Bırakırsanız akış oluşturulmaz."
          : "Bırakırsanız akış, bu sayfada son saklanan haline döner.",
        keep: "Düzenlemeye devam et", discard: "Değişiklikleri bırak",
      });
      if (!discard) return;
      announce(e.isNew ? "Yeni akış oluşturulmadı." : "Değişiklikler bırakıldı; akış son saklanan haline döndü.");
    } else if (!e.isNew) {
      // İçerik aynı: deneme/yayın gösterimi sonucu saklanan kopyaya taşınabilir (aynı içerik için geçerli).
      const stored = state.flows.find((f) => f.id === e.flow.id);
      if (stored) { stored.lastTrial = clone(e.flow.lastTrial); stored.published = clone(e.flow.published); }
    }
    closeEditor();
  }
  function saveFlow(quiet) {
    const e = state.editing;
    const copy = clone(e.flow);
    const i = state.flows.findIndex((f) => f.id === copy.id);
    if (i >= 0) state.flows[i] = copy; else state.flows.push(copy);
    e.baseline = editable(e.flow);
    e.isNew = false;
    renderFlowBar(true);
    if (!quiet) toast("Akış bu sayfada saklandı. Kalıcı kayıt değildir; sayfa yenilenince silinir.");
  }
  function clearAppBound(f) {
    // Uygulama değişince önceki uygulamanın hedefleri, deneme sonucu ve yayın gösterimi taşınmaz.
    for (const s of f.steps) {
      if (s.type === "fill") {
        s.target = null;
        if (s.suggested.name) s.name = "";
        if (s.suggested.description) s.description = "";
        if (s.binding.questionSuggested) s.binding.question = "";
      } else if (s.type === "goto") {
        s.button = null; s.expectScreen = ""; s.confirmNoData = false;
      } else if (s.type === "call") {
        s.componentId = ""; s.bindings = {};
      }
    }
    f.lastTrial = null;
    f.published = [];
    state.lastAsk = {};
    state.changingTarget.clear();
  }

  // ---------- Ortak onay: yalnız kayıp olacaksa sorulur ----------
  function confirmDiscard({ title, text, keep, discard }) {
    const dlg = byId("pd-confirm");
    byId("pd-confirm-title").textContent = title;
    byId("pd-confirm-text").textContent = text;
    const keepBtn = byId("pd-confirm-keep"); const discardBtn = byId("pd-confirm-discard");
    keepBtn.textContent = keep; discardBtn.textContent = discard;
    return new Promise((resolve) => {
      const done = (value) => {
        keepBtn.removeEventListener("click", onKeep);
        discardBtn.removeEventListener("click", onDiscard);
        dlg.removeEventListener("cancel", onCancel);
        dlg.close();
        resolve(value);
      };
      const onKeep = () => done(false);
      const onDiscard = () => done(true);
      const onCancel = (ev) => { ev.preventDefault(); done(false); }; // Esc güvenli seçenektir: düzenlemeye devam
      keepBtn.addEventListener("click", onKeep);
      discardBtn.addEventListener("click", onDiscard);
      dlg.addEventListener("cancel", onCancel);
      dlg.showModal();
      keepBtn.focus();
    });
  }

  // ---------- Akış başlığı ----------
  function renderFlowBar(light = false) {
    const f = flow();
    const nameInput = byId("pd-flow-name");
    if (!light) {
      nameInput.value = f.name;
      const sel = byId("pd-flow-app");
      sel.replaceChildren(...(APPS.length
        ? [h("option", { value: "" }, "Seçin…"), ...APPS.map((a) => h("option", { value: a.id }, a.name))]
        : [h("option", { value: "" }, "Uygulama yapılandırılmamış")]));
      sel.value = f.applicationId;
      sel.disabled = !APPS.length;
      // Tek uygulama yapılandırılmışsa seçim yükü yok: yalnız ad gösterilir.
      const single = APPS.length === 1;
      sel.hidden = single;
      byId("pd-flow-app-name").hidden = !single;
      byId("pd-flow-app-name").textContent = single ? APPS[0].name : "";
      const st = byId("pd-flow-start");
      st.replaceChildren(...Object.entries(SCREENS).map(([k, s]) => h("option", { value: k }, s.title)));
      st.value = f.startScreen;
    }
    const appErr = byId("pd-flow-app-err");
    appErr.hidden = !!f.applicationId;
    appErr.className = "pd-msg pd-msg--missing";
    appErr.textContent = f.applicationId ? "" : (APPS.length
      ? "Uygulama seçin. Prototip uygulamaya bağlanmaz; ekranlar temsilidir."
      : "Yapılandırılmış uygulama yok (AUTOMATION_APPLICATIONS_JSON boş).");
    const dirty = isDirty();
    byId("pd-dirty").textContent = dirty
      ? "Saklanmamış değişiklik var (yalnız bu sayfada)"
      : state.editing.isNew ? "Yeni akış: henüz oluşturulmadı" : "Değişiklik yok";
    byId("pd-dirty").classList.toggle("is-dirty", dirty);
    byId("pd-save-flow").disabled = !dirty;
    renderDraftBar();
    const err = byId("pd-flow-name-err");
    const missing = !f.name.trim() && f.steps.length > 0;
    err.hidden = !missing;
    err.className = "pd-msg pd-msg--missing";
    err.textContent = missing ? "Akışa bir ad verin; yayın için gereklidir." : "";
    nameInput.classList.toggle("pd-missing", missing);

    const status = byId("pd-trial-status");
    status.replaceChildren();
    const t = f.lastTrial;
    if (!t) status.append(h("span", { class: "pd-badge pd-badge--muted" }, "Denenmedi"), "Yayından önce akışı deneyin.");
    else if (t.sig !== signature(f)) status.append(h("span", { class: "pd-badge pd-badge--warn" }, "Deneme eskidi"), "Son denemeden sonra değişiklik yapıldı.");
    else if (t.ok) status.append(h("span", { class: "pd-badge pd-badge--ok" }, icon("check", "pd-ico--sm"), "Deneme başarılı"), `Saat ${t.at}.`);
    else status.append(h("span", { class: "pd-badge pd-badge--danger" }, "Deneme başarısız"), t.reason || "");
    if (f.published.length) status.append(" ", h("span", { class: "pd-badge pd-badge--proto" }, `Gösterim sürümü ${f.published.length}`));
  }

  // ---------- Sol: bileşenler ----------
  function renderComponents() {
    const item = (c) => h("li", null, h("button", {
      type: "button", class: "pd-comp",
      "aria-disabled": c.supported ? null : "true",
      "aria-describedby": c.supported ? null : "pd-unsupported-title",
      onclick: () => {
        if (!c.supported) {
          toast(`“${c.name}” henüz desteklenmiyor; sahte bir sonuç üretilmez.`);
          return;
        }
        if (c.realOnly && state.source !== "real") {
          toast(`“${c.name}” yalnız gerçek oturumda çalışır; temsili ekranda sahte bir çıktı veya etki üretilmez. Üstten “Gerçek oturum”u seçin.`);
          return;
        }
        if (c.type === "action") loadActions();
        if (c.type === "call" && state.source === "real") { addStep(newStep("call")); loadPublished(); return; }
        if (c.type === "call" && !appComponents().length) {
          toast("Önce birkaç adımı işaretleyip “Yeniden kullanılabilir bileşen olarak kaydet” deyin.");
          return;
        }
        addStep(newStep(c.type));
      },
    }, icon(c.icon), h("span", { class: "pd-comp__name" }, c.name), h("span", { class: "pd-comp__desc" }, c.desc)));
    byId("pd-components").replaceChildren(...COMPONENTS.filter((c) => c.supported).map(item));
    let extra = byId("pd-components-unsupported");
    if (!extra) {
      extra = h("div", { id: "pd-components-unsupported" });
      byId("pd-components").after(extra);
    }
    extra.replaceChildren(
      h("p", { class: "pd-comp-group__title", id: "pd-unsupported-title" }, state.source === "real" ? "Henüz desteklenmiyor" : "Bu prototipte henüz yok"),
      h("ul", { class: "pd-components" }, COMPONENTS.filter((c) => !c.supported).map(item)));
  }

  // ---------- Sol: yeniden kullanılabilir akışlar ----------
  const appComponents = () => state.components.filter((c) => c.applicationId === flow().applicationId);
  function renderLibrary() {
    const host = byId("pd-library");
    const comps = appComponents();
    if (!comps.length) {
      host.replaceChildren(h("p", { class: "pd-lib-empty" },
        "Henüz yok. Ortadaki adımlardan birkaçını işaretleyip “Yeniden kullanılabilir bileşen olarak kaydet” deyin; sonra başka akışlara ekleyebilirsiniz."));
      return;
    }
    host.replaceChildren(h("ul", { class: "pd-lib" }, comps.map((c) => h("li", { class: "pd-lib__item" },
      h("div", { class: "pd-lib__head" },
        h("div", null,
          h("p", { class: "pd-lib__name" }, c.name),
          h("p", { class: "pd-lib__meta" }, `${c.steps.length} adım · ${c.inputs.length ? `${c.inputs.length} değer ister` : "değer istemez"}`)),
        h("button", {
          type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm",
          "aria-label": `“${c.name}” bileşenini akışa ekle`,
          onclick: () => { const s = newStep("call"); s.componentId = c.id; s.bindings = defaultBindings(c); addStep(s); },
        }, icon("plus", "pd-ico--sm"), "Ekle")),
      c.description ? h("p", { class: "pd-lib__meta" }, c.description) : null,
      h("details", null, h("summary", null, "Adımları göster"),
        h("ol", null, c.steps.map((s) => h("li", null, summarize(s, c.steps)))))))));
  }

  // ---------- Orta: adım kartları ----------
  let dragId = null;

  function renderSteps() {
    const f = flow();
    const analysis = analyze(f);
    const ol = byId("pd-steps");
    byId("pd-empty").hidden = f.steps.length > 0;
    ol.hidden = f.steps.length === 0;
    ol.replaceChildren(...f.steps.map((s, i) => {
      const a = analysis.get(s.id);
      const errors = a.issues.filter((x) => x.level === "error").length;
      const missing = a.issues.length - errors;
      const meta = TYPE_META[s.type];
      const selected = s.id === state.selectedStepId;
      const card = h("li", {
        class: "pd-card" + (selected ? " is-selected" : "") + (a.issues.length ? " has-issues" : ""),
        dataset: { stepId: s.id },
      });
      const grip = h("span", { class: "pd-grip", title: "Sürükleyerek taşı", "aria-hidden": "true" }, icon("grip"));
      grip.draggable = true;
      grip.addEventListener("dragstart", (e) => {
        dragId = s.id; card.classList.add("is-dragging");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", s.id);
        e.dataTransfer.setDragImage(card, 20, 20);
      });
      grip.addEventListener("dragend", () => { dragId = null; renderSteps(); });
      card.addEventListener("dragover", (e) => {
        if (!dragId || dragId === s.id) return;
        e.preventDefault();
        const r = card.getBoundingClientRect();
        const before = e.clientY < r.top + r.height / 2;
        card.classList.toggle("drop-before", before);
        card.classList.toggle("drop-after", !before);
      });
      card.addEventListener("dragleave", () => card.classList.remove("drop-before", "drop-after"));
      card.addEventListener("drop", (e) => {
        e.preventDefault();
        if (!dragId || dragId === s.id) return;
        const r = card.getBoundingClientRect();
        const before = e.clientY < r.top + r.height / 2;
        const from = f.steps.findIndex((x) => x.id === dragId);
        const moved = f.steps.splice(from, 1)[0];
        let to = f.steps.findIndex((x) => x.id === s.id);
        if (!before) to += 1;
        f.steps.splice(to, 0, moved);
        dragId = null;
        afterMove(moved.id, `${TYPE_META[moved.type].name} adımı ${to + 1}. sıraya taşındı.`, null);
      });

      const checkbox = h("input", {
        type: "checkbox", "aria-label": `${i + 1}. adımı bileşen için işaretle`,
        checked: state.checked.has(s.id),
        onchange: (e) => { if (e.target.checked) state.checked.add(s.id); else state.checked.delete(s.id); renderSelectionBar(); },
      });
      const status = errors
        ? h("span", { class: "pd-badge pd-badge--danger" }, icon("alert", "pd-ico--sm"), `${errors} sorun`)
        : missing
          ? h("span", { class: "pd-badge pd-badge--warn" }, `${missing} eksik`)
          : h("span", { class: "pd-badge pd-badge--ok" }, icon("check", "pd-ico--sm"), "Hazır");
      const short = cardText(s);
      const main = h("button", {
        type: "button", class: "pd-card__main", "aria-pressed": selected ? "true" : "false",
        "aria-label": `${i + 1}. adım, ${meta.name}: ${summarize(s, f.steps)} ${a.issues.length ? `${a.issues.length} eksik veya sorun.` : "Hazır."} Düzenlemek için seçin.`,
        onclick: () => selectStep(s.id, true),
        onkeydown: (e) => {
          if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) { e.preventDefault(); move(s.id, e.key === "ArrowUp" ? -1 : 1, "main"); }
        },
      },
      h("span", { class: "pd-card__num", "aria-hidden": "true" }, String(i + 1)),
      h("span", { class: "pd-card__title", "aria-hidden": "true", title: meta.name }, icon(meta.icon, "pd-ico--sm"), short.title),
      h("span", { class: "pd-card__status", "aria-hidden": "true" }, status),
      h("span", { class: "pd-card__detail", "aria-hidden": "true" }, short.detail));

      const up = h("button", {
        type: "button", class: "pd-icon-btn", "aria-label": `${i + 1}. adımı yukarı taşı`, title: "Yukarı taşı",
        disabled: i === 0, dataset: { move: "up" }, onclick: () => move(s.id, -1, "up"),
      }, icon("up"));
      const down = h("button", {
        type: "button", class: "pd-icon-btn", "aria-label": `${i + 1}. adımı aşağı taşı`, title: "Aşağı taşı",
        disabled: i === f.steps.length - 1, dataset: { move: "down" }, onclick: () => move(s.id, 1, "down"),
      }, icon("down"));
      card.append(grip, h("span", { class: "pd-check" }, checkbox), main, h("span", { class: "pd-card__moves" }, up, down));
      return card;
    }));
    renderSelectionBar();
  }

  function renderSelectionBar() {
    const f = flow();
    for (const id of [...state.checked]) if (!f.steps.some((s) => s.id === id)) state.checked.delete(id);
    const n = state.checked.size;
    byId("pd-selection-bar").hidden = n === 0;
    byId("pd-selection-text").textContent = `${n} adım işaretlendi`;
  }

  function move(id, delta, focusKind) {
    const f = flow();
    const i = f.steps.findIndex((s) => s.id === id);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= f.steps.length) return;
    [f.steps[i], f.steps[j]] = [f.steps[j], f.steps[i]];
    afterMove(id, `Adım ${j + 1}. sıraya taşındı.`, focusKind);
  }

  function afterMove(id, msg, focusKind) {
    renderSteps();
    updateEditorDerived(true);
    renderFlowBar(true);
    const card = document.querySelector(`.pd-card[data-step-id="${id}"]`);
    if (card) {
      card.classList.add("is-moved");
      let target = focusKind === "main" ? card.querySelector(".pd-card__main") : card.querySelector(`[data-move="${focusKind}"]`);
      if (target && target.disabled) target = card.querySelector(".pd-card__main");
      if (focusKind && target) target.focus();
    }
    announce(msg);
  }

  function addStep(step, index) {
    const f = flow();
    if (index === undefined) f.steps.push(step); else f.steps.splice(index, 0, step);
    state.selectedStepId = step.id;
    renderSteps();
    renderEditor();
    renderFlowBar(true);
    announce(`${TYPE_META[step.type].name} adımı eklendi. Sağdaki düzenleyicide tamamlayın.`);
    focusEditorHeading();
  }

  function deleteStep(id) {
    const f = flow();
    const i = f.steps.findIndex((s) => s.id === id);
    if (i < 0) return;
    const [removed] = f.steps.splice(i, 1);
    state.checked.delete(id);
    if (state.selectedStepId === id) state.selectedStepId = null;
    renderSteps(); renderEditor(); renderFlowBar(true);
    toast(`${i + 1}. adım silindi.`, {
      action: { label: "Geri al", run: () => { f.steps.splice(i, 0, removed); state.selectedStepId = removed.id; renderAll(); } },
    });
    const next = document.querySelector(".pd-card__main") || byId("pd-flow-name");
    next.focus();
  }

  function selectStep(id, focusEditor) {
    state.selectedStepId = id;
    renderSteps();
    renderEditor();
    if (focusEditor) focusEditorHeading();
  }
  function focusEditorHeading() {
    const head = byId("pd-editor-heading");
    if (head) head.focus({ preventScroll: window.innerWidth > 1180 });
  }

  // ===================================================================
  // Sağ: seçilen adımın düzenleyicisi
  // ===================================================================
  function msgEl(id, field) {
    return h("p", { id, class: "pd-msg", hidden: true, dataset: { field } });
  }

  function renderEditor() {
    const host = byId("pd-editor");
    const s = state.selectedStepId && findStep(state.selectedStepId);
    if (!s) {
      host.replaceChildren(h("div", { class: "pd-editor-empty" },
        h("strong", null, "Bir adım seçin"),
        "Ortadan bir adım kartı seçtiğinizde burada düzenlersiniz."));
      return;
    }
    const f = flow();
    const a = analyze(f).get(s.id);
    const meta = TYPE_META[s.type];
    const body = h("div", { class: "pd-editor" },
      h("div", { class: "pd-editor__head" },
        h("h3", { id: "pd-editor-heading", tabindex: "-1" }, `${a.index + 1}. adım`),
        h("span", { class: "pd-editor__kind" }, icon(meta.icon, "pd-ico--sm"), meta.name)),
      h("p", { class: "pd-summary", id: "pd-ed-summary", "aria-live": "polite" }, summarize(s, f.steps)));

    if (s.type === "fill") body.append(...editorFill(s, f, a));
    else if (s.type === "read") body.append(...editorRead(s));
    else if (s.type === "choose") body.append(...editorChoose(s, f, a));
    else if (s.type === "check") body.append(...editorCheck(s, f, a));
    else if (s.type === "multi") body.append(...editorMulti(s, f, a));
    else if (s.type === "upload") body.append(...editorUpload(s, f, a));
    else if (s.type === "back") body.append(...editorBack(s));
    else if (s.type === "find") body.append(...editorFind(s, f, a));
    else if (s.type === "action") body.append(...editorAction(s, f, a));
    else if (s.type === "goto") body.append(...editorGoto(s, f, a));
    else body.append(...editorCall(s, f, a));

    const rowT = s.type === "goto" ? s.button : s.target;
    if (["fill", "read", "choose", "check", "goto"].includes(s.type) && rowT && (rowT.rowKey || s.inFoundRow)) {
      const box = h("input", { type: "checkbox", id: `${s.id}-found-row`, checked: !!s.inFoundRow, onchange: (e) => { s.inFoundRow = e.target.checked; refreshDerived(); } });
      const m = msgEl(`${s.id}-row-msg`, "row"); linkMsg(box, m);
      body.append(h("div", null, h("label", { class: "pd-check-row", for: box.id }, box, h("span", null, "Bulunan kaydın satırında çalışsın")), m,
        h("p", { class: "pd-help" }, "Çalışırken satır, önceki “Kayıt bul” adımının bulduğu iş anahtarıyla seçilir; kataloğa satır değeri yazılmaz.")));
    }
    if (s.type === "goto" && state.source === "real") body.append(completionBox(s, f, a));
    if (s.type === "fill" && s.target && s.target.source === "real") body.append(dateBox(s));
    if (s.type === "goto" && state.source === "real") body.append(windowBox(s));
    body.append(detailsSection(s));
    body.append(h("div", { class: "pd-editor__actions" },
      ["fill", "read", "choose", "check", "multi", "upload"].includes(s.type) && s.target && s.target.source === "real"
        ? h("button", { type: "button", class: "pd-btn pd-btn--primary", id: `${s.id}-recheck`, onclick: () => recheckReal(s) }, icon("target"), "Alanı yeniden bul (yazmadan)")
        : isRealGoto(s)
          ? h("button", { type: "button", class: "pd-btn pd-btn--primary", id: `${s.id}-recheck`, onclick: () => recheckReal(s) }, icon("target"), "Düğmeyi yeniden bul (basmadan)")
          : s.type === "action"
            ? h("p", { class: "pd-help" }, "Onaylı işlem yalnız aşağıdaki “Gerçek deneme ve yayın” panelinde, etkisi açıkça onaylanarak denenir.")
            : h("button", { type: "button", class: "pd-btn pd-btn--primary", onclick: () => openTrial({ stepId: s.id }) }, icon("play"), "Bu adımı dene"),
      h("button", { type: "button", class: "pd-btn pd-btn--danger", onclick: () => deleteStep(s.id) }, icon("trash"), "Adımı sil")));

    host.replaceChildren(body);
    updateEditorDerived();
  }

  function rerenderEditorKeepFocus() {
    const active = document.activeElement && document.activeElement.id;
    renderEditor();
    if (active && byId(active)) byId(active).focus();
  }

  function updateEditorDerived(headingToo) {
    const s = state.selectedStepId && findStep(state.selectedStepId);
    if (!s) return;
    const f = flow();
    const a = analyze(f).get(s.id);
    const sum = byId("pd-ed-summary");
    if (sum) sum.textContent = summarize(s, f.steps);
    if (headingToo) { const head = byId("pd-editor-heading"); if (head) head.textContent = `${a.index + 1}. adım`; }
    document.querySelectorAll("#pd-editor .pd-msg[data-field]").forEach((el) => {
      const own = a.issues.filter((x) => x.field === el.dataset.field);
      const inputId = el.dataset.input;
      const input = inputId ? byId(inputId) : null;
      if (!own.length) {
        el.hidden = true; el.textContent = "";
        if (input) { input.removeAttribute("aria-invalid"); input.classList.remove("pd-missing"); }
        return;
      }
      const isError = own.some((x) => x.level === "error");
      el.hidden = false;
      el.className = "pd-msg " + (isError ? "pd-msg--error" : "pd-msg--missing");
      el.replaceChildren(h("span", null, own.map((x) => x.msg).join(" ")));
      if (input) {
        if (isError) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
        input.classList.toggle("pd-missing", !isError);
      }
    });
  }

  function linkMsg(input, msg) {
    msg.dataset.input = input.id;
    const prev = input.getAttribute("aria-describedby");
    input.setAttribute("aria-describedby", prev ? `${prev} ${msg.id}` : msg.id);
  }

  function questionBox(id, num, title) {
    return h("section", { class: "pd-q", "aria-labelledby": id },
      h("h4", { class: "pd-q__title", id }, num ? h("span", { class: "pd-q__num", "aria-hidden": "true" }, num) : null, title));
  }

  // Temsili alan önerisi: akışın o adımdaki ekranında, yazılabilir ve akışta henüz kullanılmamış alanlar.
  function fieldSuggestions(s, f, a) {
    const used = new Set(f.steps.filter((x) => x.type === "fill" && x.target && x.id !== s.id).map((x) => x.target.fieldKey));
    return allFields().filter((fd) => fd.screen === a.screenBefore
      && ["text", "amount", "textarea"].includes(fd.kind)
      && !used.has(fd.key)
      && !(s.target && s.target.fieldKey === fd.key)).slice(0, 4);
  }

  // ---------- Alan doldur ----------
  function editorFill(s, f, a) {
    const changing = !s.target || state.changingTarget.has(s.id);
    const q1 = questionBox(`${s.id}-q1`, "1", "Hangi alan?");
    const tMsg = msgEl(`${s.id}-target-msg`, "target");
    if (s.target) {
      const toggle = h("button", {
        type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", id: `${s.id}-change`,
        "aria-expanded": changing ? "true" : "false",
        onclick: () => {
          if (changing) state.changingTarget.delete(s.id); else state.changingTarget.add(s.id);
          renderEditor();
          byId(`${s.id}-change`)?.focus();
        },
      }, changing ? "Vazgeç" : "Değiştir");
      const real = s.target.source === "real";
      const meta = real
        ? [KIND_TEXT[s.target.kind] || s.target.kind, "Gerçek oturum",
          s.target.frames.length ? `çerçeve: ${s.target.frames.join(" › ")}` : null,
          s.target.dialog ? `pencere: ${s.target.dialog}` : null].filter(Boolean).join(" · ")
        : `${KIND_TEXT[s.target.kind]} · ${screenTitle(s.target.screen)} ekranı`;
      q1.append(h("div", { class: "pd-chosen" },
        h("div", { class: "pd-chosen__main" },
          h("p", { class: "pd-chosen__name", id: `${s.id}-chosen` }, `${s.target.section ? `${s.target.section} › ` : ""}${s.target.label || "(etiketsiz)"}`),
          h("p", { class: "pd-chosen__meta" }, meta),
          real ? h("p", { class: "pd-chosen__meta", id: `${s.id}-check` }, checkText(s.target.check)) : null),
        toggle));
      linkMsg(toggle, tMsg);
    }
    q1.append(tMsg);
    if (changing && state.source === "real") {
      q1.append(...realAlternatives(s, tMsg));
    } else if (changing) {
      const sugs = fieldSuggestions(s, f, a);
      const pick = h("button", {
        type: "button", class: "pd-btn pd-btn--secondary", id: `${s.id}-pick`,
        onclick: () => openPicker(s.id, "field"),
      }, icon("target"), "Ekrandan kendim seçeyim");
      if (!s.target) linkMsg(pick, tMsg);
      q1.append(
        h("div", { class: "pd-alt pd-alt--suggest", role: "group", "aria-labelledby": `${s.id}-alt1` },
          h("div", { class: "pd-alt__head" },
            h("p", { class: "pd-alt__title", id: `${s.id}-alt1` }, "Önerilen alanlardan seç"),
            h("span", { class: "pd-badge pd-badge--suggest" }, "Öneri · temsili")),
          sugs.length
            ? h("ul", { class: "pd-fieldsugs" }, sugs.map((fd) => h("li", null, h("button", {
              type: "button", class: "pd-fieldsug",
              "aria-label": `${fd.section} bölümündeki ${fd.label} alanını seç`,
              onclick: () => choseField(s, fd, "öneriden"),
            }, h("span", { class: "pd-fieldsug__name" }, `${fd.section} › ${fd.label}`),
            h("span", { class: "pd-fieldsug__kind" }, KIND_TEXT[fd.kind])))))
            : h("p", { class: "pd-help" }, `“${screenTitle(a.screenBefore)}” ekranında önerilecek boş alan kalmadı.`)),
        h("p", { class: "pd-or", "aria-hidden": "true" }, "veya"),
        h("div", { class: "pd-alt" },
          pick,
          h("p", { class: "pd-help" }, "Önerilerde olmayan bir alanı temsili uygulamada doğrudan seçin. Seçerken uygulamada hiçbir şey yazılmaz veya kaydedilmez.")));
    }
    const q2 = questionBox(`${s.id}-q2`, "2", "Değer nereden gelsin?");
    // Gerçek oturumda yalnız gerçek okuma çıktısı seçilebilir; kaydedilemeyecek kaynak listelenmez.
    const sources = outputsBefore(f.steps, a.index).filter((o) => !(s.target && s.target.source === "real") || o.read);
    q2.append(bindingEditor(s.binding, s.target, sources, `${s.id}-b`, "", "Değer nereden gelsin?"));
    return [q1, q2, outcomeBox(s)];
  }

  // Sonuç koşulu ve iş etkisi: sade seçim. Etki uydurulmaz; alan doldurma kayıt yapmaz.
  function outcomeBox(s) {
    const q = questionBox(`${s.id}-q3`, "3", "Sonuç nasıl kontrol edilsin?");
    const fs = h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Sonuç kontrolü"));
    const opt = (value, name, desc) => {
      const id = `${s.id}-check-${value}`;
      return h("div", { class: "pd-choice" }, h("label", { class: "pd-choice__label", for: id },
        h("input", { type: "radio", name: `${s.id}-check`, id, value, checked: (s.successCheck || "auto") === value,
          onchange: () => { s.successCheck = value; refreshDerived(); } }),
        h("span", { class: "pd-choice__name" }, name), h("span", { class: "pd-choice__desc" }, desc)));
    };
    fs.append(
      opt("auto", "Yazılan değeri alanda okuyarak doğrula (önerilen)", "Değer alanda görülmezse adım başarısız sayılır."),
      opt("none", "Ek kontrol yapma", "Yalnız alan yazma sırasında doğrulanır; ayrı sonuç kontrolü eklenmez."));
    q.append(fs, h("p", { class: "pd-help", id: `${s.id}-effect` },
      "İş etkisi: yalnız alana yazar; kayıt yapmaz veya göndermez. Veri kaydetmek için ayrı bir “Onaylı işlem” adımı ekleyin."));
    return q;
  }

  // ---------- Bilgi oku (yalnız gerçek oturum) ----------
  function editorRead(s) {
    const q1 = questionBox(`${s.id}-q1`, "1", "Hangi alan okunsun?");
    const tMsg = msgEl(`${s.id}-target-msg`, "target");
    const changing = !s.target || state.changingTarget.has(s.id);
    if (s.target) {
      const toggle = h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", id: `${s.id}-change`,
        "aria-expanded": changing ? "true" : "false",
        onclick: () => { if (changing) state.changingTarget.delete(s.id); else state.changingTarget.add(s.id); renderEditor(); byId(`${s.id}-change`)?.focus(); } },
      changing ? "Vazgeç" : "Değiştir");
      q1.append(h("div", { class: "pd-chosen" }, h("div", { class: "pd-chosen__main" },
        h("p", { class: "pd-chosen__name", id: `${s.id}-chosen` }, `${s.target.section ? `${s.target.section} › ` : ""}${s.target.label || "(etiketsiz)"}`),
        h("p", { class: "pd-chosen__meta" }, `${KIND_TEXT[s.target.kind] || s.target.kind} · Gerçek oturum`),
        h("p", { class: "pd-chosen__meta", id: `${s.id}-check` }, checkText(s.target.check))), toggle));
      linkMsg(toggle, tMsg);
    }
    q1.append(tMsg);
    if (changing && state.source === "real") q1.append(...realAlternatives(s, tMsg));
    else if (changing) q1.append(h("p", { class: "pd-msg pd-msg--missing" }, "“Bilgi oku” yalnız gerçek oturumda çalışır. Üstten “Gerçek oturum”u seçin."));
    const q2 = questionBox(`${s.id}-q2`, "2", "Okunan değerin adı");
    q2.append(h("div", { class: "pd-field" },
      h("label", { class: "pd-label", for: `${s.id}-name` }, "Sonraki adımlarda nasıl görünsün?"),
      h("input", { type: "text", id: `${s.id}-name`, maxlength: "60", value: s.name, autocomplete: "off",
        oninput: (e) => { s.name = e.target.value; s.suggested.name = false; refreshDerived(); } }),
      h("p", { class: "pd-help" }, "Okunan değer yalnız çalışırken gerçek ekrandan alınır; tasarımda tahmin edilmez. Sonraki bir “Alan doldur” adımında “Önceki adımın çıktısı” olarak seçebilirsiniz.")));
    return [q1, q2];
  }

  // ---------- Kayıt bul ----------
  function editorFind(s, f, a) {
    const q1 = questionBox(`${s.id}-q1`, "1", "Hangi tablo?");
    const tMsg = msgEl(`${s.id}-target-msg`, "target");
    const changing = !s.target || state.changingTarget.has(s.id);
    if (s.target) {
      const toggle = h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", id: `${s.id}-change`, onclick: () => { if (changing) state.changingTarget.delete(s.id); else state.changingTarget.add(s.id); renderEditor(); } }, changing ? "Vazgeç" : "Değiştir");
      q1.append(h("div", { class: "pd-chosen" }, h("div", { class: "pd-chosen__main" },
        h("p", { class: "pd-chosen__name", id: `${s.id}-chosen` }, `${s.target.section ? `${s.target.section} › ` : ""}${s.target.label || "(adsız)"}`),
        h("p", { class: "pd-chosen__meta", id: `${s.id}-check` }, checkText(s.target.check))), toggle));
    }
    q1.append(tMsg);
    if (changing) q1.append(...realAlternatives(s, tMsg));
    const q2 = questionBox(`${s.id}-q2`, "2", "Kayıt anahtarı nereden gelsin?");
    q2.append(bindingEditor(s.binding, { fixedName: "Sabit anahtar", fixedDesc: "Her çalıştırmada aynı kayıt aranır.", previousDesc: "Önceki “Bilgi oku” adımının gerçek çıktısı." }, outputsBefore(f.steps, a.index).filter((o) => o.read), `${s.id}-b`, "", "Kayıt anahtarı"));
    const q3 = questionBox(`${s.id}-q3`, "3", "Tablo nasıl gezilsin?");
    const fs = h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Gezinme"));
    const opt = (v, name, desc) => h("div", { class: "pd-choice" }, h("label", { class: "pd-choice__label", for: `${s.id}-nav-${v}` },
      h("input", { type: "radio", name: `${s.id}-nav`, id: `${s.id}-nav-${v}`, checked: s.navigation === v, onchange: () => { s.navigation = v; refreshDerived(); rerenderEditorKeepFocus(); } }),
      h("span", { class: "pd-choice__name" }, name), h("span", { class: "pd-choice__desc" }, desc)));
    fs.append(opt("none", "Yalnız görünen satırlar", "Sayfalama yoktur."), opt("paged", "Sayfalı tablo", "“Sonraki” ile ilerler."), opt("scroll", "Kaydırarak yüklenen tablo", "Sona kaydırarak ilerler."));
    q3.append(fs);
    if (s.navigation === "paged") {
      const n = h("input", { type: "text", id: `${s.id}-next`, maxlength: "60", value: s.nextLabel, autocomplete: "off", oninput: (e) => { s.nextLabel = e.target.value; refreshDerived(); } });
      const m = msgEl(`${s.id}-nav-msg`, "nav"); linkMsg(n, m);
      q3.append(h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: n.id }, "Sonraki sayfa düğmesinin adı"), n, m));
    }
    if (s.navigation === "scroll") {
      const e2 = h("input", { type: "text", id: `${s.id}-end`, maxlength: "200", value: s.endText, autocomplete: "off", oninput: (e) => { s.endText = e.target.value; refreshDerived(); } });
      q3.append(h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: e2.id }, "Liste sonu metni (isteğe bağlı)"), e2));
    }
    q3.append(h("p", { class: "pd-help" }, "Eşleşme tam metindir ve tablonun ilk sütununda aranır. “Bulunamadı” yalnız tablonun sonu görüldüyse söylenir; sınır veya ilerleme yoksa “kesin değil” olarak durur."));
    return [q1, q2, q3];
  }
  // Geçiş sonrası kayıt bağlamı: hedef ekranda alan değeri beklenene eşit olmalı (yanlış kayıtta yazma yapılmaz).
  function completionBox(s, f, a) {
    const c = s.completion || (s.completion = { label: "", section: "", source: "", fixed: "" });
    const hasFind = f.steps.slice(0, a.index).some((x) => x.type === "find");
    const q = questionBox(`${s.id}-q-ctx`, null, "Açılan ekranda kayıt doğrulansın mı? (isteğe bağlı)");
    const input = (key, label) => { const i = h("input", { type: "text", id: `${s.id}-ctx-${key}`, value: c[key], maxlength: "120", autocomplete: "off", oninput: (e) => { c[key] = e.target.value; refreshDerived(); } }); return h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: i.id }, label), i); };
    const sel = h("select", { id: `${s.id}-ctx-source`, onchange: (e) => { c.source = e.target.value; refreshDerived(); rerenderEditorKeepFocus(); } }, h("option", { value: "" }, "Kontrol yok"), hasFind ? h("option", { value: "found" }, "Bulunan kaydın anahtarı") : null, h("option", { value: "fixed" }, "Sabit değer"));
    sel.value = c.source;
    q.append(h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: sel.id }, "Beklenen değer"), sel));
    if (c.source) q.append(input("label", "Alanın etiketi"), input("section", "Bölüm (varsa)"));
    if (c.source === "fixed") q.append(input("fixed", "Sabit değer"));
    return q;
  }

  // ---------- Seçim yap (yalnız gerçek oturum) ----------
  // Seçenekler sayfa belleğinde tutulur (taslağı kirletmez); alan işaretlemek uygulamada seçim yapmaz.
  function choiceInfo(s) { return (real.choiceInfo || {})[s.id] || null; }
  const usableOptions = (info) => (info && info.options ? info.options.filter((o) => o.state === "ok") : []);
  function askList(s) {
    if (s.askDynamic) return null;
    const ok = usableOptions(choiceInfo(s));
    if (ok.length && ok.length <= 200) return ok.map((o) => (o.value ? { label: o.label, value: o.value } : { label: o.label }));
    return s.askChoices;
  }
  async function loadChoiceOptions(step, openList) {
    const t = step.target;
    if (!t || t.source !== "real" || !t.label || step.autocomplete || !choiceKinds(step).includes(t.kind)) return;
    const multi = step.type === "multi";
    if (!real.sid) { realStatus("Önce bir tarayıcı oturumu seçin.", "warn"); return; }
    real.choiceInfo = real.choiceInfo || {};
    const before = real.choiceInfo[step.id];
    realStatus(openList ? "Liste açılıyor; seçenekler okunuyor (seçim yapılmaz)…" : "Seçenekler okunuyor…", "busy");
    let r;
    try { r = await api("POST", sessionPath("/choice-options"), { target: realSpec(t), open_list: !!openList, multi }); }
    catch (e) { r = { status: "failed", message: errText(e), options: [] }; }
    // Kapalı listeyi yeniden kontrol etmek, daha önce açıkça okunan seçenekleri silmez.
    if (r.status === "needs_open" && before && before.status === "ok") r = { ...before, stale: true };
    real.choiceInfo[step.id] = r;
    const chosen = step.binding && step.binding.fixedValue && r.options.find((o) => o.label === step.binding.fixedValue);
    if (chosen && chosen.state === "ok") step.choiceValue = chosen.value;
    realStatus(r.status === "ok" ? `${usableOptions(r).length} seçilebilir seçenek okundu. Uygulamada seçim yapılmadı.` : r.message || "", r.status === "ok" ? "ok" : "warn");
    if (state.view === "editor") { refreshDerived(); rerenderEditorKeepFocus(); }
  }
  // Örnek arama alanı geçici değiştirir; eski değer geri yazılıp okunarak doğrulanır, öneri seçilmez.
  async function sampleSearch(step, text) {
    if (!real.sid) { realStatus("Önce bir tarayıcı oturumu seçin.", "warn"); return; }
    if (!text.trim()) { realStatus("Örnek arama metnini yazın.", "warn"); return; }
    real.choiceInfo = real.choiceInfo || {};
    realStatus("Örnek arama yapılıyor; öneri seçilmez…", "busy");
    let r;
    try { r = await api("POST", sessionPath("/choice-options"), { target: realSpec(step.target), open_list: false, search: text.trim() }); }
    catch (e) { r = { status: "failed", message: errText(e), options: [] }; }
    real.choiceInfo[step.id] = r;
    if (r.status === "ok") step.searchText = text.trim();
    realStatus(r.status === "ok" ? `${usableOptions(r).length} öneri okundu. Alan eski değerine döndürüldü.` : r.message || "", r.status === "ok" ? "ok" : "warn");
    if (state.view === "editor") { refreshDerived(); rerenderEditorKeepFocus(); }
  }
  function sampleSearchBox(s) {
    const q = questionBox(`${s.id}-q-opts`, "2", "Örnek arama");
    const info = choiceInfo(s);
    const input = h("input", { type: "text", id: `${s.id}-search`, maxlength: "200", value: s.searchText, autocomplete: "off" });
    q.append(h("label", { class: "pd-label", for: input.id }, "Örnek arama metni"), input,
      h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", id: `${s.id}-read-options`, onclick: () => sampleSearch(s, input.value) }, "Örnek ara ve önerileri oku"),
      h("p", { class: "pd-help" }, "Bu düğme alana geçici olarak yazar; yazmak uygulamada arama başlatabilir. Öneriler okunur, eski değer geri yazılır ve doğrulanır. Öneri seçilmez."));
    if (info && info.status !== "ok") q.append(h("p", { class: "pd-msg pd-msg--error", id: `${s.id}-options-error` }, info.message || "Öneriler okunamadı."));
    if (info && info.status === "ok") q.append(h("ul", { class: "pd-optlist", id: `${s.id}-options` }, info.options.map((o) => h("li", { class: o.state === "ok" ? null : "is-off" }, o.label, OPTION_NOTE[o.state] ? ` (${OPTION_NOTE[o.state]})` : ""))));
    return q;
  }
  const OPTION_NOTE = { disabled: "devre dışı", duplicate: "yinelenen; seçilemez", placeholder: "yer tutucu" };
  function choiceOptionsBox(s) {
    const q = questionBox(`${s.id}-q-opts`, "2", "Listedeki seçenekler");
    const info = choiceInfo(s);
    const read = (label, open) => h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", id: `${s.id}-read-options`, onclick: () => loadChoiceOptions(s, open) }, label);
    if (!info) {
      q.append(h("p", { class: "pd-help" }, "Seçenekler alan seçildiğinde güncel ekrandan okunur. Tarayıcıda ilgili ekran açık olmalı."), read("Seçenekleri oku", false));
    } else if (info.status === "needs_open") {
      q.append(h("p", { class: "pd-msg pd-msg--missing" }, "Bu özel liste kapalıyken seçenekler görünmüyor."),
        read("Listeyi aç ve seçenekleri oku", true),
        h("p", { class: "pd-help" }, "Bu düğme uygulamada yalnız listeyi açar, seçenekleri okur ve listeyi kapatır; seçim yapmaz."));
    } else if (info.status !== "ok") {
      q.append(h("p", { class: "pd-msg pd-msg--error", id: `${s.id}-options-error` }, info.message || "Seçenekler okunamadı."),
        info.status === "unsupported" ? null : read("Yeniden dene", false));
    } else {
      q.append(h("ul", { class: "pd-optlist", id: `${s.id}-options` }, info.options.map((o) => h("li", { class: o.state === "ok" ? null : "is-off" }, o.label, OPTION_NOTE[o.state] ? ` (${OPTION_NOTE[o.state]})` : ""))),
        h("p", { class: "pd-help" }, "Liste tasarım anındaki gözlemdir; çalıştırırken seçenek güncel ekranda yeniden doğrulanır."),
        read("Seçenekleri yeniden oku", s.target.kind === "combobox"));
    }
    return q;
  }
  function editorChoose(s, f, a) {
    const q1 = questionBox(`${s.id}-q1`, "1", "Hangi seçim alanı?");
    const tMsg = msgEl(`${s.id}-target-msg`, "target");
    const changing = !s.target || state.changingTarget.has(s.id);
    if (s.target) {
      const toggle = h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", id: `${s.id}-change`, "aria-expanded": changing ? "true" : "false",
        onclick: () => { if (changing) state.changingTarget.delete(s.id); else state.changingTarget.add(s.id); renderEditor(); byId(`${s.id}-change`)?.focus(); } },
      changing ? "Vazgeç" : "Değiştir");
      q1.append(h("div", { class: "pd-chosen" }, h("div", { class: "pd-chosen__main" },
        h("p", { class: "pd-chosen__name", id: `${s.id}-chosen` }, `${s.target.section ? `${s.target.section} › ` : ""}${s.target.label || "(etiketsiz)"}`),
        h("p", { class: "pd-chosen__meta" }, [KIND_TEXT[s.target.kind] || s.target.kind, s.target.dialog ? `pencere: ${s.target.dialog}` : null, s.target.frames.length ? `çerçeve: ${s.target.frames.join(" › ")}` : null].filter(Boolean).join(" · ")),
        h("p", { class: "pd-chosen__meta", id: `${s.id}-check` }, checkText(s.target.check))), toggle));
      linkMsg(toggle, tMsg);
    }
    q1.append(tMsg);
    if (changing && state.source === "real") q1.append(...realAlternatives(s, tMsg));
    else if (changing) q1.append(h("p", { class: "pd-msg pd-msg--missing" }, "“Seçim yap” yalnız gerçek oturumda çalışır. Üstten “Gerçek oturum”u seçin."));
    q1.append(h("label", { class: "pd-check-row", for: `${s.id}-autocomplete` },
      h("input", { type: "checkbox", id: `${s.id}-autocomplete`, checked: s.autocomplete, onchange: (e) => {
        s.autocomplete = e.target.checked;
        if (real.choiceInfo) delete real.choiceInfo[s.id];
        s.choiceValue = null;
        if (s.autocomplete) { s.effect = "unknown"; s.successCheck = "auto"; s.askDynamic = true; s.changesScreen = false; }
        refreshDerived(); rerenderEditorKeepFocus();
      } }), h("span", null, "Bu alan yazınca öneri açıyor")),
    s.autocomplete ? h("p", { class: "pd-help" }, "Çalışırken arama yazılır, öneri listesinde tam eşleşen seçilir ve alandaki değer okunarak doğrulanır. Eşleşme yoksa eski değer geri yazılır. Arama yazmak uygulamada sorgu başlatabildiğinden adım en fazla bir kez gönderilir.") : null);
    const out = [q1];
    if (s.target) out.push(s.autocomplete ? sampleSearchBox(s) : choiceOptionsBox(s));
    const q3 = questionBox(`${s.id}-q2`, "3", "Hangi seçenek seçilsin?");
    const info = choiceInfo(s);
    const meta = {
      fixedName: "Sabit seçenek", fixedDesc: "Her çalıştırmada aynı seçenek seçilir.",
      previousDesc: "Önceki bir “Bilgi oku” adımının gerçek çıktısı seçenek olarak kullanılır.",
      fixedEditor: (idp, prefix) => {
        const list = info && info.options ? info.options.filter((o) => o.state !== "placeholder") : [];
        const sel = h("select", { id: `${idp}-fixed-value`, onchange: (e) => {
          const o = list.find((x) => x.label === e.target.value);
          s.binding.fixedValue = e.target.value; s.choiceValue = o ? o.value : null; refreshDerived();
        } }, h("option", { value: "" }, "Seçin…"), list.map((o) => h("option", { value: o.label, disabled: o.state !== "ok" }, `${o.label}${OPTION_NOTE[o.state] ? ` (${OPTION_NOTE[o.state]})` : ""}`)));
        if (s.binding.fixedValue && !list.some((o) => o.label === s.binding.fixedValue)) sel.append(h("option", { value: s.binding.fixedValue }, s.binding.fixedValue));
        sel.value = s.binding.fixedValue;
        const m = msgEl(`${idp}-fixed-msg`, `${prefix}fixed`); linkMsg(sel, m);
        return [h("label", { class: "pd-label", for: sel.id }, "Seçilecek seçenek"), sel, m,
          list.length ? null : h("p", { class: "pd-help" }, "Seçenekleri görmek için önce yukarıdan okuyun.")];
      },
      askExtra: (idp) => [h("label", { class: "pd-check-row", for: `${idp}-dynamic` },
        h("input", { type: "checkbox", id: `${idp}-dynamic`, checked: s.askDynamic, onchange: (e) => { s.askDynamic = e.target.checked; refreshDerived(); } }),
        h("span", null, "Seçenekler kayda veya ekrana göre değişebilir")),
      h("p", { class: "pd-help" }, "İşaretlerseniz İşlem Asistanı sabit liste göstermez; kullanıcı güncel seçenekleri açık ekrandan getirebilir. Her durumda çalışırken yeniden doğrulanır.")],
    };
    q3.append(bindingEditor(s.binding, meta, outputsBefore(f.steps, a.index).filter((o) => o.read), `${s.id}-b`, "", "Hangi seçenek seçilsin?"));
    out.push(q3);
    const q4 = questionBox(`${s.id}-q-effect`, "4", "Bu seçim ne yapar?");
    const effectFs = h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Seçimin etkisi"));
    const effectOpt = (value, name, desc) => h("div", { class: "pd-choice" }, h("label", { class: "pd-choice__label", for: `${s.id}-effect-${value}` },
      h("input", { type: "radio", name: `${s.id}-effect`, id: `${s.id}-effect-${value}`, value, checked: s.effect === value,
        onchange: () => { s.effect = value; if (value === "unknown") s.successCheck = "auto"; refreshDerived(); rerenderEditorKeepFocus(); } }),
      h("span", { class: "pd-choice__name" }, name), h("span", { class: "pd-choice__desc" }, desc)));
    effectFs.append(
      s.autocomplete ? null : effectOpt("ui_local", "Yalnız bu alanın seçimini değiştirir", "Kayıt yapmaz, ekran değiştirmez. Bundan eminseniz seçin."),
      effectOpt("unknown", "Kayıt veya ekran değişikliği tetikleyebilir / emin değilim", "Deneme ve çalıştırmada açık onay istenir; sonuç belirsizse seçim otomatik tekrarlanmaz."),
      msgEl(`${s.id}-effect-msg`, "effect"));
    const nextName = h("input", { type: "text", id: `${s.id}-expect`, maxlength: "80", value: s.expectName, autocomplete: "off", oninput: (e) => { s.expectName = e.target.value; refreshDerived(); } });
    const nextMsg = msgEl(`${s.id}-expect-msg`, "expect"); linkMsg(nextName, nextMsg);
    const screenBox = h("div", null, h("label", { class: "pd-check-row", for: `${s.id}-changes` },
      h("input", { type: "checkbox", id: `${s.id}-changes`, checked: s.changesScreen, onchange: (e) => { s.changesScreen = e.target.checked; refreshDerived(); rerenderEditorKeepFocus(); } }),
      h("span", null, "Bu seçim başka bir ekrana geçirir")),
    s.changesScreen ? h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: nextName.id }, "Seçimden sonra açılacak ekranın adı"), nextName, nextMsg,
      h("p", { class: "pd-help" }, "Seçim bir kez yapılır; sonuç hedef ekranın tanınmasıyla doğrulanır. Alan zaten bu değerdeyse geçiş tetiklenmez ve işlem durur.")) : null);
    if (!s.autocomplete) q4.append(screenBox);
    q4.append(effectFs, h("p", { class: "pd-help" }, "Sistem iş etkisini ekrana bakarak bilemez. Bilinen bir kayıt işlemi gerekiyorsa ayrı bir “Onaylı işlem” adımı ekleyin."));
    out.push(q4);
    const q5 = questionBox(`${s.id}-q3`, "5", "Sonuç nasıl kontrol edilsin?");
    const fs = h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Sonuç kontrolü"));
    const opt = (value, name, desc, disabled) => h("div", { class: "pd-choice" }, h("label", { class: "pd-choice__label", for: `${s.id}-check-${value}` },
      h("input", { type: "radio", name: `${s.id}-check`, id: `${s.id}-check-${value}`, value, disabled, checked: (s.successCheck || "auto") === value, onchange: () => { s.successCheck = value; refreshDerived(); } }),
      h("span", { class: "pd-choice__name" }, name), h("span", { class: "pd-choice__desc" }, desc)));
    fs.append(opt("auto", "Seçilen değeri alanda okuyarak doğrula (önerilen)", "Tıklamanın bitmesi yetmez; alandaki gerçek seçim okunur.", false),
      opt("none", "Ek kontrol yapma", s.effect === "unknown" ? "Etkisi bilinmeyen seçimde kullanılamaz." : "Seçim yalnız uygulanırken doğrulanır.", s.effect === "unknown"));
    const result = h("input", { type: "text", id: `${s.id}-result`, maxlength: "300", value: s.resultText, autocomplete: "off", oninput: (e) => { s.resultText = e.target.value; refreshDerived(); } });
    const rm = msgEl(`${s.id}-result-msg`, "result"); linkMsg(result, rm);
    q5.append(fs, h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: result.id }, "Ekranda görünmesi gereken durum mesajı (isteğe bağlı)"), result, rm,
      h("p", { class: "pd-help" }, "Mesaj alanın bölümündeki durum satırında aranır. Görünmezse işlem başarılı sayılmaz.")));
    out.push(q5);
    return out;
  }

  const multiChoices = (st) => { const ok = usableOptions(choiceInfo(st)); return ok.length && ok.length <= 200 ? ok.map((o) => ({ label: o.label })) : st.askChoices; };
  // Deneme dosyası yetkili depoya yüklenir; alana yalnız kimliği taşınır.
  function fileArg(x) {
    const note = h("span", { class: "pd-help", id: `pd-arg-${x.name}-note` }, live.args[x.name] ? "Dosya yüklendi." : "");
    return h("div", null, h("input", { type: "file", id: `pd-arg-${x.name}`, onchange: async (e) => {
      const file = e.target.files[0]; if (!file) return;
      note.textContent = "Yükleniyor…"; delete live.args[x.name];
      const r = await fetch("/api/artifacts/uploads", { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) }, body: file });
      if (!r.ok) { note.textContent = "Dosya kabul edilmedi."; return; }
      live.args[x.name] = (await r.json()).artifact_id; note.textContent = "Dosya yüklendi.";
    } }), note);
  }
  // Beklenen yeni pencere: yalnız analistin açıkça tanımladığı tek pencere kabul edilir.
  function windowBox(s) {
    const origin = h("input", { type: "text", id: `${s.id}-window-origin`, maxlength: "200", value: s.windowOrigin, autocomplete: "off", oninput: (e) => { s.windowOrigin = e.target.value; refreshDerived(); } });
    return h("div", null, h("label", { class: "pd-check-row", for: `${s.id}-new-window` },
      h("input", { type: "checkbox", id: `${s.id}-new-window`, checked: !!s.newWindow, onchange: (e) => { s.newWindow = e.target.checked; refreshDerived(); rerenderEditorKeepFocus(); } }),
      h("span", null, "Bu düğme yeni pencere açıyor")),
    s.newWindow ? h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: origin.id }, "Pencerenin adresi (farklı bir adresteyse)"), origin,
      h("p", { class: "pd-help" }, "Boş bırakılırsa ana sayfayla aynı adres beklenir. Birden fazla veya beklenmeyen pencere açılırsa işlem durur. Sonraki adımlardan birine “Ana pencereye dön” ekleyin.")) : null);
  }
  // İsteğe bağlı pencere: çıkarsa ad ve metin eşleşmesiyle tanımlı düğmeye basılır; çıkmazsa beklenmez.
  function optionalDialogsBlock(srv) {
    const form = live.dlgForm || (live.dlgForm = { name: "", text: "", button: "", confirm: false });
    const existing = srv.optional_dialogs || [];
    const toBody = (x) => ({ dialog_name: x.dialog_name, text: x.text.text, button_label: x.button_label, confirm_no_data: true });
    const save = async (dialogs) => {
      try { const out = await api("PUT", `/api/drafts/${encodeURIComponent(draftOf(flow()).id)}/optional-dialogs`, { expected_revision: draftOf(flow()).revision, dialogs }); draftOf(flow()).revision = out.revision; live.dlgForm = null; await refreshLive(); }
      catch (e) { liveStatus(errText(e), "error"); }
    };
    const input = (key, label) => { const i = h("input", { type: "text", id: `pd-dlg-${key}`, value: form[key], maxlength: "200", autocomplete: "off", oninput: (e) => { form[key] = e.target.value; } }); return h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: i.id }, label), i); };
    return h("div", { class: "pd-live__block" }, h("p", { class: "pd-live__label" }, "İsteğe bağlı pencereler"),
      existing.length ? h("ul", { id: "pd-optional-dialogs" }, existing.map((x, i) => h("li", null, `${x.dialog_name} → ${x.button_label} `,
        h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", onclick: () => save(existing.filter((_, n) => n !== i).map(toBody)) }, "Kaldır")))) : h("p", { class: "pd-help" }, "Tanım yok: beklenmeyen pencere çıkarsa işlem durur."),
      input("name", "Pencerenin adı"), input("text", "Pencerede geçen metin"), input("button", "Basılacak düğme"),
      h("label", { class: "pd-check-row", for: "pd-dlg-confirm" }, h("input", { type: "checkbox", id: "pd-dlg-confirm", checked: form.confirm, onchange: (e) => { form.confirm = e.target.checked; } }), h("span", null, "Bu pencere yalnız bilgi verir; düğme kayıt yapmaz")),
      h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", id: "pd-dlg-add", onclick: () => {
        if (!form.name.trim() || !form.text.trim() || !form.button.trim()) { liveStatus("Ad, metin ve düğme gerekli.", "warn"); return; }
        if (!form.confirm) { liveStatus("Düğmenin kayıt yapmadığını onaylayın. Veri değiştiren pencere onaylı işlem olarak tanımlanır.", "warn"); return; }
        save([...existing.map(toBody), { dialog_name: form.name.trim(), text: form.text.trim(), button_label: form.button.trim(), confirm_no_data: true }]);
      } }, "Pencereyi ekle"));
  }
  // Tarih alanı: biçim analistçe beyan edilir; takvim açılır penceresi desteklenmez.
  function dateBox(s) {
    const formats = ["DD.MM.YYYY", "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"];
    const sel = h("select", { id: `${s.id}-date-format`, onchange: (e) => { s.dateFormat = e.target.value; refreshDerived(); } }, formats.map((x) => h("option", { value: x }, x)));
    sel.value = s.dateFormat || formats[0];
    return h("div", null, h("label", { class: "pd-check-row", for: `${s.id}-is-date` },
      h("input", { type: "checkbox", id: `${s.id}-is-date`, checked: !!s.isDate, onchange: (e) => { s.isDate = e.target.checked; s.dateFormat = s.dateFormat || formats[0]; refreshDerived(); rerenderEditorKeepFocus(); } }),
      h("span", null, "Bu bir tarih alanı")),
    s.isDate ? h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: sel.id }, "Tarih biçimi"), sel,
      h("p", { class: "pd-help" }, "Değer bu biçimde beklenir; geçersiz tarih alana yazılmaz. Sonuç tarih olarak okunarak doğrulanır. Yalnız takvimden seçim kabul eden alanlar bu sürümde desteklenmez.")) : null);
  }
  function realTargetQuestion(s, title, realOnly) {
    const q1 = questionBox(`${s.id}-q1`, "1", title);
    const tMsg = msgEl(`${s.id}-target-msg`, "target");
    const changing = !s.target || state.changingTarget.has(s.id);
    if (s.target) {
      const toggle = h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", id: `${s.id}-change`, "aria-expanded": changing ? "true" : "false",
        onclick: () => { if (changing) state.changingTarget.delete(s.id); else state.changingTarget.add(s.id); renderEditor(); byId(`${s.id}-change`)?.focus(); } }, changing ? "Vazgeç" : "Değiştir");
      q1.append(h("div", { class: "pd-chosen" }, h("div", { class: "pd-chosen__main" },
        h("p", { class: "pd-chosen__name", id: `${s.id}-chosen` }, `${s.target.section ? `${s.target.section} › ` : ""}${s.target.label || "(etiketsiz)"}`),
        h("p", { class: "pd-chosen__meta", id: `${s.id}-check` }, checkText(s.target.check))), toggle));
      linkMsg(toggle, tMsg);
    }
    q1.append(tMsg);
    if (changing && state.source === "real") q1.append(...realAlternatives(s, tMsg));
    else if (changing) q1.append(h("p", { class: "pd-msg pd-msg--missing" }, realOnly));
    return q1;
  }
  const radioRow = (s, group, value, current, name, desc, set) => h("div", { class: "pd-choice" }, h("label", { class: "pd-choice__label", for: `${s.id}-${group}-${value}` },
    h("input", { type: "radio", name: `${s.id}-${group}`, id: `${s.id}-${group}-${value}`, checked: current === value, onchange: set }),
    h("span", { class: "pd-choice__name" }, name), desc ? h("span", { class: "pd-choice__desc" }, desc) : null));
  function editorBack(s) {
    const q = questionBox(`${s.id}-q1`, "1", "Pencere nasıl kapanacak?");
    q.append(h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Pencerenin kapanışı"),
      radioRow(s, "close", "sys", s.closeWindow ? "sys" : "app", "Sistem kapatsın", "Pencerenin işi bittiğinde kapatılır.", () => { s.closeWindow = true; refreshDerived(); }),
      radioRow(s, "close", "app", s.closeWindow ? "sys" : "app", "Uygulama kendisi kapatıyor", "Önceki adım pencereyi kapatmalı; kapanmazsa işlem durur.", () => { s.closeWindow = false; refreshDerived(); }),
      msgEl(`${s.id}-back-msg`, "back")),
    h("p", { class: "pd-help" }, "Dönüşten sonra yeni pencereyi açan adımdaki ekran yeniden doğrulanır; tanınmazsa sonraki adım başlamaz."));
    return [q];
  }
  function editorMulti(s) {
    const q1 = realTargetQuestion(s, "Hangi çoklu seçim alanı?", "“Çoklu seçim” yalnız gerçek oturumda çalışır. Üstten “Gerçek oturum”u seçin.");
    const info = choiceInfo(s);
    const usable = usableOptions(info);
    const q2 = questionBox(`${s.id}-q-opts`, "2", "Hangi seçenekler kalsın?");
    q2.append(h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Değer kaynağı"),
      radioRow(s, "src", "fixed", s.source, "Sabit küme", "Her çalıştırmada aynı seçenekler kalır.", () => { s.source = "fixed"; refreshDerived(); rerenderEditorKeepFocus(); }),
      radioRow(s, "src", "ask", s.source, "Her çalıştırmada sor", "Kullanıcı İşlem Asistanı'nda seçenekleri işaretler.", () => { s.source = "ask"; refreshDerived(); rerenderEditorKeepFocus(); })));
    if (s.source === "fixed") {
      q2.append(h("div", { id: `${s.id}-options` }, usable.map((o) => h("label", { class: "pd-check-row" },
        h("input", { type: "checkbox", checked: s.fixedSet.includes(o.label), onchange: (e) => { s.fixedSet = e.target.checked ? [...s.fixedSet, o.label] : s.fixedSet.filter((x) => x !== o.label); refreshDerived(); } }), h("span", null, o.label)))));
      if (!usable.length) q2.append(h("p", { class: "pd-help" }, "Seçenekler alan seçildiğinde güncel ekrandan okunur."));
    } else {
      const q = h("input", { type: "text", id: `${s.id}-question`, maxlength: "100", value: s.question, autocomplete: "off", oninput: (e) => { s.question = e.target.value; refreshDerived(); } });
      q2.append(h("label", { class: "pd-label", for: q.id }, "Kullanıcıya sorulacak metin"), q);
    }
    q2.append(msgEl(`${s.id}-set-msg`, "set"), h("p", { class: "pd-help" }, "Alan çalışırken tam olarak bu kümeye getirilir: fazla seçenekler kaldırılır. Üyelerden biri yoksa veya devre dışıysa hiçbir değişiklik yapılmaz."));
    const q3 = questionBox(`${s.id}-q-effect`, "3", "Bu değişiklik ne yapar?");
    q3.append(h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Değişikliğin etkisi"),
      radioRow(s, "effect", "ui_local", s.effect, "Yalnız bu alanın seçimini değiştirir", "Kayıt yapmaz, ekran değiştirmez.", () => { s.effect = "ui_local"; refreshDerived(); rerenderEditorKeepFocus(); }),
      radioRow(s, "effect", "unknown", s.effect, "Kayıt veya ekran değişikliği tetikleyebilir / emin değilim", "Açık onay istenir; sonuç belirsizse otomatik tekrarlanmaz.", () => { s.effect = "unknown"; s.successCheck = "auto"; refreshDerived(); rerenderEditorKeepFocus(); }),
      msgEl(`${s.id}-effect-msg`, "effect")));
    return [q1, q2, q3];
  }
  function editorUpload(s) {
    const q1 = realTargetQuestion(s, "Hangi dosya alanı?", "“Dosya yükle” yalnız gerçek oturumda çalışır. Üstten “Gerçek oturum”u seçin.");
    const q2 = questionBox(`${s.id}-q2`, "2", "Hangi dosya istensin?");
    const q = h("input", { type: "text", id: `${s.id}-question`, maxlength: "100", value: s.question, autocomplete: "off", oninput: (e) => { s.question = e.target.value; refreshDerived(); } });
    const qm = msgEl(`${s.id}-question-msg`, "question"); linkMsg(q, qm);
    const types = [["application/pdf", "PDF"], ["image/png", "PNG"], ["image/jpeg", "JPEG"], ["text/plain", "Düz metin"]];
    q2.append(h("label", { class: "pd-label", for: q.id }, "Kullanıcıya sorulacak metin"), q, qm,
      h("div", null, types.map(([v, n]) => h("label", { class: "pd-check-row" }, h("input", { type: "checkbox", checked: s.fileTypes.includes(v), onchange: (e) => { s.fileTypes = e.target.checked ? [...s.fileTypes, v] : s.fileTypes.filter((x) => x !== v); refreshDerived(); } }), h("span", null, n)))),
      h("p", { class: "pd-help" }, "Hiçbiri işaretlenmezse sistemin izin verdiği türler kabul edilir. Dosya yalnız yetkili depodan gönderilir; bilgisayardaki bir yol kullanılamaz."));
    const q3 = questionBox(`${s.id}-q3`, "3", "Sonuç nasıl kanıtlansın?");
    const result = h("input", { type: "text", id: `${s.id}-result`, maxlength: "300", value: s.resultText, autocomplete: "off", oninput: (e) => { s.resultText = e.target.value; refreshDerived(); } });
    const rm = msgEl(`${s.id}-result-msg`, "result"); linkMsg(result, rm);
    q3.append(h("label", { class: "pd-label", for: result.id }, "Ekranda görünmesi gereken durum mesajı (zorunlu)"), result, rm,
      h("p", { class: "pd-help" }, "Yükleme veri etkisi sayılır, açık onay ister. Mesaj görünmezse işlem başarılı sayılmaz ve dosya yeniden gönderilmez."));
    return [q1, q2, q3];
  }

  // ---------- İşaretle / kaldır (yalnız gerçek oturum) ----------
  function editorCheck(s, f, a) {
    const q1 = questionBox(`${s.id}-q1`, "1", "Hangi onay kutusu?");
    const tMsg = msgEl(`${s.id}-target-msg`, "target");
    const changing = !s.target || state.changingTarget.has(s.id);
    if (s.target) {
      const toggle = h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", id: `${s.id}-change`, "aria-expanded": changing ? "true" : "false",
        onclick: () => { if (changing) state.changingTarget.delete(s.id); else state.changingTarget.add(s.id); renderEditor(); byId(`${s.id}-change`)?.focus(); } }, changing ? "Vazgeç" : "Değiştir");
      q1.append(h("div", { class: "pd-chosen" }, h("div", { class: "pd-chosen__main" },
        h("p", { class: "pd-chosen__name", id: `${s.id}-chosen` }, `${s.target.section ? `${s.target.section} › ` : ""}${s.target.label || "(etiketsiz)"}`),
        h("p", { class: "pd-chosen__meta", id: `${s.id}-check` }, checkText(s.target.check))), toggle));
      linkMsg(toggle, tMsg);
    }
    q1.append(tMsg);
    if (changing && state.source === "real") q1.append(...realAlternatives(s, tMsg));
    else if (changing) q1.append(h("p", { class: "pd-msg pd-msg--missing" }, "“İşaretle / kaldır” yalnız gerçek oturumda çalışır. Üstten “Gerçek oturum”u seçin."));
    const radio = (group, value, current, name, desc, set) => h("div", { class: "pd-choice" }, h("label", { class: "pd-choice__label", for: `${s.id}-${group}-${value}` },
      h("input", { type: "radio", name: `${s.id}-${group}`, id: `${s.id}-${group}-${value}`, checked: current === value, onchange: set }),
      h("span", { class: "pd-choice__name" }, name), desc ? h("span", { class: "pd-choice__desc" }, desc) : null));
    const q2 = questionBox(`${s.id}-q2`, "2", "Son durum ne olsun?");
    q2.append(h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Kutunun son durumu"),
      radio("wanted", "on", s.checked === null ? null : s.checked ? "on" : "off", "İşaretli olsun", "", () => { s.checked = true; refreshDerived(); }),
      radio("wanted", "off", s.checked === null ? null : s.checked ? "on" : "off", "İşaretsiz olsun", "", () => { s.checked = false; refreshDerived(); }),
      msgEl(`${s.id}-wanted-msg`, "wanted")));
    const q3 = questionBox(`${s.id}-q-effect`, "3", "Bu değişiklik ne yapar?");
    q3.append(h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Değişikliğin etkisi"),
      radio("effect", "ui_local", s.effect, "Yalnız bu kutunun durumunu değiştirir", "Kayıt yapmaz, ekran değiştirmez. Bundan eminseniz seçin.", () => { s.effect = "ui_local"; refreshDerived(); rerenderEditorKeepFocus(); }),
      radio("effect", "unknown", s.effect, "Kayıt veya ekran değişikliği tetikleyebilir / emin değilim", "Açık onay istenir; sonuç belirsizse otomatik tekrarlanmaz.", () => { s.effect = "unknown"; s.successCheck = "auto"; refreshDerived(); rerenderEditorKeepFocus(); }),
      msgEl(`${s.id}-effect-msg`, "effect")));
    const q4 = questionBox(`${s.id}-q3`, "4", "Sonuç nasıl kontrol edilsin?");
    q4.append(h("fieldset", { class: "pd-choices" }, h("legend", { class: "pd-visually-hidden" }, "Sonuç kontrolü"),
      radio("verify", "auto", s.successCheck || "auto", "Kutunun durumunu okuyarak doğrula (önerilen)", "Tıklamanın bitmesi yetmez; kutunun gerçek durumu okunur.", () => { s.successCheck = "auto"; refreshDerived(); }),
      s.effect === "unknown" ? null : radio("verify", "none", s.successCheck || "auto", "Ek kontrol yapma", "Durum yalnız uygulanırken doğrulanır.", () => { s.successCheck = "none"; refreshDerived(); })));
    const result = h("input", { type: "text", id: `${s.id}-result`, maxlength: "300", value: s.resultText, autocomplete: "off", oninput: (e) => { s.resultText = e.target.value; refreshDerived(); } });
    const rm = msgEl(`${s.id}-result-msg`, "result"); linkMsg(result, rm);
    q4.append(h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: result.id }, "Ekranda görünmesi gereken durum mesajı (isteğe bağlı)"), result, rm));
    return [q1, q2, q3, q4];
  }

  // ---------- Onaylı işlem (yalnız gerçek oturum; katalogdaki onaylı aksiyonlar) ----------
  async function loadActions() {
    if (real.actions) return;
    try { real.actions = (await api("GET", "/api/actions")).actions || []; } catch (_) { real.actions = []; }
    if (state.view === "editor") { renderSteps(); renderEditor(); }
  }
  function editorAction(s, f, a) {
    const out = [];
    if (!real.actions) { loadActions(); return [h("p", { class: "pd-help", role: "status" }, "Onaylı işlemler yükleniyor…")]; }
    const sel = h("select", { id: `${s.id}-action`,
      onchange: (e) => {
        s.actionId = e.target.value; s.bindings = {};
        const act = real.actions.find((x) => x.action_id === s.actionId);
        if (act) for (const prm of act.params) s.bindings[prm.name] = { ...newBinding(), source: "ask", question: `${prm.title} nedir?`, questionSuggested: true };
        refreshDerived(); rerenderEditorKeepFocus();
      } }, h("option", { value: "" }, "Seçin…"), real.actions.filter((x) => !x.application_id || x.application_id === f.applicationId).map((x) => h("option", { value: x.action_id }, x.title)));
    sel.value = s.actionId;
    const m = msgEl(`${s.id}-action-msg`, "action"); linkMsg(sel, m);
    out.push(h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: sel.id }, "Hangi onaylı işlem?"), sel, m,
      h("p", { class: "pd-help" }, "Yalnız kurumca tanımlanmış ve onaylanmış işlemler listelenir; serbest tıklama veya yeni işlem tanımlanmaz.")));
    const act = real.actions.find((x) => x.action_id === s.actionId);
    if (act) {
      out.push(h("p", { class: "pd-msg pd-msg--missing", id: `${s.id}-effect` }, effectText(act)));
      const outputs = outputsBefore(f.steps, a.index).filter((o) => o.read);
      for (const prm of act.params) {
        if (!s.bindings[prm.name]) s.bindings[prm.name] = { ...newBinding(), source: "ask", question: `${prm.title} nedir?` };
        const q = questionBox(`${s.id}-in-${prm.name}-q`, null, `“${prm.title}” değeri nereden gelsin?`);
        q.append(bindingEditor(s.bindings[prm.name], { label: prm.title, maxLength: prm.max_length }, outputs, `${s.id}-in-${prm.name}`, `input:${prm.name}:`, `“${prm.title}” değeri nereden gelsin?`));
        out.push(q);
      }
    }
    return out;
  }

  function choseField(s, fd, via) {
    applyTarget(s, fd);
    state.changingTarget.delete(s.id);
    renderSteps(); renderEditor(); renderFlowBar(true);
    toast(`“${fd.section} › ${fd.label}” seçildi (${via}). Uygulamada işlem yapılmadı.`);
    byId(`${s.id}-change`)?.focus();
  }

  // ---------- Değer kaynağı seçici (alan doldur ve bileşen girdileri) ----------
  function bindingEditor(b, meta, outputs, idp, prefix, legendText) {
    const fs = h("fieldset", { class: "pd-choices" },
      h("legend", { class: "pd-visually-hidden" }, legendText || "Değer nereden gelsin?"));
    const srcMsg = msgEl(`${idp}-src-msg`, prefix + "source");
    const choice = (value, name, desc, extra, disabled) => {
      const id = `${idp}-src-${value}`;
      const radio = h("input", {
        type: "radio", name: `${idp}-src`, id, value, checked: b.source === value, disabled,
        onchange: () => { b.source = value; refreshDerived(); rerenderEditorKeepFocus(); },
      });
      return h("div", { class: "pd-choice" },
        h("label", { class: "pd-choice__label", for: id },
          radio, h("span", { class: "pd-choice__name" }, name), h("span", { class: "pd-choice__desc" }, desc)),
        b.source === value && extra ? h("div", { class: "pd-choice__extra" }, extra) : null);
    };

    let fixedExtra = null; let askExtra = null; let prevExtra = null;
    if (b.source === "fixed" && meta && meta.fixedEditor) {
      fixedExtra = meta.fixedEditor(idp, prefix);
    } else if (b.source === "fixed") {
      const inp = h("input", {
        type: "text", id: `${idp}-fixed-value`, value: b.fixedValue, autocomplete: "off",
        maxlength: meta && meta.maxLength ? String(meta.maxLength + 20) : "200",
        inputmode: meta && (meta.digits || meta.kind === "amount") ? "decimal" : null,
        oninput: (e) => { b.fixedValue = e.target.value; refreshDerived(); },
      });
      const m = msgEl(`${idp}-fixed-msg`, prefix + "fixed"); linkMsg(inp, m);
      fixedExtra = [h("label", { class: "pd-label", for: inp.id }, "Yazılacak değer"), inp, m];
    }
    if (b.source === "ask") {
      const tagId = `${idp}-question-tag`;
      const inp = h("input", {
        type: "text", id: `${idp}-question`, value: b.question, maxlength: "120", autocomplete: "off",
        oninput: (e) => { b.question = e.target.value; b.questionSuggested = false; byId(tagId)?.remove(); refreshDerived(); },
      });
      const m = msgEl(`${idp}-question-msg`, prefix + "question"); linkMsg(inp, m);
      askExtra = [
        h("label", { class: "pd-label", for: inp.id }, "Çalıştırırken ne sorulsun?"), inp, m,
        b.questionSuggested ? h("p", { class: "pd-sug-note", id: tagId },
          h("span", { class: "pd-badge pd-badge--suggest" }, state.source === "real" ? "Önerilen soru" : "Önerilen soru · temsili"), "İsterseniz değiştirin.") : null,
        ...(meta && meta.askExtra ? meta.askExtra(idp) : []),
      ];
    }
    if (b.source === "previous") {
      const sel = h("select", {
        id: `${idp}-previous`,
        onchange: (e) => { b.previousRef = e.target.value; refreshDerived(); },
      }, h("option", { value: "" }, "Seçin…"), outputs.map((o) => h("option", { value: o.ref }, o.label)));
      if (b.previousRef && !outputs.some((o) => o.ref === b.previousRef)) sel.append(h("option", { value: b.previousRef }, "Geçersiz kaynak"));
      sel.value = b.previousRef;
      const m = msgEl(`${idp}-previous-msg`, prefix + "previous"); linkMsg(sel, m);
      prevExtra = [h("label", { class: "pd-label", for: sel.id }, "Hangi adımın değeri?"), sel, m];
    }
    const noOutputs = !outputs.length && b.source !== "previous";
    fs.append(
      choice("fixed", (meta && meta.fixedName) || "Sabit değer", (meta && meta.fixedDesc) || "Her çalıştırmada aynı değer yazılır.", fixedExtra),
      choice("ask", "Her çalıştırmada sor", "İşlemi başlatan kişiden istenir.", askExtra),
      choice("previous", "Önceki adımın çıktısı",
        noOutputs ? "Bu adımdan önce değer üreten bir adım yok." : (meta && meta.previousDesc) || "Daha önce yazılan bir değeri yeniden kullanır.",
        prevExtra, noOutputs),
      srcMsg);
    return fs;
  }

  // ---------- Ayrıntılar: otomatik hazırlanan ad/açıklama, not ve teknik bilgiler ----------
  function detailsSection(s) {
    const parts = [];
    if (s.type === "fill") {
      const sug = s.target ? suggestFor(s.target) : null;
      if (s.target && (s.suggested.name || s.suggested.description)) {
        parts.push(h("p", { class: "pd-sug-note" }, h("span", { class: "pd-badge pd-badge--suggest" }, state.source === "real" ? "Otomatik öneri" : "Otomatik · temsili öneri"),
          "Ad ve açıklama seçilen alandan hazırlandı; değiştirebilirsiniz."));
      }
      parts.push(h("div", { class: "pd-field" },
        h("label", { class: "pd-label", for: `${s.id}-name` }, "Adım adı"),
        h("input", {
          type: "text", id: `${s.id}-name`, maxlength: "60", value: s.name, autocomplete: "off",
          placeholder: sug ? sug.name : "Alan seçilince önerilir",
          oninput: (e) => { s.name = e.target.value; s.suggested.name = false; refreshDerived(); },
        })));
      parts.push(h("div", { class: "pd-field" },
        h("label", { class: "pd-label", for: `${s.id}-desc` }, "Alanın açıklaması"),
        h("textarea", {
          id: `${s.id}-desc`, rows: "3", maxlength: "300", value: s.description,
          placeholder: "Alan seçilince önerilir.",
          oninput: (e) => { s.description = e.target.value; s.suggested.description = false; },
        })));
    }
    parts.push(h("div", { class: "pd-field" },
      h("label", { class: "pd-label", for: `${s.id}-note` }, "Not (isteğe bağlı)"),
      h("textarea", {
        id: `${s.id}-note`, rows: "2", maxlength: "300", value: s.note,
        placeholder: "Örn. Yalnız kefilli başvurularda gerekir.",
        "aria-describedby": `${s.id}-note-help`,
        oninput: (e) => { s.note = e.target.value; },
      }),
      h("p", { class: "pd-help", id: `${s.id}-note-help` }, "Sistem adımın iş sonucunu ekrandan bilemez; gerekiyorsa siz yazın.")));

    const tech = [h("p", { class: "pd-subhead" }, "Teknik bilgiler")];
    if (s.type === "fill" && s.target) {
      tech.push(h("p", null, "Anlamsal hedef: ", h("code", null, s.target.source === "real"
        ? JSON.stringify(realSpec(s.target))
        : `ekran=${s.target.screen} · bölüm=${s.target.section} · etiket=${s.target.label} · tür=${s.target.kind}`)));
      if (s.binding.source === "ask") tech.push(h("p", null, "Parametre adı (otomatik, sizden istenmez): ", h("code", null, slug(s.name || suggestFor(s.target).name) || "—")));
    }
    if (s.type === "goto" && s.button) {
      tech.push(h("p", null, "Anlamsal hedef: ", h("code", null, `ekran=${s.button.screen} · düğme=${s.button.label}`)));
    }
    tech.push(h("p", null, "Kalıcı seçici, DOM kimliği, frame yolu veya koordinat saklanmaz; hedef çalışırken yeniden bulunur. Aşağıdaki gösterim sayfa içi taslaktır, katalog sözleşmesi değildir."));
    tech.push(h("pre", null, JSON.stringify(s, null, 2)));
    parts.push(h("div", { class: "pd-tech" }, tech));

    const det = h("details", { class: "pd-details", open: state.openDetails.has(s.id) },
      h("summary", null, "Ayrıntılar"), h("div", { class: "pd-details__body" }, parts));
    det.addEventListener("toggle", () => { if (det.open) state.openDetails.add(s.id); else state.openDetails.delete(s.id); });
    return det;
  }

  // ---------- Ekrana geç ----------
  // Gerçek oturum: düğme gerçek ekrandan seçilir; açılacak ekranın adı analistten alınır (sistem tahmin etmez).
  // Tasarım sırasında sistem düğmeye basmaz; sonraki ekranın alanlarını seçmek için düğmeye tarayıcıda siz basarsınız.
  function editorGotoReal(s) {
    const out = [];
    const box = questionBox(`${s.id}-q1`, "1", "Hangi düğme?");
    const bMsg = msgEl(`${s.id}-button-msg`, "button");
    const changing = !s.button || state.changingTarget.has(s.id);
    if (s.button) {
      const toggle = h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", id: `${s.id}-change`,
        "aria-expanded": changing ? "true" : "false",
        onclick: () => { if (changing) state.changingTarget.delete(s.id); else state.changingTarget.add(s.id); renderEditor(); byId(`${s.id}-change`)?.focus(); } },
      changing ? "Vazgeç" : "Değiştir");
      box.append(h("div", { class: "pd-chosen" }, h("div", { class: "pd-chosen__main" },
        h("p", { class: "pd-chosen__name", id: `${s.id}-chosen` }, `“${s.button.label || "(adsız)"}” ${s.button.kind === "link" ? "bağlantısı" : s.button.kind === "tab" ? "sekmesi" : "düğmesi"}${s.button.section ? ` · ${s.button.section}` : ""}`),
        h("p", { class: "pd-chosen__meta", id: `${s.id}-check` }, checkText(s.button.check))), toggle));
      linkMsg(toggle, bMsg);
    }
    box.append(bMsg);
    if (changing) box.append(...realAlternatives(s, bMsg));
    out.push(box);
    const q2 = questionBox(`${s.id}-q2`, "2", "Sonra ne olmalı?");
    const inp = h("input", { type: "text", id: `${s.id}-expect`, maxlength: "80", value: s.expectName, autocomplete: "off",
      oninput: (e) => { s.expectName = e.target.value; refreshDerived(); } });
    const em = msgEl(`${s.id}-expect-msg`, "expect"); linkMsg(inp, em);
    const cb = h("input", { type: "checkbox", id: `${s.id}-confirm`, checked: s.confirmNoData,
      onchange: (e) => { s.confirmNoData = e.target.checked; refreshDerived(); } });
    const cm = msgEl(`${s.id}-confirm-msg`, "confirm"); linkMsg(cb, cm);
    q2.append(
      h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: inp.id }, "Düğmeye basınca açılacak ekranın adı"), inp, em,
        h("p", { class: "pd-help" }, "Bunu siz belirtirsiniz; sistem tahmin etmez. Ekranı, açıldığında “Gerçek deneme ve yayın” panelindeki “Ekranı tanıt” ile tanıtırsınız.")),
      h("div", null, h("label", { class: "pd-check-row", for: cb.id }, cb,
        h("span", null, "Bu düğmenin yalnız ekran değiştirdiğini biliyorum; veri kaydetmez veya göndermez.")), cm),
      h("p", { class: "pd-help" }, "Tasarım sırasında sistem bu düğmeye basmaz. Sonraki ekranın alanlarını seçmek için düğmeye tarayıcıda kendiniz basın."));
    out.push(q2);
    return out;
  }

  function editorGoto(s) {
    if (state.source === "real" || isRealGoto(s)) return editorGotoReal(s);
    const out = [];
    const box = questionBox(`${s.id}-q1`, "1", "Hangi düğme?");
    if (s.button) {
      box.append(h("div", { class: "pd-chosen" }, h("div", { class: "pd-chosen__main" },
        h("p", { class: "pd-chosen__name" }, `“${s.button.label}” düğmesi`),
        h("p", { class: "pd-chosen__meta" }, `${screenTitle(s.button.screen)} ekranı`))));
    }
    const pick = h("button", {
      type: "button", class: "pd-btn pd-btn--secondary", id: `${s.id}-pick`,
      onclick: () => openPicker(s.id, "button"),
    }, icon("target"), s.button ? "Başka düğme seç" : "Ekrandan düğme seç");
    const m = msgEl(`${s.id}-button-msg`, "button"); linkMsg(pick, m);
    box.append(pick, m);
    out.push(box);

    const q2 = questionBox(`${s.id}-q2`, "2", "Sonra ne olmalı?");
    const sel = h("select", {
      id: `${s.id}-expect`,
      onchange: (e) => { s.expectScreen = e.target.value; refreshDerived(); },
    }, h("option", { value: "" }, "Seçin…"), Object.entries(SCREENS).map(([k, v]) => h("option", { value: k }, v.title)));
    sel.value = s.expectScreen;
    const em = msgEl(`${s.id}-expect-msg`, "expect"); linkMsg(sel, em);
    const cb = h("input", {
      type: "checkbox", id: `${s.id}-confirm`, checked: s.confirmNoData,
      onchange: (e) => { s.confirmNoData = e.target.checked; refreshDerived(); },
    });
    const cm = msgEl(`${s.id}-confirm-msg`, "confirm"); linkMsg(cb, cm);
    q2.append(
      h("div", { class: "pd-field" },
        h("label", { class: "pd-label", for: sel.id }, "Düğmeye basınca hangi ekran açılmalı?"), sel, em,
        h("p", { class: "pd-help" }, "Bunu siz belirtirsiniz; sistem tahmin etmez.")),
      h("div", null,
        h("label", { class: "pd-check-row", for: cb.id }, cb,
          h("span", null, "Bu düğmenin yalnız ekran değiştirdiğini biliyorum; veri kaydetmez veya göndermez.")), cm));
    out.push(q2);
    return out;
  }

  // ---------- Akış çağır ----------
  function defaultBindings(c) {
    const out = {};
    for (const inp of c.inputs) out[inp.key] = { ...newBinding(), source: "ask", question: inp.question, questionSuggested: false };
    return out;
  }
  // E: yayımlanmış ve onaylı bir işlemi belirli sürümüyle çağırır (bileşen). Sürüm kendiliğinden değişmez.
  async function loadPublished() {
    const d = draftOf(flow());
    if (!d.id) return;
    try { real.published = (await api("GET", `/api/drafts/${encodeURIComponent(d.id)}/components`)).components; real.publishedError = ""; }
    catch (e) { real.published = []; real.publishedError = errText(e); }
    if (state.view === "editor") { renderSteps(); renderEditor(); }
  }
  // Taslağı (adımsız) sunucuda açar; adımlar yine “Taslağı kaydet” ile yazılır.
  async function ensureDraft() {
    const f = flow(); const d = draftOf(f);
    if (d.id) return true;
    if (!f.name.trim()) { draftStatus("Önce akışa bir ad verin.", "warn"); byId("pd-flow-name").focus(); return false; }
    if (!f.applicationId) { draftStatus("Önce uygulamayı seçin.", "warn"); return false; }
    try {
      const server = await api("POST", "/api/drafts", { application_id: f.applicationId, operation_id: `${safeSlug(f.name, "islem")}_${rand4()}`, title: f.name.trim().slice(0, 200), description: "" });
      d.id = server.draft_id; d.revision = server.revision; d.savedSig = "";
      renderDraftBar();
      return true;
    } catch (e) { draftStatus(errText(e), "error"); return false; }
  }
  function editorCallPublished(s, f, a) {
    const d = draftOf(f);
    if (!d.id || !real.published) {
      return [h("p", { class: "pd-help" }, "Bileşenler yayımlanmış ve onaylı katalogdan listelenir. Liste için akış sunucuda taslak olarak açılır (adımlar kaydetmede yazılır)."),
        h("button", { type: "button", class: "pd-btn pd-btn--secondary", id: `${s.id}-load-published`, onclick: async () => { if (await ensureDraft()) loadPublished(); } }, "Yayımlanmış bileşenleri getir")];
    }
    const out = [];
    if (real.publishedError) out.push(h("p", { class: "pd-msg pd-msg--error" }, real.publishedError));
    const key = (c) => `${c.operation_id}@${c.revision}`;
    const sel = h("select", { id: `${s.id}-published`,
      onchange: (e) => {
        const c = real.published.find((x) => key(x) === e.target.value) || null;
        s.published = c ? clone(c) : null; s.bindings = {};
        if (c) for (const inp of c.inputs) s.bindings[inp.name] = { ...newBinding(), source: "ask", question: `${inp.title} nedir?`, questionSuggested: true };
        refreshDerived(); rerenderEditorKeepFocus();
      } }, h("option", { value: "" }, "Seçin…"), real.published.map((c) => h("option", { value: key(c) }, `${c.title} · sürüm ${c.revision}`)));
    if (s.published && !real.published.some((x) => key(x) === key(s.published))) sel.append(h("option", { value: key(s.published) }, `${s.published.title} · sürüm ${s.published.revision} (sabitlenmiş)`));
    sel.value = s.published ? key(s.published) : "";
    const m = msgEl(`${s.id}-component-msg`, "component"); linkMsg(sel, m);
    out.push(h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: sel.id }, "Hangi bileşen?"), sel, m,
      h("p", { class: "pd-help" }, "Yalnız yayımlanmış ve onaylı işlemler listelenir. Seçilen sürüm sabitlenir; bileşenin yeni sürümü bu akışı kendiliğinden değiştirmez.")));
    if (s.published) {
      const c = s.published;
      out.push(h("p", { class: c.effect === "mutating" ? "pd-msg pd-msg--missing" : "pd-help" },
        c.effect === "mutating" ? "İş etkisi: bileşen veri değiştiren onaylı işlem içerir." : "İş etkisi: bileşen yalnız alanlara yazar/okur; kayıt yapmaz."),
      h("p", { class: "pd-help" }, `Ekran: “${c.start_screen}” ekranında başlar, “${c.end_screen}” ekranında biter.`),
      c.outputs.length ? h("p", { class: "pd-help" }, `Çıktılar (sonraki adımlarda “Önceki adımın çıktısı”): ${c.outputs.map((o) => o.title).join(", ")}.`) : null);
      const outputs = outputsBefore(f.steps, a.index).filter((o) => o.read);
      for (const inp of c.inputs) {
        if (!s.bindings[inp.name]) s.bindings[inp.name] = { ...newBinding(), source: "ask", question: `${inp.title} nedir?` };
        const q = questionBox(`${s.id}-in-${inp.name}-q`, null, `“${inp.title}” değeri nereden gelsin?`);
        q.append(bindingEditor(s.bindings[inp.name], { label: inp.title, maxLength: inp.max_length }, outputs, `${s.id}-in-${inp.name}`, `input:${inp.name}:`, `“${inp.title}” değeri nereden gelsin?`));
        out.push(q);
      }
    }
    return out;
  }
  function editorCall(s, f, a) {
    if (state.source === "real" || s.published) return editorCallPublished(s, f, a);
    const out = [];
    const sel = h("select", {
      id: `${s.id}-component`,
      onchange: (e) => {
        s.componentId = e.target.value;
        const c = findComp(s.componentId);
        s.bindings = c ? defaultBindings(c) : {};
        refreshDerived(); rerenderEditorKeepFocus();
      },
    }, h("option", { value: "" }, "Seçin…"), appComponents().map((c) => h("option", { value: c.id }, c.name)));
    sel.value = s.componentId;
    const m = msgEl(`${s.id}-component-msg`, "component"); linkMsg(sel, m);
    out.push(h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: sel.id }, "Hangi bileşen?"), sel, m));
    const c = findComp(s.componentId);
    if (c) {
      out.push(h("section", { class: "pd-q" },
        h("h4", { class: "pd-q__title" }, "Bileşenin adımları"),
        h("ol", { class: "pd-inner-steps" }, c.steps.map((x) => h("li", null, summarize(x, c.steps))))));
      const outputs = outputsBefore(f.steps, a.index);
      for (const inp of c.inputs) {
        if (!s.bindings[inp.key]) s.bindings[inp.key] = defaultBindings(c)[inp.key];
        const q = questionBox(`${s.id}-in-${inp.key}-q`, null, `“${inp.name}” değeri nereden gelsin?`);
        q.append(bindingEditor(s.bindings[inp.key], inp, outputs, `${s.id}-in-${inp.key}`, `input:${inp.key}:`, `“${inp.name}” değeri nereden gelsin?`));
        out.push(q);
      }
      if (!c.inputs.length) out.push(h("p", { class: "pd-help" }, "Bu bileşen değer istemez."));
    }
    return out;
  }

  // ===================================================================
  // Temsili uygulamayı çizme (seçim ve deneme modları)
  // ===================================================================
  function renderMock(host, mock, mode, onPick) {
    const sc = SCREENS[mock.screen];
    const sections = sc.sections.map((sec) => {
      if (mode === "view" && mock.hiddenSections && mock.hiddenSections.includes(sec.name)) {
        return h("fieldset", null, h("legend", null, sec.name), h("p", { class: "pd-mock__missing" }, "(Bu senaryoda bölüm ekranda yok.)"));
      }
      return h("fieldset", null, h("legend", null, sec.name), sec.fields.map((fd) => {
        const field = { ...fd, screen: mock.screen, section: sec.name, owner: sec.owner };
        if (mode === "pick-field" || mode === "pick-button") {
          const allowed = mode === "pick-field";
          return h("button", {
            type: "button", class: "pd-pick" + (mock.currentKey === fd.key ? " is-current" : ""),
            "aria-disabled": allowed ? null : "true", "aria-current": mock.currentKey === fd.key ? "true" : null,
            "aria-label": `${field.label}, ${sec.name} bölümü, ${lower(KIND_TEXT[fd.kind])}${allowed ? " — bu alanı seç" : " — şu an düğme seçiliyor"}`,
            onclick: () => { if (allowed) onPick(field); },
          }, h("span", { class: "pd-pick__label" }, fd.label), h("span", { class: "pd-pick__fake" }, KIND_TEXT[fd.kind]));
        }
        const id = `mock-${host.id}-${fd.key}`;
        const val = mock.values[fd.key] || "";
        const cls = "pd-mock__field" + (mock.active === fd.key ? " is-active" : "") + (val ? " is-written" : "");
        const ctl = fd.kind === "textarea"
          ? h("textarea", { id, rows: "2", readonly: true, tabindex: "-1", value: val })
          : fd.kind === "select"
            ? h("select", { id, disabled: true, tabindex: "-1" }, h("option", null, "Seçin…"), fd.options.map((o) => h("option", null, o)))
            : h("input", { type: "text", id, readonly: true, tabindex: "-1", value: fd.kind === "readonly" ? "—" : val });
        return h("div", { class: cls }, h("label", { for: id }, fd.label), ctl);
      }));
    });
    const buttons = sc.buttons.map((b) => {
      const btn = { ...b, screen: mock.screen };
      if (mode === "pick-button" || mode === "pick-field") {
        const allowed = mode === "pick-button";
        return h("button", {
          type: "button", class: "pd-pick pd-pick--button",
          "aria-disabled": allowed ? null : "true",
          "aria-label": `${b.label} düğmesi${allowed ? " — bu düğmeyi seç" : " — şu an alan seçiliyor"}`,
          onclick: () => { if (allowed) onPick(btn); },
        }, b.label);
      }
      return h("span", { class: "pd-mock__btn" + (mock.activeButton === b.key ? " is-active" : "") }, b.label);
    });
    host.replaceChildren(h("div", { class: "pd-mock" },
      h("div", { class: "pd-mock__bar" }, h("strong", null, "Temsili ekranlar"),
        h("span", null, `${appName(flow().applicationId) || "Uygulama seçilmedi"} · gerçek bağlantı yok`)),
      h("div", { class: "pd-mock__screen" },
        h("p", { class: "pd-mock__title" }, sc.title),
        h("div", { class: "pd-mock__sections" }, sections),
        h("div", { class: "pd-mock__buttons" }, buttons),
        mock.notice ? h("p", { class: "pd-mock__notice", role: "status" }, mock.notice) : null)));
  }

  // ===================================================================
  // Alan/düğme seçme (yalnız temsili uygulamada; hiçbir eylem tetiklemez)
  // ===================================================================
  let picker = null;
  function openPicker(stepId, want) {
    if (!flow().applicationId) {
      toast("Önce akışın uygulamasını seçin.");
      byId("pd-flow-app").focus();
      return;
    }
    const s = findStep(stepId);
    const a = analyze(flow()).get(stepId);
    const initial = (want === "field" ? s.target && s.target.screen : s.button && s.button.screen) || a.screenBefore;
    picker = { stepId, want, screen: initial, returnFocus: document.activeElement };
    picker.currentKey = want === "field" ? (s.target && s.target.fieldKey) : (s.button && s.button.key);
    byId("pd-picker-title").textContent = want === "field" ? "Ekrandan kendim seçeyim" : "Basılacak düğmeyi seçin";
    byId("pd-picker-help").textContent = want === "field"
      ? "Değer yazılacak alana tıklayın. Önerilerde olmayan alanları da seçebilirsiniz. Seçim modunda uygulamada hiçbir şey yazılmaz veya kaydedilmez; gerçek tarayıcıya bağlanılmaz."
      : "Temsili uygulamada bir düğmeye tıklayın. Seçim modunda düğmeye basılmaz; yalnız hangi düğme olduğu kaydedilir.";
    drawPicker();
    byId("pd-picker").showModal();
    const firstPick = byId("pd-picker-app").querySelector(".pd-pick:not([aria-disabled])");
    if (firstPick) firstPick.focus();
  }
  function drawPicker() {
    const seg = byId("pd-picker-screens");
    seg.replaceChildren(...Object.entries(SCREENS).map(([k, v]) => h("button", {
      type: "button", "aria-pressed": picker.screen === k ? "true" : "false",
      onclick: () => { picker.screen = k; drawPicker(); seg.querySelector(`[aria-pressed="true"]`).focus(); },
    }, v.title)));
    renderMock(byId("pd-picker-app"), { screen: picker.screen, values: {}, currentKey: picker.currentKey }, picker.want === "field" ? "pick-field" : "pick-button", onPicked);
  }
  function onPicked(item) {
    const s = findStep(picker.stepId);
    if (picker.want === "field") {
      applyTarget(s, item);
      state.changingTarget.delete(s.id);
      toast(`“${item.section} › ${item.label}” ekrandan seçildi. Uygulamada işlem yapılmadı.`);
    } else {
      s.button = { screen: item.screen, key: item.key, label: item.label };
      toast(`“${item.label}” düğmesi seçildi. Düğmeye basılmadı.`);
    }
    byId("pd-picker").close();
    picker = null;
    renderSteps(); renderEditor(); renderFlowBar(true);
    const next = byId(`${s.id}-change`) || byId(`${s.id}-pick`);
    if (next) next.focus();
  }

  // ===================================================================
  // "Ne yapmak istiyorsunuz?" — temsili öneri (kurallı, model yok)
  // ===================================================================
  const SYNONYM = { numar: "no", nosu: "no", nolu: "no" };
  const stem = (w) => { const s = slug(w).slice(0, 5); return SYNONYM[s] || s; };
  const STOP = new Set(["bir", "ve", "ile", "icin", "bu", "su", "o", "alan", "alani", "alanina", "deger", "degeri", "lutfen"]);
  function tokens(text) {
    return lower(text).split(/[^0-9a-zçğıöşü]+/i).filter((w) => w.length > 1 && !STOP.has(slug(w))).map(stem);
  }
  function suggestFromText(text) {
    const words = lower(text).split(/[^0-9a-zçğıöşü]+/i).filter(Boolean);
    // Kelime başıyla eşleşir; "aç" gibi kısa kökler yalnız tam kelime olarak sayılır ("açıklama" ≠ "aç").
    const has = (...ps) => words.some((w) => ps.some((p) => (p.length <= 2 ? w === p : w.startsWith(p))));
    const isFill = has("yaz", "gir", "doldur");
    if (has("seç", "seçim")) return { kind: "unsupported", name: "Seçim yap" };
    if (has("kaydet", "gönder", "onayla")) return { kind: "unsupported", name: "Düğmeye bas", why: "Kaydetme/gönderme gibi iş yapan düğmeler bu prototipte desteklenmiyor;" };
    if (!isFill && has("bul", "ara", "arat")) return { kind: "unsupported", name: "Kayıt bul" };
    if (!isFill && has("oku", "öğren", "al")) return { kind: "unsupported", name: "Bilgi oku" };
    const q = tokens(text);
    if (!isFill && has("geç", "git", "aç", "devam")) {
      const dest = Object.entries(SCREENS).find(([, s]) => q.some((w) => tokens(s.title).includes(w)));
      const cands = allButtons().filter((b) => b.goes && (!dest || b.goes === dest[0]));
      if (cands.length) return { kind: "goto", candidates: cands, dest: dest && dest[0] };
    }
    if (isFill || q.length) {
      const scored = allFields().map((fd) => {
        const ft = [...tokens(fd.label), ...tokens(fd.section)];
        return { fd, score: q.filter((w) => ft.includes(w)).length };
      }).filter((x) => x.score > 0);
      if (scored.length) {
        const top = Math.max(...scored.map((x) => x.score));
        const best = scored.filter((x) => x.score === top).map((x) => x.fd);
        const num = (text.match(/\d+([.,]\d{1,2})?/) || [])[0];
        return { kind: "fill", candidates: best, number: num };
      }
    }
    return { kind: "none" };
  }

  function renderIntentResult(text) {
    const host = byId("pd-intent-result");
    if (!text.trim()) {
      host.replaceChildren(h("p", { class: "pd-msg pd-msg--missing" }, "Önce ne yapmak istediğinizi yazın."));
      byId("pd-intent-input").focus();
      return;
    }
    const r = suggestFromText(text);
    const tag = h("span", { class: "pd-badge pd-badge--proto" }, "Temsili öneri · gerçek model değil");
    let content;
    if (r.kind === "unsupported") {
      content = [h("p", null, `Bu istek “${r.name}” bileşenine benziyor. ${r.why || "Bu bileşen prototipte henüz yok;"} sahte bir adım oluşturulmadı.`)];
    } else if (r.kind === "none") {
      content = [h("p", null, "Bu cümleden bir alan veya ekran çıkaramadım. Soldaki bileşenlerden birini seçin ya da alan adını yazın (ör. “teminat tutarı”).")];
    } else if (r.kind === "fill") {
      const many = r.candidates.length > 1;
      content = [
        h("p", null, many
          ? `${r.candidates.length} alan eşleşti. Yanlış alana yazmamak için birini siz seçin:`
          : "Şu alan eşleşti. Doğruysa ekleyin:"),
        h("ul", { class: "pd-suggest__list" }, r.candidates.map((fd) => h("li", { class: "pd-suggest__item" },
          h("span", null, h("strong", null, fd.label), ` · ${fd.section} · ${screenTitle(fd.screen)}`),
          h("button", {
            type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm",
            "aria-label": `${fd.label} (${fd.section}) için Alan doldur adımı ekle`,
            onclick: () => {
              const s = newStep("fill"); applyTarget(s, fd);
              if (r.number && fd.kind !== "select" && fd.kind !== "readonly") { s.binding.source = "fixed"; s.binding.fixedValue = r.number; }
              host.replaceChildren(); byId("pd-intent-input").value = "";
              addStep(s);
            },
          }, "Ekle")))),
        r.number ? h("p", { class: "pd-help" }, `Cümledeki “${r.number}” sabit değer olarak önerilecek; değiştirebilirsiniz.`) : null,
      ];
    } else {
      content = [
        h("p", null, r.dest ? `“${screenTitle(r.dest)}” ekranına geçmek için şu düğme(ler) bulundu:` : "Ekran değiştirebilecek düğmeler:"),
        h("ul", { class: "pd-suggest__list" }, r.candidates.map((b) => h("li", { class: "pd-suggest__item" },
          h("span", null, h("strong", null, b.label), ` · ${screenTitle(b.screen)} ekranı`),
          h("button", {
            type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm",
            onclick: () => {
              const s = newStep("goto"); s.button = { screen: b.screen, key: b.key, label: b.label };
              s.expectScreen = r.dest || "";
              host.replaceChildren(); byId("pd-intent-input").value = "";
              addStep(s);
            },
          }, "Ekle")))),
        h("p", { class: "pd-help" }, "Düğmenin yalnız ekran değiştirdiğini adımda siz onaylarsınız."),
      ];
    }
    host.replaceChildren(h("div", { class: "pd-suggest" }, tag, content));
  }

  // ===================================================================
  // Yeniden kullanılabilir bileşen olarak kaydet
  // ===================================================================
  function openComponentDialog() {
    const f = flow();
    const chosen = f.steps.filter((s) => state.checked.has(s.id));
    if (!chosen.length) return;
    const analysis = analyze(f);
    const problems = [];
    const chosenIds = new Set(chosen.map((s) => s.id));
    for (const s of chosen) {
      const a = analysis.get(s.id);
      if (a.issues.length) problems.push(`${a.index + 1}. adımın eksikleri var; önce tamamlayın.`);
      const refs = s.type === "fill" ? [s.binding] : s.type === "call" ? Object.values(s.bindings) : [];
      for (const b of refs) {
        if (b.source === "previous" && b.previousRef && !chosenIds.has(b.previousRef.split("/")[0])) {
          problems.push(`${a.index + 1}. adım işaretlenmemiş bir adımın değerini kullanıyor. O adımı da işaretleyin veya kaynağı değiştirin.`);
        }
      }
      if (s.type === "call") problems.push(`${a.index + 1}. adım zaten bir bileşen; bu prototipte iç içe bileşen kaydedilemez.`);
      if (["choose", "check", "multi", "upload"].includes(s.type)) problems.push(`${a.index + 1}. adım gerçek oturum seçimi; bu sayfalık bileşene alınamaz. Yayımlanmış bileşen olarak yeniden kullanın.`);
    }
    const inputs = chosen.filter((s) => s.type === "fill" && s.binding.source === "ask")
      .map((s) => ({ name: s.name, question: s.binding.question }));
    const body = byId("pd-component-body");
    const nameInput = h("input", { type: "text", id: "pd-comp-name", maxlength: "60", autocomplete: "off", placeholder: "Örn. Teminat bilgilerini gir", "aria-describedby": "pd-comp-name-msg" });
    body.replaceChildren(
      h("p", null, `${chosen.length} adım tek bir bileşen olacak. Başka akışlarda “Akış çağır” ile kullanabilirsiniz.`),
      h("ol", { class: "pd-inner-steps" }, chosen.map((s) => h("li", null, summarize(s, f.steps)))),
      problems.length
        ? h("div", { class: "pd-result pd-result--error", role: "alert" }, icon("alert"),
          h("div", null, h("p", null, h("strong", null, "Bu adımlar henüz bileşen yapılamaz:")),
            h("ul", null, [...new Set(problems)].map((p) => h("li", null, p)))))
        : null,
      h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: "pd-comp-name" }, "Bileşenin adı ", h("span", { class: "pd-req" }, "(zorunlu)")),
        nameInput, h("p", { id: "pd-comp-name-msg", class: "pd-msg pd-msg--missing", hidden: true }, "Bileşene bir ad verin.")),
      h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: "pd-comp-desc" }, "Kısa açıklama (isteğe bağlı)"),
        h("textarea", { id: "pd-comp-desc", rows: "2", maxlength: "200" })),
      h("p", { class: "pd-help" }, inputs.length
        ? `Kullanıldığı yerde sorulacak değerler: ${inputs.map((x) => `“${x.name}”`).join(", ")}. Sabit değerler bileşenin içinde kalır.`
        : "Bu bileşen dışarıdan değer istemeyecek."),
      h("label", { class: "pd-check-row", for: "pd-comp-replace" },
        h("input", { type: "checkbox", id: "pd-comp-replace", checked: true }),
        h("span", null, "İşaretli adımları bu akıştan çıkar, yerine bileşeni koy.")));
    byId("pd-component-submit").disabled = problems.length > 0;
    byId("pd-component-dialog").showModal();
    (problems.length ? byId("pd-component-submit").previousElementSibling : nameInput).focus();
  }

  function saveComponent() {
    const f = flow();
    const nameInput = byId("pd-comp-name");
    const name = nameInput.value.trim();
    const msg = byId("pd-comp-name-msg");
    if (!name) { msg.hidden = false; nameInput.setAttribute("aria-invalid", "true"); nameInput.focus(); return; }
    const chosen = f.steps.filter((s) => state.checked.has(s.id));
    const analysis = analyze(f);
    const idMap = {};
    const inner = chosen.map((s) => { const c = clone(s); c.id = uid("s"); idMap[s.id] = c.id; c.note = s.note; return c; });
    for (const s of inner) {
      if (s.type === "fill" && s.binding.source === "previous") s.binding.previousRef = idMap[s.binding.previousRef] || "";
    }
    const comp = {
      id: uid("c"), name, description: byId("pd-comp-desc").value.trim(), applicationId: f.applicationId,
      startScreen: analysis.get(chosen[0].id).screenBefore,
      steps: inner,
      inputs: inner.filter((s) => s.type === "fill" && s.binding.source === "ask").map((s) => ({
        key: s.id, name: s.name.trim() || suggestFor(s.target).name, question: s.binding.question, label: s.target.label,
        kind: s.target.kind, maxLength: s.target.maxLength, digits: s.target.digits,
      })),
    };
    state.components.push(comp);
    if (byId("pd-comp-replace").checked) {
      const at = f.steps.findIndex((s) => s.id === chosen[0].id);
      const call = newStep("call"); call.componentId = comp.id; call.bindings = defaultBindings(comp);
      // İşaretli adımlar soruluyorduysa aynı soruları koru.
      for (const s of chosen) {
        if (s.type === "fill" && s.binding.source === "ask") call.bindings[idMap[s.id]] = clone(s.binding);
      }
      f.steps = f.steps.filter((s) => !state.checked.has(s.id));
      f.steps.splice(at, 0, call);
      // Sonraki adımlar işaretli adımların değerini kullanıyorsa bileşenin çıktısına yönlendir.
      for (const s of f.steps) {
        const bs = s.type === "fill" ? [s.binding] : s.type === "call" ? Object.values(s.bindings) : [];
        for (const b of bs) if (b.source === "previous" && idMap[b.previousRef]) b.previousRef = `${call.id}/${idMap[b.previousRef]}`;
      }
      state.selectedStepId = call.id;
    }
    state.checked.clear();
    byId("pd-component-dialog").close();
    renderAll();
    toast(`“${name}” bileşeni kaydedildi (yalnız bu sayfada). Soldaki listeden başka akışlara ekleyebilirsiniz.`);
  }

  // ===================================================================
  // Deneme (temsili uygulamada; gerçek yürütücü değil)
  // ===================================================================
  let trial = null;

  function askPrompts(steps, onlyStep) {
    const prompts = [];
    const pushBinding = (key, b, meta, title) => {
      if (b.source === "ask") prompts.push({ key, label: b.question || title, meta });
    };
    for (const s of steps) {
      if (onlyStep && s.id !== onlyStep) continue;
      if (s.type === "fill" && s.target) {
        pushBinding(s.id, s.binding, s.target, s.name);
        if (onlyStep && s.binding.source === "previous") {
          prompts.push({ key: s.binding.previousRef, label: `Önceki adımdan gelecek değer (yalnız bu deneme için örnek): ${refLabel(steps, s.binding.previousRef)}`, meta: s.target });
        }
      }
      if (s.type === "call") {
        const c = findComp(s.componentId);
        if (!c) continue;
        for (const inp of c.inputs) {
          const b = s.bindings[inp.key] || newBinding();
          pushBinding(`${s.id}/${inp.key}`, b, inp, inp.name);
          if (onlyStep && b.source === "previous") prompts.push({ key: b.previousRef, label: `Önceki adımdan gelecek değer (örnek): ${refLabel(steps, b.previousRef)}`, meta: inp });
        }
      }
    }
    return prompts;
  }

  function openTrial(opts = {}) {
    const f = flow();
    const analysis = analyze(f);
    const only = opts.stepId || null;
    const scope = only ? f.steps.filter((s) => s.id === only) : f.steps;
    const realSteps = (only ? f.steps.filter((x) => x.id === only) : f.steps).filter((x) => ["read", "choose", "check", "multi", "upload", "action", "back"].includes(x.type) || isRealGoto(x) || (x.type === "call" && x.published) || (x.type === "fill" && x.target && x.target.source === "real"));
    if (realSteps.length) {
      byId("pd-trial-title").textContent = only ? "Bu adım denenemez" : "Akışı dene";
      byId("pd-trial-progress").replaceChildren(); byId("pd-trial-result").replaceChildren(); byId("pd-trial-stop").hidden = true;
      trial = { only, scope: [], startScreen: f.startScreen, returnFocus: document.activeElement, running: false, cancelled: false };
      byId("pd-trial-setup").replaceChildren(h("div", { class: "pd-result pd-result--error", role: "alert" }, icon("alert"),
        h("p", null, `${realSteps.length} adım gerçek oturumdan seçildi. Temsili deneme gerçek alanlara yazmaz; bu adımlar için “Alanı yeniden bul (yazmadan)” kullanın. Gerçek yürütme Katalog Tasarımcısı ve İşlem Asistanı'ndaki mevcut yürütücüyle yapılır.`)));
      byId("pd-trial-app").replaceChildren();
      byId("pd-trial").showModal();
      return;
    }
    const blockers = only
      ? analysis.get(only).issues.map((x) => ({ msg: x.msg, stepId: only }))
      : flowIssues(f, analysis).filter((x) => !x.focus || x.blockTrial);
    byId("pd-trial-title").textContent = only ? `${analysis.get(only).index + 1}. adımı dene` : "Akışı dene";
    byId("pd-trial-progress").replaceChildren();
    byId("pd-trial-result").replaceChildren();
    byId("pd-trial-stop").hidden = true;
    const startScreen = only ? analysis.get(only).screenBefore : f.startScreen;
    trial = { only, scope, startScreen, returnFocus: document.activeElement, running: false, cancelled: false };
    const mock = { screen: startScreen, values: {}, hiddenSections: [] };
    renderMock(byId("pd-trial-app"), mock, "view");

    const setup = byId("pd-trial-setup");
    if (blockers.length) {
      setup.replaceChildren(h("div", { class: "pd-result pd-result--error", role: "alert" }, icon("alert"),
        h("div", null,
          h("p", null, h("strong", null, "Deneme başlatılamadı. Önce şu eksikleri giderin:")),
          h("ul", null, blockers.slice(0, 8).map((b) => h("li", null, b.stepId
            ? h("button", { type: "button", class: "pd-linkbtn", onclick: () => { trial.returnFocus = null; byId("pd-trial").close(); selectStep(b.stepId, true); } }, b.msg)
            : b.msg))))));
      byId("pd-trial").showModal();
      setup.querySelector(".pd-linkbtn")?.focus();
      return;
    }
    const prompts = askPrompts(f.steps, only);
    const form = h("form", { class: "pd-askform", novalidate: true });
    if (prompts.length) {
      form.append(h("fieldset", null, h("legend", null, "Bu deneme için değerler"),
        prompts.map((p, i) => {
          const id = `pd-ask-${i}`;
          const m = h("p", { class: "pd-msg pd-msg--error", id: `${id}-msg`, hidden: true });
          return h("div", { class: "pd-field" },
            h("label", { class: "pd-label", for: id }, p.label),
            h("input", { type: "text", id, autocomplete: "off", value: state.lastAsk[p.key] || "", dataset: { key: p.key }, "aria-describedby": m.id,
              inputmode: p.meta && (p.meta.digits || p.meta.kind === "amount") ? "decimal" : null }),
            m);
        })));
    } else form.append(h("p", { class: "pd-help" }, "Bu deneme için sorulacak değer yok."));
    const scen = h("select", { id: "pd-scenario" },
      h("option", { value: "normal" }, "Normal"),
      h("option", { value: "no-kefil" }, "Kefil bölümü ekranda yok"),
      h("option", { value: "slow" }, "Yeni ekran geç açılıyor"),
      h("option", { value: "unknown-dialog" }, "Tanımsız bir pencere açılıyor"),
      h("option", { value: "new-window" }, "Yeni pencere/sekme açılıyor"));
    form.append(h("div", { class: "pd-field" },
      h("label", { class: "pd-label", for: "pd-scenario" }, "Temsili senaryo (prototip)"), scen,
      h("p", { class: "pd-help" }, "Hata ve bekleme durumlarını görmek için senaryoyu değiştirin.")));
    form.append(h("button", { type: "submit", class: "pd-btn pd-btn--primary", id: "pd-trial-start" }, icon("play"), "Denemeyi başlat"));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const ask = {};
      let firstBad = null;
      prompts.forEach((p, i) => {
        const input = byId(`pd-ask-${i}`); const m = byId(`pd-ask-${i}-msg`);
        const v = input.value.trim();
        const problem = !v ? "Bu değer gerekli." : valueProblem(p.meta, v);
        m.hidden = !problem; m.textContent = problem || "";
        if (problem) { input.setAttribute("aria-invalid", "true"); firstBad = firstBad || input; } else input.removeAttribute("aria-invalid");
        ask[p.key] = v;
      });
      if (firstBad) { firstBad.focus(); return; }
      Object.assign(state.lastAsk, ask);
      runTrial(ask, scen.value);
    });
    setup.replaceChildren(form);
    byId("pd-trial").showModal();
    (form.querySelector("input") || byId("pd-trial-start")).focus();
  }

  function progressItem(list, title) {
    const stateEl = h("span", { class: "pd-progress__state" }, h("span", { class: "pd-dot", "aria-hidden": "true" }));
    const label = h("span", { class: "pd-visually-hidden" }, "Bekliyor: ");
    const detail = h("span", { class: "pd-progress__detail" }, "Bekliyor");
    const li = h("li", null, stateEl, h("span", null, label, title), detail);
    list.append(li);
    return {
      li,
      set(kind, text) {
        li.className = `is-${kind}`;
        detail.textContent = text;
        const map = { running: "Çalışıyor: ", ok: "Tamam: ", error: "Hata: ", stopped: "Durduruldu: ", skipped: "Atlandı: " };
        label.textContent = map[kind] || "";
        stateEl.replaceChildren(kind === "running" ? h("span", { class: "pd-spinner", "aria-hidden": "true" })
          : kind === "ok" ? icon("check", "pd-state-ok") : kind === "error" ? icon("x", "pd-state-error")
            : kind === "stopped" ? icon("alert", "pd-state-warn")
              : h("span", { class: "pd-dot", "aria-hidden": "true" }));
      },
      sub() { const ol = h("ol"); li.append(ol); return ol; },
    };
  }

  class TrialStop extends Error {}

  async function runTrial(ask, scenario) {
    const f = flow();
    const startBtn = byId("pd-trial-start");
    startBtn.disabled = true; startBtn.setAttribute("aria-busy", "true");
    byId("pd-trial-setup").querySelectorAll("input, select").forEach((x) => { x.disabled = true; });
    const stopBtn = byId("pd-trial-stop"); stopBtn.hidden = false;
    const result = byId("pd-trial-result");
    result.replaceChildren(h("span", { class: "pd-result pd-result--busy" }, "Deneme çalışıyor…"));
    const list = byId("pd-trial-progress"); list.replaceChildren();
    const mock = { screen: trial.startScreen, values: {}, hiddenSections: scenario === "no-kefil" ? ["Kefil"] : [], active: null, activeButton: null, notice: "" };
    const app = byId("pd-trial-app");
    const draw = () => renderMock(app, mock, "view");
    draw();
    trial.running = true; trial.cancelled = false;
    const values = new Map(Object.entries(ask));
    const items = trial.scope.map((s) => ({ s, p: progressItem(list, summarize(s, f.steps)) }));
    // Durdurma: o anki adımda ne yapıldığı dürüstçe söylenir; tamamlanan işlemler geri alınmış gibi gösterilmez.
    const pace = async (ms, stoppedMsg = "Bu adımda hiçbir işlem yapılmadı.") => {
      await sleep(ms);
      if (trial.cancelled) throw new TrialStop(stoppedMsg);
    };

    const resolve = (b, key, inner) => {
      if (b.source === "fixed") return b.fixedValue.trim();
      if (b.source === "ask") return inner && inner.has(key) ? inner.get(key) : values.get(key);
      if (b.source === "previous") return (inner && inner.has(b.previousRef)) ? inner.get(b.previousRef) : values.get(b.previousRef);
      return undefined;
    };

    async function doFill(s, p, value) {
      p.set("running", "Alan yeniden bulunuyor…");
      await pace(500);
      if (mock.screen !== s.target.screen) throw new Error(`“${screenTitle(s.target.screen)}” ekranı açık değil; açık ekran “${screenTitle(mock.screen)}”. Hiçbir şey yazılmadı.`);
      if (mock.hiddenSections.includes(s.target.section)) throw new Error(`“${s.target.section}” bölümündeki “${s.target.label}” alanı ekranda bulunamadı. Yanlış alana yazmamak için durduruldu; hiçbir şey yazılmadı.`);
      if (value === undefined || value === "") throw new Error("Yazılacak değer bulunamadı.");
      mock.active = s.target.fieldKey; draw();
      await pace(350);
      mock.values[s.target.fieldKey] = value; draw();
      p.set("ok", `“${s.target.label}” alanına “${value}” yazıldı.`);
    }

    async function doGoto(s, p) {
      p.set("running", `“${s.button.label}” düğmesi aranıyor…`);
      await pace(450);
      if (mock.screen !== s.button.screen) throw new Error(`Düğme “${screenTitle(s.button.screen)}” ekranında; açık ekran “${screenTitle(mock.screen)}”. Düğmeye basılmadı.`);
      mock.activeButton = s.button.key; mock.active = null; draw();
      const def = SCREENS[s.button.screen].buttons.find((b) => b.key === s.button.key);
      p.set("running", "Düğmeye bir kez basıldı; ekran bekleniyor…");
      await pace(scenario === "slow" ? 2600 : 600,
        "Düğmeye basılmıştı; yeni ekranın açılıp açılmadığı doğrulanmadı. Basış geri alınmadı; sonucu uygulamada kontrol edin.");
      mock.activeButton = null;
      if (scenario === "unknown-dialog") {
        mock.notice = "Temsili: tanımsız bir “Uyarı” penceresi açıldı.";
        draw();
        throw new Error("Müdahale gerekiyor: tanımlı olmayan bir pencere açıldı. Kapatılmadı; düğmeye tekrar basılmadı ve sonraki adım başlatılmadı.");
      }
      if (scenario === "new-window") {
        p.set("running", "Açılan pencere bekleniyor…");
        await pace(500, "Düğmeye basılmıştı; açılan pencere doğrulanmadı. Geri alınmadı.");
        throw new Error("Müdahale gerekiyor: yeni bir pencere/sekme açıldı. Otomatik geçilmedi ve kapatılmadı; sonraki adım başlatılmadı.");
      }
      if (def && def.goes) { mock.screen = def.goes; mock.notice = ""; } else { mock.notice = `“${s.button.label}” düğmesine basıldı (temsili). Ekran değişmedi.`; }
      draw();
      p.set("running", "Sonuç doğrulanıyor…");
      if (mock.screen !== s.expectScreen) {
        throw new Error(`Beklenen “${screenTitle(s.expectScreen)}” ekranı açılmadı. Düğme veri kaydetmiş olabilir; adım otomatik olarak tekrarlanmadı. Sonucu uygulamada kontrol edin.`);
      }
      p.set("ok", `“${screenTitle(s.expectScreen)}” ekranı açıldı. Düğmeye yalnız bir kez basıldı.`);
    }

    async function doCall(s, p) {
      const c = findComp(s.componentId);
      p.set("running", `“${c.name}” bileşeni çalışıyor…`);
      const innerVals = new Map();
      for (const inp of c.inputs) {
        const v = resolve(s.bindings[inp.key] || newBinding(), `${s.id}/${inp.key}`);
        innerVals.set(inp.key, v);
      }
      const sub = p.sub();
      const subItems = c.steps.map((x) => ({ x, sp: progressItem(sub, summarize(x, c.steps)) }));
      for (let k = 0; k < subItems.length; k++) {
        const { x, sp } = subItems[k];
        try {
          if (x.type === "fill") {
            const v = resolve(x.binding, x.id, innerVals);
            await doFill(x, sp, v);
            innerVals.set(x.id, v);
          } else if (x.type === "goto") await doGoto(x, sp);
        } catch (err) {
          sp.set(err instanceof TrialStop ? "stopped" : "error", err.message);
          subItems.slice(k + 1).forEach((y) => y.sp.set("skipped", "Çalıştırılmadı."));
          throw err;
        }
      }
      for (const inp of c.inputs) values.set(`${s.id}/${inp.key}`, innerVals.get(inp.key));
      p.set("ok", `“${c.name}” tamamlandı (${c.steps.length} adım).`);
    }

    let failed = null;
    for (let i = 0; i < items.length; i++) {
      const { s, p } = items[i];
      try {
        if (s.type === "fill") { const v = resolve(s.binding, s.id); await doFill(s, p, v); values.set(s.id, v); }
        else if (s.type === "goto") await doGoto(s, p);
        else await doCall(s, p);
      } catch (err) {
        failed = { index: i, message: err.message, stopped: err instanceof TrialStop };
        p.set(failed.stopped ? "stopped" : "error", err.message);
        items.slice(i + 1).forEach((x) => x.p.set("skipped", failed.stopped ? "Çalıştırılmadı (deneme durduruldu)." : "Çalıştırılmadı."));
        break;
      }
    }
    trial.running = false;
    stopBtn.hidden = true; stopBtn.disabled = false; stopBtn.textContent = "Durdur";
    startBtn.disabled = false; startBtn.removeAttribute("aria-busy");
    byId("pd-trial-setup").querySelectorAll("input, select").forEach((x) => { x.disabled = false; });
    startBtn.lastChild.textContent = "Yeniden dene";
    const at = new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
    if (failed && failed.stopped) {
      const done = failed.index;
      result.replaceChildren(h("span", { class: "pd-result pd-result--error" }, icon("alert"),
        h("span", null, h("strong", null, "Deneme durduruldu. "),
          `${done ? `Tamamlanan ${done} adım geri alınmadı; temsili uygulamada yaptıkları duruyor. ` : ""}${failed.index + 1}. adım: ${failed.message} Sonraki adımlar başlatılmadı.`)));
      if (!trial.only) f.lastTrial = { sig: signature(f), ok: false, at, reason: "Deneme durduruldu." };
    } else if (failed) {
      result.replaceChildren(h("span", { class: "pd-result pd-result--error" }, icon("alert"),
        h("span", null, h("strong", null, `${failed.index + 1}. adımda durdu. `), failed.message)));
      if (!trial.only) f.lastTrial = { sig: signature(f), ok: false, at, reason: `${failed.index + 1}. adımda durdu.` };
    } else {
      result.replaceChildren(h("span", { class: "pd-result pd-result--ok" }, icon("check"),
        h("span", null, h("strong", null, "Deneme başarılı. "), trial.only
          ? "Yalnız bu adım denendi; yayın için akışın tamamını deneyin."
          : "Bütün adımlar temsili uygulamada çalıştı. Gerçek sistemde çalıştığı anlamına gelmez.")));
      if (!trial.only) f.lastTrial = { sig: signature(f), ok: true, at };
    }
    renderFlowBar(true);
    announce(failed ? (failed.stopped ? "Deneme durduruldu." : "Deneme başarısız.") : "Deneme başarılı.");
  }

  // ===================================================================
  // Yayın (yalnız prototip içi gösterim)
  // ===================================================================
  function openPublish() {
    const f = flow();
    const analysis = analyze(f);
    const issues = flowIssues(f, analysis);
    const fresh = f.lastTrial && f.lastTrial.ok && f.lastTrial.sig === signature(f);
    const rows = [
      { ok: !!f.name.trim(), text: "Akışın adı var", fix: () => byId("pd-flow-name").focus() },
      { ok: f.steps.length > 0, text: "En az bir adım var" },
      { ok: issues.every((x) => !x.stepId), text: "Bütün adımlar tamamlandı", fix: () => { const x = issues.find((y) => y.stepId); if (x) selectStep(x.stepId, true); } },
      { ok: !!fresh, text: "Son değişiklikten sonra akışın tamamı başarıyla denendi", fix: () => openTrial() },
      { ok: !isDirty() && !state.editing.isNew, text: "Değişiklikler bu sayfada saklandı", fix: () => byId("pd-save-flow").focus() },
    ];
    const ready = rows.every((r) => r.ok);
    const body = byId("pd-publish-body");
    body.replaceChildren(
      h("p", null, "Yayın; denenmiş akışın onaylanıp diğer kullanıcılara açılmasıdır. ",
        h("strong", null, "Bu prototipte gerçek yayın yapılmaz;"), " katalog, MongoDB veya taslaklar değişmez."),
      h("ul", { class: "pd-checklist", "aria-label": "Yayın koşulları" }, rows.map((r) => h("li", { class: r.ok ? "is-ok" : "is-bad" },
        icon(r.ok ? "check" : "alert"),
        h("span", null, h("span", { class: "pd-visually-hidden" }, r.ok ? "Tamam: " : "Eksik: "), r.text,
          !r.ok && r.fix ? [" — ", h("button", { type: "button", class: "pd-linkbtn", onclick: () => { byId("pd-publish-dialog").close(); r.fix(); } }, "Düzelt")] : null)))),
      h("div", { id: "pd-publish-result", role: "status", "aria-live": "polite" },
        ready ? null : h("p", { class: "pd-msg pd-msg--missing" }, "Eksikler giderilmeden yayımlanamaz.")));
    const btn = byId("pd-publish-confirm");
    btn.disabled = !ready;
    btn.hidden = false;
    btn.textContent = "Yayımla (prototip gösterimi)";
    byId("pd-publish-dialog").showModal();
    (ready ? btn : body.querySelector(".pd-linkbtn") || btn.previousElementSibling).focus();
  }

  async function confirmPublish() {
    const f = flow();
    const btn = byId("pd-publish-confirm");
    const out = byId("pd-publish-result");
    btn.disabled = true; btn.setAttribute("aria-busy", "true"); btn.textContent = "Hazırlanıyor…";
    out.replaceChildren(h("p", { class: "pd-result pd-result--busy" }, h("span", { class: "pd-spinner", "aria-hidden": "true" }), "Yayın gösterimi hazırlanıyor (temsili)…"));
    await sleep(900);
    if (!(f.lastTrial && f.lastTrial.ok && f.lastTrial.sig === signature(f))) {
      out.replaceChildren(h("p", { class: "pd-result pd-result--error" }, icon("alert"), "Akış bu arada değişti; yeniden deneyin."));
      btn.removeAttribute("aria-busy"); btn.textContent = "Yayımla (prototip gösterimi)";
      return;
    }
    f.published.push({ at: new Date().toISOString(), sig: signature(f) });
    const stored = state.flows.find((x) => x.id === f.id);
    if (stored && !isDirty()) stored.published = clone(f.published);
    btn.removeAttribute("aria-busy"); btn.hidden = true;
    out.replaceChildren(h("p", { class: "pd-result pd-result--ok" }, icon("check"),
      h("span", null, h("strong", null, `Gösterim sürümü ${f.published.length} oluşturuldu. `),
        "Bu yalnız prototip içi bir gösterimdir: gerçek kataloğa, MongoDB'ye veya taslaklara hiçbir şey yazılmadı ve sayfa yenilenince kaybolur.")));
    out.querySelector(".pd-result").setAttribute("tabindex", "-1");
    out.querySelector(".pd-result").focus();
    renderFlowBar(true);
  }

  // ===================================================================
  // Örnek akış (kullanıcı denemesi için)
  // ===================================================================
  function loadSample() {
    const f = flow();
    if (!f.applicationId) { toast("Önce akışın uygulamasını seçin."); byId("pd-flow-app").focus(); return; }
    if (!f.name.trim()) f.name = "Kefil ve teminat bilgisi gir";
    const fld = (key) => allFields().find((x) => x.key === key);
    const a = newStep("fill"); applyTarget(a, fld("m_no")); a.binding.source = "ask";
    const b = newStep("fill"); applyTarget(b, fld("k_no")); b.binding.source = "ask";
    const c = newStep("goto"); c.button = { screen: "musteri", key: "b_devam", label: "Devam" }; c.expectScreen = "teminat"; c.confirmNoData = true;
    const d = newStep("fill"); applyTarget(d, fld("t_tutar")); d.binding.source = "ask";
    const e = newStep("fill"); applyTarget(e, fld("t_aciklama")); e.binding.source = "fixed"; e.binding.fixedValue = "Prototip denemesi";
    f.steps.push(a, b, c, d, e);
    state.selectedStepId = a.id;
    renderAll();
    announce("Örnek akış yüklendi: 5 adım.");
    document.querySelector(".pd-card__main")?.focus();
  }

  // ===================================================================
  // Olay bağlantıları
  // ===================================================================
  async function requestCloseComponent() {
    const name = byId("pd-comp-name"); const desc = byId("pd-comp-desc"); const replace = byId("pd-comp-replace");
    const dirty = (name && name.value.trim()) || (desc && desc.value.trim()) || (replace && !replace.checked);
    if (dirty) {
      const discard = await confirmDiscard({
        title: "Bileşen oluşturmadan çıkılsın mı?",
        text: "Yazdığınız bileşen bilgileri bırakılır. Akışınızın adımları değişmez.",
        keep: "Düzenlemeye devam et", discard: "Değişiklikleri bırak",
      });
      if (!discard) return;
    }
    byId("pd-component-dialog").close();
    announce("Bileşen oluşturulmadı; akışın adımları değişmedi.");
  }

  function closeDialog(dlg) {
    if (dlg.id === "pd-trial" && trial && trial.running) trial.cancelled = true;
    dlg.close();
  }
  document.querySelectorAll("dialog").forEach((dlg) => {
    dlg.addEventListener("click", (e) => {
      if (!e.target.closest("[data-close]")) return;
      if (dlg.id === "pd-component-dialog") requestCloseComponent(); else closeDialog(dlg);
    });
    dlg.addEventListener("cancel", (e) => {
      if (dlg.id === "pd-component-dialog") { e.preventDefault(); requestCloseComponent(); return; }
      if (dlg.id === "pd-trial" && trial && trial.running) trial.cancelled = true;
    });
    dlg.addEventListener("close", () => {
      if (dlg.id === "pd-trial" && trial) { const rf = trial.returnFocus; if (rf && rf.isConnected) rf.focus(); }
      if (dlg.id === "pd-picker" && picker) { const rf = picker.returnFocus; picker = null; if (rf && rf.isConnected) rf.focus(); }
    });
  });

  byId("pd-flow-name").addEventListener("input", (e) => { flow().name = e.target.value; refreshDerived(); });
  byId("pd-flow-start").addEventListener("change", (e) => { flow().startScreen = e.target.value; refreshDerived(); announce(`Başlangıç ekranı: ${screenTitle(e.target.value)}.`); });
  byId("pd-new-flow").addEventListener("click", startNewFlow);
  byId("pd-back").addEventListener("click", goBack);
  byId("pd-save-flow").addEventListener("click", () => saveFlow());
  byId("pd-flow-app").addEventListener("change", async (e) => {
    const f = flow();
    const next = e.target.value;
    const prev = f.applicationId;
    if (next === prev) return;
    if (f.draft && f.draft.id) {
      e.target.value = prev;
      toast("Kaydedilmiş taslağın uygulaması değiştirilemez; yayınlar uygulama kimliğine bağlıdır.");
      return;
    }
    const bound = f.steps.some((s) => (s.type === "fill" && s.target) || (s.type === "goto" && s.button) || (s.type === "call" && s.componentId))
      || f.lastTrial || f.published.length;
    if (prev && bound) {
      e.target.value = prev;
      const proceed = await confirmDiscard({
        title: "Uygulama değiştirilsin mi?",
        text: "Bu akıştaki seçili alanlar, düğmeler, bileşen bağlantıları, deneme sonucu ve yayın gösterimi temizlenir. Adımlar kalır; hedefleri yeniden seçmeniz gerekir.",
        keep: "Vazgeç", discard: "Uygulamayı değiştir",
      });
      if (!proceed) { byId("pd-flow-app").focus(); return; }
      clearAppBound(f);
    }
    f.applicationId = next;
    state.checked.clear();
    renderAll();
    byId("pd-flow-app").focus();
    announce(next ? `Uygulama: ${appName(next)}.` : "Uygulama seçimi kaldırıldı.");
  });
  byId("pd-try-flow").addEventListener("click", () => openTrial());
  byId("pd-publish").addEventListener("click", openPublish);
  byId("pd-publish-confirm").addEventListener("click", confirmPublish);
  byId("pd-trial-stop").addEventListener("click", (e) => {
    if (!trial || !trial.running) return;
    trial.cancelled = true;
    e.currentTarget.disabled = true;
    e.currentTarget.textContent = "Durduruluyor…";
    announce("Durduruluyor; sonraki adımlar başlatılmayacak.");
  });
  byId("pd-save-component").addEventListener("click", openComponentDialog);
  byId("pd-clear-selection").addEventListener("click", () => { state.checked.clear(); renderSteps(); announce("İşaretler kaldırıldı."); });
  byId("pd-component-form").addEventListener("submit", (e) => { e.preventDefault(); saveComponent(); });
  byId("pd-load-sample").addEventListener("click", loadSample);
  byId("pd-intent-form").addEventListener("submit", (e) => { e.preventDefault(); renderIntentResult(byId("pd-intent-input").value); });
  byId("pd-intent-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); renderIntentResult(e.target.value); }
  });

  const root = document.documentElement;
  const themeBtn = byId("pd-theme-toggle");
  const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const currentTheme = () => root.dataset.theme || (darkQuery.matches ? "dark" : "light");
  function syncThemeButton() {
    const dark = currentTheme() === "dark";
    themeBtn.setAttribute("aria-pressed", dark ? "true" : "false");
    themeBtn.replaceChildren(icon(dark ? "moon" : "sun", "pd-ico--sm"), h("span", null, "Koyu tema"));
  }
  themeBtn.addEventListener("click", () => {
    root.dataset.theme = currentTheme() === "dark" ? "light" : "dark";
    syncThemeButton();
    announce(root.dataset.theme === "dark" ? "Koyu tema açık." : "Açık tema açık.");
  });
  darkQuery.addEventListener("change", syncThemeButton);
  syncThemeButton();

  // ===================================================================
  // Gerçek tarayıcı oturumu (mevcut oturum/gözlem/seçim/çözüm API'leri; paralel motor yok)
  // Seçim modunda sayfaya olay gitmez (picker katmanı); hiçbir değer yazılmaz, kayıt/gönderme yapılmaz.
  // ===================================================================
  const real = { sid: "", sessions: [], pick: null, intrTimer: null };
  const SESSION_KEY = "agentask.session"; // diğer sayfalarla ortak öneri; yetki her istekte sunucuda denetlenir

  async function api(method, path, body) {
    const r = await fetch(path, {
      method, credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (r.status === 204) return null;
    let d = null;
    try { d = await r.json(); } catch (_) { d = null; }
    if (!r.ok) throw Object.assign(new Error((d && d.code) || `http_${r.status}`), { body: d, status: r.status });
    return d;
  }
  const errText = (e) => (e && e.body && e.body.safe_message) || "İşlem tamamlanamadı.";
  const sessionPath = (suffix) => `/api/sessions/${encodeURIComponent(real.sid)}${suffix}`;

  function realStatus(text, kind) {
    const el = byId("pd-real-status");
    el.textContent = text || "";
    el.className = "pd-real__status" + (kind ? ` is-${kind}` : "");
  }

  // Temsili moda ait öğeler gerçek oturumda görünmez; “Prototip” etiketi gerçek akışı yanıltmasın.
  function applySourceLabels() {
    const isReal = state.source === "real";
    document.title = isReal ? "Akış Tasarımcısı · AgenTask" : "Akış Tasarımcısı (Prototip) · AgenTask";
    byId("pd-proto-badge").hidden = isReal;
    byId("pd-notice-label").textContent = isReal ? "Gerçek oturum:" : "Prototip:";
    for (const id of ["pd-try-flow", "pd-publish", "pd-save-flow", "pd-dirty", "pd-trial-status"]) byId(id).hidden = isReal;
    byId("pd-flow-start").closest(".pd-field").hidden = isReal;
    renderComponents();
  }
  function setSource(next) {
    if (state.source === next) return;
    if (real.pick) cancelRealPick("Seçim kaynağı değişti; seçim modu kapatıldı.");
    state.source = next;
    byId("pd-src-mock").setAttribute("aria-pressed", next === "mock" ? "true" : "false");
    byId("pd-src-real").setAttribute("aria-pressed", next === "real" ? "true" : "false");
    byId("pd-real").hidden = next !== "real";
    byId("pd-notice-text").textContent = next === "real"
      ? "alan seçerken uygulamada değer yazılmaz. “Gerçek dene” ise uygulamada gerçekten işlem yapar. “Taslağı kaydet” ile kaydedilmeyen değişiklikler sayfa yenilenince silinir."
      : "gerçek sisteme bağlanmaz. Veriler yalnız bu sayfada; yenileyince silinir.";
    byId("pd-src-help").textContent = next === "real"
      ? "Gerçek oturum: alanı kendi açtığınız tarayıcı oturumunda seçersiniz. Uygulamaya girişi o pencerede siz yaparsınız."
      : "Temsili ekranlar yalnız bu sayfada çalışır; gerçek uygulamaya bağlanmaz.";
    applySourceLabels();
    if (next === "real") loadSessions(); else stopIntrPolling();
    if (state.view === "editor") renderEditor();
    announce(next === "real" ? "Gerçek oturum seçildi." : "Temsili ekranlar seçildi.");
  }

  async function loadSessions(chooseId) {
    try {
      real.sessions = (await api("GET", "/api/sessions")).filter((x) => x.alive && x.purpose === "interactive");
    } catch (e) { realStatus(errText(e), "error"); return; }
    let remembered = "";
    try { remembered = localStorage.getItem(SESSION_KEY) || ""; } catch (_) { remembered = ""; }
    const wanted = chooseId || real.sid || remembered;
    real.sid = real.sessions.some((x) => x.session_id === wanted) ? wanted : "";
    const sel = byId("pd-real-session");
    sel.replaceChildren(h("option", { value: "" }, real.sessions.length ? "Seçin…" : "Açık oturum yok"),
      ...real.sessions.map((x) => h("option", { value: x.session_id }, `${x.session_id.slice(0, 8)} · ${x.current_url || "boş sayfa"}`)));
    sel.value = real.sid;
    renderRealSession();
  }
  function renderRealSession() {
    const cur = real.sessions.find((x) => x.session_id === real.sid);
    byId("pd-real-url").textContent = cur ? `Açık sayfa: ${cur.current_url || "boş sayfa"}` : "Oturum seçilmedi.";
    if (cur) { try { localStorage.setItem(SESSION_KEY, cur.session_id); } catch (_) { /* yok sayılır */ } }
    if (cur) startIntrPolling(); else stopIntrPolling();
  }

  // Kesintiler: tarayıcı dialog'u ve yeni pencere. Otomatik kapatılmaz; yalnız kullanıcının açık kararıyla.
  async function refreshInterruptions() {
    if (!real.sid) return;
    let d;
    try { d = await api("GET", sessionPath("/interruptions")); } catch (_) { return; }
    const box = byId("pd-real-intr");
    const parts = [];
    if (d.browser_dialog) {
      const seen = d.browser_dialog.id; // karar yalnız bu (görülen) pencereye uygulanır
      parts.push(h("p", null, h("strong", null, "Müdahale gerekiyor: "), `tarayıcı penceresi açık (${d.browser_dialog.type}): “${d.browser_dialog.message}”. Kendiliğinden kapatılmadı veya onaylanmadı.`),
        h("button", { type: "button", class: "pd-btn pd-btn--danger pd-btn--sm", onclick: () => resolveIntr("dismiss_browser_dialog", [seen]) }, "Bu pencereyi iptal ederek kapat"));
    }
    if (d.focused_window) {
      parts.push(h("p", null, h("strong", null, "Tasarım yeni pencerede: "), d.focused_window),
        h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", id: "pd-window-main", onclick: () => resolveIntr("design_main_window", []) }, "Ana pencerede tasarlamaya dön"));
    }
    if (d.new_windows.length === 1 && !d.focused_window) {
      parts.push(h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", id: "pd-window-design", onclick: () => resolveIntr("design_new_window", [d.new_windows[0].id]) }, "Bu pencerede tasarla"));
    }
    if (d.new_windows.length) {
      const seen = d.new_windows.map((w) => w.id);
      parts.push(h("p", null, h("strong", null, "Müdahale gerekiyor: "), `${d.new_windows.length} yeni pencere/sekme açıldı; otomatik geçilmedi.`),
        h("p", { class: "pd-help" }, "Kapatılacaklar: ", d.new_windows.map((w) => w.origin).join(", "), ". Ana çalışma sayfası kapatılmaz; bu listeden sonra açılan pencereler de kapatılmaz."),
        h("button", { type: "button", class: "pd-btn pd-btn--danger pd-btn--sm", onclick: () => resolveIntr("close_new_windows", seen) },
          `Listelenen ${seen.length} pencereyi kapat`));
    }
    box.hidden = !parts.length;
    // Dar pencerede kapalı sol panel kesintiyi gizleyemez: rozet gösterilir ve panel açılır.
    byId("pd-left-alert").hidden = !parts.length;
    if (parts.length && narrow.matches) setLeftOpen(true);
    box.replaceChildren(...parts);
  }
  async function resolveIntr(action, ids) {
    try { await api("POST", sessionPath("/interruptions"), { action, ids }); realStatus("Seçtiğiniz işlem uygulandı.", "ok"); }
    catch (e) { realStatus(e.status === 409 ? "Durum değişti; hiçbir pencere kapatılmadı. Güncel durumu görüp yeniden karar verin." : errText(e), "warn"); }
    refreshInterruptions();
  }
  function startIntrPolling() {
    stopIntrPolling();
    refreshInterruptions();
    real.intrTimer = setInterval(refreshInterruptions, 3000);
  }
  function stopIntrPolling() { if (real.intrTimer) clearInterval(real.intrTimer); real.intrTimer = null; }

  async function openAppInSession() {
    const app = APPS.find((a) => a.id === (state.editing ? flow().applicationId : ""));
    if (!real.sid) { realStatus("Önce bir tarayıcı oturumu seçin veya açın.", "warn"); return; }
    if (!app) { realStatus("Önce akışın uygulamasını seçin.", "warn"); return; }
    realStatus("Ekran bekleniyor…", "busy");
    try {
      const r = await api("POST", sessionPath("/navigate"), { url: app.base_url });
      realStatus(`Açıldı: ${r.url}. Gerekiyorsa uygulamaya bu oturumda giriş yapın.`, "ok");
    } catch (e) { realStatus(errText(e), "error"); }
    loadSessions(real.sid);
  }

  function checkText(c) {
    if (!c) return "Tekillik henüz doğrulanmadı.";
    if (c.outcome === "saved") return "Kayıtlı tanım; ekranda yeniden aramak için “yeniden bul” deyin.";
    if (c.outcome === "resolved") return "Ekranda tek olarak bulundu.";
    if (c.outcome === "ambiguous") return `Belirsiz: ${c.count} aday.`;
    return c.reason === "blocked" || c.reason === "multiple_active_dialogs" ? "Müdahale gerekiyor." : "Şu an doğrulanamadı.";
  }

  const realTargetOf = (step) => (step.type === "goto" ? step.button : step.target);
  // Seçimden sonra ve istendiğinde hedef GÜNCEL ekranda mevcut semantik çözümleyiciyle yeniden bulunur.
  async function recheckReal(step, quiet) {
    const t = realTargetOf(step);
    if (!t || t.source !== "real" || !t.label) return;
    if (!real.sid) { realStatus("Önce bir tarayıcı oturumu seçin.", "warn"); return; }
    realStatus("Alan yeniden bulunuyor…", "busy");
    try {
      const r = await api("POST", sessionPath("/resolve"), realSpec(t));
      t.check = { outcome: r.outcome, reason: r.reason, explanation: r.explanation, count: r.candidates.length };
      if (t.check.outcome !== "resolved" && step.inFoundRow && !t.rowKey) t.check = { outcome: "saved" };  // satır çalışırken bulunur
      if (r.outcome === "resolved" && r.candidate_id) {
        await api("POST", sessionPath(`/candidates/${encodeURIComponent(r.candidate_id)}/highlight`)).catch(() => null);
        realStatus(step.type === "goto" ? "Düğme ekranda tek olarak bulundu ve işaretlendi. Düğmeye basılmadı."
          : "Alan ekranda tek olarak bulundu ve tarayıcıda işaretlendi. Değer yazılmadı.", "ok");
      } else {
        realStatus(r.reason === "blocked" || r.reason === "multiple_active_dialogs" ? `Müdahale gerekiyor: ${r.explanation}` : r.explanation, "warn");
      }
    } catch (e) {
      t.check = null;
      realStatus(errText(e), "error");
    }
    refreshInterruptions();
    if ((step.type === "multi" || (step.type === "choose" && !step.autocomplete)) && t.check && t.check.outcome === "resolved") await loadChoiceOptions(step, false);
    renderSteps(); renderFlowBar(true);
    if (state.selectedStepId === step.id) { renderEditor(); if (!quiet) byId(`${step.id}-recheck`)?.focus(); }
  }

  function chooseRealControl(step, control, via) {
    if ((step.type === "choose" || step.type === "multi") && real.choiceInfo) delete real.choiceInfo[step.id];
    if (step.type === "goto") step.button = realTargetFrom(control);
    else if (["read", "choose", "find", "check", "multi", "upload"].includes(step.type)) {
      step.target = realTargetFrom(control);
      const sug = suggestForReal(step.target);
      if (!step.name.trim() || step.suggested.name) { step.name = sug.name; step.suggested.name = true; }
      if (!step.description.trim() || step.suggested.description) { step.description = sug.description; step.suggested.description = true; }
      if ((step.type === "choose" || step.type === "find") && (!step.binding.question.trim() || step.binding.questionSuggested)) { step.binding.question = sug.question; step.binding.questionSuggested = true; }
    } else applyRealTarget(step, control);
    state.changingTarget.delete(step.id);
    if (realTargetOf(step).rowKey && flow().steps.slice(0, flow().steps.indexOf(step)).some((x) => x.type === "find")) step.inFoundRow = true;
    renderSteps(); renderEditor(); renderFlowBar(true);
    toast(`“${targetTitle(realTargetOf(step))}” ${via}. Uygulamada işlem yapılmadı.`);
    byId(`${step.id}-change`)?.focus();
    recheckReal(step, true);
  }

  function realAlternatives(step, tMsg) {
    if (!real.sid) {
      return [h("p", { class: "pd-msg pd-msg--missing" }, "Gerçek oturumdan seçmek için soldaki “Tarayıcı oturumu” alanından bir oturum seçin veya açın.")];
    }
    const pick = h("button", { type: "button", class: "pd-btn pd-btn--secondary", id: `${step.id}-pick`, onclick: () => startRealPick(step) },
      icon("target"), "Tarayıcıda kendim seçeyim");
    if (!realTargetOf(step)) linkMsg(pick, tMsg);
    const scan = h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", id: `${step.id}-scan`, onclick: () => scanRealFields(step) }, step.type === "goto" ? "Ekrandaki düğmeleri listele" : "Ekrandaki alanları listele");
    const list = h("div", { id: `${step.id}-scan-list` });
    const picking = real.pick && real.pick.stepId === step.id;
    return [
      h("div", { class: "pd-alt" },
        h("div", { class: "pd-alt__head" }, h("p", { class: "pd-alt__title" }, step.type === "goto" ? "Ekrandaki düğmelerden seç" : "Ekranda bulunan alanlardan seç"), scan),
        list,
        h("p", { class: "pd-help" }, "Liste o anki ekranın gözlemidir; öneri değildir ve sizi sınırlamaz.")),
      h("p", { class: "pd-or", "aria-hidden": "true" }, "veya"),
      h("div", { class: "pd-alt" },
        picking
          ? h("div", { class: "pd-picking", role: "status" },
            h("span", { class: "pd-spinner", "aria-hidden": "true" }),
            h("span", null, "Tarayıcı penceresinde alanı seçmeniz bekleniyor… Bu sırada uygulamada tıklama, yazma veya kayıt yapılmaz."),
            h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", id: `${step.id}-pick-cancel`, onclick: () => cancelRealPick("Seçimden vazgeçildi; seçim modu kapatıldı.") }, "Vazgeç"))
          : pick,
        h("p", { class: "pd-help" }, "Listede olmayan herhangi bir alanı oturumun tarayıcı penceresinde tıklayarak seçebilirsiniz.")),
    ];
  }

  async function scanRealFields(step) {
    const host = byId(`${step.id}-scan-list`);
    if (!host) return;
    host.replaceChildren(h("p", { class: "pd-help", role: "status" }, "Ekran bekleniyor…"));
    let snap;
    try { snap = await api("POST", sessionPath("/observe")); } catch (e) { host.replaceChildren(h("p", { class: "pd-msg pd-msg--error" }, errText(e))); return; }
    const wanted = step.type === "goto" ? (c) => ["button", "tab", "link"].includes(c.kind)
      : step.type === "read" ? (c) => ["textbox", "select", "combobox"].includes(c.kind)
        : step.type === "choose" ? (c) => choiceKinds(step).includes(c.kind) && !c.multiple
          : step.type === "multi" ? (c) => ["select", "combobox"].includes(c.kind) && c.multiple
          : step.type === "upload" ? (c) => c.kind === "file"
          : step.type === "check" ? (c) => c.kind === "checkbox"
          : step.type === "find" ? (c) => c.kind === "table"
        : (c) => c.kind === "textbox";
    const fields = snap.controls.filter((c) => wanted(c) && c.visible && !c.sensitive && c.interaction === "open" && (c.label || c.accessible_name)).slice(0, 20);
    const note = snap.coverage === "complete" ? null : h("p", { class: "pd-help" }, "Ekranın bir kısmı taranamadı; aradığınız alan listede olmayabilir. “Tarayıcıda kendim seçeyim” ile seçebilirsiniz.");
    if (!fields.length) { host.replaceChildren(h("p", { class: "pd-help" }, step.type === "goto" ? "Bu ekranda düğme bulunamadı." : "Bu ekranda uygun alan bulunamadı."), note); return; }
    host.replaceChildren(h("ul", { class: "pd-fieldsugs" }, fields.map((c) => {
      const t = realTargetFrom(c);
      return h("li", null, h("button", {
        type: "button", class: "pd-fieldsug", "aria-label": `${t.rowKey ? `${t.rowKey} satırındaki ` : ""}${t.section ? `${t.section} bölümündeki ` : ""}${t.label} ${step.type === "goto" ? "düğmesini" : step.type === "find" ? "tablosunu" : "alanını"} seç`,
        onclick: () => chooseRealControl(step, c, "ekrandaki listeden seçildi"),
      }, h("span", { class: "pd-fieldsug__name" }, `${t.section ? `${t.section} › ` : ""}${t.label}`),
      h("span", { class: "pd-fieldsug__kind" }, [t.dialog ? `pencere: ${t.dialog}` : null, t.frames.length ? `çerçeve: ${t.frames[t.frames.length - 1]}` : null].filter(Boolean).join(" · ") || KIND_TEXT[t.kind] || t.kind)));
    })), note);
  }

  const PICK_TOTAL_MS = 120000; // bir seçim isteğinin üst sınırı; dolunca seçim modu kapatılır
  async function startRealPick(step) {
    if (real.pick) return;
    const pick = { stepId: step.id, sid: real.sid, active: true };
    real.pick = pick;
    realStatus("Tarayıcıda seçiminiz bekleniyor…", "busy");
    try { await api("POST", sessionPath("/picker/start")); }
    catch (e) { real.pick = null; realStatus(errText(e), "error"); renderEditor(); return; }
    renderEditor();
    byId(`${step.id}-pick-cancel`)?.focus();
    const deadline = Date.now() + PICK_TOTAL_MS;
    let picked = null;
    try {
      while (pick.active && Date.now() < deadline) {
        let r;
        try { r = await api("GET", `/api/sessions/${encodeURIComponent(pick.sid)}/picker/selection?wait_ms=10000`); }
        catch (e) { realStatus(errText(e), "error"); break; }
        if (!pick.active) break;
        if (!r.selected) continue;
        if (r.pick && r.pick.reason === "picked" && r.pick.control) { picked = r.pick.control; break; }
        realStatus(r.pick && r.pick.reason === "unsupported_element"
          ? "Seçilen öğe desteklenen bir kontrol değil; bir alan seçin."
          : "Seçim sırasında ekran değişti; alanı yeniden seçin.", "warn");
      }
    } finally {
      // Her çıkışta (seçim, vazgeç, süre, hata) seçim modu ve dinleyiciler kaldırılır.
      await api("POST", `/api/sessions/${encodeURIComponent(pick.sid)}/picker/stop`).catch(() => null);
      if (real.pick === pick) real.pick = null;
    }
    if (picked) {
      const s = findStepIfOpen(pick.stepId);
      if (s) chooseRealControl(s, picked, "tarayıcıda seçildi");
    } else if (pick.active) {
      realStatus("Süre doldu; seçim modu kapatıldı. Tekrar deneyebilirsiniz.", "warn");
      if (state.view === "editor") renderEditor();
    }
  }
  function findStepIfOpen(id) { return state.editing ? flow().steps.find((x) => x.id === id) : null; }
  function cancelRealPick(message) {
    const pick = real.pick;
    if (!pick) return;
    pick.active = false;
    real.pick = null;
    api("POST", `/api/sessions/${encodeURIComponent(pick.sid)}/picker/stop`).catch(() => null);
    realStatus(message, "warn");
    if (state.view === "editor") { renderEditor(); byId(`${pick.stepId}-pick`)?.focus(); }
  }

  // Sol panel (dar pencere): akış içinde açılır/kapanır; geniş pencerede hep açıktır. Durum yalnız arayüzdedir.
  const narrow = window.matchMedia("(max-width: 1180px)");
  function setLeftOpen(open) {
    byId("pd-left").classList.toggle("is-collapsed", !open);
    byId("pd-left-toggle").setAttribute("aria-expanded", open ? "true" : "false");
  }
  setLeftOpen(!narrow.matches);
  narrow.addEventListener("change", (e) => setLeftOpen(!e.matches)); // eşik geçilince varsayılan durum
  byId("pd-left-toggle").addEventListener("click", () => setLeftOpen(byId("pd-left").classList.contains("is-collapsed")));
  byId("pd-src-mock").addEventListener("click", () => setSource("mock"));
  byId("pd-src-real").addEventListener("click", () => setSource("real"));
  byId("pd-real-session").addEventListener("change", (e) => {
    if (real.pick) cancelRealPick("Oturum değişti; seçim modu kapatıldı.");
    real.sid = e.target.value; renderRealSession(); if (state.view === "editor") renderEditor();
  });
  byId("pd-real-refresh").addEventListener("click", () => loadSessions());
  byId("pd-real-new").addEventListener("click", async () => {
    try { const v = await api("POST", "/api/sessions"); realStatus("Yeni oturum açıldı.", "ok"); await loadSessions(v.session_id); }
    catch (e) { realStatus(errText(e), "error"); }
    if (state.view === "editor") renderEditor();
  });
  byId("pd-real-open").addEventListener("click", openAppInSession);
  // Sayfa kapanırken açık seçim modu bırakılmaz.
  window.addEventListener("pagehide", () => {
    if (real.pick) fetch(`/api/sessions/${encodeURIComponent(real.pick.sid)}/picker/stop`, { method: "POST", credentials: "same-origin", keepalive: true }).catch(() => null);
  });

  // ===================================================================
  // Kalıcı taslak: mevcut /api/drafts servisi (LocalFileDraftRepository; revizyon kontrollü). Paralel depo yok.
  // Teknik kimlikleri kod üretir. Hedef, kaydetme anında canlı ekranda yeniden çözülür (select-target).
  // ===================================================================
  function draftOf(f) {
    if (!f.draft) f.draft = { id: "", revision: 0, synced: [], params: {}, readOnly: false, notes: [], savedSig: "", startScreenId: "", screens: {}, transitions: {} };
    return f.draft;
  }
  const rand4 = () => Math.random().toString(36).slice(2, 6).replace(/[^a-z0-9]/g, "a");
  function safeSlug(text, prefix) {
    let v = slug(text).slice(0, 40).replace(/_+$/, "");
    if (!/^[a-z]/.test(v)) v = `${prefix}_${v}`.replace(/_+$/, "");
    return v || prefix;
  }
  const bindValueSig = (x, steps) => (x.source === "fixed" ? x.fixedValue.trim() : x.source === "previous" ? `${steps.findIndex((y) => y.id === x.previousRef.split("/")[0])}/${x.previousRef.split("/")[1] || ""}` : x.question.trim());
  const priorBad = (bb, steps) => {
    if (bb.source !== "previous") return false;
    const [id, out] = (bb.previousRef || "").split("/");
    const src = steps.find((x) => x.id === id);
    return !(src && ((src.type === "read" && !out) || (src.type === "call" && src.published && src.published.outputs.some((o) => o.name === out))));
  };
  // Kalıcı adım imzası: yalnız sunucuya giden tanımsal içerik. Değişirse adım yeniden oluşturulur.
  const stepSig = (st, steps) => baseStepSig(st, steps) + (st.inFoundRow ? "|row" : "") + (st.type === "goto" && st.completion ? JSON.stringify(st.completion) : "");
  function baseStepSig(st, steps) {
    const b = st.binding;
    if (st.type === "read") return JSON.stringify({ k: "read", t: realSpec(st.target), n: st.name.trim() });
    if (st.type === "find") return JSON.stringify({ k: "find", t: realSpec(st.target), src: st.binding.source, v: bindValueSig(st.binding, steps), n: st.navigation, l: st.nextLabel.trim(), e: st.endText.trim() });
    if (st.type === "goto") return JSON.stringify({ k: "goto", t: realSpec(st.button), e: st.expectName.trim(), w: !!st.newWindow, o: st.newWindow ? st.windowOrigin.trim() : "" });
    if (st.type === "back") return JSON.stringify({ k: "back", c: !!st.closeWindow });
    if (st.type === "call") return JSON.stringify({ k: "call", o: st.published.operation_id, r: st.published.revision, b: Object.entries(st.bindings).map(([k, x]) => [k, x.source, bindValueSig(x, steps)]) });
    if (st.type === "choose") {
      const prevC = b.source === "previous" ? `${steps.findIndex((x) => x.id === b.previousRef.split("/")[0])}/${b.previousRef.split("/")[1] || ""}` : null;
      return JSON.stringify({ k: "choose", t: realSpec(st.target), src: b.source, v: b.source === "fixed" ? b.fixedValue : b.source === "ask" ? b.question.trim() : prevC, cv: st.choiceValue || null,
        l: b.source === "ask" ? askList(st) : null, d: st.description.trim() || st.name.trim(), c: st.successCheck || "auto", e: st.effect, r: st.resultText.trim(), n: st.changesScreen ? st.expectName.trim() : "", ac: !!st.autocomplete, st: st.autocomplete ? st.searchText : "" });
    }
    if (st.type === "multi") return JSON.stringify({ k: "multi", t: realSpec(st.target), src: st.source, v: st.source === "fixed" ? [...st.fixedSet].sort() : st.question.trim(), e: st.effect, l: multiChoices(st), d: st.description.trim() || st.name.trim() });
    if (st.type === "upload") return JSON.stringify({ k: "upload", t: realSpec(st.target), q: st.question.trim(), ft: [...st.fileTypes].sort(), r: st.resultText.trim(), d: st.description.trim() || st.name.trim() });
    if (st.type === "check") return JSON.stringify({ k: "check", t: realSpec(st.target), v: st.checked, c: st.successCheck || "auto", e: st.effect, r: st.resultText.trim(), d: st.description.trim() || st.name.trim() });
    if (st.type === "action") return JSON.stringify({ k: "action", a: st.actionId, b: Object.entries(st.bindings).map(([k, x]) => [k, x.source, bindValueSig(x, steps)]) });
    const prev = b.source === "previous" ? `${steps.findIndex((x) => x.id === b.previousRef.split("/")[0])}/${b.previousRef.split("/")[1] || ""}` : null;
    return JSON.stringify({ t: realSpec(st.target), src: b.source, v: b.source === "fixed" ? b.fixedValue.trim() : b.source === "ask" ? b.question.trim() : prev, d: st.description.trim() || st.name.trim(), c: st.successCheck || "auto" });
  }
  const badFixed = (b) => (b.source === "fixed" && /[{}]/.test(b.fixedValue) ? "sabit değer { } içeremez"
    : b.source === "fixed" && !b.fixedValue.trim() ? "sabit değer boş" : !b.source ? "değer kaynağı seçilmedi" : null);
  function persistable(f) {
    const steps = []; const skipped = [];
    f.steps.forEach((st, i) => {
      let why = null;
      if (st.type === "read") {
        why = !st.target ? "okunacak alan seçilmedi" : st.target.source !== "real" ? "temsili ekrandan seçildi"
          : !st.target.label ? "alanın etiketi yok" : st.target.sensitive ? "hassas alan okunup aktarılmaz" : null;
      } else if (st.type === "goto") {
        why = !st.button ? "düğme seçilmedi" : st.button.source !== "real" ? "temsili ekrandan seçildi (gerçek düğme değil)"
          : !st.button.label ? "düğmenin adı yok" : !["button", "tab", "link"].includes(st.button.kind) ? "seçilen öğe düğme, sekme veya bağlantı değil"
            : !st.expectName.trim() ? "açılacak ekranın adı yazılmadı" : !st.confirmNoData ? "düğmenin veri kaydetmediği onaylanmadı" : null;
      } else if (st.type === "action") {
        const act = (real.actions || []).find((x) => x.action_id === st.actionId);
        why = !act ? "onaylı işlem seçilmedi" : act.params.map((prm) => {
          const bb = st.bindings[prm.name] || newBinding();
          return priorBad(bb, steps) ? `“${prm.title}” için önceki çıktı kaynağı kaydedilmemiş` : badFixed(bb) && `“${prm.title}”: ${badFixed(bb)}`;
        }).find(Boolean) || null;
      } else if (st.type === "call" && st.published) {
        why = st.published.inputs.map((inp) => {
          const bb = st.bindings[inp.name] || newBinding();
          return priorBad(bb, steps) ? `“${inp.title}” için önceki çıktı kaynağı kaydedilmemiş` : badFixed(bb) && `“${inp.title}”: ${badFixed(bb)}`;
        }).find(Boolean) || null;
      } else if (st.type === "find") {
        why = !st.target ? "tablo seçilmedi" : st.target.source !== "real" ? "temsili ekrandan seçildi" : st.target.kind !== "table" ? "seçilen öğe tablo değil" : !st.target.label ? "tablonun adı yok"
          : priorBad(st.binding, steps) ? "önceki çıktı kaynağı kaydedilmemiş" : badFixed(st.binding);
      } else if (st.type === "back") {
        why = !steps.slice(0, steps.indexOf(st)).some((x) => x.type === "goto" && x.newWindow) ? "önce yeni pencere açan adım gerekli" : null;
      } else if (st.type === "multi") {
        why = !st.target ? "alan seçilmedi" : st.target.source !== "real" ? "temsili ekrandan seçildi" : !["select", "combobox"].includes(st.target.kind) ? "seçilen öğe seçim alanı değil"
          : st.source === "fixed" && !st.fixedSet.length ? "seçenek işaretlenmedi" : st.source === "ask" && !st.question.trim() ? "sorulacak metin yazılmadı" : !st.effect ? "seçimin etkisi belirtilmedi" : null;
      } else if (st.type === "upload") {
        why = !st.target ? "dosya alanı seçilmedi" : st.target.source !== "real" ? "temsili ekrandan seçildi" : st.target.kind !== "file" ? "seçilen öğe dosya alanı değil"
          : !st.question.trim() ? "sorulacak metin yazılmadı" : !st.resultText.trim() ? "durum mesajı yazılmadı" : null;
      } else if (st.type === "check") {
        why = !st.target ? "onay kutusu seçilmedi" : st.target.source !== "real" ? "temsili ekrandan seçildi" : st.target.kind !== "checkbox" ? "seçilen öğe onay kutusu değil"
          : !st.target.label ? "kutunun etiketi yok" : st.checked === null ? "son durum seçilmedi" : !st.effect ? "değişikliğin etkisi belirtilmedi" : null;
      } else if (st.type === "choose") {
        const [cSrcId, cSrcOut] = (st.binding.previousRef || "").split("/");
        const cSrc = st.binding.source === "previous" ? steps.find((x) => x.id === cSrcId) : null;
        const cOk = cSrc && ((cSrc.type === "read" && !cSrcOut) || (cSrc.type === "call" && cSrc.published && cSrc.published.outputs.some((o) => o.name === cSrcOut)));
        why = !st.target ? "seçim alanı seçilmedi" : st.target.source !== "real" ? "temsili ekrandan seçildi"
          : !st.target.label ? "alanın etiketi yok" : !choiceKinds(st).includes(st.target.kind) ? "seçilen öğe seçim alanı değil"
            : !st.effect ? "seçimin etkisi belirtilmedi" : st.changesScreen && !st.expectName.trim() ? "açılacak ekranın adı yazılmadı" : (choiceInfo(st) || {}).status === "unsupported" ? "bu kontrol türü desteklenmiyor"
              : st.binding.source === "previous" && !cOk ? "önceki çıktı yalnız daha önce kaydedilen “Bilgi oku” adımından gelebilir"
                : st.binding.source === "ask" && !st.askDynamic && !askList(st) ? "geçerli seçenekler okunmadı" : /[{}]/.test(st.resultText) ? "durum mesajı { } içeremez" : badFixed(st.binding);
      } else if (st.type !== "fill") {
        why = st.type === "call" ? "temsili (yalnız bu sayfadaki) bileşen kalıcı taslağa aktarılmaz; yayımlanmış bir bileşen seçin" : "bu bileşen kalıcı taslağa henüz aktarılmıyor";
      } else {
        const [srcId, srcOut] = (st.binding.previousRef || "").split("/");
        const src = st.binding.source === "previous" ? steps.find((x) => x.id === srcId) : null;
        const okSrc = src && ((src.type === "read" && !srcOut) || (src.type === "call" && src.published && src.published.outputs.some((o) => o.name === srcOut)));
        why = !st.target ? "alan seçilmedi"
          : st.target.source !== "real" ? "temsili ekrandan seçildi (gerçek alan değil)"
            : !st.target.label ? "alanın etiketi yok"
              : st.binding.source === "previous" && !okSrc ? "önceki adım çıktısı yalnız daha önce kaydedilen gerçek bir “Bilgi oku” adımından veya bileşen çıktısından gelebilir"
                : badFixed(st.binding);
      }
      if (why) skipped.push(`${i + 1}. adım: ${why}`); else steps.push(st);
    });
    return { steps, skipped };
  }
  const draftSig = (f) => { const ps = persistable(f).steps; return JSON.stringify({ n: f.name.trim(), s: ps.map((st) => [st.id, stepSig(st, ps)]) }); };
  // Rota: başlangıç ekranı ve her geçişten sonraki ekran (kimlikleri kod üretir; adları analist verir).
  function routeScreens(d, steps) {
    const taken = new Set([d.startScreenId]);
    for (const id of Object.values(d.screens)) taken.add(id);
    let current = d.startScreenId;
    let windowSource = null;
    const from = {};
    for (const st of steps) {
      from[st.id] = current;
      if (st.type === "goto" && st.newWindow) windowSource = current;
      if (st.type === "back") { d.screens[st.id] = windowSource || current; current = d.screens[st.id]; }
      if (st.type === "goto" || (st.type === "choose" && st.changesScreen)) {
        if (!d.screens[st.id]) d.screens[st.id] = uniqueName(safeSlug(st.expectName, "ekran"), taken);
        current = d.screens[st.id];
      }
      if (st.type === "call" && st.published) current = st.published.end_screen;
    }
    return from;
  }
  function targetFromSpec(spec) {
    return { source: "real", kind: spec.kind, label: spec.labels[0], section: spec.region || null, dialog: null,
      frames: spec.frame_title ? [spec.frame_title] : [], sensitive: false, interaction: "open", screen: null, fieldKey: null,
      maxLength: null, digits: false, check: { outcome: "saved" } };
  }

  function draftStatus(text, kind) {
    const el = byId("pd-draft-status");
    el.textContent = text;
    el.className = "pd-draft-status" + (kind ? ` is-${kind}` : "");
  }
  function renderDraftBar() {
    if (!state.editing) return;
    const f = flow(); const d = draftOf(f);
    const link = byId("pd-open-designer");
    link.hidden = !d.id;
    if (d.id) link.href = `/designer?draft=${encodeURIComponent(d.id)}`;
    byId("pd-save-draft").disabled = d.readOnly;
    if (d.readOnly) { draftStatus(`Salt okunur: ${d.notes.join(" ")} Mevcut tasarımcıda düzenleyin.`, "warn"); return; }
    if (!d.id) { draftStatus("Kalıcı taslak yok. Gerçek oturumdan seçilen adımlar “Taslağı kaydet” ile sunucuda saklanır."); return; }
    if (d.savedSig !== draftSig(f)) draftStatus(`Taslakta kaydedilmemiş değişiklik var (son kayıt: revizyon ${d.revision}).`, "warn");
    else draftStatus(`Taslak kaydedildi · revizyon ${d.revision}. Ekran tanıtma, deneme, onay ve yayın aşağıdaki panelde.`, "ok");
  }

  function uniqueName(base, taken) {
    let name = base; let n = 2;
    while (taken.has(name)) { name = `${base.slice(0, 55)}_${n}`; n += 1; }
    taken.add(name);
    return name;
  }

  async function saveDraft() {
    const f = flow(); const d = draftOf(f);
    if (d.readOnly) return;
    if (!f.name.trim()) { draftStatus("Önce akışa bir ad verin.", "warn"); byId("pd-flow-name").focus(); return; }
    if (!f.applicationId) { draftStatus("Önce uygulamayı seçin.", "warn"); return; }
    const { steps, skipped } = persistable(f);
    if (!steps.length) { draftStatus(`Kaydedilecek gerçek oturum adımı yok.${skipped.length ? ` ${skipped.join("; ")}.` : ""}`, "warn"); return; }
    if (!real.sid) { draftStatus("Kaydetme alanları canlı ekranda yeniden doğrular: gerçek oturumu seçin ve ilgili ekranı açın.", "warn"); return; }
    const btn = byId("pd-save-draft");
    btn.disabled = true; btn.setAttribute("aria-busy", "true");
    draftStatus("Taslak kaydediliyor; alanlar yeniden doğrulanıyor…", "busy");
    const draftPath = (suffix) => `/api/drafts/${encodeURIComponent(d.id)}${suffix}`;
    let pendingStep = null;
    try {
      let server;
      if (!d.id) {
        server = await api("POST", "/api/drafts", {
          application_id: f.applicationId, operation_id: `${safeSlug(f.name, "islem")}_${rand4()}`,
          title: f.name.trim().slice(0, 200), description: "",
        });
        d.id = server.draft_id;
      } else {
        server = await api("GET", draftPath(""));
        if (server.title !== f.name.trim()) server = await api("PATCH", draftPath(""), { expected_revision: server.revision, title: f.name.trim().slice(0, 200) });
      }
      d.revision = server.revision;
      if (server.screen) d.startScreenId = server.screen.screen_id;
      // Ekran kimliği uygulama genelinde mantıksal ekrandır: anlamlı addan üretilir (ör. "vaka_kopyala_ekrani").
      // İlk adım bir bileşen çağrısıysa başlangıç ekranı bileşenin başlangıç ekranıdır (rota uyumu).
      // Başlangıç ekranında çağrılan bileşen varsa ekran kimliği bileşeninkiyle aynı olmalı (rota uyumu).
      const firstLeave = steps.findIndex((x) => x.type === "goto");
      const startCall = (firstLeave < 0 ? steps : steps.slice(0, firstLeave)).find((x) => x.type === "call");
      if (!d.startScreenId) d.startScreenId = startCall ? startCall.published.start_screen : safeSlug(`${f.name} ekranı`, "ekran");
      const from = routeScreens(d, steps);
      // Parametreler: "her çalıştırmada sor" → user_input; "önceki adımın çıktısı" → prior_output (kaynak okuma
      // adımının sırası). Adları kod üretir; aynı adla gönderim günceller (servis upsert eder).
      const known = new Map(server.parameters.map((x) => [x.name, x]));
      const takenParams = new Set([...known.keys()]);
      const wantParam = async (key, base, body) => {
        if (!d.params[key]) d.params[key] = uniqueName(safeSlug(base, "deger"), takenParams);
        const name = d.params[key]; const old = known.get(name);
        if (!old || old.title !== body.title || old.source !== body.source || (old.prior_step ?? null) !== (body.prior_step ?? null) || (old.prior_output ?? null) !== (body.prior_output ?? null) || JSON.stringify(old.choices ?? null) !== JSON.stringify(body.choices ?? null)) {
          server = await api("POST", draftPath("/parameters"), { expected_revision: d.revision, name, max_length: 200, required: true, ...body });
          d.revision = server.revision; known.set(name, { name, ...body });
        }
        return name;
      };
      const wantPrior = async (key, base, bb) => {
        const [srcId, srcOut] = bb.previousRef.split("/");
        const at = steps.findIndex((x) => x.id === srcId);
        const src = steps[at];
        const outTitle = src.type === "call" ? (src.published.outputs.find((o) => o.name === srcOut) || {}).title || srcOut : src.name || src.target.label;
        await wantParam(key, `${base} ${outTitle} okunan`, { title: `${String(outTitle).slice(0, 80)} (okunan değer)`, source: "prior_output", prior_step: at, ...(src.type === "call" ? { prior_output: srcOut } : {}) });
      };
      for (const st of steps) {
        if (st.type === "multi" && st.source === "ask") { const l = multiChoices(st); await wantParam(st.id, st.name || st.question, { title: st.question.trim().slice(0, 100), source: "user_input", max_length: 500, multiple: true, ...(l ? { choices: l } : {}) }); }
        if (st.type === "upload") await wantParam(st.id, st.name || st.question, { title: st.question.trim().slice(0, 100), source: "user_input", max_length: 40, file: true });
        if (st.type === "fill" && st.binding.source === "ask") await wantParam(st.id, st.name || st.binding.question, { title: st.binding.question.trim().slice(0, 100), source: "user_input" });
        if (st.type === "find" && st.binding.source === "ask") await wantParam(st.id, st.name || st.binding.question, { title: st.binding.question.trim().slice(0, 100), source: "user_input" });
        if (st.type === "find" && st.binding.source === "previous") await wantPrior(st.id, "kayit", st.binding);
        if (st.type === "choose" && st.binding.source === "ask") {
          const list = askList(st);
          await wantParam(st.id, st.name || st.binding.question, { title: st.binding.question.trim().slice(0, 100), source: "user_input", ...(list ? { choices: list } : {}) });
        }
        if ((st.type === "fill" || st.type === "choose") && st.binding.source === "previous") {
          const [srcId, srcOut] = st.binding.previousRef.split("/");
          const at = steps.findIndex((x) => x.id === srcId);
          const src = steps[at];
          const outTitle = src.type === "call" ? (src.published.outputs.find((o) => o.name === srcOut) || {}).title || srcOut : src.name || src.target.label;
          await wantParam(st.id, `${outTitle} okunan`, { title: `${String(outTitle).slice(0, 80)} (okunan değer)`, source: "prior_output", prior_step: at, ...(src.type === "call" ? { prior_output: srcOut } : {}) });
        }
        if (st.type === "call") {
          for (const [pname, bb] of Object.entries(st.bindings)) {
            if (bb.source === "ask") await wantParam(`${st.id}/${pname}`, `${st.published.operation_id} ${pname}`, { title: bb.question.trim().slice(0, 100) || pname, source: "user_input" });
            if (bb.source === "previous") await wantPrior(`${st.id}/${pname}`, pname, bb);
          }
        }
        if (st.type === "action") {
          for (const [pname, bb] of Object.entries(st.bindings)) {
            if (bb.source === "ask") await wantParam(`${st.id}/${pname}`, `${st.actionId.split(".").pop()} ${pname}`, { title: bb.question.trim().slice(0, 100) || pname, source: "user_input" });
            if (bb.source === "previous") await wantPrior(`${st.id}/${pname}`, pname, bb);
          }
        }
      }
      // Adımlar: ilk farklılık noktasından sonrası silinip sırayla yeniden oluşturulur (eski deneme/onay geçersiz).
      let k = 0;
      while (k < d.synced.length && k < steps.length && d.synced[k].localId === steps[k].id && d.synced[k].sig === stepSig(steps[k], steps)) k += 1;
      for (const old of d.synced.slice(k).reverse()) {
        server = await api("DELETE", draftPath(`/steps/${encodeURIComponent(old.draftStepId)}?expected_revision=${d.revision}`));
        d.revision = server.revision;
        if (old.transitionId) {
          server = await api("DELETE", draftPath(`/transitions/${encodeURIComponent(old.transitionId)}?expected_revision=${d.revision}`));
          d.revision = server.revision;
        }
      }
      d.synced = d.synced.slice(0, k);
      const takenElements = new Set(Object.keys(server.elements || {}));
      const resolveNow = async (st, spec) => {
        const res = await api("POST", sessionPath("/resolve"), spec);
        if (res.outcome !== "resolved" || !res.candidate_id) throw Object.assign(new Error("unresolved"), { stepIndex: f.steps.indexOf(st) + 1, explanation: res.explanation });
        return res.candidate_id;
      };
      const selectTarget = async (st) => {
        server = await api("POST", draftPath(`/steps/${encodeURIComponent(pendingStep)}/select-target`), {
          expected_revision: d.revision, session_id: real.sid, candidate_id: await resolveNow(st, realSpec(st.target)), in_found_row: !!st.inFoundRow,
          element_id: uniqueName(safeSlug(`${st.target.section || ""} ${st.target.label}`, "alan"), takenElements),
          // Otomatik açıklama iç nottur (kaynak/çerçeve bilgisi); işlem metninde görünecek anlam adımın adıdır.
          meaning: ((st.suggested.description ? "" : st.description.trim()) || st.name.trim() || st.target.label).slice(0, 200),
          provenance: "observed", include_region: !!st.target.section,
        });
        d.revision = server.revision;
      };
      const patch = async (body) => {
        server = await api("PATCH", draftPath(`/steps/${encodeURIComponent(pendingStep)}`), { expected_revision: d.revision, ...body });
        d.revision = server.revision;
      };
      // Kayıt bağlamı: bulunan kaydın anahtarı veya sabit değer; hedef ekrandaki metin alanıyla karşılaştırılır.
      const gotoCompletion = (st, list) => {
        const c = st.completion;
        if (!c || !c.source || !c.label.trim()) return [];
        const finder = [...list.slice(0, list.indexOf(st))].reverse().find((x) => x.type === "find");
        const template = c.source === "fixed" ? c.fixed.trim() : finder.binding.source === "fixed" ? finder.binding.fixedValue.trim() : `{${d.params[finder.id]}}`;
        return [{ target: { kind: "textbox", labels: [c.label.trim()], ...(c.section.trim() ? { region: c.section.trim() } : {}) }, value_template: template }];
      };
      for (const st of steps.slice(k)) {
        const intent = st.type === "goto" ? `“${st.button.label}” düğmesiyle “${st.expectName.trim()}” ekranına geç` : st.type === "back" ? "Ana pencereye dön" : summarize(st, f.steps);
        server = await api("POST", draftPath("/steps"), { expected_revision: d.revision, intent_text: intent.slice(0, 500) });
        d.revision = server.revision;
        pendingStep = server.steps[server.steps.length - 1].step_id;
        let transitionId = null;
        if (st.type === "fill") {
          await selectTarget(st);
          await patch({ op: st.isDate ? "ensure_date" : "ensure_value", ...(st.isDate ? { date_format: st.dateFormat } : {}), success_check: st.successCheck || "auto",
            value_template: st.binding.source === "fixed" ? st.binding.fixedValue.trim() : `{${d.params[st.id]}}` });
        } else if (st.type === "read") {
          await selectTarget(st);
          await patch({ op: "read" });
        } else if (st.type === "find") {
          await selectTarget(st);
          await patch({ op: "find_record", navigation: st.navigation, key_template: st.binding.source === "fixed" ? st.binding.fixedValue.trim() : `{${d.params[st.id]}}`,
            ...(st.navigation === "paged" ? { next_labels: [st.nextLabel.trim()] } : {}), ...(st.navigation === "scroll" && st.endText.trim() ? { end_text: st.endText.trim() } : {}) });
        } else if (st.type === "choose") {
          await selectTarget(st);
          const fixed = st.binding.source === "fixed";
          if (st.changesScreen) {
            if (!d.transitions[st.id]) d.transitions[st.id] = `gecis_${safeSlug(st.expectName, "ekran").slice(0, 40)}_${rand4()}`;
            transitionId = d.transitions[st.id];
            server = await api("PUT", draftPath("/transitions"), { expected_revision: d.revision, transition_id: transitionId, from_screen: from[st.id], to_screen: d.screens[st.id], trigger_kind: "choice" });
            d.revision = server.revision;
          }
          await patch({ ...(transitionId ? { transition_id: transitionId } : {}), op: "ensure_choice", success_check: st.successCheck || "auto", choice_effect: st.effect,
            choice_template: fixed ? st.binding.fixedValue : `{${d.params[st.id]}}`,
            ...(fixed && st.choiceValue ? { choice_value: st.choiceValue } : {}),
            ...(st.autocomplete ? { autocomplete: true, ...(fixed && st.searchText.trim() ? { search_text: st.searchText.trim() } : {}) } : {}),
            ...(st.resultText.trim() ? { result_text: st.resultText.trim() } : {}) });
        } else if (st.type === "back") {
          if (!d.transitions[st.id]) d.transitions[st.id] = `gecis_ana_pencere_${rand4()}`;
          transitionId = d.transitions[st.id];
          server = await api("PUT", draftPath("/transitions"), { expected_revision: d.revision, transition_id: transitionId, from_screen: from[st.id], to_screen: d.screens[st.id], trigger_kind: "window_return", close: !!st.closeWindow });
          d.revision = server.revision;
          await patch({ op: "follow_transition", transition_id: transitionId });
        } else if (st.type === "multi") {
          await selectTarget(st);
          await patch({ op: "ensure_choices", choice_effect: st.effect, success_check: st.successCheck || "auto", ...(st.source === "fixed" ? { choice_set: st.fixedSet } : { choice_template: `{${d.params[st.id]}}` }) });
        } else if (st.type === "upload") {
          await selectTarget(st);
          await patch({ op: "upload_file", value_template: `{${d.params[st.id]}}`, result_text: st.resultText.trim(), ...(st.fileTypes.length ? { file_types: st.fileTypes } : {}) });
        } else if (st.type === "check") {
          await selectTarget(st);
          await patch({ op: "ensure_checked", checked: st.checked, choice_effect: st.effect, success_check: st.successCheck || "auto", ...(st.resultText.trim() ? { result_text: st.resultText.trim() } : {}) });
        } else if (st.type === "goto") {
          // Tetikleyici şimdi tekil çözülür; tıklama yapılmaz. Hedef ekran sonra “Ekranı tanıt” ile tanımlanır.
          if (!d.transitions[st.id]) d.transitions[st.id] = `gecis_${safeSlug(st.expectName, "ekran").slice(0, 40)}_${rand4()}`;
          transitionId = d.transitions[st.id];
          server = await api("PUT", draftPath("/transitions"), {
            expected_revision: d.revision, transition_id: transitionId, from_screen: from[st.id], to_screen: d.screens[st.id],
            trigger_kind: "control", session_id: real.sid, trigger_candidate_id: await resolveNow(st, realSpec(st.button)), trigger_in_found_row: !!st.inFoundRow,
            completion: gotoCompletion(st, steps),
            ...(st.newWindow ? { window: "new", ...(st.windowOrigin.trim() ? { window_origin: st.windowOrigin.trim() } : {}) } : {}),
          });
          d.revision = server.revision;
          await patch({ op: "follow_transition", transition_id: transitionId, ...(st.inFoundRow ? { in_found_row: true } : {}) });
        } else if (st.type === "call") {
          // Sözleşme özeti (girdi/çıktı/ekran/hash) sunucuda değişmez revizyondan çıkarılır.
          const args = Object.fromEntries(Object.entries(st.bindings).map(([pname, bb]) => [pname, bb.source === "fixed" ? bb.fixedValue.trim() : `{${d.params[`${st.id}/${pname}`]}}`]));
          server = await api("PUT", draftPath(`/steps/${encodeURIComponent(pendingStep)}/call`), { expected_revision: d.revision, operation_id: st.published.operation_id, revision: st.published.revision, arguments: args });
          d.revision = server.revision;
        } else {
          const params = Object.fromEntries(Object.entries(st.bindings).map(([pname, bb]) => [pname, bb.source === "fixed" ? bb.fixedValue.trim() : `{${d.params[`${st.id}/${pname}`]}}`]));
          await patch({ op: "invoke_approved_action", action_id: st.actionId, action_params: params });
        }
        d.synced.push({ localId: st.id, draftStepId: pendingStep, sig: stepSig(st, steps), transitionId });
        pendingStep = null;
      }
      // Hiçbir adımın kullanmadığı parametreler kaldırılır (silinen adımların soruları çalıştırmada istenmesin).
      const used = new Set(server.steps.flatMap((x) => [x.value_template, x.choice_template, x.key_template, ...Object.values(x.action_params || {}), ...Object.values((x.call || {}).arguments || {})])
        .filter(Boolean).flatMap((t) => [...t.matchAll(/\{([a-z][a-z0-9_]*)\}/g)].map((m) => m[1])));
      for (const t of server.transitions || []) for (const c of t.completion || []) for (const m of c.value_template.matchAll(/\{([a-z][a-z0-9_]*)\}/g)) used.add(m[1]);
      for (const prm of server.parameters.filter((x) => !used.has(x.name))) {
        server = await api("DELETE", draftPath(`/parameters/${encodeURIComponent(prm.name)}?expected_revision=${d.revision}`));
        d.revision = server.revision;
      }
      d.savedSig = draftSig(f);
      saveFlow(true);
      renderDraftBar();
      if (skipped.length) draftStatus(`Taslak kaydedildi · revizyon ${d.revision}. Kaydedilmeyen: ${skipped.join("; ")}.`, "warn");
      toast("Taslak sunucuda kaydedildi. Gerçek deneme ve yayın aşağıdaki panelde.");
      refreshLive();
    } catch (e) {
      if (pendingStep && d.id) {
        // Yarım kalan adım taslakta bırakılmaz (en iyi çaba; başarısızsa taslak yeniden açılınca görünür).
        try { const r = await api("DELETE", draftPath(`/steps/${encodeURIComponent(pendingStep)}?expected_revision=${d.revision}`)); d.revision = r.revision; } catch (_) { /* aşağıda bildirilir */ }
      }
      const msg = e.status === 409 ? "Taslak başka bir yerde değişti; hiçbir şey üzerine yazılmadı. Taslağı yeniden açıp tekrar deneyin."
        : e.message === "unresolved" ? `${e.stepIndex}. adımın hedefi ekranda tekil bulunamadı: ${e.explanation} Adımın ekranını açıp tekrar kaydedin (önceki adımlar kaydedildi).`
          : errText(e);
      draftStatus(`Kaydetme tamamlanmadı. ${msg}`, "error");
    } finally {
      btn.removeAttribute("aria-busy");
      btn.disabled = draftOf(flow()).readOnly;
    }
  }

  async function loadDraftList() {
    const ul = byId("pd-draft-list");
    ul.replaceChildren(h("li", { class: "pd-help" }, "Yükleniyor…"));
    let list;
    try { list = await api("GET", "/api/drafts"); } catch (e) { ul.replaceChildren(h("li", { class: "pd-msg pd-msg--error" }, errText(e))); return; }
    if (!list.length) { ul.replaceChildren(h("li", { class: "pd-help" }, "Kayıtlı taslak yok.")); return; }
    ul.replaceChildren(...list.map((x) => h("li", { class: "pd-flowitem" },
      h("div", { class: "pd-flowitem__main" }, h("p", { class: "pd-flowitem__name" }, x.title),
        h("p", { class: "pd-flowitem__meta" }, `${x.steps} adım · revizyon ${x.revision}${x.ready ? " · incelemeye hazır" : ""}`)),
      h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", "aria-label": `“${x.title}” taslağını aç`, onclick: () => openDraft(x.draft_id) }, "Aç"))));
  }

  const componentCache = {};
  async function componentsFor(draftId) {
    if (!componentCache[draftId]) {
      try { componentCache[draftId] = (await api("GET", `/api/drafts/${encodeURIComponent(draftId)}/components`)).components; } catch (_) { componentCache[draftId] = []; }
    }
    return componentCache[draftId];
  }
  // Taslaktan bağlama: sabit, sorulan veya önceki okuma çıktısı. Kaynağı çözülemeyen bağlama düzenlenemez.
  function openedBinding(v, pm, pp, localAt) {
    if (!pm) return { ...newBinding(), source: "fixed", fixedValue: v };
    if (pp && pp.source === "user_input") return { ...newBinding(), source: "ask", question: pp.title, questionSuggested: false };
    if (pp && pp.source === "prior_output") {
      const src = localAt[pp.prior_step];
      if (src && ((src.type === "read" && !pp.prior_output) || (src.type === "call" && pp.prior_output))) {
        return { ...newBinding(), source: "previous", previousRef: pp.prior_output ? `${src.id}/${pp.prior_output}` : src.id };
      }
    }
    return null;
  }
  async function openDraft(draftId) {
    let server;
    try { server = await api("GET", `/api/drafts/${encodeURIComponent(draftId)}`); } catch (e) { toast(errText(e)); return; }
    // Kalıcı taslaklar gerçek oturum adımlarıdır; önceki akışın deneme değerleri ve başlangıç yolu taşınmaz.
    live.args = {}; live.entryPath = undefined; live.entry = undefined; live.manualLogin = false;
    setSource("real");
    if (server.steps.some((x) => x.op === "invoke_approved_action")) await loadActions();
    const f = newFlow(server.title);
    f.applicationId = server.application_id;
    const d = draftOf(f);
    d.id = server.draft_id; d.revision = server.revision;
    if (server.screen) d.startScreenId = server.screen.screen_id;
    else if ((server.transitions || []).length) d.startScreenId = server.transitions[0].from_screen;
    const params = Object.fromEntries(server.parameters.map((x) => [x.name, x]));
    const screens = Object.fromEntries([server.screen, ...(server.extra_screens || [])].filter(Boolean).map((x) => [x.screen_id, x]));
    const localAt = [];
    const tpl = (v) => /^\{([a-z][a-z0-9_]*)\}$/.exec(v || "");
    const cannot = (ds, why) => { d.readOnly = true; d.notes.push(`“${ds.intent_text.slice(0, 60)}” adımı yeni tasarımcıda düzenlenemiyor${why ? ` (${why})` : ""}.`); localAt.push(null); };
    for (const ds of server.steps) {
      const el = ds.element_id ? server.elements[ds.element_id] : null;
      const m = tpl(ds.value_template);
      const prm = m ? params[m[1]] : null;
      if (ds.screen_id) { cannot(ds, "adıma özel ekran"); continue; }
      let st = null;
      if (ds.op === "ensure_choices" && el) {
        st = newStep("multi");
        st.target = targetFromSpec(el.target); st.name = capFirst(el.target.labels[0]); st.description = el.meaning;
        st.effect = ds.choice_effect || ""; st.successCheck = ds.success_check || "auto";
        const mm = tpl(ds.choice_template); const mp = mm ? params[mm[1]] : null;
        if (mp) { st.source = "ask"; st.question = mp.title; st.askChoices = mp.choices || null; d.params[st.id] = mm[1]; } else { st.source = "fixed"; st.fixedSet = ds.choice_set || []; }
      } else if (ds.op === "upload_file" && el) {
        st = newStep("upload");
        st.target = targetFromSpec(el.target); st.name = capFirst(el.target.labels[0]); st.description = el.meaning;
        const um = tpl(ds.value_template); const up = um ? params[um[1]] : null;
        if (!up || !up.file) { cannot(ds, "dosya parametresi okunamadı"); continue; }
        st.question = up.title; d.params[st.id] = um[1]; st.fileTypes = ds.file_types || []; st.resultText = ds.result_text || "";
      } else if ((ds.op === "ensure_value" || ds.op === "ensure_date") && el && !ds.transition_id && (!m || (prm && ["user_input", "prior_output"].includes(prm.source)))) {
        st = newStep("fill");
        st.target = targetFromSpec(el.target);
        if (ds.op === "ensure_date") { st.isDate = true; st.dateFormat = ds.date_format; }
        st.name = capFirst(el.target.region ? `${el.target.region} ${lower(el.target.labels[0])}` : el.target.labels[0]);
        st.description = el.meaning;
        st.successCheck = ds.success_check || "auto";
        if (prm && prm.source === "prior_output") {
          const src = localAt[prm.prior_step];
          const fits = src && ((src.type === "read" && !prm.prior_output) || (src.type === "call" && prm.prior_output));
          if (!fits) { cannot(ds, "önceki çıktının kaynağı okunamadı"); continue; }
          st.binding.source = "previous"; st.binding.previousRef = prm.prior_output ? `${src.id}/${prm.prior_output}` : src.id; d.params[st.id] = m[1];
        } else if (prm) { st.binding.source = "ask"; st.binding.question = prm.title; st.binding.questionSuggested = false; d.params[st.id] = m[1]; }
        else { st.binding.source = "fixed"; st.binding.fixedValue = ds.value_template || ""; }
      } else if (ds.op === "ensure_checked" && el) {
        st = newStep("check");
        st.target = targetFromSpec(el.target);
        st.name = capFirst(el.target.region ? `${el.target.region} ${lower(el.target.labels[0])}` : el.target.labels[0]);
        st.description = el.meaning;
        st.checked = ds.checked; st.effect = ds.choice_effect || ""; st.successCheck = ds.success_check || "auto"; st.resultText = ds.result_text || "";
      } else if (ds.op === "ensure_choice" && el) {
        const cm = tpl(ds.choice_template);
        const cp = cm ? params[cm[1]] : null;
        if (cm && !(cp && ["user_input", "prior_output"].includes(cp.source))) { cannot(ds, "değer kaynağı desteklenmiyor"); continue; }
        st = newStep("choose");
        st.target = targetFromSpec(el.target);
        st.name = capFirst(el.target.region ? `${el.target.region} ${lower(el.target.labels[0])}` : el.target.labels[0]);
        st.description = el.meaning;
        st.effect = ds.choice_effect || "";
        st.successCheck = ds.success_check || "auto";
        st.resultText = ds.result_text || "";
        st.autocomplete = !!ds.autocomplete; st.searchText = ds.search_text || "";
        if (ds.transition_id) {
          const t = (server.transitions || []).find((x) => x.transition_id === ds.transition_id);
          if (!t || t.trigger.kind !== "choice") { cannot(ds, "geçiş tanımı desteklenmiyor"); continue; }
          st.changesScreen = true;
          st.expectName = screens[t.to_screen] ? screens[t.to_screen].title : t.to_screen;
          d.screens[st.id] = t.to_screen; d.transitions[st.id] = t.transition_id;
        }
        if (cp && cp.source === "prior_output") {
          const src = localAt[cp.prior_step];
          if (!src || !((src.type === "read" && !cp.prior_output) || (src.type === "call" && cp.prior_output))) { cannot(ds, "önceki çıktının kaynağı okunamadı"); continue; }
          st.binding.source = "previous"; st.binding.previousRef = cp.prior_output ? `${src.id}/${cp.prior_output}` : src.id; d.params[st.id] = cm[1];
        } else if (cp) {
          st.binding.source = "ask"; st.binding.question = cp.title; st.binding.questionSuggested = false; d.params[st.id] = cm[1];
          st.askChoices = cp.choices || null; st.askDynamic = !cp.choices;
        } else { st.binding.source = "fixed"; st.binding.fixedValue = ds.choice_template || ""; st.choiceValue = ds.choice_value || null; }
      } else if (ds.op === "find_record" && el) {
        const km = tpl(ds.key_template);
        const kp = km ? params[km[1]] : null;
        const bound = openedBinding(ds.key_template || "", km, kp, localAt);
        if (!bound) { cannot(ds, "anahtar kaynağı desteklenmiyor"); continue; }
        st = newStep("find");
        st.target = targetFromSpec(el.target);
        st.name = capFirst(el.target.labels[0]); st.description = el.meaning;
        st.binding = bound; if (km) d.params[st.id] = km[1];
        st.navigation = ds.navigation || "none";
        st.nextLabel = (ds.next_labels || ["Sonraki"])[0]; st.endText = ds.end_text || "";
      } else if (ds.op === "read" && el && !ds.transition_id) {
        st = newStep("read");
        st.target = targetFromSpec(el.target);
        st.name = capFirst(el.target.region ? `${el.target.region} ${lower(el.target.labels[0])}` : el.target.labels[0]);
        st.description = el.meaning;
      } else if (ds.op === "follow_transition") {
        const t = (server.transitions || []).find((x) => x.transition_id === ds.transition_id);
        if (t && t.trigger.kind === "window_return") {
          st = newStep("back"); st.closeWindow = t.trigger.close !== false;
          d.screens[st.id] = t.to_screen; d.transitions[st.id] = t.transition_id;
          st.inFoundRow = false; localAt.push(st); f.steps.push(st);
          d.synced.push({ localId: st.id, draftStepId: ds.step_id, sig: "", transitionId: t.transition_id });
          continue;
        }
        if (!t || t.trigger.kind !== "control" || (t.completion || []).length > 1) { cannot(ds, "geçiş tanımı desteklenmiyor"); continue; }
        st = newStep("goto");
        st.newWindow = t.window === "new"; st.windowOrigin = t.window_origin || "";
        st.button = targetFromSpec(t.trigger.target);
        const named = /“([^”]+)” ekranına geç/.exec(ds.intent_text || "");
        st.expectName = screens[t.to_screen] ? screens[t.to_screen].title : named ? named[1] : t.to_screen;
        st.confirmNoData = true; // kaydedilirken onaylanmıştı
        d.screens[st.id] = t.to_screen; d.transitions[st.id] = t.transition_id;
        if ((t.completion || []).length) {
          const cc = t.completion[0]; const finder = [...localAt].reverse().find((x) => x && x.type === "find");
          const same = finder && (finder.binding.source === "fixed" ? finder.binding.fixedValue === cc.value_template : `{${d.params[finder.id]}}` === cc.value_template);
          st.completion = { label: cc.target.labels[0], section: cc.target.region || "", source: same ? "found" : "fixed", fixed: same ? "" : cc.value_template };
        }
      } else if (ds.op === "call_operation" && ds.call) {
        st = newStep("call");
        const meta = (await componentsFor(d.id)).find((x) => x.operation_id === ds.call.operation_id) || {};
        st.published = { operation_id: ds.call.operation_id, revision: ds.call.revision, title: meta.title || ds.call.operation_id,
          inputs: ds.call.inputs.map((n) => ({ name: n, title: ((meta.inputs || []).find((x) => x.name === n) || {}).title || n, max_length: 200 })),
          outputs: ds.call.outputs.map((n) => ({ name: n, title: ((meta.outputs || []).find((x) => x.name === n) || {}).title || n })),
          start_screen: ds.call.start_screen, end_screen: ds.call.end_screen, effect: meta.effect || "mutating", steps: meta.steps || 0 };
        let ok = true;
        for (const [pname, v] of Object.entries(ds.call.arguments || {})) {
          const pm = tpl(v); const pp = pm ? params[pm[1]] : null;
          const bound = openedBinding(v, pm, pp, localAt);
          if (!bound) ok = false;
          else st.bindings[pname] = bound;
          if (pp) d.params[`${st.id}/${pname}`] = pm[1];
        }
        if (!ok) { cannot(ds, "değer kaynağı desteklenmiyor"); continue; }
      } else if (ds.op === "invoke_approved_action" && !ds.transition_id && (real.actions || []).some((x) => x.action_id === ds.action_id)) {
        st = newStep("action");
        st.actionId = ds.action_id;
        let ok = true;
        for (const [pname, v] of Object.entries(ds.action_params || {})) {
          const pm = tpl(v); const pp = pm ? params[pm[1]] : null;
          const bound = openedBinding(v, pm, pp, localAt);
          if (!bound) ok = false;
          else st.bindings[pname] = bound;
          if (pp) d.params[`${st.id}/${pname}`] = pm[1];
        }
        if (!ok) { cannot(ds, "değer kaynağı desteklenmiyor"); continue; }
      } else { cannot(ds); continue; }
      st.inFoundRow = !!ds.in_found_row;
      localAt.push(st);
      f.steps.push(st);
      d.synced.push({ localId: st.id, draftStepId: ds.step_id, sig: "", transitionId: d.transitions[st.id] || null });
    }
    const ps = persistable(f).steps;
    for (const x of d.synced) { const st = f.steps.find((y) => y.id === x.localId); x.sig = st ? stepSig(st, ps) : ""; }
    d.savedSig = draftSig(f);
    // Onaylı işlem tanımı değiştiyse adım eski özetle kalamaz: “Taslağı kaydet” yeniden bağlar, deneme ve onay yenilenir.
    for (const x of d.synced) {
      const ds = server.steps.find((y) => y.step_id === x.draftStepId);
      const act = ds && ds.action_id ? (real.actions || []).find((y) => y.action_id === ds.action_id) : null;
      if (act && ds.action_hash && ds.action_hash !== act.fingerprint) { x.sig = ""; d.savedSig = ""; }
    }
    state.flows.push(clone(f));
    state.editing = { flow: f, baseline: editable(f), isNew: false };
    enterEditor();
    refreshLive();
    if (!APPS.some((a) => a.id === f.applicationId)) toast("Bu taslağın uygulaması yapılandırılmış uygulamalar arasında değil.");
  }

  // ===================================================================
  // Gerçek deneme ve yayın: mevcut taslak uçları (confirm / trial / confirm-outcome / screen / fresh-test) ve
  // onay/yayın (approve / publish; yayıncı rolü). Yeni onay katmanı yok; politika sunucudadır.
  // ===================================================================
  const STEP_STATUS_TR = {
    intent_entered: "Tanım eksik", target_proposed: "Hedef öneriliyor", target_selected: "Onay bekliyor",
    meaning_and_target_confirmed: "Denemeye hazır", trial_requested: "Deneniyor", observed: "Sonuç onayı bekliyor",
    outcome_confirmed: "Sonuç onaylandı", ready_for_review: "Hazır",
  };
  const live = { server: null, args: {} };
  function liveStatus(text, kind) { const el = byId("pd-runpanel-status"); el.textContent = text || ""; el.className = "pd-real__status" + (kind ? ` is-${kind}` : ""); }
  async function liveCall(method, path, body, okText) {
    liveStatus("Çalışıyor…", "busy");
    try {
      const r = await api(method, path, body);
      if (r && r.draft_id && r.steps) live.server = r;
      if (okText) liveStatus(okText, "ok");
      return r;
    } catch (e) {
      const why = e.body && e.body.details ? Object.values(e.body.details).filter((x) => typeof x === "string").join(" ") : "";
      liveStatus(e.status === 403 ? "Bu işlem için yetkiniz yok (ör. onay/yayın yayıncı rolü ister)." : `${errText(e)} ${why}`.trim(), "error");
      return null;
    } finally { renderLive(); }
  }
  async function refreshLive() {
    if (!state.editing) return;
    const d = draftOf(flow());
    if (!d.id || d.readOnly) { live.server = null; renderLive(); return; }
    if (state.source === "real") await loadSessions(real.sid);  // başlangıç yolu güncel oturumdan önerilsin
    try { live.server = await api("GET", `/api/drafts/${encodeURIComponent(d.id)}`); d.revision = live.server.revision; } catch (_) { live.server = null; }
    live.updates = [];
    if (live.server && live.server.steps.some((x) => x.call)) {
      try { live.updates = (await api("GET", `/api/drafts/${encodeURIComponent(d.id)}/component-updates`)).updates; } catch (_) { live.updates = []; }
    }
    renderLive();
  }
  const dpath = (suffix) => `/api/drafts/${encodeURIComponent(live.server.draft_id)}${suffix}`;
  function rev() { return live.server.revision; }

  function renderLive() {
    const host = byId("pd-runpanel");
    const srv = live.server;
    host.hidden = !srv;
    if (!srv) return;
    draftOf(flow()).revision = srv.revision;
    const body = [];
    // 1) Ekranlar: rotadaki her ekran (başlangıç + her geçişin hedefi) tanıtılmalıdır.
    const route = liveRoute(srv);
    const pending = route.filter((x) => !x.defined);
    const choose = h("select", { id: "pd-screen-which" }, route.map((x) => h("option", { value: x.id }, `${x.title}${x.defined ? " (tanıtıldı; yeniden tanıt)" : ""}`)));
    if (pending.length) choose.value = pending[0].id;
    body.push(h("div", { class: "pd-live__block" }, h("p", { class: "pd-live__label" }, "1. Ekranlar"),
      h("ul", { class: "pd-live__screens" }, route.map((x) => h("li", null, `${x.title}: `, h("span", { class: x.defined ? "pd-badge pd-badge--ok" : "pd-badge pd-badge--warn" }, x.defined ? "tanıtıldı" : "tanıtılmadı")))),
      h("p", { class: "pd-help" }, pending.length
        ? "Onay ve yayın için her ekranın tanıtılması gerekir. İlgili ekran oturumda açıkken sistem tanıtıcı işaretler önerir; siz onaylarsınız. Sonraki ekrana geçmek için düğmeye tarayıcıda kendiniz basın."
        : `Tanımlı: ${route.map((x) => x.title).join(", ")}. Her işlemden önce beklenen ekran doğrulanır.`),
      h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: "pd-screen-which" }, "Tarayıcıda şu an açık olan ekran"), choose),
      h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", onclick: () => proposeScreen(choose.value) }, "Ekranı tanıt"),
      h("div", { id: "pd-screen-proposal" })));
    // Başlangıç kayıt bağlamı: açık kayıt istenen kayıt değilse işlem başlamaz.
    body.push(startContextBlock(srv));
    body.push(optionalDialogsBlock(srv));
    // 2) Sorulacak değerler (deneme için)
    const asks = srv.parameters.filter((x) => x.source === "user_input");
    if (asks.length) {
      body.push(h("div", { class: "pd-live__block" }, h("p", { class: "pd-live__label" }, "2. Deneme değerleri"),
        asks.map((x) => h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: `pd-arg-${x.name}` }, x.title),
          x.file ? fileArg(x) : x.multiple ? h("textarea", { id: `pd-arg-${x.name}`, rows: "3", oninput: (e) => { live.args[x.name] = e.target.value; } }, live.args[x.name] || "") :
          x.choices
            ? (() => { const sel = h("select", { id: `pd-arg-${x.name}`, onchange: (e) => { live.args[x.name] = e.target.value; } }, h("option", { value: "" }, "Seçin…"), x.choices.map((c) => h("option", { value: c.label }, c.label))); sel.value = live.args[x.name] || ""; return sel; })()
            : h("input", { type: "text", id: `pd-arg-${x.name}`, value: live.args[x.name] || "", autocomplete: "off", oninput: (e) => { live.args[x.name] = e.target.value; } })))));
    }
    // 3) Adımlar: onay → gerçek deneme → sonuç onayı
    body.push(h("div", { class: "pd-live__block" }, h("p", { class: "pd-live__label" }, "3. Adımlar"),
      h("ol", { class: "pd-live__steps" }, srv.steps.map((st) => liveStep(st)))));
    // 3b) Bileşen sürümleri: yeni sürüm kendiliğinden kullanılmaz; etki gösterilir, yükseltme açık işlemdir.
    if ((live.updates || []).length) {
      body.push(h("div", { class: "pd-live__block" }, h("p", { class: "pd-live__label" }, "Bileşen sürümleri"),
        h("ul", null, live.updates.map((u) => h("li", { class: "pd-live__update" },
          h("p", null, `${u.step}. adım: “${u.operation_id}” sürüm ${u.pinned_revision} kullanılıyor; yayında sürüm ${u.latest_revision} var.`),
          h("p", { class: u.compatible ? "pd-help" : "pd-msg pd-msg--error" }, u.compatible ? "Uyumlu: girdiler, kullanılan çıktılar ve ekranlar aynı."
            : [u.new_inputs.length ? `Yeni girdi: ${u.new_inputs.join(", ")}.` : "", u.lost_outputs.length ? `Kullanılan çıktı kalktı: ${u.lost_outputs.join(", ")}.` : "", u.screen_changed ? "Başlangıç/bitiş ekranı değişti." : ""].join(" ").trim()),
          h("p", { class: "pd-help" }, "Yükseltme bu adımın onayını, denemesini ve yeni oturum testini sıfırlar; yeniden denemeniz gerekir."),
          u.compatible ? h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", onclick: () => upgradeCall(u) }, `Sürüm ${u.latest_revision}'e yükselt`)
            : h("p", { class: "pd-help" }, "Uyumsuz sürüme geçmek için adımı düzenleyicide yeniden kurun."))))));
    }
    // 4) Yeni oturum testi ve yayın. Test sizin oturumunuzu kullanmaz: yeni oturum girişsiz açılır.
    // Lab'da başlangıç ekranı deney uygulamasının otomatik giriş adresiyle açılır (eski tasarımcıyla aynı yol).
    // Otomatik giriş kararı sunucudadır (taslak yanıtındaki politika); sayfaya gömülü değere dayanmaz.
    const app = APPS.find((a) => a.id === srv.application_id);
    const policy = srv.fresh_test_entry || { mode: "url", reason: "Sunucu başlangıç adresi politikasını vermedi." };
    const labApp = policy.mode === "lab_autologin";
    const LAB = labApp ? policy.origin : "";
    const wait = srv.fresh_wait;
    const cur = real.sessions.find((x) => x.session_id === real.sid);
    const curPath = cur && cur.current_url && cur.current_url.startsWith(LAB) ? new URL(cur.current_url).pathname : "";
    if (labApp && live.entryPath === undefined) live.entryPath = curPath && curPath !== "/login" ? curPath : "/pages/duplicates";
    const entryField = labApp
      ? h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: "pd-entry-path" }, "Başlangıç ekranı (deney uygulamasındaki yol)"),
        h("input", { type: "text", id: "pd-entry-path", value: live.entryPath, autocomplete: "off", oninput: (e) => { live.entryPath = e.target.value; } }),
        h("p", { class: "pd-help" }, "Yeni oturum, deney uygulamasına otomatik giriş yapılarak bu ekranda açılır. Sizin tarayıcı oturumunuz kullanılmaz."))
      : h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: "pd-entry-url" }, "Başlangıç adresi (izinli adresler içinde)"),
        h("input", { type: "text", id: "pd-entry-url", value: live.entry || (app ? app.base_url : ""), autocomplete: "off", oninput: (e) => { live.entry = e.target.value; } }),
        h("p", { class: "pd-help" }, "Yeni oturum girişsiz açılır; adres giriş gerektiriyorsa test giriş ekranında durur. Gerçek uygulamada yeni oturuma giriş (SSO) yöntemi henüz yok."),
        h("details", null, h("summary", null, "Otomatik giriş neden yok?"), h("p", { class: "pd-help", id: "pd-entry-reason" }, policy.reason)));
    const labPath = () => (live.entryPath.startsWith("/") ? live.entryPath : `/${live.entryPath}`);
    const entryUrl = () => (labApp
      ? (live.manualLogin ? `${LAB}${labPath()}` : `${LAB}/__lab/autologin?user=tasarim&next=${encodeURIComponent(labPath())}`)
      : byId("pd-entry-url").value);
    // Elle giriş: kimlik bilgisi yalnız otomasyon penceresine yazılır; bu sayfaya veya sunucuya gelmez.
    const manualBox = labApp ? h("label", { class: "pd-check-row" },
      h("input", { type: "checkbox", id: "pd-manual-login", checked: !!live.manualLogin, onchange: (e) => { live.manualLogin = e.target.checked; } }),
      h("span", null, "Girişi yeni pencerede elle yapacağım (otomatik giriş kullanılmasın)")) : null;
    const waitBox = wait ? h("div", { class: "pd-msg pd-msg--missing", id: "pd-fresh-wait", role: "status" }, h("div", null,
      h("p", null, h("strong", null, wait.resuming ? "Yeniden giriş bekleniyor. " : "Elle giriş bekleniyor. "), wait.message),
      h("p", null, `Kalan süre: yaklaşık ${Math.ceil(wait.expires_in_s / 60)} dakika. Kullanıcı adı ve parolanız AgenTask'a gelmez ve saklanmaz.`),
      h("div", { class: "pd-real__buttons" },
        h("button", { type: "button", class: "pd-btn pd-btn--primary pd-btn--sm", disabled: !!wait.busy, onclick: async () => {
          const r = await liveCall("POST", dpath("/fresh-test/continue"));
          if (r) liveStatus(r.fresh_wait ? r.fresh_wait.message : r.fresh_test && r.fresh_test.passed ? "Yeni oturum testi tamamlandı: BAŞARILI." : "Yeni oturum testi başarısız; nedeni ve sonraki adım aşağıda.", r.fresh_wait ? "warn" : r.fresh_test && r.fresh_test.passed ? "ok" : "error");
        } }, "Giriş yaptım, devam et"),
        h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", disabled: !!wait.busy, onclick: () => liveCall("POST", dpath("/fresh-test/cancel"), undefined, "Yeni oturum testi iptal edildi; sonuç yazılmadı.") }, "Vazgeç")))) : null;
    const issues = srv.issues || [];
    const fail = srv.fresh_test_failure;
    const failBox = fail ? h("div", { class: "pd-msg pd-msg--error", id: "pd-fresh-failure", role: "alert" }, h("div", null,
      h("p", null, h("strong", null, `Yeni oturum testi başarısız (${fail.stage}${fail.step ? `, ${fail.step}. komut` : ""}): `), fail.reason),
      h("p", null, h("strong", null, "Sonraki adım: "), fail.code === "SESSION_EXPIRED"
        ? (labApp ? "Başlangıç ekranı yolunu kontrol edip “Yeni oturum testi”ni yeniden çalıştırın; deney uygulamasında giriş artık otomatik yapılır."
          : "Gerçek uygulamada yeni oturuma otomatik giriş henüz desteklenmiyor (SSO kararı bekliyor); bu test gerçek ortamda yapılamaz.")
        : fail.next),
      h("details", null, h("summary", null, "Teknik ayrıntı"), h("p", null, `${fail.error_class || fail.code} · run ${fail.run_id} · durum ${fail.run_status || "-"}`)))) : null;
    const ISSUE_TR = { fresh_session_test_missing: "Yeni oturum testi henüz yapılmadı.", fresh_session_test_stale: "Tanım değişti; yeni oturum testini yeniden çalıştırın.",
      fresh_session_test_failed: "Yeni oturum testi başarısız (nedeni yukarıda).", screen_missing: "Başlangıç ekranı tanıtılmadı." };
    const actionIssue = (x) => (/^step_\d+_action_(changed|unpinned|wrong_application)/.test(x) ? `${x.split("_")[1]}. adımın onaylı işlemi değişti veya bu uygulamaya ait değil; “Taslağı kaydet” deyip yeniden deneyin ve onaylayın.` : null);
    const plain = issues.map((x) => ISSUE_TR[x] || actionIssue(x) || (/^step_\d+_not_ready$/.test(x) ? `${x.split("_")[1]}. adım onay/deneme bekliyor.` : null)).filter(Boolean);
    body.push(h("div", { class: "pd-live__block" }, h("p", { class: "pd-live__label" }, "4. Yeni oturum testi, onay ve yayın"),
      entryField, manualBox, waitBox,
      h("div", { class: "pd-real__buttons" },
        h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", disabled: !!wait, onclick: async () => {
          const r = await liveCall("POST", dpath("/fresh-test"), { expected_revision: rev(), args: { ...live.args }, entry_url: entryUrl(), manual_login: !!live.manualLogin });
          if (r && r.fresh_wait) liveStatus("Elle giriş bekleniyor; açılan pencerede giriş yapın.", "warn");
          else if (r) liveStatus(r.fresh_test && r.fresh_test.passed ? "Yeni oturum testi tamamlandı: BAŞARILI." : "Yeni oturum testi başarısız; nedeni ve sonraki adım aşağıda.", r.fresh_test && r.fresh_test.passed ? "ok" : "error");
        } }, "Yeni oturum testi"),
        h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", onclick: async () => { const r = await liveCall("POST", dpath("/approve"), { expected_revision: rev() }, "Onaylandı (yayıncı)."); if (r) refreshLive(); } }, "Onayla (yayıncı)"),
        h("button", { type: "button", class: "pd-btn pd-btn--publish pd-btn--sm", onclick: async () => { const r = await liveCall("POST", dpath("/publish"), { request_id: crypto.randomUUID() }); if (r) liveStatus(`Yayımlandı ve etkin: ${r.release_id}`, "ok"); } }, "Yayımla")),
      failBox,
      srv.fresh_test && srv.fresh_test.passed && !issues.includes("fresh_session_test_stale") ? h("p", { class: "pd-help" }, "Yeni oturum testi: BAŞARILI.") : null,
      h("p", { class: "pd-help", id: "pd-approval-state" }, !srv.approval ? "Henüz yayıncı onayı yok."
        : srv.approval.content_hash === srv.content_hash ? "Yayıncı onayı var ve bu tanım için geçerli." : "Eski yayıncı onayı bu tanım için geçersiz; yeniden onaylayın."),
      issues.length ? h("div", null, h("p", { class: "pd-help" }, "Onaydan önce tamamlanacaklar:"), h("ul", { id: "pd-issues" }, plain.map((x) => h("li", null, x))),
        h("details", null, h("summary", null, `${issues.length} eksik (teknik)`), h("ul", null, issues.map((x) => h("li", null, x)))))
        : h("p", { class: "pd-help" }, "Eksik yok: incelemeye hazır.")));
    byId("pd-runpanel-body").replaceChildren(...body);
  }

  function startContextBlock(srv) {
    const form = live.ctxForm || (live.ctxForm = { label: "", section: "", value: "" });
    const asks = srv.parameters.filter((x) => x.source === "user_input");
    const list = (srv.start_context || []).map((c, i) => h("li", null, `${c.target.region ? `${c.target.region} › ` : ""}${c.target.labels[0]} = ${c.value_template} `,
      h("button", { type: "button", class: "pd-btn pd-btn--ghost pd-btn--sm", onclick: () => saveStartContext(srv.start_context.filter((_, x) => x !== i)) }, "Kaldır")));
    const input = (key, label) => { const i = h("input", { type: "text", id: `pd-ctx-${key}`, value: form[key], maxlength: "120", autocomplete: "off", oninput: (e) => { form[key] = e.target.value; } }); return h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: i.id }, label), i); };
    return h("div", { class: "pd-live__block" }, h("p", { class: "pd-live__label" }, "Başlangıç kayıt bağlamı (isteğe bağlı)"),
      list.length ? h("ul", { id: "pd-start-context" }, list) : h("p", { class: "pd-help" }, "Tanım yok: işlem açık kaydı doğrulamadan başlar."),
      input("label", "Alanın etiketi"), input("section", "Bölüm (varsa)"), input("value", asks.length ? `Beklenen değer (sabit veya ${asks.map((x) => `{${x.name}}`).join(", ")})` : "Beklenen değer"),
      h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", onclick: () => {
        if (!form.label.trim() || !form.value.trim()) { liveStatus("Etiket ve beklenen değer gerekli.", "warn"); return; }
        const next = [...(srv.start_context || []), { target: { kind: "textbox", labels: [form.label.trim()], ...(form.section.trim() ? { region: form.section.trim() } : {}) }, value_template: form.value.trim() }];
        live.ctxForm = null; saveStartContext(next);
      } }, "Bağlam koşulu ekle"));
  }
  const saveStartContext = (checks) => liveCall("PUT", dpath("/start-context"), { expected_revision: rev(), checks: checks.map((c) => ({ target: c.target, value_template: c.value_template })) }, "Başlangıç kayıt bağlamı kaydedildi.");

  function liveStep(st) {
    const status = STEP_STATUS_TR[st.status] || st.status;
    const acks = ["meaning", "target", "effect", "params"];
    const ackText = { meaning: "Adımın ne yaptığı doğru", target: "Seçilen alan doğru", effect: st.effect === "mutating" ? "Veri değiştirdiğini biliyorum" : st.effect === "unknown" ? "Kayıt veya ekran değişikliği tetikleyebileceğini biliyorum" : "İş etkisi yok / yalnız alana yazar", params: "Değer kaynağı doğru" };
    const ackBoxes = acks.map((k) => h("label", { class: "pd-check-row" }, h("input", { type: "checkbox", "data-ack": k }), h("span", null, ackText[k])));
    const box = h("div", { class: "pd-live__acks" }, ackBoxes);
    const effectAck = h("label", { class: "pd-check-row" }, h("input", { type: "checkbox", "data-effect": "1" }), h("span", null, "Bu deneme hedef uygulamada işlem yapabilir; onaylıyorum"));
    const verified = st.trial && st.trial.verified;
    return h("li", { class: "pd-live__step" },
      h("p", null, h("strong", null, st.intent_text), " · ", h("span", { class: "pd-badge pd-badge--muted" }, status)),
      st.status === "target_selected" ? h("div", null, box,
        h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", onclick: () => {
          const v = Object.fromEntries(acks.map((k) => [k, box.querySelector(`[data-ack=${k}]`).checked]));
          if (!acks.every((k) => v[k])) { liveStatus("Dört maddeyi de kontrol edip işaretleyin.", "warn"); return; }
          liveCall("POST", dpath(`/steps/${encodeURIComponent(st.step_id)}/confirm`), { expected_revision: rev(), ...v }, "Adım onaylandı.");
        } }, "Onayla")) : null,
      ["meaning_and_target_confirmed", "observed"].includes(st.status) ? h("div", null, effectAck,
        h("button", { type: "button", class: "pd-btn pd-btn--primary pd-btn--sm", onclick: () => {
          if (!real.sid) { liveStatus("Gerçek deneme için tarayıcı oturumu seçin ve ekranı açın.", "warn"); return; }
          if (!effectAck.querySelector("input").checked) { liveStatus("Gerçek denemenin etkisini onaylayın.", "warn"); return; }
          liveCall("POST", dpath(`/steps/${encodeURIComponent(st.step_id)}/trial`), { expected_revision: rev(), session_id: real.sid, args: { ...live.args }, acknowledge_effect: true },
            "Deneme bitti; sonucu kontrol edin.");
        } }, "Gerçek dene")) : null,
      st.trial ? h("p", { class: verified ? "pd-help" : "pd-msg pd-msg--error" }, verified ? "Sistem doğrulaması: BAŞARILI (yalnız tıklama değil; değer/ekran kontrol edildi)." : `Sistem doğrulaması başarısız${st.trial.error_class ? ` (${st.trial.error_class})` : ""}.`) : null,
      st.status === "observed" && verified ? h("button", { type: "button", class: "pd-btn pd-btn--secondary pd-btn--sm", onclick: () => liveCall("POST", dpath(`/steps/${encodeURIComponent(st.step_id)}/confirm-outcome`), { expected_revision: rev() }, "Sonuç onaylandı.") }, "Sonucu onayla") : null);
  }

  // Rota ekranları: kimlikleri taslaktan (geçişler) okunur; adı tanıtılmışsa ekran başlığı, değilse analistin
  // "Ekrana geç" adımında yazdığı ad.
  function liveRoute(srv) {
    const d = draftOf(flow());
    const defined = Object.fromEntries([srv.screen, ...(srv.extra_screens || [])].filter(Boolean).map((x) => [x.screen_id, x]));
    const firstCall = srv.steps.find((x) => x.call);
    const start = srv.screen ? srv.screen.screen_id : (srv.transitions || []).length ? srv.transitions[0].from_screen
      : firstCall ? firstCall.call.start_screen : d.startScreenId || safeSlug(`${flow().name} ekranı`, "ekran");
    const ids = [start];
    for (const st of srv.steps) {
      const t = (srv.transitions || []).find((x) => x.transition_id === st.transition_id);
      if (t && !ids.includes(t.to_screen)) ids.push(t.to_screen);
    }
    const nameOf = (id) => {
      if (defined[id]) return defined[id].title;
      if (id === start) return `${flow().name.trim() || "İşlem"} ekranı`;
      const local = flow().steps.find((x) => d.screens[x.id] === id && x.type !== "back");
      return local ? local.expectName.trim() : id;
    };
    return ids.map((id) => ({ id, title: nameOf(id), defined: !!defined[id], start: id === start }));
  }

  async function upgradeCall(u) {
    const st = live.server.steps.find((x) => x.step_id === u.step_id);
    if (!st || !st.call) return;
    const r = await liveCall("PUT", dpath(`/steps/${encodeURIComponent(u.step_id)}/call`), { expected_revision: rev(), operation_id: u.operation_id, revision: u.latest_revision, arguments: st.call.arguments },
      `Sürüm ${u.latest_revision}'e yükseltildi; adımı yeniden onaylayıp deneyin.`);
    if (!r) return;
    const f = flow(); const d = draftOf(f);
    const link = d.synced.find((x) => x.draftStepId === u.step_id);
    const local = link && f.steps.find((x) => x.id === link.localId);
    if (local && local.published) {
      local.published.revision = u.latest_revision;
      const ps = persistable(f).steps;
      link.sig = stepSig(local, ps); d.savedSig = draftSig(f);
      renderSteps(); renderDraftBar();
    }
    delete componentCache[d.id];
    refreshLive();
  }

  async function proposeScreen(screenId) {
    const host = byId("pd-screen-proposal");
    if (!real.sid) { liveStatus("Önce gerçek oturumu seçin ve alanların bulunduğu ekranı açın.", "warn"); return; }
    const which = liveRoute(live.server).find((x) => x.id === screenId) || liveRoute(live.server)[0];
    host.replaceChildren(h("p", { class: "pd-help" }, "Ekran bekleniyor…"));
    let snap;
    try { snap = await api("POST", sessionPath("/observe")); } catch (e) { host.replaceChildren(h("p", { class: "pd-msg pd-msg--error" }, errText(e))); return; }
    const srv = live.server;
    // Yalnız bu ekrandaki adımların hedefleri işlem hedefidir (işaret olamaz).
    const targets = srv.steps.filter((st) => st.element_id && (st.expected_screen || liveRoute(srv)[0].id) === which.id)
      .map((st) => srv.elements[st.element_id]).filter(Boolean).map((el) => el.target);
    const isTarget = (c) => targets.some((t) => t.kind === c.kind && t.labels.includes(c.label || c.accessible_name) && (!t.region || (c.contexts || []).some((x) => x.name === t.region)));
    const regionOf = (c) => ((c.contexts || []).find((x) => x.kind !== "table_row" && x.name) || {}).name || null;
    const usable = snap.controls.filter((c) => c.kind !== "link" && !(c.contexts || []).some((x) => x.kind === "table_row") && c.visible && !c.sensitive && c.interaction === "open" && (c.label || c.accessible_name) && !isTarget(c));
    const regions = [...new Set(targets.map((t) => t.region).filter(Boolean))];
    const picks = [];
    for (const r of regions) { const c = usable.find((x) => regionOf(x) === r && !picks.includes(x)); if (c) picks.push(c); }
    for (const c of usable) { if (picks.length >= 3) break; if (!picks.includes(c) && !regionOf(c)) picks.push(c); }
    // Bu ekranda işlem hedefi yoksa (ör. geçişin hedef ekranı) bölgeli kontroller de tanıtıcı olabilir.
    if (!picks.length) for (const c of usable) { if (picks.length >= 3) break; picks.push(c); }
    // Tek alanlı bölüm: işlem hedefi bölge kanıtı olabilir; ekranda en az bir başka işaret varsa (domain/screens).
    if (picks.length) {
      for (const r of regions) {
        if (picks.some((c) => regionOf(c) === r)) continue;
        const own = snap.controls.find((c) => regionOf(c) === r && c.visible && !c.sensitive && c.interaction === "open" && (c.label || c.accessible_name));
        if (own) picks.push(own);
      }
    }
    if (!picks.length) { host.replaceChildren(h("p", { class: "pd-msg pd-msg--missing" }, "Bu ekranda işlem hedefi olmayan tanıtıcı bir kontrol bulunamadı; ekran tanımı yapılamıyor.")); return; }
    const title = h("input", { type: "text", id: "pd-screen-title", value: which.title, maxlength: "120" });
    const list = picks.map((c) => h("label", { class: "pd-check-row" }, h("input", { type: "checkbox", checked: true, "data-cid": c.candidate_id }), h("span", null, c.caption)));
    const missingRegions = regions.filter((r) => !picks.some((c) => regionOf(c) === r));
    host.replaceChildren(
      h("div", { class: "pd-field" }, h("label", { class: "pd-label", for: "pd-screen-title" }, "Ekranın adı"), title),
      h("p", { class: "pd-help" }, "Bu ekranı tanıtan işaretler (işlem hedefi olmayan, ekranda hep bulunan kontroller):"), ...list,
      ...(missingRegions.length ? [h("p", { class: "pd-msg pd-msg--missing" }, `Şu bölümler için tanıtıcı işaret bulunamadı: ${missingRegions.join(", ")}.`)] : []),
      h("button", { type: "button", class: "pd-btn pd-btn--primary pd-btn--sm", onclick: () => {
        const ids = [...host.querySelectorAll("[data-cid]")].filter((x) => x.checked).map((x) => x.dataset.cid);
        if (!ids.length) { liveStatus("En az bir işaret seçin.", "warn"); return; }
        const chosen = picks.filter((c) => ids.includes(c.candidate_id));
        const proven = [...new Set(chosen.map(regionOf).filter((r) => r && regions.includes(r)))];
        liveCall("PUT", dpath("/screen"), { expected_revision: rev(), session_id: real.sid, screen_id: which.id, title: title.value.trim().slice(0, 120),
          marker_candidate_ids: ids, regions: proven.map((name) => ({ name })) }, `“${title.value.trim()}” ekranı tanımlandı ve doğrulandı.`);
      } }, "Bu işaretlerle ekranı tanıt"));
  }

  byId("pd-save-draft").addEventListener("click", saveDraft);
  byId("pd-load-drafts").addEventListener("click", loadDraftList);

  // Sayfa yenileme/kapatma: her şey bellekte olduğundan kayıp olacak veri varsa tarayıcı uyarısı istenir.
  // Metni tarayıcı belirler; sayfayla hiç etkileşim olmadıysa bazı tarayıcılar uyarıyı göstermez.
  window.addEventListener("beforeunload", (e) => {
    if (state.flows.length || state.components.length || isDirty()) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  renderAll();
})();
