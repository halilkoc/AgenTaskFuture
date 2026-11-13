// Deney uygulaması davranışları. Gerçek Pega kodu değildir.
"use strict";

function randomId() {
  return "pz" + Math.random().toString(16).slice(2, 10);
}

// Sonradan oluşan frame
(function lateFrame() {
  const slot = document.getElementById("late-frame-slot");
  if (!slot) return;
  setTimeout(() => {
    const frame = document.createElement("iframe");
    frame.title = "Ek Belgeler";
    frame.src = "/frames/late";
    frame.width = "600";
    frame.height = "120";
    slot.appendChild(frame);
  }, Number(slot.dataset.delayMs || 0));
})();

// Özel combobox: seçenekler yalnızca açılınca ve gecikmeyle oluşur
(function combobox() {
  document.querySelectorAll("[role=combobox].combo").forEach((combo) => {
    const options = (combo.dataset.options || "").split("|").filter(Boolean);
    const hidden = combo.parentElement.querySelector(".combo-hidden");
    let listbox = null;

    function close() {
      if (listbox) { listbox.remove(); listbox = null; }
      combo.setAttribute("aria-expanded", "false");
      combo.removeAttribute("aria-controls");
    }

    function open() {
      if (listbox) return;
      combo.setAttribute("aria-expanded", "true");
      setTimeout(() => {
        if (combo.getAttribute("aria-expanded") !== "true" || listbox) return;
        listbox = document.createElement("ul");
        listbox.setAttribute("role", "listbox");
        listbox.id = randomId();
        listbox.className = "combo-list";
        options.forEach((label) => {
          const li = document.createElement("li");
          li.setAttribute("role", "option");
          li.id = randomId();
          li.textContent = label;
          li.addEventListener("click", (event) => {
            event.stopPropagation();
            combo.querySelector(".combo-value").textContent = label;
            if (hidden) hidden.value = label;
            close();
          });
          listbox.appendChild(li);
        });
        combo.setAttribute("aria-controls", listbox.id);
        combo.after(listbox);
      }, Number(combo.dataset.delayMs || 0));
    }

    combo.addEventListener("click", () => (listbox ? close() : open()));
    combo.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); listbox ? close() : open(); }
      if (event.key === "Escape") close();
    });
    document.addEventListener("click", (event) => {
      if (listbox && !combo.contains(event.target) && !listbox.contains(event.target)) close();
    });
  });
})();

// Kaydırdıkça yüklenen tablo
(function scrollTable() {
  const region = document.querySelector(".scroll[data-batch]");
  if (!region) return;
  const tbody = region.querySelector("tbody");
  const status = region.querySelector(".scroll-status");
  const batch = Number(region.dataset.batch);
  let offset = 0, loading = false, done = false;

  async function loadMore() {
    if (loading || done) return;
    loading = true;
    status.textContent = "Yükleniyor…";
    try {
      const response = await fetch(`/lab-api/rows?offset=${offset}&limit=${batch}`, { credentials: "same-origin" });
      if (!response.ok) { status.textContent = "Kayıtlar yüklenemedi."; return; }
      const body = await response.json();
      body.rows.forEach((row) => {
        const tr = document.createElement("tr");
        tr.id = randomId();
        [row.key, row.customer, row.status].forEach((v) => {
          const td = document.createElement("td"); td.textContent = v; tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      offset += body.rows.length;
      done = body.done;
      status.textContent = done ? "Tüm kayıtlar yüklendi" : "";
    } finally {
      loading = false;
    }
  }

  region.addEventListener("scroll", () => {
    if (region.scrollTop + region.clientHeight >= region.scrollHeight - 20) loadMore();
  });
  loadMore();
})();

// Gecikmeli içerik
(function delayedReveal() {
  const loading = document.querySelector(".loading[data-reveal-delay-ms]");
  if (!loading) return;
  setTimeout(() => {
    const template = document.getElementById("delayed-content");
    document.querySelector(".delayed-target").appendChild(template.content.cloneNode(true));
    loading.remove();
  }, Number(loading.dataset.revealDelayMs));
})();

// Not formu: uyarı penceresi ve yanıt kaybı
(function noteForm() {
  const form = document.querySelector("form.note-form");
  if (!form) return;
  const status = form.querySelector(".note-status");
  const textarea = form.querySelector("textarea");
  const timeoutMs = Number(form.dataset.timeoutMs);

  if (form.dataset.dialog === "native") {
    setTimeout(() => window.alert("Bu vaka başka bir kullanıcı tarafından güncellendi."), 0);
  }
  document.querySelectorAll(".modal-close").forEach((button) =>
    button.addEventListener("click", () => button.closest(".overlay").remove())
  );

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    status.textContent = "Kaydediliyor…";
    try {
      const response = await fetch(`/lab-api/cases/${form.dataset.caseId}/notes`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: textarea.value, client_request_id: crypto.randomUUID() }),
        signal: controller.signal,
      });
      if (response.status === 401) { status.textContent = "Oturumunuz sona erdi."; return; }
      if (!response.ok) { status.textContent = "Kayıt başarısız."; return; }
      const body = await response.json();
      status.textContent = `Kaydedildi (Not #${body.note_no})`;
      textarea.value = "";
    } catch (error) {
      status.textContent = "Yanıt alınamadı — işlem sonucu bilinmiyor";
    } finally {
      clearTimeout(timer);
    }
  });
})();

// Kontrol paneli
(function controlPanel() {
  const form = document.querySelector("form.control-form");
  if (!form) return;
  const output = document.querySelector(".control-output");
  async function send(method, path, body) {
    const response = await fetch(path, {
      method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
    });
    output.textContent = JSON.stringify(await response.json(), null, 2);
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const body = {};
    form.querySelectorAll("input, select").forEach((el) => {
      if (el.type === "checkbox") body[el.name] = el.checked;
      else if (el.type === "number") body[el.name] = Number(el.value);
      else body[el.name] = el.value;
    });
    send("PUT", "/__lab/scenario", body);
  });
  document.querySelectorAll("button[data-action]").forEach((button) =>
    button.addEventListener("click", () => send("POST", button.dataset.action))
  );
})();

// Sekmeler (aria-selected + panel görünürlüğü)
(function tabs() {
  document.querySelectorAll("[role=tablist]").forEach((list) => {
    const tabs = Array.from(list.querySelectorAll("[role=tab]"));
    tabs.forEach((tab) => tab.addEventListener("click", () => {
      tabs.forEach((t) => {
        const active = t === tab;
        t.setAttribute("aria-selected", active ? "true" : "false");
        const panel = document.getElementById(t.getAttribute("aria-controls"));
        if (panel) panel.hidden = !active;
      });
    }));
  });
})();

// Taraf bölümü kaydetme (yalnız istemci tarafı; sunucuya yazmaz)
(function partySave() {
  document.querySelectorAll("button.party-save").forEach((button) => button.addEventListener("click", () => {
    const section = button.closest("section");
    const status = section.querySelector(".party-status");
    const name = section.querySelectorAll("input")[1].value.trim();
    status.textContent = name ? `Bilgiler kaydedildi: ${name}` : "Ad Soyad zorunludur";
  }));
})();
