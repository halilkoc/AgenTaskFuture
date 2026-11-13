"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const el = (t, x, c) => { const e = document.createElement(t); if (x != null) e.textContent = x; if (c) e.className = c; return e; };
  const when = (iso) => new Date(iso).toLocaleString("tr-TR");
  async function call(path) { const r = await fetch(path, { credentials: "same-origin" }); const d = await r.json(); if (!r.ok) { $(".tl-error").textContent = d.safe_message; throw new Error(d.code); } return d; }
  call("/api/metrics/runs").then((m) => {
    const box = $(".rn-metrics"); box.replaceChildren();
    box.appendChild(el("p", `Toplam ${m.total} · iş başarısı oranı ${m.business_success_rate == null ? "-" : Math.round(m.business_success_rate * 100) + "%"} · teknik toparlanmayla başarılı ${m.completed_with_technical_recovery} · belirsiz ${m.outcome_unknown}`));
    box.appendChild(el("p", `Durumlar: ${JSON.stringify(m.by_status)} · süre p50 ${m.duration_seconds.p50 ?? "-"} sn, p95 ${m.duration_seconds.p95 ?? "-"} sn`));
    box.appendChild(el("p", `Toparlanmalar: ${JSON.stringify(m.recoveries)} · hata sınıfları: ${JSON.stringify(m.error_classes)}`));
  }).catch(() => {});
  call("/api/runs").then((runs) => {
    const t = $(".rn-list"); const h = t.insertRow();
    ["İşlem", "Zaman", "Durum", "Neden", ""].forEach((x) => h.appendChild(el("th", x)));
    if (!runs.length) t.insertRow().insertCell().textContent = "Henüz çalışma yok.";
    runs.forEach((r) => {
      const tr = t.insertRow();
      [r.summary.title, when(r.created_at), r.outcome_label, r.summary.reason || ""].forEach((v) => tr.insertCell().textContent = v);
      const b = el("button", "Ayrıntı"); b.type = "button"; b.addEventListener("click", () => detail(r)); tr.insertCell().appendChild(b);
    });
  }).catch(() => {});
  function detail(r) {
    const box = $(".rn-detail"); box.replaceChildren();
    const s = r.summary;
    box.appendChild(el("h3", s.title));
    box.appendChild(el("p", `${r.outcome_label} · başlangıç ${when(r.created_at)} · son güncelleme ${when(r.updated_at)}`));
    if (s.failed_stage) box.appendChild(el("p", `Aşama: ${s.failed_stage}`, "rn-stage"));
    if (s.reason) box.appendChild(el("p", `Neden: ${s.reason}`, "rn-reason"));
    if (s.next_step) box.appendChild(el("p", `Sonraki adım: ${s.next_step}`, "rn-next"));
    box.appendChild(el("p", s.correlation_id ? `Destek numarası: ${s.correlation_id}` : "Destek numarası: bu eski kayıtta yok", "rn-support"));
    const tech = el("details", null, "rn-tech"); tech.appendChild(el("summary", "Teknik ayrıntılar"));
    tech.appendChild(el("p", `${r.run_id} · ${r.status}${r.status_reason ? ", " + r.status_reason : ""}${r.binding ? ` · ${r.binding.operation_id || "birleşik"} · ${r.binding.release_id}` : ""}`, "muted"));
    const ol = el("ol");
    r.steps.forEach((s) => ol.appendChild(el("li", `${s.command.op} — ${s.state} · deneme ${s.attempts}${s.error_class ? " · " + s.error_class : ""}${s.recoveries.length ? " · toparlanma: " + s.recoveries.join(", ") : ""}${s.message ? " · " + s.message : ""}`)));
    tech.appendChild(ol); box.appendChild(tech);
  }
})();
