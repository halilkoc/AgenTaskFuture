// İşlem Asistanı ekranı. Plan sunucuda derlenir; istemci yalnız işlem kimliği ve argüman gönderir.
"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const errorBox = $(".tl-error");
  const labOrigin = $(".as-config").dataset.labOrigin;
  let sessionId = null, choice = null, runId = null;
  const STATE_TR = { pending: "Bekliyor", prepared: "Hazırlandı", dispatched: "İşlem gönderildi", verifying: "Sonuç doğrulanıyor",
    succeeded: "Başarılı", known_failed: "Bilinen başarısızlık", outcome_unknown: "Sonuç belirsiz", skipped: "Atlandı (iptal)" };
  const el = (t, x, c) => { const e = document.createElement(t); if (x != null) e.textContent = x; if (c) e.className = c; return e; };
  async function call(method, path, body) {
    errorBox.textContent = "";
    const r = await fetch(path, { method, credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 204) return null;
    const d = await r.json();
    if (!r.ok) { errorBox.textContent = `${d.safe_message}${d.details && d.details.reason ? " (" + d.details.reason + ")" : ""}`; throw new Error(d.code); }
    return d;
  }
  call("GET", "/api/assistant/catalog").then((c) => {
    $(".as-llm").textContent = `Etkin yayında ${c.operations.length} işlem · model: ${c.llm_available ? "kullanılabilir" : "kapalı"}`;
    window.__catalog = c.operations;
  }).catch(() => { $(".as-llm").textContent = "Katalog alınamadı."; });

  function showInterpretation(r) {
    const box = $(".as-result"); box.replaceChildren();
    box.appendChild(el("p", `${r.status === "matched" ? "Eşleşti" : r.status === "no_match" ? "Eşleşme yok" : "Açıklama gerekli"} · ${r.explanation}${r.provenance === "model_suggested" ? " [model önerisi]" : ""}`));
    if (!r.operation_id) {
      (r.candidates || []).forEach((c) => { const b = el("button", `${c.title} (${c.operation_id})`); b.type = "button";
        b.addEventListener("click", () => choose(c.operation_id, (window.__catalog.find((o) => o.operation_id === c.operation_id) || {}).release_id, {})); box.appendChild(b); });
      return;
    }
    choose(r.operation_id, r.release_id, r.arguments || {}, r.missing || []);
  }
  function choose(operationId, releaseId, args, missing = []) {
    const op = (window.__catalog || []).find((o) => o.operation_id === operationId);
    choice = { operation_id: operationId, release_id: releaseId || (op && op.release_id), arguments: { ...args } };
    const box = $(".as-result");
    const form = el("form", null, "as-args");
    form.appendChild(el("p", `İşlem: ${op ? op.title : operationId}`));
    (op ? op.parameters : []).forEach((p) => {
      const lab = el("label", `${p.title}${missing.includes(p.name) ? " (eksik)" : ""} `); const i = el("input"); i.name = p.name; i.value = args[p.name] || ""; i.maxLength = p.max_length;
      lab.appendChild(i); form.appendChild(lab);
    });
    const b = el("button", "Planı göster"); b.type = "submit"; form.appendChild(b);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      form.querySelectorAll("input").forEach((i) => { choice.arguments[i.name] = i.value; });
      const plan = await call("POST", "/api/assistant/preview", choice).catch(() => null);
      if (!plan) return;
      const sec = $(".as-plan").parentElement; sec.hidden = false;
      const pb = $(".as-plan"); pb.replaceChildren();
      pb.appendChild(el("p", `${plan.title} · yayın ${plan.release_id} · revizyon ${plan.revision} · etki: ${plan.effect === "mutating" ? "veri değiştirir" : plan.effect === "ui_local" ? "yalnız ekran alanları" : "okuma"}`));
      const ol = el("ol"); plan.steps.forEach((s) => ol.appendChild(el("li", s))); pb.appendChild(ol);
      $(".as-ack-wrap").hidden = plan.effect !== "mutating";
    });
    box.appendChild(form);
  }
  $(".as-ask").addEventListener("submit", async (e) => {
    e.preventDefault();
    const r = await call("POST", "/api/assistant/interpret", { prompt: e.target.prompt.value, use_model: e.target.use_model.checked }).catch(() => null);
    if (r) showInterpretation(r);
  });
  $("[data-action=open]").addEventListener("click", async () => {
    const s = await call("POST", "/api/sessions").catch(() => null);
    if (s) { sessionId = s.session_id; $(".as-session").textContent = `Oturum: ${s.session_id}`; }
  });
  const screen = $("[data-action=screen]");
  if (screen) screen.addEventListener("click", async () => {
    if (!sessionId) { errorBox.textContent = "Önce oturum açın."; return; }
    const url = `${labOrigin}/__lab/autologin?user=operator&next=${encodeURIComponent($("[name=lab_page]").value)}`;
    const r = await call("POST", `/api/sessions/${sessionId}/navigate`, { url }).catch(() => null);
    if (r) $(".as-session").textContent = `Oturum: ${sessionId} · ${r.url}`;
  });
  function render(run) {
    const p = $(".rl-run"); p.replaceChildren();
    const cls = { completed: "resolved", failed: "unresolved", outcome_unknown: "ambiguous" }[run.status] || (run.status.startsWith("paused") ? "ambiguous" : "");
    p.appendChild(el("span", run.outcome_label, `badge ${cls}`));
    p.appendChild(document.createTextNode(` ${run.status}${run.status_reason ? " (" + run.status_reason + ")" : ""} · yayın ${(run.binding || {}).release_id || "-"}`));
    const t = $(".rl-steps"); t.replaceChildren();
    const h = t.insertRow(); ["#", "Komut", "Durum", "Hata", "Açıklama"].forEach((x) => h.appendChild(el("th", x)));
    run.steps.forEach((s) => { const tr = t.insertRow(); tr.dataset.state = s.state;
      [s.index + 1, s.command.op, STATE_TR[s.state] || s.state, s.error_class || "", s.message || ""].forEach((v) => tr.insertCell().textContent = v); });
  }
  async function poll() {
    while (runId) {
      const run = await call("GET", `/api/runs/${runId}`).catch(() => null);
      if (run) { render(run); if (!["created", "running", "cancel_requested"].includes(run.status)) return; }
      await new Promise((ok) => setTimeout(ok, 500));
    }
  }
  $("[data-action=run]").addEventListener("click", async () => {
    if (!choice || !sessionId) { errorBox.textContent = "Önce talebi yorumlayın, planı görün ve oturum açın."; return; }
    const ack = $("[name=ack]");
    const run = await call("POST", "/api/assistant/execute", { ...choice, session_id: sessionId, request_id: crypto.randomUUID(),
      acknowledge_effect: ack ? ack.checked : false }).catch(() => null);
    if (run) { runId = run.run_id; render(run); poll(); }
  });
  const compAdd = $("[data-action=comp-add]");
  if (compAdd) {
    const rows = $(".as-comp-rows");
    compAdd.addEventListener("click", () => {
      const row = el("div", null, "as-comp-row"); const sel = el("select"); sel.name = "op";
      (window.__catalog || []).forEach((o) => { const opt = el("option", o.title); opt.value = o.operation_id; sel.appendChild(opt); });
      const args = el("span");
      const draw = () => { args.replaceChildren(); const op = window.__catalog.find((o) => o.operation_id === sel.value);
        (op ? op.parameters : []).forEach((p) => { const i = el("input"); i.name = p.name; i.placeholder = p.title; args.appendChild(i); }); };
      sel.addEventListener("change", draw); row.appendChild(sel); row.appendChild(args); rows.appendChild(row); draw();
    });
    const compPlan = () => ({ nodes: [...document.querySelectorAll(".as-comp-row")].map((r) => ({ kind: "call_operation",
      operation_id: r.querySelector("[name=op]").value,
      arguments: Object.fromEntries([...r.querySelectorAll("span input")].map((i) => [i.name, i.value])) })) });
    let compRelease = null;
    $("[data-action=comp-preview]").addEventListener("click", async () => {
      const r = await call("POST", "/api/assistant/composite/preview", { plan: compPlan() }).catch(() => null);
      if (r) { compRelease = r.release_id; $(".as-comp").textContent = `${r.steps} adım · işlemler: ${Object.keys(r.operations).join(", ")} · yayın ${r.release_id}`; }
    });
    $("[data-action=comp-run]").addEventListener("click", async () => {
      if (!sessionId || !compRelease) { errorBox.textContent = "Önce birleşik planı görün ve oturum açın."; return; }
      const run = await call("POST", "/api/assistant/composite/execute", { plan: compPlan(), session_id: sessionId,
        release_id: compRelease, request_id: crypto.randomUUID() }).catch(() => null);
      if (run) { runId = run.run_id; render(run); poll(); }
    });
  }
  $("[data-action=cancel]").addEventListener("click", async () => { if (runId) { const r = await call("POST", `/api/runs/${runId}/cancel`).catch(() => null); if (r) render(r); } });
})();
