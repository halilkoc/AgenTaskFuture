// Ortak istemci yardımcıları. Secret veya backend ayarı içermez; yalnızca /api/config/public okunur.
"use strict";
window.AgenTask = {
  async getJson(path) {
    const response = await fetch(path, { credentials: "same-origin", headers: { Accept: "application/json" } });
    const body = await response.json();
    if (!response.ok) { throw Object.assign(new Error(body.safe_message || "İstek başarısız."), { body }); }
    return body;
  },
};
