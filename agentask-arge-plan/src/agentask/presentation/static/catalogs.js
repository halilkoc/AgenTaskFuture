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
  function askActivate(id, activeId) {
    const box = $(".ct-detail"); box.replaceChildren();
    box.appendChild(el("p", `${id} etkin yapılacak. Yeni kayıt silinmez; süren çalışmalar kendi sürümünde kalır. Yalnız yayıncı yapabilir.`));
    const label = el("label", "Gerekçe (en az 10 karakter) "); const reason = el("input"); reason.name = "reason"; reason.size = 60; reason.maxLength = 500; label.appendChild(reason); box.appendChild(label);
    const go = el("button", "Etkinleştirmeyi onayla"); go.type = "button";
    go.addEventListener("click", async () => {
      $(".tl-error").textContent = ""; go.disabled = true;
      const r = await fetch(`/api/catalogs/releases/${encodeURIComponent(id)}/activate`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_active_release_id: activeId, reason: reason.value }) });
      const d = await r.json();
      if (r.ok) { location.reload(); return; }
      go.disabled = false;
      const problems = d.details && d.details.problems ? ` (${d.details.problems.join(", ")})` : "";
      $(".tl-error").textContent = `${d.safe_message || "İşlem yapılamadı."}${problems}`;
    });
    box.appendChild(go);
  }
  call("/api/catalogs/releases").then((data) => {
    const box = $(".ct-list"); box.replaceChildren();
    box.appendChild(el("p", `Uygulama ${data.application_id} · ortam ${data.environment} · etkin: ${data.active_release_id || "yok"}`));
    const ul = el("ul");
    data.releases.forEach((r) => { const li = el("li", `${r.release_id} ${r.active ? "(etkin)" : ""} · ${r.operations.length} işlem · ${r.created_by} `);
      const b = el("button", "Ayrıntı"); b.type = "button"; b.addEventListener("click", () => detail(r.release_id).catch(() => {})); li.appendChild(b);
      if (!r.active) { const a = el("button", "Bu yayını etkinleştir"); a.type = "button"; a.addEventListener("click", () => askActivate(r.release_id, data.active_release_id)); li.appendChild(a); } ul.appendChild(li); });
    box.appendChild(ul);
    if ((data.activations || []).length) {
      box.appendChild(el("h3", "Etkin yayın geçmişi"));
      const hist = el("ul", null, "ct-history");
      data.activations.forEach((a) => hist.appendChild(el("li", `${new Date(a.at).toLocaleString("tr-TR")} · ${a.by} · ${a.from_release_id || "-"} → ${a.to_release_id} · ${a.reason}`)));
      box.appendChild(hist);
    }
  }).catch(() => { $(".ct-list").textContent = "Yayın bilgisi alınamadı."; });
})();
