"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const el = (t, x, c) => { const e = document.createElement(t); if (x != null) e.textContent = x; if (c) e.className = c; return e; };
  async function call(path) { const r = await fetch(path, { credentials: "same-origin" }); const d = await r.json(); if (!r.ok) { $(".tl-error").textContent = d.safe_message; throw new Error(d.code); } return d; }
  call("/api/metrics/runs").then((m) => {
    const box = $(".rn-metrics"); box.replaceChildren();
    box.appendChild(el("p", `Toplam ${m.total} · iş başarısı oranı ${m.business_success_rate == null ? "-" : Math.round(m.business_success_rate * 100) + "%"} · teknik toparlanmayla başarılı ${m.completed_with_technical_recovery} · belirsiz ${m.outcome_unknown}`));
    box.appendChild(el("p", `Durumlar: ${JSON.stringify(m.by_status)} · süre p50 ${m.duration_seconds.p50 ?? "-"} sn, p95 ${m.duration_seconds.p95 ?? "-"} sn`));
    box.appendChild(el("p", `Toparlanmalar: ${JSON.stringify(m.recoveries)} · hata sınıfları: ${JSON.stringify(m.error_classes)}`));
  }).catch(() => {});
  call("/api/runs").then((runs) => {
    const t = $(".rn-list"); const h = t.insertRow();
    ["Çalışma", "Sonuç", "Durum", "İşlem/yayın", "Oluşturma", ""].forEach((x) => h.appendChild(el("th", x)));
    runs.forEach((r) => {
      const tr = t.insertRow();
      [r.run_id, r.outcome_label, r.status, r.binding ? `${r.binding.operation_id} · ${r.binding.release_id}` : "deneme", r.created_at].forEach((v) => tr.insertCell().textContent = v);
      const b = el("button", "Ayrıntı"); b.type = "button"; b.addEventListener("click", () => detail(r)); tr.insertCell().appendChild(b);
    });
  }).catch(() => {});
  function detail(r) {
    const box = $(".rn-detail"); box.replaceChildren();
    box.appendChild(el("p", `${r.run_id} · ${r.outcome_label} (${r.status}${r.status_reason ? ", " + r.status_reason : ""})`));
    const ol = el("ol");
    r.steps.forEach((s) => ol.appendChild(el("li", `${s.command.op} — ${s.state} · deneme ${s.attempts}${s.error_class ? " · " + s.error_class : ""}${s.recoveries.length ? " · toparlanma: " + s.recoveries.join(", ") : ""}${s.message ? " · " + s.message : ""}`)));
    box.appendChild(ol);
  }
})();
