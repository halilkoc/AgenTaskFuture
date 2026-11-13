// İşlem Asistanı ekranı. Plan sunucuda derlenir; istemci yalnız işlem kimliği ve argüman gönderir.
"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  const errorBox = $(".tl-error");
  const labOrigin = $(".as-config").dataset.labOrigin;
  let choice = null, runId = null, runActive = false, compRelease = null;
  // Uygulama kapsamı: liste sunucudan (AUTOMATION_APPLICATIONS_JSON allowlist alanları) gelir.
  const apps = JSON.parse(document.getElementById("as-apps").textContent || "[]");
  const appSelect = document.querySelector("[name=application]");
  let appId = appSelect ? appSelect.value : "";
  const currentApp = () => apps.find((a) => a.id === appId) || null;
  const S = window.AgenTaskSession;
  const STATE_TR = { pending: "Bekliyor", prepared: "Hazırlandı", dispatched: "İşlem gönderildi", verifying: "Sonuç doğrulanıyor",
    succeeded: "Başarılı", known_failed: "Bilinen başarısızlık", outcome_unknown: "Sonuç belirsiz", skipped: "Atlandı (iptal)" };
  const el = (t, x, c) => { const e = document.createElement(t); if (x != null) e.textContent = x; if (c) e.className = c; return e; };
  async function call(method, path, body) {
    errorBox.textContent = "";
    const r = await fetch(path, { method, credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 204) return null;
    const d = await r.json();
    if (!r.ok) { errorBox.textContent = `${d.safe_message}${d.details && d.details.reason ? " (" + d.details.reason + ")" : ""} · Destek numarası: ${d.correlation_id}`; throw new Error(d.code); }
    return d;
  }
  function loadCatalog() {
    window.__catalog = [];
    const app = currentApp();
    if (!app) {
      $(".as-llm").textContent = apps.length ? "Önce bir uygulama seçin." : "Yapılandırılmış uygulama yok.";
      return;
    }
    const requested = app.id;
    call("GET", `/api/assistant/catalog?application_id=${encodeURIComponent(app.id)}`).then((c) => {
      if (requested !== appId) return; // bu arada uygulama değişti; eski yanıt kullanılmaz
      const legacy = c.operations.filter((o) => o.migration_required).length;
      $(".as-llm").textContent = `Etkin yayında ${c.operations.length} işlem${legacy ? ` (${legacy} işlem ekran tanımı olmadığı için geçiş bekliyor)` : ""} · model: ${c.llm_available ? "kullanılabilir" : "kapalı"} · uygulama: ${app.name}${c.operations.length ? "" : " (bu uygulama için yayımlanmış işlem yok)"}`;
      window.__catalog = c.operations;
      const propose = $("[data-action=propose]"); if (propose) propose.hidden = !c.llm_available;
      renderReady();
    }).catch(() => { $(".as-llm").textContent = "Katalog alınamadı."; });
  }
  function needApp() {
    if (currentApp()) return true;
    errorBox.textContent = apps.length ? "Önce bir uygulama seçin." : "Yapılandırılmış uygulama yok; işlem yapılamaz.";
    return false;
  }
  function resetForApp() {
    // Önceki uygulamanın yorumu, planı ve birleşik planı yeni uygulamaya taşınmaz.
    choice = null; compRelease = null;
    $(".as-result").replaceChildren();
    $(".as-missing").replaceChildren(); $(".as-missing").parentElement.hidden = true; planReady = false;
    $(".as-plan").replaceChildren(); $(".as-plan").parentElement.hidden = true;
    $(".as-ack-wrap").hidden = true; const ack = $("[name=ack]"); if (ack) ack.checked = false;
    const comp = $(".as-comp"); if (comp) comp.textContent = "";
  }
  if (appSelect) appSelect.addEventListener("change", () => {
    const next = appSelect.value;
    if (runActive) {
      appSelect.value = appId;
      errorBox.textContent = "Çalıştırma sürerken uygulama değiştirilemez; önce bitmesini bekleyin veya iptal edin.";
      return;
    }
    const hasWork = choice !== null || compRelease !== null || $(".as-result").childElementCount > 0;
    if (hasWork && !window.confirm("Uygulama değişirse mevcut yorum ve plan temizlenir. Değiştirilsin mi?")) {
      appSelect.value = appId;
      return;
    }
    appId = next;
    resetForApp();
    $(".as-app-status").textContent = currentApp() ? `Seçili uygulama: ${currentApp().name}` : "";
    loadCatalog();
  });
  const openApp = $("[data-action=open-app]");
  if (openApp) openApp.addEventListener("click", async () => {
    if (!needApp()) return;
    const sid = S.id(); if (!sid) { errorBox.textContent = "Önce bir tarayıcı oturumu seçin veya açın."; return; }
    const r = await call("POST", `/api/sessions/${sid}/navigate`, { url: currentApp().base_url }).catch(() => null);
    if (r) { $(".as-session").textContent = `Uygulama açıldı: ${r.url}`; S.refresh(); }
  });
  if (currentApp()) $(".as-app-status").textContent = `Seçili uygulama: ${currentApp().name}`;
  loadCatalog();

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
  // Onaylanan plan yalnız gösterildiği bilgilerle geçerlidir; bilgi değişirse plan yeniden gösterilmeden başlatılmaz.
  let planReady = false;
  function invalidatePlan(note) {
    planReady = false;
    $(".as-plan").parentElement.hidden = true;
    $(".as-ack-wrap").hidden = true; const ack = $("[name=ack]"); if (ack) ack.checked = false;
    if (note) errorBox.textContent = note;
  }
  const EFFECT_TR = { mutating: "veri değiştirir", unknown: "etkisi bilinmiyor (kayıt veya ekran değişikliği tetikleyebilir)", ui_local: "yalnız ekran alanları", none: "okuma" };
  function showAck(effect) {
    const needs = effect === "mutating" || effect === "unknown";
    $(".as-ack-wrap").hidden = !needs;
    $(".as-ack-text").textContent = effect === "unknown" ? " Bu işlem kayıt veya ekran değişikliği tetikleyebilir; onaylıyorum" : " Bu işlem veri değiştirir; onaylıyorum";
  }
  // Seçim parametresi: sabit listede serbest metin yerine seçim; liste değişkense açık ekrandan güncel seçenekler.
  function paramControl(p, value, step, operationId, onChange) {
    const makeSelect = (labels, current) => {
      const s = el("select"); s.name = p.name; if (step != null) s.dataset.step = String(step);
      const blank = el("option", "Seçin…"); blank.value = ""; s.appendChild(blank);
      labels.forEach((l) => { const o = el("option", l); o.value = l; s.appendChild(o); });
      s.value = labels.includes(current) ? current : "";
      s.addEventListener("change", onChange);
      return s;
    };
    if (p.file || p.multiple) {
      const hidden = el("input"); hidden.type = "hidden"; hidden.name = p.name; hidden.value = value; if (step != null) hidden.dataset.step = String(step);
      if (p.file) {
        const f = el("input"); f.type = "file"; f.className = "as-file"; const note = el("span", value ? "Dosya yüklendi." : "", "muted as-choice-note");
        f.addEventListener("change", async () => {
          const file = f.files[0]; if (!file) return;
          note.textContent = "Yükleniyor…"; hidden.value = ""; onChange();
          const r = await fetch("/api/artifacts/uploads", { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) }, body: file });
          if (!r.ok) { note.textContent = "Dosya kabul edilmedi (tür, boyut veya içerik)."; return; }
          hidden.value = (await r.json()).artifact_id; note.textContent = "Dosya yüklendi."; onChange();
        });
        return [hidden, f, note];
      }
      const current = value ? value.split("\n") : [];
      const sync = (box) => { hidden.value = Array.from(box.querySelectorAll("input:checked")).map((x) => x.value).join("\n"); onChange(); };
      if (p.choices) {
        const box = el("div", null, "as-multi");
        p.choices.forEach((l) => { const row = el("label"); const c = el("input"); c.type = "checkbox"; c.value = l; c.checked = current.includes(l); c.addEventListener("change", () => sync(box)); row.append(c, ` ${l}`); box.appendChild(row); });
        return [hidden, box];
      }
      const area = el("textarea"); area.rows = 3; area.value = value; area.placeholder = "Her satıra bir seçenek";
      area.addEventListener("input", () => { hidden.value = area.value; onChange(); });
      return [hidden, area];
    }
    if (p.choices) return [makeSelect(p.choices, value)];
    const i = el("input"); i.name = p.name; if (step != null) i.dataset.step = String(step); i.value = value; i.maxLength = p.max_length; i.addEventListener("input", onChange);
    if (!p.is_choice) return [i];
    const fetchBtn = el("button", "Ekrandaki güncel seçenekleri getir"); fetchBtn.type = "button";
    const note = el("span", null, "muted as-choice-note");
    fetchBtn.addEventListener("click", async () => {
      const sid = S.id(); if (!sid) { note.textContent = "Önce bir tarayıcı oturumu seçin ve ekranı açın."; return; }
      note.textContent = "Okunuyor (seçim yapılmaz)…";
      const r = await call("POST", "/api/assistant/parameter-options", { application_id: appId, release_id: choice.release_id, operation_id: operationId, parameter: p.name, session_id: sid, open_list: true }).catch(() => null);
      if (!r) { note.textContent = ""; return; }
      if (r.status !== "ok") { note.textContent = r.message || "Seçenekler okunamadı; değeri yazabilirsiniz."; return; }
      const usable = r.options.filter((o) => o.state === "ok").map((o) => o.label);
      if (!usable.length) { note.textContent = "Seçilebilir seçenek yok."; return; }
      const current = i.parentElement.querySelector("input, select");
      current.replaceWith(makeSelect(usable, current.value));
      note.textContent = "Güncel ekrandan okundu; çalışırken yeniden doğrulanır."; fetchBtn.hidden = true;
    });
    return [i, fetchBtn, note];
  }
  function choose(operationId, releaseId, args, missing = []) {
    const op = (window.__catalog || []).find((o) => o.operation_id === operationId);
    choice = { application_id: appId, operation_id: operationId, release_id: releaseId || (op && op.release_id), arguments: { ...args } };
    invalidatePlan();
    const box = $(".as-missing"); box.replaceChildren(); box.parentElement.hidden = false;
    const form = el("form", null, "as-args");
    form.appendChild(el("p", `İşlem: ${op ? op.title : operationId}`));
    if (op && op.migration_required) form.appendChild(el("p", "Bu işlem ekran tanımı olmayan eski bir yayından; çalıştırılamaz (migration_required). Katalog Tasarımcısı'nda geçiş gerekli.", "dz-bad as-migration"));
    const params = op ? op.parameters : [];
    if (!params.length) form.appendChild(el("p", "Bu işlem sizden bilgi istemiyor.", "muted"));
    params.forEach((p) => {
      const lab = el(p.multiple ? "div" : "label", `${p.title}${missing.includes(p.name) ? " (eksik)" : ""} `);
      lab.append(...paramControl(p, args[p.name] || "", null, operationId, () => { if (planReady) invalidatePlan("Bilgi değişti; işlemin özetini yeniden gösterin."); }));
      form.appendChild(lab);
    });
    const b = el("button", "Planı göster"); b.type = "submit"; form.appendChild(b);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      form.querySelectorAll("input[name], select[name]").forEach((i) => { choice.arguments[i.name] = i.value; });
      const plan = await call("POST", "/api/assistant/preview", choice).catch(() => null);
      if (!plan) return;
      const sec = $(".as-plan").parentElement; sec.hidden = false;
      const pb = $(".as-plan"); pb.replaceChildren();
      pb.appendChild(el("p", `${plan.title} · ekran: ${plan.screen.title} · etki: ${EFFECT_TR[plan.effect] || plan.effect}`));
      if (plan.navigation) pb.appendChild(el("p", `Ekran rotası: ${plan.route.join(" → ")} · bu işlem ekran değiştirir (onaylı geçişler)`, "as-route"));
      // U3: sunucu adımları bağlı değerlerle doldurur; hassas değerler maskeli gelir.
      const bl = el("ul", null, "as-bindings"); (plan.bindings || []).forEach((b) => bl.appendChild(el("li", `${b.title}: ${b.value == null ? "(boş)" : b.value}`))); pb.appendChild(bl);
      const ol = el("ol"); plan.steps.forEach((s) => ol.appendChild(el("li", s))); pb.appendChild(ol);
      // Teknik kimlikler normal görünümde değil; gerektiğinde açılır.
      const tech = el("details", null, "as-tech"); tech.appendChild(el("summary", "Teknik ayrıntılar"));
      tech.appendChild(el("p", `yayın ${plan.release_id} · işlem ${plan.operation_id} · revizyon ${plan.revision}`, "muted"));
      pb.appendChild(tech);
      showAck(plan.effect);
      planReady = true;
    });
    box.appendChild(form);
  }
  // F: model yalnız yayındaki işlemlerden SIRALI bir plan önerir; sunucu doğrular. Öneri kendiliğinden çalışmaz.
  function chooseSequence(p) {
    choice = { kind: "sequence", application_id: appId, release_id: p.release_id, steps: p.steps.map((s) => ({ operation_id: s.operation_id, arguments: { ...s.arguments } })) };
    invalidatePlan();
    const box = $(".as-missing"); box.replaceChildren(); box.parentElement.hidden = false;
    const form = el("form", null, "as-args");
    p.steps.forEach((s, i) => {
      const op = (window.__catalog || []).find((o) => o.operation_id === s.operation_id);
      const fs = el("fieldset"); fs.appendChild(el("legend", `${i + 1}. ${s.title}`));
      (op ? op.parameters : []).forEach((prm) => {
        const missing = s.missing.some((m) => m.name === prm.name);
        const lab = el(prm.multiple ? "div" : "label", `${prm.title}${missing ? " (eksik)" : ""} `);
        lab.append(...paramControl(prm, s.arguments[prm.name] || "", i, s.operation_id, () => { if (planReady) invalidatePlan("Bilgi değişti; işlemin özetini yeniden gösterin."); }));
        fs.appendChild(lab);
      });
      if (!op || !op.parameters.length) fs.appendChild(el("p", "Bu işlem sizden bilgi istemiyor.", "muted"));
      form.appendChild(fs);
    });
    const b = el("button", "Planı göster"); b.type = "submit"; form.appendChild(b);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      form.querySelectorAll("input[name], select[name]").forEach((inp) => { choice.steps[Number(inp.dataset.step)].arguments[inp.name] = inp.value; });
      const plan = await call("POST", "/api/assistant/plan/preview", { application_id: appId, release_id: choice.release_id, steps: choice.steps }).catch(() => null);
      if (!plan) return;
      const sec = $(".as-plan").parentElement; sec.hidden = false;
      const pb = $(".as-plan"); pb.replaceChildren();
      pb.appendChild(el("p", `${plan.operations.length} işlem sırayla · etki: ${EFFECT_TR[plan.effect] || plan.effect} · model önerisi, sunucuda doğrulandı`));
      const bl = el("ul", null, "as-bindings"); plan.bindings.forEach((b) => bl.appendChild(el("li", `${b.step}. işlem · ${b.title}: ${b.value == null ? "(boş)" : b.value}`))); pb.appendChild(bl);
      const ol = el("ol"); plan.steps.forEach((x) => ol.appendChild(el("li", x))); pb.appendChild(ol);
      const tech = el("details", null, "as-tech"); tech.appendChild(el("summary", "Teknik ayrıntılar"));
      tech.appendChild(el("p", `yayın ${plan.release_id} · ${plan.operations.map((o) => `${o.operation_id}@${o.revision}`).join(", ")}`, "muted"));
      pb.appendChild(tech);
      showAck(plan.effect);
      planReady = true;
    });
    box.appendChild(form);
  }
  const proposeBtn = $("[data-action=propose]");
  if (proposeBtn) proposeBtn.addEventListener("click", async () => {
    if (!needApp()) return;
    const prompt = $(".as-ask").prompt.value;
    if (!prompt.trim()) { errorBox.textContent = "Önce talebinizi yazın."; return; }
    const r = await call("POST", "/api/assistant/plan/propose", { application_id: appId, prompt }).catch(() => null);
    if (!r) return;
    const box = $(".as-result"); box.replaceChildren();
    const word = { proposed: "Plan önerildi", rejected: "Plan reddedildi", model_unavailable: "Model kullanılamıyor", needs_clarification: "Açıklama gerekli", no_match: "Eşleşme yok" }[r.status] || r.status;
    box.appendChild(el("p", `${word} · ${r.explanation} [model önerisi]`, "as-proposal"));
    if (r.steps.length) { const ol = el("ol"); r.steps.forEach((s) => ol.appendChild(el("li", s.title))); box.appendChild(ol); }
    if (r.issues.length) box.appendChild(el("p", `Sorunlar: ${r.issues.join(", ")}`, "dz-bad"));
    if (r.status === "proposed") chooseSequence(r); else { choice = null; invalidatePlan(); $(".as-missing").parentElement.hidden = true; }
  });
  function renderReady() {
    const ul = $(".as-ready"); if (!ul) return; ul.replaceChildren();
    (window.__catalog || []).filter((o) => !o.migration_required).forEach((o) => {
      const li = el("li"); const b = el("button", o.title); b.type = "button";
      b.addEventListener("click", () => { $(".as-result").replaceChildren(el("p", `Hazır işlem seçildi: ${o.title}`)); choose(o.operation_id, o.release_id, {}, o.parameters.map((p) => p.name)); });
      li.appendChild(b); ul.appendChild(li);
    });
    if (!ul.childElementCount) ul.appendChild(el("li", "Yayımlanmış hazır işlem yok.", "muted"));
  }
  $(".as-ask").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!needApp()) return;
    // Model kullanımı kurum politikasıyla belirlenir (sunucu); çalışan seçmez.
    const r = await call("POST", "/api/assistant/interpret", { application_id: appId, prompt: e.target.prompt.value }).catch(() => null);
    if (r) showInterpretation(r);
  });
  const screen = $("[data-action=screen]");
  if (screen) screen.addEventListener("click", async () => {
    const sid = S.id(); if (!sid) { errorBox.textContent = "Önce bir tarayıcı oturumu seçin veya açın."; return; }
    const url = `${labOrigin}/__lab/autologin?user=operator&next=${encodeURIComponent($("[name=lab_page]").value)}`;
    const r = await call("POST", `/api/sessions/${sid}/navigate`, { url }).catch(() => null);
    if (r) { $(".as-session").textContent = `Ekran açıldı: ${r.url}`; S.refresh(); }
  });
  // Analist için sade aşama metni; teknik durum kodu yanında kalır.
  function phase(run) {
    const current = run.steps.find((s) => !["succeeded", "skipped"].includes(s.state));
    if (run.status.startsWith("paused") || run.status === "outcome_unknown") {
      const why = current && current.message ? `: ${current.message}` : "";
      return `Müdahale gerekiyor${why}`;
    }
    if (!["created", "running", "cancel_requested"].includes(run.status) || !current) return "";
    if (current.state === "verifying" || current.state === "dispatched") return "Sonuç doğrulanıyor…";
    if ((current.recoveries || []).some((r) => r.startsWith("TARGET_NOT_READY") || r.startsWith("FRAME_CHANGED"))) return "Alan yeniden bulunuyor…";
    if (current.command && ["assert_screen", "follow_transition"].includes(current.command.op)) return "Ekran bekleniyor…";
    return "Çalışıyor…";
  }
  function render(run) {
    const p = $(".rl-run"); p.replaceChildren();
    const cls = { completed: "resolved", failed: "unresolved", outcome_unknown: "ambiguous" }[run.status] || (run.status.startsWith("paused") ? "ambiguous" : "");
    p.appendChild(el("span", run.outcome_label, `badge ${cls}`));
    const word = { completed: "Tamamlandı", cancelled: "Durduruldu", outcome_unknown: "Sonuç belirsiz", failed: "Tamamlanamadı" }[run.status];
    if (word) p.appendChild(el("span", ` · ${word}`, "as-status-word"));
    const ph = phase(run); if (ph) p.appendChild(el("span", ` · ${ph}`, "as-phase"));
    const sum = run.summary || {};
    if (sum.reason) {
      const why = el("div", null, "as-failure");
      if (sum.failed_stage) why.appendChild(el("p", `Aşama: ${sum.failed_stage}`));
      why.appendChild(el("p", `Neden: ${sum.reason}`));
      if (sum.next_step) why.appendChild(el("p", `Sonraki adım: ${sum.next_step}`));
      p.appendChild(why);
    }
    if (sum.correlation_id) p.appendChild(el("p", `Destek numarası: ${sum.correlation_id}`, "muted as-support"));
    const outputs = run.steps.filter((s) => s.result && s.result.value != null && s.command.op === "read").map((s) => s.result.value);
    if (outputs.length) p.appendChild(el("p", `Çıktı: ${outputs.join(", ")}`, "as-output"));
    const tech = el("details", null, "as-tech"); tech.appendChild(el("summary", "Teknik ayrıntılar"));
    tech.appendChild(el("p", `${run.status}${run.status_reason ? " (" + run.status_reason + ")" : ""} · yayın ${(run.binding || {}).release_id || "-"}`, "muted"));
    p.appendChild(tech);
    const t = $(".rl-steps"); t.replaceChildren();
    const h = t.insertRow(); ["#", "Komut", "Durum", "Hata", "Açıklama"].forEach((x) => h.appendChild(el("th", x)));
    run.steps.forEach((s) => { const tr = t.insertRow(); tr.dataset.state = s.state;
      [s.index + 1, s.command.op, STATE_TR[s.state] || s.state, s.error_class || "", s.message || ""].forEach((v) => tr.insertCell().textContent = v); });
  }
  async function poll() {
    const watching = runId;
    while (runId === watching && watching) {
      const run = await call("GET", `/api/runs/${watching}`).catch(() => null);
      if (runId !== watching) return; // yeni çalıştırma başladı; eski yanıt ekrana yazılmaz
      if (run) { render(run); if (!["created", "running", "cancel_requested"].includes(run.status)) { runActive = false; return; } }
      await new Promise((ok) => setTimeout(ok, 500));
    }
  }
  $("[data-action=run]").addEventListener("click", async () => {
    const sessionId = S.id();
    if (!needApp()) return;
    if (!choice) { errorBox.textContent = "Önce talebinizi yazıp yorumlayın veya hazır bir işlem seçin."; return; }
    if (choice.application_id !== appId) { errorBox.textContent = "Plan başka bir uygulamaya ait; talebi yeniden yorumlayın."; return; }
    if (!planReady) { errorBox.textContent = "Önce işlemin özetini gösterin; bilgiler değiştiyse özet yeniden gösterilmeli."; return; }
    if (!sessionId) { errorBox.textContent = "Bir tarayıcı oturumu seçin veya açın."; return; }
    // Önceki çalıştırmanın sonucu ve hatası yeni çalıştırmanın altında kalmaz.
    runId = null;
    $(".rl-run").replaceChildren(el("span", "Başlatılıyor…", "muted")); $(".rl-steps").replaceChildren();
    const ack = $("[name=ack]");
    const common = { session_id: sessionId, request_id: crypto.randomUUID(), acknowledge_effect: ack ? ack.checked : false };
    const run = choice.kind === "sequence"
      ? await call("POST", "/api/assistant/plan/execute", { application_id: choice.application_id, release_id: choice.release_id, steps: choice.steps, ...common }).catch(() => null)
      : await call("POST", "/api/assistant/execute", { ...choice, ...common }).catch(() => null);
    if (run) { runId = run.run_id; runActive = true; render(run); poll(); }
    else $(".rl-run").replaceChildren(el("span", "İşlem başlatılamadı; nedeni aşağıda.", "muted"));
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
    $("[data-action=comp-preview]").addEventListener("click", async () => {
      if (!needApp()) return;
      const r = await call("POST", "/api/assistant/composite/preview", { application_id: appId, plan: compPlan() }).catch(() => null);
      if (r) { compRelease = r.release_id; $(".as-comp").textContent = `${r.steps} adım · işlemler: ${Object.keys(r.operations).join(", ")} · yayın ${r.release_id}`; }
    });
    $("[data-action=comp-run]").addEventListener("click", async () => {
      const sessionId = S.id();
      if (!sessionId || !compRelease) { errorBox.textContent = "Önce birleşik planı görün ve bir oturum seçin."; return; }
      if (!needApp()) return;
      const run = await call("POST", "/api/assistant/composite/execute", { application_id: appId, plan: compPlan(), session_id: sessionId,
        release_id: compRelease, request_id: crypto.randomUUID() }).catch(() => null);
      if (run) { runId = run.run_id; runActive = true; render(run); poll(); }
    });
  }
  $("[data-action=cancel]").addEventListener("click", async () => { if (runId) { const r = await call("POST", `/api/runs/${runId}/cancel`).catch(() => null); if (r) render(r); } });
})();
