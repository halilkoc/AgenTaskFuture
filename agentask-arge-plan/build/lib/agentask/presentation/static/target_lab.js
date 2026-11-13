// Hedef Deneme ekranı. Yalnız /api uçlarını çağırır; secret veya backend ayarı içermez.
"use strict";
(function () {
  let sessionId = null;
  let picking = false;
  const $ = (s) => document.querySelector(s);
  const errorBox = $(".tl-error");

  async function call(method, path, body) {
    errorBox.textContent = "";
    const response = await fetch(path, {
      method, credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (response.status === 204) return null;
    const data = await response.json();
    if (!response.ok) {
      errorBox.textContent = `${data.safe_message || "İstek başarısız."}${data.details && data.details.reason ? " (" + data.details.reason + ")" : ""}`;
      throw new Error(data.code);
    }
    return data;
  }
  const base = () => { if (!sessionId) { errorBox.textContent = "Önce oturum açın."; throw new Error("no_session"); } return `/api/sessions/${sessionId}`; };
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };

  function highlightButton(cid) {
    const b = el("button", "Vurgula");
    b.type = "button";
    b.addEventListener("click", () => call("POST", `${base()}/candidates/${encodeURIComponent(cid)}/highlight`).catch(() => {}));
    return b;
  }
  function contextText(c) {
    return [...(c.frame_titles || []), ...(c.contexts || []).slice().reverse().map((x) => x.key ? `${x.name} [${x.key}]` : (x.name || x.kind))].join(" › ");
  }
  function candidatesTable(rows) {
    const table = el("table", null, "tl-table");
    const head = table.insertRow();
    ["Etiket / ad", "Tür", "Bağlam", "Görünür", "Etkin", "Hassas", ""].forEach((h) => head.appendChild(el("th", h)));
    rows.forEach((c) => {
      const tr = table.insertRow();
      [c.label || c.accessible_name || "(adsız)", c.kind, contextText(c), c.visible ? "evet" : "hayır",
       c.enabled ? "evet" : "hayır", c.sensitive ? "evet" : "-"].forEach((v) => tr.insertCell().textContent = v);
      tr.insertCell().appendChild(highlightButton(c.candidate_id));
    });
    return table;
  }

  document.querySelector("[data-action=open]").addEventListener("click", async () => {
    const s = await call("POST", "/api/sessions").catch(() => null);
    if (s) { sessionId = s.session_id; $(".tl-session-id").textContent = `Oturum: ${s.session_id}`; }
  });
  document.querySelector("[data-action=close]").addEventListener("click", async () => {
    if (!sessionId) return;
    await call("DELETE", `/api/sessions/${sessionId}`).catch(() => {});
    sessionId = null; picking = false; $(".tl-session-id").textContent = "Oturum yok";
  });
  $(".tl-nav").addEventListener("submit", async (e) => {
    e.preventDefault();
    const r = await call("POST", `${base()}/navigate`, { url: e.target.url.value }).catch(() => null);
    if (r) errorBox.textContent = `Açıldı: ${r.url}`;
  });
  document.querySelector("[data-action=observe]").addEventListener("click", async () => {
    const s = await call("POST", `${base()}/observe`).catch(() => null);
    if (!s) return;
    const box = $(".tl-observe"); box.replaceChildren();
    box.appendChild(el("p", `Snapshot ${s.snapshot_revision} · kapsam: ${s.coverage === "complete" ? "tam" : "eksik"} · ${s.controls.length} kontrol`));
    const frames = el("ul");
    s.frames.forEach((f) => frames.appendChild(el("li", `${"  ".repeat(f.depth)}${f.title || "(ana sayfa)"} — ${f.status}${f.reason ? " (" + f.reason + ")" : ""}`)));
    box.appendChild(frames);
    box.appendChild(candidatesTable(s.controls));
  });
  $(".tl-resolve").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    const spec = { kind: f.kind.value, labels: f.labels.value.split(",").map((x) => x.trim()).filter(Boolean) };
    ["region", "frame_title", "row_key"].forEach((k) => { if (f[k].value.trim()) spec[k] = f[k].value.trim(); });
    $(".tl-spec").textContent = JSON.stringify(spec, null, 2);
    const r = await call("POST", `${base()}/resolve`, spec).catch(() => null);
    if (!r) return;
    const box = $(".tl-result"); box.replaceChildren();
    const title = el("p");
    title.appendChild(el("span", r.outcome, `badge ${r.outcome}`));
    title.appendChild(document.createTextNode(` ${r.reason} — ${r.explanation} (snapshot ${r.snapshot_revision})`));
    box.appendChild(title);
    if (r.coverage.incomplete.length) {
      const ul = el("ul");
      r.coverage.incomplete.forEach((x) => ul.appendChild(el("li", `Eksik kapsam: ${x.title || x.frame_ref} — ${x.status}${x.reason ? " (" + x.reason + ")" : ""}`)));
      box.appendChild(ul);
    }
    if (r.candidates.length) box.appendChild(candidatesTable(r.candidates.map((c) => ({ ...c, sensitive: false }))));
    if (r.candidate_id) call("POST", `${base()}/candidates/${encodeURIComponent(r.candidate_id)}/highlight`).catch(() => {});
  });

  async function pollPick() {
    while (picking && sessionId) {
      const r = await call("GET", `${base()}/picker/selection?wait_ms=20000`).catch(() => null);
      if (!r) { await new Promise((ok) => setTimeout(ok, 1000)); continue; }
      if (r.selected && r.pick) {
        const box = $(".tl-pick"); box.replaceChildren();
        if (r.pick.control) {
          box.appendChild(el("p", `Seçilen: ${r.pick.control.caption}`));
          box.appendChild(el("p", `Aday: ${r.pick.candidate_id} · snapshot ${r.pick.snapshot_revision}`, "muted"));
        } else {
          box.appendChild(el("p", `Desteklenmeyen öğe (${r.pick.reason})`));
        }
      }
    }
  }
  document.querySelector("[data-action=picker-start]").addEventListener("click", async () => {
    await call("POST", `${base()}/picker/start`).catch(() => null);
    picking = true; $(".tl-pick").textContent = "Seçim açık: tarayıcıda bir kontrole tıklayın (tıklama sayfaya iletilmez).";
    pollPick();
  });
  document.querySelector("[data-action=picker-stop]").addEventListener("click", async () => {
    picking = false;
    await call("POST", `${base()}/picker/stop`).catch(() => null);
    $(".tl-pick").textContent = "Seçim kapalı.";
  });
  document.querySelector("[data-action=clear]").addEventListener("click", () => call("DELETE", `${base()}/highlight`).catch(() => {}));
})();
