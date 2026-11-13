// Sayfalar arası tarayıcı oturumu seçimi. İstemcide saklanan kimlik yalnız öneridir; yetki ve durum her yüklemede
// ve her işlemde backend'de doğrulanır. Seçim oturumun adresini/içeriğini değiştirmez; sessizce oturum açılmaz.
"use strict";
window.AgenTaskSession = (function () {
  const KEY = "agentask.session";
  const panel = document.querySelector(".sp-panel");
  const $ = (s) => panel.querySelector(s);
  const el = (t, x, c) => { const e = document.createElement(t); if (x != null) e.textContent = x; if (c) e.className = c; return e; };
  let current = null, quota = null;
  const listeners = [];

  async function call(method, path) {
    const r = await fetch(path, { method, credentials: "same-origin" });
    if (r.status === 204) return null;
    const d = await r.json();
    if (!r.ok) throw Object.assign(new Error(d.code), { body: d, status: r.status });
    return d;
  }
  const short = (id) => id.slice(0, 8);
  const stateText = (s) => !s.alive ? "kapanmış" : s.busy_operation ? `meşgul (${s.busy_operation})` : "hazır";
  function note(text) { $(".sp-note").textContent = text || ""; }
  function emit() { listeners.forEach((cb) => cb(current)); }

  function select(s) {
    current = s;
    if (s) localStorage.setItem(KEY, s.session_id); else localStorage.removeItem(KEY);
    render([]); emit();
  }
  function render(sessions) {
    $(".sp-current").textContent = current
      ? `Seçili oturum: ${short(current.session_id)} · ${current.current_url || "-"} · durum: ${stateText(current)}`
      : "Seçili oturum yok.";
    if (quota) $(".sp-quota").textContent = `Etkileşimli oturum: ${quota.interactive_used}/${quota.interactive_limit}` +
      (quota.verification_in_use ? ` · süren doğrulama oturumu: ${quota.verification_in_use}` : "");
    const full = quota && quota.interactive_used >= quota.interactive_limit;
    $("[data-sp=new]").disabled = Boolean(full);
    $("[data-sp=new]").title = full ? "Kota dolu: mevcut oturumu kullanın veya kapatın." : "";
    if (!sessions.length && current) return;
    const list = $(".sp-list"); list.replaceChildren();
    sessions.forEach((s) => {
      const li = el("li", `${short(s.session_id)} · ${s.current_url || "-"} · ${stateText(s)} `);
      li.dataset.sessionId = s.session_id;
      const use = el("button", current && current.session_id === s.session_id ? "Seçili" : "Bu oturumu kullan");
      use.type = "button"; use.disabled = !s.alive || (current && current.session_id === s.session_id);
      use.addEventListener("click", async () => { note(""); await refresh(s.session_id); });
      const close = el("button", "Kapat"); close.type = "button"; close.disabled = Boolean(s.busy_operation);
      close.addEventListener("click", async () => {
        if (!window.confirm("Bu tarayıcı oturumu kapatılsın mı? Açık sayfadaki işler kaybolur.")) return;
        try { await call("DELETE", `/api/sessions/${s.session_id}`); if (current && current.session_id === s.session_id) select(null); note("Oturum kapatıldı."); }
        catch (e) { note(e.body ? e.body.safe_message : "Kapatılamadı."); }
        await refresh();
      });
      li.appendChild(use); li.appendChild(close); list.appendChild(li);
    });
    if (full && !current && !$(".sp-note").textContent) {
      note("Etkileşimli oturum kotası dolu. Listeden mevcut oturumu seçin veya kapatıp yenisini açın.");
    }
  }

  async function refresh(chooseId) {
    let ov;
    try { ov = await call("GET", "/api/sessions/overview"); } catch (e) { note("Oturum bilgisi alınamadı."); return; }
    quota = ov.quota;
    const sessions = ov.sessions;
    if (chooseId) {
      try { select(await call("GET", `/api/sessions/${chooseId}`)); }
      catch (e) { note("Bu oturum artık geçerli değil."); select(null); }
    } else if (current) {
      const still = sessions.find((s) => s.session_id === current.session_id);
      if (!still) { note("Seçili oturum kapanmış veya geçersiz; yeniden seçin."); current = null; localStorage.removeItem(KEY); emit(); }
      else current = still;
    } else {
      const stored = localStorage.getItem(KEY);
      if (stored) {
        if (sessions.some((s) => s.session_id === stored)) note("Önceki oturumunuz bulundu; kullanmak için listeden seçin.");
        else { localStorage.removeItem(KEY); note("Kayıtlı oturum artık geçerli değil."); }
      }
    }
    render(sessions);
  }

  $("[data-sp=new]").addEventListener("click", async () => {
    note("");
    try { select(await call("POST", "/api/sessions")); }
    catch (e) {
      const d = e.body || {};
      note(e.status === 429 ? `Oturum açılamadı: ${d.safe_message} (${(d.details && d.details.interactive_used) || "?"}/${(d.details && d.details.interactive_limit) || "?"}). Mevcut oturumu kullanın veya kapatın.` : (d.safe_message || "Oturum açılamadı."));
    }
    await refresh();
  });
  $("[data-sp=refresh]").addEventListener("click", () => refresh());
  refresh();

  return {
    id: () => (current ? current.session_id : null),
    require() {
      if (!current) { note("Önce bir tarayıcı oturumu seçin veya açın."); throw new Error("no_session"); }
      return current.session_id;
    },
    onChange: (cb) => listeners.push(cb),
    refresh: () => refresh(),
  };
})();
