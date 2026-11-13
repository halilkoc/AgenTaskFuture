// Deney: çok ekranlı başvuru sihirbazı. "Devam" SPA geçişi (tam sayfa gezinmesi yok; içerik ve iframe yeniden
// oluşur, adres pushState ile değişir). "Gönder" kayıt oluşturur ve özet ekranına gezinir.
"use strict";
(function () {
  const main = document.querySelector("main");
  async function post(path, body) {
    return fetch(path, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}) });
  }
  function bind() {
    const wizard = document.querySelector(".wizard"); if (!wizard) return;
    const caseId = wizard.dataset.caseId;
    const next = wizard.querySelector(".wz-next");
    if (next) next.addEventListener("click", async () => {
      const r = await post(`/lab-api/wizard/${caseId}/advance`);
      const data = await r.json();
      if (!data.html) return;
      main.innerHTML = data.html;
      history.pushState({}, "", data.url);
      bind();
    });
    wizard.querySelectorAll(".wz-submit").forEach((button) => button.addEventListener("click", async () => {
      const status = wizard.querySelector(".wz-status");
      const section = button.closest("section");
      const frame = section.querySelector("iframe");
      const doc = frame && frame.contentDocument ? frame.contentDocument.querySelector(".wz-document") : null;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), Number(wizard.dataset.timeoutMs || 2000));
      status.textContent = "Gönderiliyor…";
      try {
        const r = await fetch(`/lab-api/wizard/${caseId}/submit`, { method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json" }, signal: controller.signal,
          body: JSON.stringify({ customer_no: sessionStorage.getItem("wz-customer") || "-",
            amount: section.querySelector(".wz-amount").value || "-", document_no: doc ? doc.value || "-" : "-" }) });
        clearTimeout(timer);
        if (!r.ok) { status.textContent = "Yanıt alınamadı — işlem sonucu bilinmiyor"; return; }
        const data = await r.json();
        location.assign(`/wizard/${caseId}/summary?no=${data.application_no}`);
      } catch (e) {
        status.textContent = "Yanıt alınamadı — işlem sonucu bilinmiyor";
      }
    }));
    const customer = wizard.querySelector(".wz-customer");
    if (customer) customer.addEventListener("input", () => sessionStorage.setItem("wz-customer", customer.value));
  }
  bind();
})();
