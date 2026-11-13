// Katalog Tasarımcısı: yönlendirilmiş, modelsiz taslak hazırlama. Yalnız /api uçlarını çağırır.
"use strict";
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const errorBox = $(".tl-error");
  const labOrigin = $(".dz-config").dataset.labOrigin;
  let draft = null, actions = [];
  const S = window.AgenTaskSession;
  const STATUS_TR = { intent_entered: "Niyet girildi", target_proposed: "Hedef önerildi", target_selected: "Hedef seçildi",
    meaning_and_target_confirmed: "Anlam ve hedef onaylandı", trial_requested: "Deneme istendi", observed: "Gözlendi",
    outcome_confirmed: "Sonuç onaylandı", ready_for_review: "İncelemeye hazır" };
  const OPS = { ensure_value: "Değer yaz", ensure_choice: "Seçim yap", activate_tab: "Sekme aç", find_record: "Kayıt bul",
    read: "Oku", invoke_approved_action: "Onaylı aksiyon", follow_transition: "Ekran geçişi (onaylı düğme/sekme)" };
  const screenTitle = (id) => { const s = allScreens().find((x) => x.screen_id === id); return s ? s.title : id || "-"; };
  const allScreens = () => (draft && draft.screen ? [draft.screen, ...(draft.extra_screens || [])] : []);
  const ISSUE_TR = (i) => i.replace(/^step_(\d+)_not_ready$/, "Adım $1 incelemeye hazır değil")
    .replace("fresh_session_test_missing", "Yeni oturum testi yapılmadı").replace("fresh_session_test_stale", "İçerik testten sonra değişti; testi yenileyin")
    .replace("fresh_session_test_failed", "Yeni oturum testi başarısız").replace("no_steps", "Adım yok")
    .replace("screen_missing", "Ekran tanımı yok").replace("screen_markers_only_targets", "Ekran tanıma yalnız işlemin kendi hedeflerine dayanıyor")
    .replace(/^element_region_not_in_screen:([^@]+)/, "'$1' elemanının bölgesi ekran tanımında yok")
    .replace(/^step_(\d+)_screen_out_of_route:(.+)$/, "Adım $1 rotadaki ekranda değil ($2)").replace(/^step_(\d+)_transition_missing$/, "Adım $1 için geçiş seçilmedi")
    .replace(/^transition_used_0_times:(.+)$/, "'$1' geçişini kullanan adım yok").replace(/^step_(\d+)_transition_trigger_mismatch$/, "Adım $1: geçiş tetikleyicisi komutla uyumsuz");
  const FIELD_TR = { name: "Ad", title: "Başlık", max_length: "En fazla", source: "Kaynak", constant: "Sabit", operation_id: "İşlem kimliği",
    application_id: "Uygulama", description: "Açıklama", intent_text: "Adım", screen_id: "Ekran kimliği", regions: "Bölgeler",
    marker_candidate_ids: "Tanıma işaretleri", absent_markers: "Olmaması gereken işaretler", value_template: "Değer/şablon",
    entry_url: "Başlangıç ekranı", session_id: "Tarayıcı oturumu", "(genel)": "Tanım" };
  const fieldTr = (f) => f.split(".").map((p) => FIELD_TR[p] || p).join(" › ");

  async function call(method, path, body) {
    errorBox.textContent = "";
    const r = await fetch(path, { method, credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 204) return null;
    const data = await r.json();
    if (!r.ok) {
      const d = data.details || {};
      if (Array.isArray(d.errors) && d.errors.length) {
        // U2: hangi alan neden hatalı; girdi değeri gösterilmez (sunucu da göndermez).
        errorBox.replaceChildren(el("span", "Form doğrulanamadı:"));
        const ul = el("ul", null, "dz-field-errors");
        d.errors.forEach((x) => ul.appendChild(el("li", `${fieldTr(x.field)}: ${x.message}`)));
        errorBox.appendChild(ul);
      } else {
        errorBox.textContent = `${data.safe_message}${d.reason ? " (" + d.reason + ")" : ""}${d.outcome ? " (" + d.outcome + ")" : ""}`;
      }
      throw new Error(data.code);
    }
    return data;
  }
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };
  const btn = (text, fn) => { const b = el("button", text); b.type = "button"; b.addEventListener("click", () => fn().catch(() => {})); return b; };
  const needSession = () => S.require();
  const slug = (s) => (s || "").toLowerCase().replace(/ı/g, "i").normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50) || "alan";

  $(".dz-nav").addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = `${labOrigin}/__lab/autologin?user=tasarim&next=${encodeURIComponent(e.target.lab_page.value)}`;
    const r = await call("POST", `/api/sessions/${needSession()}/navigate`, { url }).catch(() => null);
    if (r) { $(".dz-session").textContent = `Ekran açıldı: ${r.url}`; S.refresh(); }
  });

  async function loadMigrations() {
    const ul = $(".dz-migrations"); if (!ul) return;
    const r = await fetch("/api/drafts/migrations", { credentials: "same-origin" });
    ul.replaceChildren();
    if (!r.ok) { ul.appendChild(el("li", "Yayımlanmış katalog okunamadı.", "muted")); return; }
    const data = await r.json();
    if (!data.operations.length) { ul.appendChild(el("li", "Geçiş gereken işlem yok.", "muted")); return; }
    data.operations.forEach((o) => {
      const li = el("li", `${o.title} (${o.operation_id} r${o.revision}) · ekran tanımı yok · yayın ${data.release_id} `);
      li.appendChild(btn("Geçiş taslağı oluştur", async () => {
        draft = await call("POST", "/api/drafts/migrations", { operation_id: o.operation_id }); render(); loadDrafts();
      }));
      ul.appendChild(li);
    });
  }
  function describeSpec(s) { return `${s.kind} "${s.labels.join("/")}"${s.region ? " · bölüm " + s.region : ""}${s.frame_title ? " · frame " + s.frame_title : ""}`; }
  function showVerdict(v) {
    const box = $(".dz-screen"); const p = el("p", `Doğrulama: ${v.recognized ? "TANINDI" : "TANINMADI"} — ${v.explanation}`, v.recognized ? "dz-ok" : "dz-bad");
    p.dataset.status = v.status; box.querySelectorAll(".dz-verdict").forEach((x) => x.remove()); p.classList.add("dz-verdict"); box.appendChild(p);
  }
  $("[data-action=screen-controls]").addEventListener("click", async () => {
    const snap = await call("POST", `/api/sessions/${needSession()}/observe`).catch(() => null); if (!snap) return;
    const ul = $(".dz-screen-controls"); ul.replaceChildren();
    snap.controls.filter((c) => c.visible).forEach((c) => {
      const li = el("li"); const cb = el("input"); cb.type = "checkbox"; cb.name = "marker"; cb.value = c.candidate_id;
      const lab = el("label"); lab.appendChild(cb); lab.appendChild(document.createTextNode(` ${c.caption}`)); li.appendChild(lab); ul.appendChild(li);
    });
    if (!ul.children.length) ul.appendChild(el("li", "Görünür kontrol yok.", "muted"));
  });
  $(".dz-screen-form").addEventListener("submit", async (e) => {
    e.preventDefault(); if (!draft) return; const f = e.target;
    const markers = [...document.querySelectorAll(".dz-screen-controls input[name=marker]:checked")].map((x) => x.value);
    const regions = f.regions.value.split(",").map((x) => x.trim()).filter(Boolean).map((name) => ({ name }));
    const absent = f.absent_label.value.trim() ? [{ kind: f.absent_kind.value, labels: [f.absent_label.value.trim()], ...(f.absent_region.value.trim() ? { region: f.absent_region.value.trim() } : {}) }] : [];
    const r = await call("PUT", api("/screen"), { expected_revision: draft.revision, session_id: needSession(), screen_id: f.screen_id.value,
      title: f.title.value, marker_candidate_ids: markers, regions, absent_markers: absent }).catch(() => null);
    if (r) { draft = r; render(); loadDrafts(); showVerdict(r.screen_verdict); }
  });

  const tForm = $(".dz-transition-form");
  if (tForm) {
    $("[data-action=trigger-controls]").addEventListener("click", async () => {
      // Yalnız gözlem: adaylar listelenir, hiçbir şeye tıklanmaz.
      const snap = await call("POST", `/api/sessions/${needSession()}/observe`).catch(() => null); if (!snap) return;
      const ul = $(".dz-trigger-controls"); ul.replaceChildren();
      snap.controls.filter((c) => c.visible && ["button", "tab"].includes(c.kind)).forEach((c) => {
        const lab = el("label"); const r = el("input"); r.type = "radio"; r.name = "trigger_candidate"; r.value = c.candidate_id;
        lab.appendChild(r); lab.appendChild(document.createTextNode(` ${c.caption}`)); const li = el("li"); li.appendChild(lab); ul.appendChild(li); });
    });
    tForm.addEventListener("submit", async (e) => {
      e.preventDefault(); if (!draft) return; const f = e.target;
      const picked = document.querySelector(".dz-trigger-controls input[name=trigger_candidate]:checked");
      const completion = f.c_label.value.trim() ? [{ target: { kind: f.c_kind.value, labels: [f.c_label.value.trim()], ...(f.c_region.value.trim() ? { region: f.c_region.value.trim() } : {}) }, value_template: f.c_template.value }] : [];
      const body = { expected_revision: draft.revision, transition_id: f.transition_id.value, from_screen: f.from_screen.value, to_screen: f.to_screen.value,
        trigger_kind: f.trigger_kind.value, timeout_ms: Number(f.timeout_ms.value), completion };
      if (f.trigger_kind.value === "control") { body.session_id = needSession(); body.trigger_candidate_id = picked ? picked.value : null; }
      const r = await call("PUT", api("/transitions"), body).catch(() => null);
      if (r) { draft = r; render(); }
    });
    $(".dz-context-form").addEventListener("submit", async (e) => {
      e.preventDefault(); if (!draft) return; const f = e.target;
      const checks = f.s_label.value.trim() ? [{ target: { kind: f.s_kind.value, labels: [f.s_label.value.trim()], ...(f.s_region.value.trim() ? { region: f.s_region.value.trim() } : {}) }, value_template: f.s_template.value }] : [];
      const r = await call("PUT", api("/start-context"), { expected_revision: draft.revision, checks }).catch(() => null);
      if (r) { draft = r; render(); }
    });
  }

  async function loadDrafts() {
    const list = await call("GET", "/api/drafts").catch(() => []);
    const ul = $(".dz-drafts"); ul.replaceChildren();
    list.forEach((d) => { const li = el("li", `${d.title} (${d.operation_id}) · ${d.steps} adım · ${d.screen_id ? "ekran " + d.screen_id : "ekran tanımı yok"}${d.migrated_from ? " · geçiş: r" + d.migrated_from.revision : ""} · ${d.ready ? "incelemeye hazır" : "hazırlanıyor"} `);
      li.dataset.draftId = d.draft_id; li.dataset.steps = d.steps;
      li.appendChild(btn("Aç", async () => { draft = await call("GET", `/api/drafts/${d.draft_id}`); render(); })); ul.appendChild(li); });
  }
  $(".dz-create").addEventListener("submit", async (e) => {
    e.preventDefault(); const f = e.target;
    draft = await call("POST", "/api/drafts", { application_id: document.querySelector(".dz-app").dataset.app, operation_id: f.operation_id.value, title: f.title.value, description: f.description.value }).catch(() => null);
    if (draft) { render(); loadDrafts(); }
  });
  const api = (path) => `/api/drafts/${draft.draft_id}${path}`;
  // U1: her değişiklikten sonra taslak listesi de yenilenir (adım sayısı ve hazır durumu güncel kalır).
  async function mutate(method, path, body) { draft = await call(method, api(path), { expected_revision: draft.revision, ...(body || {}) }); render(); loadDrafts(); return draft; }

  $(".dz-param").addEventListener("submit", async (e) => {
    e.preventDefault(); const f = e.target;
    const body = { name: f.name.value, title: f.title.value, max_length: Number(f.max_length.value), source: f.source.value };
    if (f.source.value === "approved_constant") body.constant = f.constant.value;
    await mutate("POST", "/parameters", body).catch(() => {});
  });
  $(".dz-step").addEventListener("submit", async (e) => { e.preventDefault(); await mutate("POST", "/steps", { intent_text: e.target.intent_text.value }).catch(() => {}); e.target.reset(); });

  function stepCard(step, index) {
    const card = el("div", null, "card dz-card"); card.dataset.stepId = step.step_id; card.dataset.status = step.status;
    card.appendChild(el("h4", `${index + 1}. ${step.intent_text}`));
    card.appendChild(el("p", `Durum: ${STATUS_TR[step.status]} · Komut: ${OPS[step.op] || "seçilmedi"} (${step.provenance.op || "-"}) · Etki: ${step.effect}${step.changes_screen ? " · EKRAN DEĞİŞTİRİR" : ""}`, "muted"));
    if (allScreens().length > 1 || step.transition_id) {
      const tr = (draft.transitions || []).find((x) => x.transition_id === step.transition_id);
      card.appendChild(el("p", `Beklenen ekran: ${screenTitle(step.expected_screen)}${tr ? " → geçiş: " + screenTitle(tr.to_screen) : " (ekran aynı kalır)"}`, "dz-step-screen"));
      const sel = el("select"); sel.name = "step_screen";
      [["", "Rotaya göre"], ...allScreens().map((s) => [s.screen_id, s.title])].forEach(([k, v]) => { const o = el("option", v); o.value = k; o.selected = (step.screen_id || "") === k; sel.appendChild(o); });
      const row = el("div"); row.appendChild(el("label", "Adımın ekranı ")).appendChild(sel);
      row.appendChild(btn("Ekranı kaydet", () => mutate("PATCH", `/steps/${step.step_id}`, { screen_id: sel.value || null })));
      card.appendChild(row);
    }
    if (step.standard_text) card.appendChild(el("p", `Standart açıklama: ${step.standard_text}`));
    const element = step.element_id ? draft.elements[step.element_id] : null;
    if (element) card.appendChild(el("p", `Hedef: ${element.meaning} — ${element.target.kind} "${element.target.labels.join("/")}"${element.target.region ? " · bölüm " + element.target.region : ""}${element.target.frame_title ? " · frame " + element.target.frame_title : ""} (${element.provenance})`));

    // 1) komut ve tanım
    const def = el("div");
    const opSel = el("select"); opSel.name = "op";
    Object.entries(OPS).forEach(([k, v]) => { const o = el("option", v); o.value = k; o.selected = step.op === k; opSel.appendChild(o); });
    def.appendChild(el("label", "Komut ")).appendChild(opSel);
    if (step.op === "invoke_approved_action") {
      const aSel = el("select"); aSel.name = "action_id";
      actions.forEach((a) => { const o = el("option", a.title); o.value = a.action_id; o.selected = step.action_id === a.action_id; aSel.appendChild(o); });
      def.appendChild(el("label", " Aksiyon ")).appendChild(aSel);
      const pIn = el("input"); pIn.name = "action_param"; pIn.placeholder = "{parametre}"; pIn.value = Object.values(step.action_params || {})[0] || "";
      def.appendChild(el("label", " Aksiyon değeri ")).appendChild(pIn);
      const tSel = transitionSelect(step, "approved_action");
      def.appendChild(el("label", " Ekran geçişi ")).appendChild(tSel);
      def.appendChild(btn("Tanımı kaydet", () => {
        const a = actions.find((x) => x.action_id === aSel.value);
        const params = {}; (a ? a.params : []).forEach((p) => { params[p.name] = pIn.value; });
        return mutate("PATCH", `/steps/${step.step_id}`, { op: opSel.value, action_id: aSel.value, action_params: params, ...(tSel.value ? { transition_id: tSel.value } : {}) });
      }));
    } else if (step.op === "follow_transition") {
      const tSel = transitionSelect(step, "control");
      def.appendChild(el("label", " Geçiş ")).appendChild(tSel);
      def.appendChild(btn("Tanımı kaydet", () => mutate("PATCH", `/steps/${step.step_id}`, { op: "follow_transition", transition_id: tSel.value })));
    } else {
      const v = el("input"); v.name = "template"; v.placeholder = "{musteri_no}"; v.value = step.value_template || step.choice_template || step.key_template || "";
      def.appendChild(el("label", " Değer/şablon ")).appendChild(v);
      const chk = el("select"); chk.name = "success_check";
      [["auto", "Otomatik başarı kontrolü"], ["none", "Kontrol yok"]].forEach(([k, t]) => { const o = el("option", t); o.value = k; o.selected = step.success_check === k; chk.appendChild(o); });
      def.appendChild(el("label", " Başarı koşulu ")).appendChild(chk);
      def.appendChild(btn("Tanımı kaydet", () => {
        const body = { op: opSel.value, success_check: chk.value };
        if (opSel.value === "ensure_value") body.value_template = v.value;
        if (opSel.value === "ensure_choice") body.choice_template = v.value;
        if (opSel.value === "find_record") { body.key_template = v.value; body.navigation = "paged"; }
        return mutate("PATCH", `/steps/${step.step_id}`, body);
      }));
    }
    card.appendChild(def);

    // 2) hedef önerisi / işaretleme
    if (step.op !== "invoke_approved_action") {
      const tgt = el("div", null, "dz-targets");
      const cands = el("ul", null, "dz-candidates");
      const elementId = el("input"); elementId.name = "element_id"; elementId.placeholder = "eleman kimliği (boşsa otomatik)";
      const meaning = el("input"); meaning.name = "meaning"; meaning.placeholder = "anlam (ör. Kefil müşteri numarası)";
      async function choose(candidateId, label, region, provenance) {
        return mutate("POST", `/steps/${step.step_id}/select-target`, { session_id: needSession(), candidate_id: candidateId,
          element_id: elementId.value || slug(`${region || ""}_${label}`), meaning: meaning.value || `${label}${region ? " (" + region + ")" : ""}`, provenance });
      }
      tgt.appendChild(btn("Hedef adaylarını göster", async () => {
        const r = await call("POST", api(`/steps/${step.step_id}/propose`), { session_id: needSession() });
        cands.replaceChildren();
        if (!r.candidates.length) cands.appendChild(el("li", "Aday bulunamadı; tarayıcıda işaretleyin."));
        r.candidates.forEach((c) => {
          const region = (c.contexts.find((x) => x.kind !== "table_row" && x.name) || {}).name;
          const li = el("li", `${c.label} · ${c.kind}${region ? " · " + region : ""}${c.frame_titles.length ? " · " + c.frame_titles.join(" › ") : ""} (puan ${c.score}) `);
          li.appendChild(btn("Bu hedefi seç", () => choose(c.candidate_id, c.label, region, "observed")));
          cands.appendChild(li);
        });
        (r.reuse || []).forEach((u) => cands.appendChild(el("li", `Yeniden kullanım önerisi: ${u.meaning} (${u.element_id}, ${u.draft_id})`, "muted")));
        const d = await call("GET", api("")); draft.revision = d.revision;
      }));
      tgt.appendChild(btn("Tarayıcıda işaretle", async () => {
        const sid = needSession();
        await call("POST", `/api/sessions/${sid}/picker/start`);
        cands.replaceChildren(el("li", "Tarayıcıda alana tıklayın (tıklama sayfaya iletilmez)…"));
        try {
          for (let i = 0; i < 6; i++) {
            const r = await call("GET", `/api/sessions/${sid}/picker/selection?wait_ms=20000`);
            if (r.selected && r.pick && r.pick.control) {
              const c = r.pick.control; const region = (c.contexts.find((x) => x.kind !== "table_row" && x.name) || {}).name;
              await call("POST", `/api/sessions/${sid}/picker/stop`);
              return choose(c.candidate_id, c.label || c.accessible_name, region, "human_verified");
            }
          }
        } finally { call("POST", `/api/sessions/${sid}/picker/stop`).catch(() => {}); }
      }));
      tgt.appendChild(elementId); tgt.appendChild(meaning); tgt.appendChild(cands);
      card.appendChild(tgt);
    }

    // 3) ayrı onaylar
    if (step.status === "target_selected") {
      const box = el("div", null, "dz-confirm");
      const checks = {};
      [["meaning", "Anlam doğru"], ["target", "Hedef doğru"], ["effect", `Etki doğru (${step.effect})`], ["params", "Parametre doğru"]].forEach(([k, t]) => {
        const lab = el("label"); const cb = el("input"); cb.type = "checkbox"; cb.name = k; checks[k] = cb; lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + t + " ")); box.appendChild(lab); });
      box.appendChild(btn("Onayla", () => mutate("POST", `/steps/${step.step_id}/confirm`, Object.fromEntries(Object.entries(checks).map(([k, cb]) => [k, cb.checked])))));
      card.appendChild(box);
    }
    // 4) deneme
    if (["meaning_and_target_confirmed", "observed"].includes(step.status)) {
      const box = el("div", null, "dz-trial");
      const inputs = {};
      draft.parameters.filter((p) => p.source === "user_input").forEach((p) => { const i = el("input"); i.name = `arg_${p.name}`; i.placeholder = p.title; inputs[p.name] = i; box.appendChild(el("label", `Deneme değeri: ${p.title} `)).appendChild(i); });
      let ack = null;
      if (step.effect === "mutating" || step.changes_screen) {
        const text = step.changes_screen ? ` Bu deneme tarayıcıda ekran geçişini tetikler${step.effect === "mutating" ? " ve veri değiştirir" : ""}; onaylıyorum ` : " Bu deneme veri değiştirir; onaylıyorum ";
        const lab = el("label", text, "dz-ack"); ack = el("input"); ack.type = "checkbox"; ack.name = "ack"; lab.appendChild(ack); box.appendChild(lab);
      }
      box.appendChild(btn("Dene", () => mutate("POST", `/steps/${step.step_id}/trial`, { session_id: needSession(),
        args: Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value])), acknowledge_effect: ack ? ack.checked : false })));
      if (step.trial) box.appendChild(el("p", `Deneme: ${step.trial.run_status} · sistem doğrulaması: ${step.trial.verified ? "BAŞARILI" : "BAŞARISIZ"}${step.trial.detail ? " (" + step.trial.detail + ")" : ""}`, step.trial.verified ? "dz-ok" : "dz-bad"));
      if (step.status === "observed" && step.trial && step.trial.verified) box.appendChild(btn("Sonucu onayla", () => mutate("POST", `/steps/${step.step_id}/confirm-outcome`)));
      card.appendChild(box);
    }
    card.appendChild(btn("Adımı sil", async () => { draft = await call("DELETE", api(`/steps/${step.step_id}?expected_revision=${draft.revision}`)); render(); }));
    return card;
  }

  function transitionSelect(step, kind) {
    const sel = el("select"); sel.name = "transition_id";
    if (kind === "approved_action") { const o = el("option", "Yok (ekran aynı kalır)"); o.value = ""; sel.appendChild(o); }
    (draft.transitions || []).filter((x) => x.trigger.kind === kind).forEach((x) => {
      const o = el("option", `${x.transition_id}: ${screenTitle(x.from_screen)} → ${screenTitle(x.to_screen)}`); o.value = x.transition_id; o.selected = step.transition_id === x.transition_id; sel.appendChild(o); });
    return sel;
  }
  function renderRoutes() {
    const box = $(".dz-routes"); if (!box) return; box.replaceChildren();
    const ul = el("ul");
    (draft.transitions || []).forEach((x) => {
      const li = el("li", `${x.transition_id}: ${screenTitle(x.from_screen)} → ${screenTitle(x.to_screen)} · tetikleyici: ${x.trigger.kind === "control" ? describeSpec(x.trigger.target) : "adımın onaylı aksiyonu"} · en fazla ${x.timeout_ms} ms${x.completion.length ? " · tamamlanma: " + x.completion.map((c) => `${c.target.labels[0]} = ${c.value_template}`).join(", ") : ""} `);
      li.appendChild(btn("Kaldır", async () => { draft = await call("DELETE", api(`/transitions/${x.transition_id}?expected_revision=${draft.revision}`)); render(); }));
      ul.appendChild(li);
    });
    if (!ul.children.length) ul.appendChild(el("li", "Geçiş yok (tek ekranlı işlem).", "muted"));
    box.appendChild(ul);
    const sc = (draft.start_context || []).map((c) => `${c.target.labels[0]} = ${c.value_template}`).join(", ");
    box.appendChild(el("p", `Başlangıç kayıt bağlamı: ${sc || "yok"}`, "muted dz-start-context"));
    document.querySelectorAll(".dz-transition-form select[name=from_screen], .dz-transition-form select[name=to_screen]").forEach((s) => {
      const keep = s.value; s.replaceChildren(); allScreens().forEach((x) => { const o = el("option", x.title); o.value = x.screen_id; s.appendChild(o); }); if (keep) s.value = keep; });
  }

  function render() {
    if (!draft) return;
    $(".dz-editor").hidden = false;
    $(".dz-title").textContent = `${draft.title} (${draft.operation_id})`;
    $(".dz-meta").textContent = `Revizyon ${draft.revision} · içerik özeti ${draft.content_hash.slice(0, 12)}`;
    const mig = $(".dz-migrated"); mig.hidden = !draft.migrated_from;
    if (draft.migrated_from) mig.textContent = `Geçiş taslağı: ${draft.migrated_from.operation_id} r${draft.migrated_from.revision} (${draft.migrated_from.release_id}) — eski yayın değişmez; yayımlanınca yeni revizyon oluşur.`;
    const sc = $(".dz-screen"); sc.replaceChildren();
    if (draft.screen) {
      allScreens().forEach((screen, i) => {
        const item = el("div", null, "dz-screen-item"); item.dataset.screenId = screen.screen_id;
        item.appendChild(el("p", `${i === 0 ? "Başlangıç ekranı" : "Ekran"}: ${screen.title} (${screen.screen_id}) · bölgeler: ${screen.regions.map((r) => r.name).join(", ") || "-"}`));
        const ul = el("ul"); screen.markers.forEach((m) => ul.appendChild(el("li", `Tanıma işareti: ${describeSpec(m)}`)));
        screen.absent_markers.forEach((m) => ul.appendChild(el("li", `Olmamalı: ${describeSpec(m)}`))); item.appendChild(ul);
        item.appendChild(btn("Ekranı doğrula", async () => { const v = await call("POST", api("/screen/verify"), { session_id: needSession(), screen_id: screen.screen_id }); showVerdict(v); }));
        item.appendChild(btn("Ekran tanımını kaldır", async () => { draft = await call("DELETE", api(`/screen?expected_revision=${draft.revision}&screen_id=${screen.screen_id}`)); render(); loadDrafts(); }));
        sc.appendChild(item);
      });
    } else sc.appendChild(el("p", "Ekran tanımı yok; taslak onaya hazır olamaz.", "dz-bad"));
    renderRoutes();
    const pl = $(".dz-params"); pl.replaceChildren();
    draft.parameters.forEach((p) => pl.appendChild(el("li", `{${p.name}} — ${p.title} · ${p.source}${p.constant != null ? " = " + p.constant : ""} · en fazla ${p.max_length}`)));
    const steps = $(".dz-steps"); steps.replaceChildren();
    draft.steps.forEach((s, i) => steps.appendChild(stepCard(s, i)));
    const args = $(".dz-fresh-args"); args.replaceChildren();
    draft.parameters.filter((p) => p.source === "user_input").forEach((p) => { const i = el("input"); i.name = `fresh_${p.name}`; i.placeholder = p.title; args.appendChild(el("label", `Test değeri: ${p.title} `)).appendChild(i); });
    const issues = $(".dz-issues"); issues.replaceChildren();
    draft.issues.forEach((i) => issues.appendChild(el("li", ISSUE_TR(i))));
    const review = $(".dz-review"); review.replaceChildren();
    review.appendChild(el("p", draft.issues.length ? `İncelemeye hazır değil (${draft.issues.length} eksik).` : "İncelemeye hazır: bütün adımlar doğrulandı ve yeni oturum testi geçti.", draft.issues.length ? "dz-bad" : "dz-ok"));
    if (draft.approval) review.appendChild(el("p", `Onay: ${draft.approval.approver} · ${draft.approval.content_hash === draft.content_hash ? "güncel" : "GEÇERSİZ (içerik değişti)"}`, draft.approval.content_hash === draft.content_hash ? "dz-ok" : "dz-bad"));
    if (draft.fresh_test) review.appendChild(el("p", `Yeni oturum testi: ${draft.fresh_test.passed ? "geçti" : "başarısız"} (${draft.fresh_test.run_id})`, "muted"));
  }
  $(".dz-fresh").addEventListener("submit", async (e) => {
    e.preventDefault();
    const args = {}; document.querySelectorAll(".dz-fresh-args input").forEach((i) => { args[i.name.replace("fresh_", "")] = i.value; });
    const entry = e.target.entry ? `${labOrigin}/__lab/autologin?user=tasarim&next=${encodeURIComponent(e.target.entry.value)}` : "";
    await mutate("POST", "/fresh-test", { args, entry_url: entry }).catch(() => {});
  });

  $("[data-action=approve]").addEventListener("click", async () => {
    if (!draft) return;
    const r = await call("POST", api("/approve"), { expected_revision: draft.revision }).catch(() => null);
    if (r) { draft = await call("GET", api("")); render(); $(".dz-publish").textContent = `Onaylandı: ${r.approval.approver} · içerik ${r.approval.content_hash.slice(0, 12)} · test ${r.approval.test_run_id}`; }
  });
  $("[data-action=publish]").addEventListener("click", async () => {
    if (!draft) return;
    const r = await call("POST", api("/publish"), { request_id: crypto.randomUUID() }).catch(() => null);
    if (r) { $(".dz-publish").textContent = `Yayımlandı ve etkin: ${r.release_id} · ${r.operations.map((o) => o.operation_id + " r" + o.revision).join(", ")}`; loadMigrations(); }
  });

  call("GET", "/api/actions").then((d) => { actions = d.actions; }).catch(() => {});
  loadDrafts();
  loadMigrations();
  // Yeni Akış Tasarımcısından gelen derin bağlantı: kaydedilmiş taslak doğrudan açılır (yetki sunucuda).
  const linked = new URLSearchParams(location.search).get("draft");
  if (linked) call("GET", `/api/drafts/${encodeURIComponent(linked)}`).then((d) => { draft = d; render(); }).catch(() => {});
})();
