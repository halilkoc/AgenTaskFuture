"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const errorBox = $(".tl-error"); const labOrigin = $(".ch-config").dataset.labOrigin;
  let sessionId = null;
  const el = (t, x, c) => { const e = document.createElement(t); if (x != null) e.textContent = x; if (c) e.className = c; return e; };
  const STATUS_TR = { unchanged: "Değişmedi", ambiguous: "Belirsiz (birden fazla aday)", not_found: "Bulunamadı",
    hidden_or_disabled: "Gizli/devre dışı", unknown: "Bilinmiyor (kapsam eksik)" };
  async function call(method, path, body) {
    errorBox.textContent = "";
    const r = await fetch(path, { method, credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json();
    if (!r.ok) { errorBox.textContent = `${d.safe_message}${d.details && d.details.reason ? " (" + d.details.reason + ")" : ""}`; throw new Error(d.code); }
    return d;
  }
  call("GET", "/api/changes/operations").then((d) => {
    const sel = $("[name=operation]");
    d.operations.forEach((o) => { const opt = el("option", `${o.title} (${o.operation_id} r${o.revision})`); opt.value = o.operation_id; sel.appendChild(opt); });
  }).catch(() => {});
  function impacted(list, box) {
    if (!list.length) { box.appendChild(el("p", "Etkilenen işlem yok.")); return; }
    const ul = el("ul");
    list.forEach((i) => ul.appendChild(el("li", `${i.operation_id} r${i.revision} — nedenler: ${i.reasons.join(", ")} · yeniden test: ${i.regression_tests.join(", ")}`)));
    box.appendChild(el("p", "Etkilenen işlemler:")); box.appendChild(ul);
  }
  $("[data-action=open]").addEventListener("click", async () => {
    const s = await call("POST", "/api/sessions").catch(() => null);
    if (s) { sessionId = s.session_id; $(".ch-session").textContent = `Oturum: ${s.session_id}`; }
  });
  const screen = $("[data-action=screen]");
  if (screen) screen.addEventListener("click", async () => {
    if (!sessionId) { errorBox.textContent = "Önce oturum açın."; return; }
    const r = await call("POST", `/api/sessions/${sessionId}/navigate`, { url: `${labOrigin}/__lab/autologin?user=bakim&next=${encodeURIComponent($("[name=lab_page]").value)}` }).catch(() => null);
    if (r) $(".ch-session").textContent = `Oturum: ${sessionId} · ${r.url}`;
  });
  $("[data-action=analyze]").addEventListener("click", async () => {
    if (!sessionId) { errorBox.textContent = "Önce oturum açın ve ekranı açın."; return; }
    const op = $("[name=operation]").value;
    const r = await call("POST", "/api/changes/analyze", { session_id: sessionId, operation_id: op }).catch(() => null);
    if (!r) return;
    const box = $(".ch-result"); box.replaceChildren();
    const table = el("table", null, "tl-table"); const h = table.insertRow();
    ["Eleman", "Anlam", "Hedef", "Durum", "Öneri"].forEach((x) => h.appendChild(el("th", x)));
    const broken = [];
    r.elements.forEach((e) => {
      const tr = table.insertRow(); tr.dataset.status = e.status;
      if (["not_found", "ambiguous"].includes(e.status)) broken.push(e.element_id);
      [e.element_id, e.meaning, `${e.target.kind} "${e.target.labels.join("/")}"${e.target.region ? " · " + e.target.region : ""}`,
       STATUS_TR[e.status] || e.status, (e.suggestions || []).map((s) => s.label).join(", ")].forEach((v) => tr.insertCell().textContent = v);
    });
    box.appendChild(table); impacted(r.impacted, box);
    if (broken.length) {
      const b = el("button", "Onarım taslağı oluştur"); b.type = "button";
      b.addEventListener("click", async () => {
        const d = await call("POST", "/api/changes/repair", { operation_id: op, element_ids: broken }).catch(() => null);
        if (d) box.appendChild(el("p", `Onarım taslağı açıldı: ${d.draft_id} — Katalog Tasarımcısı'nda hedefi yeniden seçin. Etkin yayın değişmedi.`, "dz-ok"));
      });
      box.appendChild(b);
    }
  });
  $("[data-action=dependency]").addEventListener("click", async () => {
    const kind = $("[name=kind]").value; const action = $("[name=action_id]").value.trim();
    const r = await call("POST", "/api/changes/dependency-impact", { adapter_kinds: kind ? [kind] : [], action_ids: action ? [action] : [] }).catch(() => null);
    if (!r) return;
    const box = $(".ch-dependency"); box.replaceChildren(); impacted(r.impacted, box);
  });
})();
