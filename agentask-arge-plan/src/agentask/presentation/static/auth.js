// Geçici admin girişi: durum değiştiren isteklere CSRF belirteci ekler, oturum düşünce giriş ekranına yönlendirir.
"use strict";
(function () {
  const meta = document.querySelector('meta[name="agentask-csrf"]');
  if (!meta || !meta.content) return;
  const token = meta.content;
  const original = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    const options = { ...(init || {}) };
    if (!["GET", "HEAD", "OPTIONS"].includes((options.method || "GET").toUpperCase())) {
      const headers = new Headers(options.headers || {});
      headers.set("X-CSRF-Token", token);
      options.headers = headers;
    }
    const response = await original(input, options);
    if (response.status === 401) location.assign(`/login?next=${encodeURIComponent(location.pathname)}`);
    return response;
  };
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-logout]").forEach((button) => button.addEventListener("click", async () => {
      await window.fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
      location.assign("/login");
    }));
  });
})();
