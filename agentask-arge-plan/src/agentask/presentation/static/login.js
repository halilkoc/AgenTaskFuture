"use strict";
(function () {
  const form = document.querySelector(".lg-form");
  const error = document.querySelector(".tl-error");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";
    const button = form.querySelector("button"); button.disabled = true;
    const password = form.password;
    try {
      const r = await fetch("/api/auth/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: form.username.value, password: password.value }) });
      if (r.ok) { location.assign(form.dataset.next || "/"); return; }
      const d = await r.json();
      error.textContent = d.safe_message || "Giriş yapılamadı.";
    } catch (_) { error.textContent = "Sunucuya ulaşılamadı."; }
    password.value = ""; button.disabled = false; password.focus();
  });
})();
