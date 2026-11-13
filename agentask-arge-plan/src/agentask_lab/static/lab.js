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

// Seçim senaryoları: kimlikler her yüklemede değişir; değerler (data-value) anlamlıdır.
(function selectionScenarios() {
  document.querySelectorAll(".xcombo").forEach((combo) => {
    const items = JSON.parse(combo.dataset.options || "[]");
    const delay = Number(combo.dataset.delayMs || 0);
    let list = null;
    const close = () => { if (list) { list.remove(); list = null; } combo.setAttribute("aria-expanded", "false"); combo.removeAttribute("aria-controls"); };
    function draw() {
      list.replaceChildren(...items.map((it) => {
        const li = document.createElement("li");
        li.setAttribute("role", "option"); li.id = randomId(); li.textContent = it.l; li.dataset.value = it.v;
        if (it.d) li.setAttribute("aria-disabled", "true");
        li.addEventListener("click", (e) => {
          e.stopPropagation();
          if (it.d) return;
          combo.querySelector(".xcombo-value").textContent = it.l;
          combo.dataset.value = combo.dataset.trap === "1" ? "YANLIS" : it.v;
          close();
        });
        return li;
      }));
      list.removeAttribute("aria-busy");
    }
    function open() {
      combo.setAttribute("aria-expanded", "true");
      list = document.createElement("ul");
      list.setAttribute("role", "listbox"); list.id = randomId(); list.className = "combo-list"; list.setAttribute("aria-busy", "true");
      combo.setAttribute("aria-controls", list.id); combo.after(list);
      const mine = list;
      setTimeout(() => {
        if (list !== mine) return;
        draw();
        if (combo.dataset.redraw === "1") setTimeout(() => { if (list === mine) draw(); }, 100);
      }, delay);
    }
    combo.addEventListener("click", () => (list ? close() : open()));
    document.addEventListener("click", (e) => { if (list && !combo.contains(e.target) && !list.contains(e.target)) close(); });
  });
  document.querySelectorAll(".xlist").forEach((box) => box.querySelectorAll("[role=option]").forEach((o) => o.addEventListener("click", () => {
    box.querySelectorAll("[role=option]").forEach((x) => x.setAttribute("aria-selected", x === o ? "true" : "false"));
  })));
  document.querySelectorAll(".xbroken").forEach((c) => c.addEventListener("click", () => c.setAttribute("aria-expanded", c.getAttribute("aria-expanded") === "true" ? "false" : "true")));
  document.querySelectorAll("select.xlate").forEach((sel) => setTimeout(() => {
    sel.dataset.items.split("|").forEach((t) => { const o = document.createElement("option"); o.value = t.toLowerCase(); o.textContent = t; sel.appendChild(o); });
  }, Number(sel.dataset.delayMs || 0)));
  document.querySelectorAll("select.xcommit").forEach((sel) => {
    let current = sel.value;
    const status = sel.closest("section").querySelector(".xstatus");
    sel.addEventListener("change", async () => {
      const chosen = sel.value; const label = sel.options[sel.selectedIndex].text; const before = current;
      await fetch("/lab-api/selection", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value: chosen }) });
      const outcome = sel.dataset.outcome;
      if (outcome === "ok") { current = chosen; status.textContent = `Öncelik güncellendi: ${label}`; }
      else if (outcome === "reject") { current = chosen; status.textContent = "Öncelik kaydedilemedi"; }
      else if (outcome === "revert") { setTimeout(() => { sel.value = before; }, 80); }
      else { sel.value = before; setTimeout(() => { sel.value = chosen; current = chosen; }, 1500); }
    });
  });
})();

// Seçimle ekran geçişi: değer seçilince sayfa değişir.
document.querySelectorAll("select.xnavselect").forEach((sel) => sel.addEventListener("change", () => {
  if (sel.value) setTimeout(() => location.assign(sel.dataset.target), 150);
}));

// Kontrol sayfası: tıklama sayacı, kendini geri alan kutu, ARIA kutu/radyo ve gecikmeli öneri alanı.
document.querySelectorAll(".xcount").forEach((el) => el.addEventListener("click", () => {
  el.dataset.clicks = String(Number(el.dataset.clicks || 0) + 1);
  if (el.dataset.revert) setTimeout(() => { el.checked = false; }, 50);
}));
document.querySelectorAll(".xaria").forEach((el) => el.addEventListener("click", () => {
  el.setAttribute("aria-checked", el.getAttribute("aria-checked") === "true" ? "false" : "true");
}));
document.querySelectorAll(".xradio").forEach((el) => el.addEventListener("click", () => {
  el.parentElement.querySelectorAll(".xradio").forEach((r) => r.setAttribute("aria-checked", r === el ? "true" : "false"));
}));
document.querySelectorAll("input.xauto").forEach((input) => {
  const list = document.getElementById(input.getAttribute("aria-controls"));
  const items = JSON.parse(input.dataset.items);
  let timer = null, redraw = null;
  const paint = (found) => {
    list.replaceChildren(...found.map((x) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option"); li.dataset.value = x.v; li.textContent = x.l;
      li.addEventListener("click", () => {
        input.value = x.l; input.setAttribute("data-value", x.set || x.v);
        list.hidden = true; input.setAttribute("aria-expanded", "false");
      });
      return li;
    }));
    list.hidden = !found.length;
    input.setAttribute("aria-expanded", found.length ? "true" : "false");
  };
  input.addEventListener("input", () => {
    clearTimeout(timer); clearTimeout(redraw);
    input.removeAttribute("data-value");
    paint([]);
    window.__autoSearches = (window.__autoSearches || 0) + 1;
    const q = input.value.toLocaleLowerCase("tr");
    if (!q) return;
    timer = setTimeout(() => {
      const found = items.filter((x) => x.l.toLocaleLowerCase("tr").includes(q));
      paint(found);
      redraw = setTimeout(() => paint(found), 250); // liste bir kez yeniden çizilir
    }, 800);
  });
});

// Çoklu seçim, tarih çeviren alan ve dosya yükleme.
document.querySelectorAll("select.xmulti").forEach((el) => el.addEventListener("change", () => {
  el.dataset.changes = String(Number(el.dataset.changes || 0) + 1);
}));
document.querySelectorAll(".xarialist [role=option]").forEach((o) => o.addEventListener("click", () => {
  o.setAttribute("aria-selected", o.getAttribute("aria-selected") === "true" ? "false" : "true");
  o.parentElement.dataset.clicks = String(Number(o.parentElement.dataset.clicks || 0) + 1);
}));
document.querySelectorAll("input.xshift").forEach((el) => el.addEventListener("input", () => {
  setTimeout(() => { el.value = "01.01.2000"; }, 30);
}));
document.querySelectorAll("input.xfile").forEach((el) => el.addEventListener("change", () => {
  el.dataset.uploads = String(Number(el.dataset.uploads || 0) + 1);
  const f = el.files[0];
  el.dataset.received = f ? `${f.name}|${f.type}|${f.size}` : "";
  setTimeout(() => { el.closest("section").querySelector(".xstatus").textContent = "Belge alındı"; }, 150);
}));
