// İşlem Deneme ekranı: formdan tipli komut planı oluşturur, /api/runs ile çalıştırır ve adım durumlarını izler.
"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const errorBox = $(".tl-error");
  const labOrigin = $(".rl-config").dataset.labOrigin;
  let sessionId = null, runId = null, plan = [], actions = [], polling = false;

  const STATE_TR = { pending: "Bekliyor", prepared: "Hazırlandı", dispatched: "İşlem gönderildi",
    verifying: "Sonuç doğrulanıyor", succeeded: "Başarılı", known_failed: "Bilinen başarısızlık",
    outcome_unknown: "Sonuç belirsiz", skipped: "Atlandı (iptal)" };
  const RUN_CLASS = { completed: "resolved", failed: "unresolved", outcome_unknown: "ambiguous" };

  async function call(method, path, body) {
    errorBox.textContent = "";
    const r = await fetch(path, { method, credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 204) return null;
    const data = await r.json();
    if (!r.ok) {
      const d = data.details || {};
      errorBox.textContent = `${data.safe_message || "İstek başarısız."}${d.reason ? " (" + d.reason + (d.step != null ? ", adım " + (d.step + 1) : "") + ")" : ""}`;
      throw new Error(data.code);
    }
    return data;
  }
  const needSession = () => { if (!sessionId) { errorBox.textContent = "Önce oturum açın."; throw new Error("no_session"); } return sessionId; };
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };

  // ---- oturum ve ekran
  $("[data-action=open]").addEventListener("click", async () => {
    const s = await call("POST", "/api/sessions").catch(() => null);
    if (s) { sessionId = s.session_id; $(".rl-session").textContent = `Oturum: ${s.session_id}`; }
  });
  $("[data-action=close]").addEventListener("click", async () => {
    if (!sessionId) return;
    await call("DELETE", `/api/sessions/${sessionId}`).catch(() => {});
    sessionId = null; $(".rl-session").textContent = "Oturum yok";
  });
  $(".rl-nav").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target; const mode = e.submitter ? e.submitter.value : "url";
    const url = mode === "lab" ? `${labOrigin}/__lab/autologin?user=deneme&next=${encodeURIComponent(f.lab_page.value)}` : f.url.value;
    const r = await call("POST", `/api/sessions/${needSession()}/navigate`, { url }).catch(() => null);
    if (r) $(".rl-session").textContent = `Oturum: ${sessionId} · ${r.url}`;
  });

  // ---- adım formu
  const stepForm = $(".rl-step");
  function showOpFields() {
    const op = stepForm.op.value;
    document.querySelectorAll(".rl-op").forEach((fs) => { fs.hidden = fs.dataset.for !== op; });
    $(".rl-target").hidden = op === "invoke_approved_action" ||
      (op === "assert_condition" && stepForm.condition.value === "text_present");
    const kinds = { ensure_value: "textbox", ensure_choice: null, activate_tab: "tab", find_record: "table" };
    if (kinds[op]) stepForm.kind.value = kinds[op];
  }
  stepForm.op.addEventListener("change", showOpFields);
  stepForm.condition.addEventListener("change", showOpFields);

  function targetSpec() {
    const f = stepForm;
    const spec = { kind: f.kind.value, labels: f.labels.value.split(",").map((x) => x.trim()).filter(Boolean) };
    ["region", "frame_title", "row_key"].forEach((k) => { if (f[k].value.trim()) spec[k] = f[k].value.trim(); });
    return spec;
  }
  function buildStep() {
    const f = stepForm; const op = f.op.value;
    if (op === "ensure_value") return { op, target: targetSpec(), value: f.value.value };
    if (op === "ensure_choice") return { op, target: targetSpec(), choice: f.choice.value };
    if (op === "activate_tab" || op === "read") return { op, target: targetSpec() };
    if (op === "find_record") {
      const s = { op, table: targetSpec(), key: f.key.value, navigation: f.navigation.value };
      if (f.navigation.value === "paged") s.next_labels = [f.next_label.value || "Sonraki"];
      if (f.navigation.value === "scroll" && f.end_text.value.trim()) s.end_text = f.end_text.value.trim();
      return s;
    }
    if (op === "assert_condition") {
      const type = f.condition.value;
      if (type === "text_present") return { op, condition: { type, evidence: { kind: "status_text" }, match: { mode: f.match_mode.value, text: f.expected.value } } };
      if (type === "tab_active") return { op, condition: { type, target: targetSpec() } };
      if (type === "choice_equals") return { op, condition: { type, target: targetSpec(), choice: f.expected.value } };
      return { op, condition: { type, target: targetSpec(), value: f.expected.value } };
    }
    const params = {};
    document.querySelectorAll(".rl-params input").forEach((i) => { params[i.name] = i.value; });
    return { op, action_id: f.action_id.value, params };
  }
  function describe(s) {
    const t = s.target || s.table || (s.condition && s.condition.target);
    const where = t ? `${(t.labels || []).join("/")} ${t.region ? "· " + t.region : ""}${t.row_key ? " · " + t.row_key : ""}` : "";
    const extra = s.value != null ? ` = "${s.value}"` : s.choice ? ` = "${s.choice}"` : s.key ? ` anahtar ${s.key}` :
      s.action_id ? ` ${s.action_id} ${JSON.stringify(s.params)}` : s.condition ? ` ${s.condition.type} ${s.condition.value || s.condition.choice || (s.condition.match && s.condition.match.text) || ""}` : "";
    return `${s.op} — ${where}${extra}`;
  }
  function renderPlan() {
    const ol = $(".rl-plan"); ol.replaceChildren();
    plan.forEach((s, i) => {
      const li = el("li", describe(s) + " ");
      const rm = el("button", "Kaldır"); rm.type = "button";
      rm.addEventListener("click", () => { plan.splice(i, 1); renderPlan(); });
      li.appendChild(rm); ol.appendChild(li);
    });
  }
  stepForm.addEventListener("submit", (e) => { e.preventDefault(); plan.push(buildStep()); renderPlan(); });
  $("[data-action=clear-plan]").addEventListener("click", () => { plan = []; renderPlan(); });

  $("[data-action=resolve]").addEventListener("click", async () => {
    const r = await call("POST", `/api/sessions/${needSession()}/resolve`, targetSpec()).catch(() => null);
    if (!r) return;
    $(".rl-resolve").textContent = `${r.outcome} · ${r.reason} — ${r.explanation}`;
    if (r.candidate_id) call("POST", `/api/sessions/${sessionId}/candidates/${encodeURIComponent(r.candidate_id)}/highlight`).catch(() => {});
  });
  $("[data-action=pick]").addEventListener("click", async () => {
    const sid = needSession();
    await call("POST", `/api/sessions/${sid}/picker/start`).catch(() => null);
    $(".rl-resolve").textContent = "Tarayıcıda alana tıklayın (tıklama sayfaya iletilmez)…";
    for (let i = 0; i < 6; i++) {
      const r = await call("GET", `/api/sessions/${sid}/picker/selection?wait_ms=20000`).catch(() => null);
      if (r && r.selected && r.pick && r.pick.control) {
        const c = r.pick.control; const f = stepForm;
        if ([...f.kind.options].some((o) => o.value === c.kind)) f.kind.value = c.kind;
        f.labels.value = c.label || c.accessible_name || "";
        const region = (c.contexts || []).find((x) => x.kind !== "table_row" && x.name);
        const row = (c.contexts || []).find((x) => x.kind === "table_row" && x.key);
        f.region.value = region ? region.name : "";
        f.row_key.value = row ? row.key : "";
        f.frame_title.value = (c.frame_titles || []).slice(-1)[0] || "";
        $(".rl-resolve").textContent = `Seçildi: ${c.caption}`;
        break;
      }
    }
    await call("POST", `/api/sessions/${sid}/picker/stop`).catch(() => null);
  });

  // ---- onaylı aksiyonlar
  async function loadActions() {
    const data = await call("GET", "/api/actions").catch(() => ({ actions: [] }));
    actions = data.actions;
    const select = stepForm.action_id; select.replaceChildren();
    actions.forEach((a) => { const o = el("option", `${a.title} (${a.action_id})`); o.value = a.action_id; select.appendChild(o); });
    renderParams();
  }
  function renderParams() {
    const a = actions.find((x) => x.action_id === stepForm.action_id.value);
    const box = $(".rl-params"); box.replaceChildren();
    if (!a) { $(".rl-action-info").textContent = "Onaylı aksiyon yok."; return; }
    a.params.forEach((p) => { const l = el("label", p.title + " "); const i = el("input"); i.name = p.name; i.maxLength = p.max_length; l.appendChild(i); box.appendChild(l); });
    $(".rl-action-info").textContent = `Etki: ${a.effect === "mutating" ? "veri değiştirir (otomatik tekrar edilmez)" : "yalnız ekran"} · hedef: ${(a.target.labels || []).join("/")}${a.target.region ? " · " + a.target.region : ""}`;
  }
  stepForm.action_id.addEventListener("change", renderParams);

  // ---- örnek senaryolar (aynı adapterlerin farklı işlemlerde kullanımı)
  const EX = {
    note: () => [{ op: "ensure_value", target: { kind: "textbox", labels: ["Not"] }, value: "Müşteri arandı" },
      { op: "invoke_approved_action", action_id: "lab.add_case_note", params: { text: "Müşteri arandı" } }],
    guarantor: () => [{ op: "ensure_value", target: { kind: "textbox", labels: ["Müşteri No"], region: "Kefil" }, value: "00123" },
      { op: "ensure_value", target: { kind: "textbox", labels: ["Ad Soyad"], region: "Kefil" }, value: "Zeynep Kaya" },
      { op: "invoke_approved_action", action_id: "lab.save_guarantor", params: {} },
      { op: "assert_condition", condition: { type: "value_equals", target: { kind: "textbox", labels: ["Müşteri No"], region: "Kefil" }, value: "00123" } }],
    card: () => [{ op: "ensure_choice", target: { kind: "select", labels: ["Şube"] }, choice: "Konak" },
      { op: "ensure_choice", target: { kind: "combobox", labels: ["Ürün Tipi"] }, choice: "Ticari Kart" },
      { op: "activate_tab", target: { kind: "tab", labels: ["Teslimat"] } },
      { op: "ensure_value", target: { kind: "textbox", labels: ["Teslimat Adresi"] }, value: "Alsancak / İzmir" },
      { op: "assert_condition", condition: { type: "tab_active", target: { kind: "tab", labels: ["Teslimat"] } } }],
    record: () => [{ op: "find_record", table: { kind: "table", labels: ["Başvurular"] }, key: "B-1027", navigation: "paged", next_labels: ["Sonraki"] }],
    ambiguous: () => [{ op: "ensure_value", target: { kind: "textbox", labels: ["Müşteri No"] }, value: "1" }],
  };
  $(".rl-example").addEventListener("change", (e) => { if (EX[e.target.value]) { plan = EX[e.target.value](); renderPlan(); } });

  // ---- çalıştırma ve izleme
  function renderRun(run) {
    const cls = RUN_CLASS[run.status] || (run.status.startsWith("paused") ? "ambiguous" : "");
    const p = $(".rl-run"); p.replaceChildren();
    p.appendChild(el("span", run.outcome_label, `badge ${cls}`));
    p.appendChild(document.createTextNode(` ${run.status}${run.status_reason ? " (" + run.status_reason + ")" : ""} · ${run.run_id}`));
    const table = $(".rl-steps"); table.replaceChildren();
    const head = table.insertRow();
    ["#", "Komut", "Durum", "Deneme", "Hata sınıfı", "Açıklama", "Doğrulama / sonuç", "Toparlanma"].forEach((h) => head.appendChild(el("th", h)));
    run.steps.forEach((s) => {
      const tr = table.insertRow(); tr.dataset.state = s.state;
      [s.index + 1, describe(s.command), STATE_TR[s.state] || s.state, s.attempts, s.error_class || "", s.message || "",
       JSON.stringify(s.result), (s.recoveries || []).join(", ")].forEach((v) => tr.insertCell().textContent = v);
    });
  }
  async function poll() {
    if (polling) return; polling = true;
    try {
      while (runId) {
        const run = await call("GET", `/api/runs/${runId}`).catch(() => null);
        if (run) { renderRun(run); if (!["created", "running", "cancel_requested"].includes(run.status)) break; }
        await new Promise((ok) => setTimeout(ok, 500));
      }
    } finally { polling = false; }
  }
  $("[data-action=run]").addEventListener("click", async () => {
    if (!plan.length) { errorBox.textContent = "Plan boş."; return; }
    const run = await call("POST", "/api/runs", { session_id: needSession(), request_id: crypto.randomUUID(), steps: plan }).catch(() => null);
    if (run) { runId = run.run_id; renderRun(run); poll(); }
  });
  $("[data-action=cancel]").addEventListener("click", async () => {
    if (!runId) return;
    const run = await call("POST", `/api/runs/${runId}/cancel`).catch(() => null);
    if (run) renderRun(run);
  });
  $("[data-action=resume]").addEventListener("click", async () => {
    if (!runId) return;
    const run = await call("POST", `/api/runs/${runId}/resume`, { session_id: needSession() }).catch(() => null);
    if (run) { renderRun(run); poll(); }
  });

  showOpFields();
  loadActions();
})();
