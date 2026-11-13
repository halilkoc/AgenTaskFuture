// Katalog Tasarımcısı: yönlendirilmiş, modelsiz taslak hazırlama. Yalnız /api uçlarını çağırır.
"use strict";
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const errorBox = $(".tl-error");
  const labOrigin = $(".dz-config").dataset.labOrigin;
  let sessionId = null, draft = null, actions = [];
  const STATUS_TR = { intent_entered: "Niyet girildi", target_proposed: "Hedef önerildi", target_selected: "Hedef seçildi",
    meaning_and_target_confirmed: "Anlam ve hedef onaylandı", trial_requested: "Deneme istendi", observed: "Gözlendi",
    outcome_confirmed: "Sonuç onaylandı", ready_for_review: "İncelemeye hazır" };
  const OPS = { ensure_value: "Değer yaz", ensure_choice: "Seçim yap", activate_tab: "Sekme aç", find_record: "Kayıt bul",
    read: "Oku", invoke_approved_action: "Onaylı aksiyon" };
  const ISSUE_TR = (i) => i.replace(/^step_(\d+)_not_ready$/, "Adım $1 incelemeye hazır değil")
    .replace("fresh_session_test_missing", "Yeni oturum testi yapılmadı").replace("fresh_session_test_stale", "İçerik testten sonra değişti; testi yenileyin")
    .replace("fresh_session_test_failed", "Yeni oturum testi başarısız").replace("no_steps", "Adım yok");

  async function call(method, path, body) {
    errorBox.textContent = "";
    const r = await fetch(path, { method, credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 204) return null;
    const data = await r.json();
    if (!r.ok) { const d = data.details || {}; errorBox.textContent = `${data.safe_message}${d.reason ? " (" + d.reason + ")" : ""}${d.outcome ? " (" + d.outcome + ")" : ""}`; throw new Error(data.code); }
    return data;
  }
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };
  const btn = (text, fn) => { const b = el("button", text); b.type = "button"; b.addEventListener("click", () => fn().catch(() => {})); return b; };
  const needSession = () => { if (!sessionId) { errorBox.textContent = "Önce oturum açın ve ekranı açın."; throw new Error("no_session"); } return sessionId; };
  const slug = (s) => (s || "").toLowerCase().replace(/ı/g, "i").normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50) || "alan";

  $("[data-action=open]").addEventListener("click", async () => {
    const s = await call("POST", "/api/sessions").catch(() => null);
    if (s) { sessionId = s.session_id; $(".dz-session").textContent = `Oturum: ${s.session_id}`; }
  });
  $(".dz-nav").addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = `${labOrigin}/__lab/autologin?user=tasarim&next=${encodeURIComponent(e.target.lab_page.value)}`;
    const r = await call("POST", `/api/sessions/${needSession()}/navigate`, { url }).catch(() => null);
    if (r) $(".dz-session").textContent = `Oturum: ${sessionId} · ${r.url}`;
  });

  async function loadDrafts() {
    const list = await call("GET", "/api/drafts").catch(() => []);
    const ul = $(".dz-drafts"); ul.replaceChildren();
    list.forEach((d) => { const li = el("li", `${d.title} (${d.operation_id}) · ${d.steps} adım · ${d.ready ? "incelemeye hazır" : "hazırlanıyor"} `);
      li.appendChild(btn("Aç", async () => { draft = await call("GET", `/api/drafts/${d.draft_id}`); render(); })); ul.appendChild(li); });
  }
  $(".dz-create").addEventListener("submit", async (e) => {
    e.preventDefault(); const f = e.target;
    draft = await call("POST", "/api/drafts", { application_id: "lab", operation_id: f.operation_id.value, title: f.title.value, description: f.description.value }).catch(() => null);
    if (draft) { render(); loadDrafts(); }
  });
  const api = (path) => `/api/drafts/${draft.draft_id}${path}`;
  async function mutate(method, path, body) { draft = await call(method, api(path), { expected_revision: draft.revision, ...(body || {}) }); render(); return draft; }

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
    card.appendChild(el("p", `Durum: ${STATUS_TR[step.status]} · Komut: ${OPS[step.op] || "seçilmedi"} (${step.provenance.op || "-"}) · Etki: ${step.effect}`, "muted"));
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
      def.appendChild(btn("Tanımı kaydet", () => {
        const a = actions.find((x) => x.action_id === aSel.value);
        const params = {}; (a ? a.params : []).forEach((p) => { params[p.name] = pIn.value; });
        return mutate("PATCH", `/steps/${step.step_id}`, { op: opSel.value, action_id: aSel.value, action_params: params });
      }));
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
      if (step.effect === "mutating") { const lab = el("label", " Bu deneme veri değiştirir; onaylıyorum "); ack = el("input"); ack.type = "checkbox"; ack.name = "ack"; lab.appendChild(ack); box.appendChild(lab); }
      box.appendChild(btn("Dene", () => mutate("POST", `/steps/${step.step_id}/trial`, { session_id: needSession(),
        args: Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value])), acknowledge_effect: ack ? ack.checked : false })));
      if (step.trial) box.appendChild(el("p", `Deneme: ${step.trial.run_status} · sistem doğrulaması: ${step.trial.verified ? "BAŞARILI" : "BAŞARISIZ"}${step.trial.detail ? " (" + step.trial.detail + ")" : ""}`, step.trial.verified ? "dz-ok" : "dz-bad"));
      if (step.status === "observed" && step.trial && step.trial.verified) box.appendChild(btn("Sonucu onayla", () => mutate("POST", `/steps/${step.step_id}/confirm-outcome`)));
      card.appendChild(box);
    }
    card.appendChild(btn("Adımı sil", async () => { draft = await call("DELETE", api(`/steps/${step.step_id}?expected_revision=${draft.revision}`)); render(); }));
    return card;
  }

  function render() {
    if (!draft) return;
    $(".dz-editor").hidden = false;
    $(".dz-title").textContent = `${draft.title} (${draft.operation_id})`;
    $(".dz-meta").textContent = `Revizyon ${draft.revision} · içerik özeti ${draft.content_hash.slice(0, 12)}`;
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
    if (r) $(".dz-publish").textContent = `Yayımlandı ve etkin: ${r.release_id} · ${r.operations.map((o) => o.operation_id + " r" + o.revision).join(", ")}`;
  });

  call("GET", "/api/actions").then((d) => { actions = d.actions; }).catch(() => {});
  loadDrafts();
})();
