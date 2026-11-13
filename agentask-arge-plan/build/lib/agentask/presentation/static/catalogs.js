// Yayın inceleme: yalnız okuma.
"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };
  async function call(path) {
    const r = await fetch(path, { credentials: "same-origin" }); const d = await r.json();
    if (!r.ok) { $(".tl-error").textContent = d.safe_message || "İstek başarısız."; throw new Error(d.code); }
    return d;
  }
  async function detail(id) {
    const d = await call(`/api/catalogs/releases/${id}`);
    const box = $(".ct-detail"); box.replaceChildren();
    box.appendChild(el("p", `${d.release_id} · ${d.active ? "ETKİN" : "pasif"} · manifest ${d.manifest_hash.slice(0, 12)} · temel: ${d.base_release_id || "-"} · adapter ${d.adapter_version} · şema ${d.schema_version}`));
    const ul = el("ul");
    d.operation_details.forEach((o) => ul.appendChild(el("li", `${o.operation_id} r${o.revision} — ${o.title} (${o.steps} adım) · ${o.content_hash.slice(0, 12)}`)));
    box.appendChild(ul);
    const ap = el("ul");
    d.approvals.forEach((a) => ap.appendChild(el("li", `Onay: ${a.approver} · içerik ${a.content_hash.slice(0, 12)} · test ${a.test_run_id}`)));
    box.appendChild(ap);
  }
  call("/api/catalogs/releases?application_id=lab").then((data) => {
    const box = $(".ct-list"); box.replaceChildren();
    box.appendChild(el("p", `Uygulama ${data.application_id} · ortam ${data.environment} · etkin: ${data.active_release_id || "yok"}`));
    const ul = el("ul");
    data.releases.forEach((r) => { const li = el("li", `${r.release_id} ${r.active ? "(etkin)" : ""} · ${r.operations.length} işlem · ${r.created_by} `);
      const b = el("button", "Ayrıntı"); b.type = "button"; b.addEventListener("click", () => detail(r.release_id).catch(() => {})); li.appendChild(b); ul.appendChild(li); });
    box.appendChild(ul);
  }).catch(() => { $(".ct-list").textContent = "Yayın bilgisi alınamadı."; });
})();
