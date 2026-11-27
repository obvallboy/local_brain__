"use strict";

// ---- small helpers -------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else n.setAttribute(k, v);
  }
  for (const kid of kids) n.append(kid?.nodeType ? kid : document.createTextNode(kid ?? ""));
  return n;
};
async function api(path, opts) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}
const fmtBytes = (n) => {
  if (n == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0; n = Number(n);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
};

// ---- state ---------------------------------------------------------------
let snapshot = null;
let notes = {};
let selected = null;          // {kind, dev, key, label}
let consoleSession = null;    // {id, since, timer}

// ---- device inventory ----------------------------------------------------
async function loadDevices() {
  $("#device-list").innerHTML = '<p class="muted">Scanning…</p>';
  try {
    [snapshot, notes] = await Promise.all([api("/api/devices"), api("/api/notes")]);
  } catch (e) {
    $("#device-list").innerHTML = `<p class="err">${e.message}</p>`;
    return;
  }
  renderCaps(snapshot.capabilities);
  renderList();
}

function renderCaps(caps) {
  const on = [];
  if (caps.pyserial) on.push("pyserial");
  if (caps.pyusb) on.push("pyusb");
  if (caps.psutil) on.push("psutil");
  if (caps.sysfs) on.push("sysfs");
  if (caps.lsusb) on.push("lsusb");
  $("#caps").textContent = `${caps.platform} · ${on.join(" ") || "builtin only"}`;
}

function labelFor(key, fallback) {
  const n = notes[key];
  return (n && n.label) || fallback;
}

function renderList() {
  const filter = $("#filter").value.trim().toLowerCase();
  const list = $("#device-list");
  list.innerHTML = "";

  const groups = [
    ["Serial ports", "serial", snapshot.serial, serialDevNode],
    ["USB devices", "usb", snapshot.usb, usbDevNode],
    ["Storage", "storage", snapshot.storage, storageDevNode],
    ["Network", "network", snapshot.network, networkDevNode],
  ];

  let shown = 0;
  for (const [title, kind, items, renderer] of groups) {
    const matched = (items || []).filter((d) =>
      JSON.stringify(d).toLowerCase().includes(filter)
    );
    if (!matched.length) continue;
    list.append(el("div", { class: "group-title" }, title,
      el("span", { class: "count" }, ` (${matched.length})`)));
    for (const d of matched) {
      const node = renderer(d);
      node.addEventListener("click", () => select(kind, d));
      if (selected && selected.kind === kind && selected.key === keyOf(kind, d))
        node.classList.add("active");
      list.append(node);
      shown++;
    }
  }
  if (!shown) list.innerHTML = '<p class="muted">No devices match. Plug something in and Refresh.</p>';
}

function keyOf(kind, d) {
  if (kind === "serial") return d.key || "serial:" + d.device;
  if (kind === "usb") return d.key || `usb:${d.vid}:${d.pid}`;
  if (kind === "storage") return "storage:" + d.device;
  if (kind === "network") return "net:" + d.name;
  return kind + ":?";
}

function serialDevNode(d) {
  const key = keyOf("serial", d);
  return el("div", { class: "device" },
    el("div", { class: "d-name" }, labelFor(key, d.device),
      el("span", { class: "d-badge" }, "serial")),
    el("div", { class: "d-meta" },
      [d.description, d.manufacturer, (d.vid ? `${d.vid}:${d.pid}` : "")]
        .filter((v) => v && v.toLowerCase() !== "n/a").join(" · ") || d.device));  // pyserial says "n/a" for unnamed ports
}
function usbDevNode(d) {
  const key = keyOf("usb", d);
  const name = d.product || d.manufacturer || `${d.vid}:${d.pid}`;
  return el("div", { class: "device" },
    el("div", { class: "d-name" }, labelFor(key, name),
      el("span", { class: "d-badge" }, d.device_class_name || "usb")),
    el("div", { class: "d-meta" },
      `${d.vid}:${d.pid}` + (d.serial_number ? ` · sn ${d.serial_number}` : "")));
}
function storageDevNode(d) {
  return el("div", { class: "device" },
    el("div", { class: "d-name" }, d.device,
      el("span", { class: "d-badge" }, d.fstype || "disk")),
    el("div", { class: "d-meta" },
      [d.mountpoint, d.usage ? fmtBytes(d.usage.total) : null].filter(Boolean).join(" · ")));
}
function networkDevNode(d) {
  return el("div", { class: "device" },
    el("div", { class: "d-name" }, d.name,
      el("span", { class: "d-badge " + (d.is_up ? "ok" : "") }, d.is_up ? "up" : "down")),
    el("div", { class: "d-meta" },
      (d.addresses || []).map((a) => a.address).filter(Boolean).slice(0, 2).join(" · ") || d.mac || ""));
}

// ---- selection + detail --------------------------------------------------
function select(kind, d) {
  selected = { kind, dev: d, key: keyOf(kind, d) };
  stopConsolePolling();
  renderList();
  $("#detail-empty").classList.add("hidden");
  $("#detail-view").classList.remove("hidden");

  const title =
    kind === "serial" ? d.device :
    kind === "usb" ? (d.product || d.manufacturer || `${d.vid}:${d.pid}`) :
    kind === "storage" ? d.device : d.name;
  $("#detail-title").textContent = labelFor(selected.key, title);
  $("#detail-sub").textContent = selected.key;

  // Console tab only for serial ports.
  $("#tab-console").classList.toggle("hidden", kind !== "serial");

  renderInfo(kind, d);
  loadNotesInto(selected.key);
  resetConsole(kind === "serial" ? d.device : null);
  switchTab("info");
}

function kvRows(obj) {
  const t = $("#info-table");
  t.innerHTML = "";
  for (const [k, v] of obj) {
    if (v === null || v === undefined || v === "") continue;
    t.append(el("tr", {}, el("td", { class: "k" }, k), el("td", { class: "v" }, String(v))));
  }
}

async function renderInfo(kind, d) {
  $("#info-extra").innerHTML = "";
  if (kind === "serial") {
    kvRows([
      ["device", d.device], ["description", d.description], ["manufacturer", d.manufacturer],
      ["product", d.product], ["serial number", d.serial_number],
      ["vid:pid", d.vid ? `${d.vid}:${d.pid}` : null], ["hwid", d.hwid], ["source", d.source],
    ]);
  } else if (kind === "usb") {
    kvRows([
      ["vid:pid", `${d.vid}:${d.pid}`], ["product", d.product], ["manufacturer", d.manufacturer],
      ["serial number", d.serial_number], ["class", d.device_class_name],
      ["bus:addr", `${d.bus ?? "?"}:${d.address ?? "?"}`], ["usb version", d.usb_version],
      ["speed", d.speed], ["source", d.source],
    ]);
    if (d.sysfs_path) await loadUsbDetail(d);
  } else if (kind === "storage") {
    kvRows([
      ["device", d.device], ["mountpoint", d.mountpoint], ["fstype", d.fstype],
      ["model", d.model], ["removable", d.removable], ["options", d.opts],
      ["total", d.usage ? fmtBytes(d.usage.total) : null],
      ["free", d.usage && d.usage.free != null ? fmtBytes(d.usage.free) : null],
      ["used %", d.usage && d.usage.percent != null ? d.usage.percent + "%" : null],
    ]);
  } else if (kind === "network") {
    kvRows([
      ["interface", d.name], ["state", d.is_up ? "up" : "down"], ["mac", d.mac],
      ["speed", d.speed_mbps ? d.speed_mbps + " Mbps" : null], ["mtu", d.mtu],
    ]);
    if (d.addresses && d.addresses.length) {
      const box = el("div", {}, el("h3", {}, "Addresses"));
      for (const a of d.addresses)
        box.append(el("div", { class: "iface" }, `${a.address || ""}  ${a.netmask ? "/ " + a.netmask : ""}`));
      $("#info-extra").append(box);
    }
  }
}

async function loadUsbDetail(d) {
  const extra = $("#info-extra");
  extra.append(el("p", { class: "muted" }, "Loading kernel details…"));
  let detail;
  try {
    const q = new URLSearchParams({ sysfs_path: d.sysfs_path, vid: d.vid, pid: d.pid });
    detail = await api("/api/usb/detail?" + q.toString());
  } catch (e) {
    extra.innerHTML = `<p class="err">${e.message}</p>`;
    return;
  }
  extra.innerHTML = "";
  if (detail.driver) extra.append(el("h3", {}, "Driver"), el("div", { class: "iface" }, detail.driver));
  if (detail.interfaces && detail.interfaces.length) {
    extra.append(el("h3", {}, "Interfaces"));
    for (const i of detail.interfaces) {
      extra.append(el("div", { class: "iface" },
        `#${i.bInterfaceNumber ?? "?"}  class ${i.bInterfaceClass ?? "?"}` +
        `  endpoints ${i.bNumEndpoints ?? "?"}  driver ${i.driver || "—"}`));
    }
  }
  renderDmesg(extra, detail.dmesg);
}

function renderDmesg(container, dmesg) {
  container.append(el("h3", {}, "Kernel log (dmesg)"));
  if (!dmesg || !dmesg.available) {
    container.append(el("p", { class: "muted" }, (dmesg && dmesg.error) || "unavailable"));
    return;
  }
  if (!dmesg.lines.length) {
    container.append(el("p", { class: "muted" }, "no matching lines"));
    return;
  }
  container.append(el("div", { class: "dmesg" }, dmesg.lines.join("\n")));
}

// ---- tabs ----------------------------------------------------------------
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $("#tab-info").classList.toggle("hidden", name !== "info");
  $("#tab-notes-body").classList.toggle("hidden", name !== "notes");
  $("#tab-console-body").classList.toggle("hidden", name !== "console");
}
document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => switchTab(t.dataset.tab)));

// ---- notes ---------------------------------------------------------------
function loadNotesInto(key) {
  const n = notes[key] || {};
  $("#note-label").value = n.label || "";
  $("#note-text").value = n.note || "";
  $("#note-status").textContent = n.updated ? "last saved " + n.updated : "";
}
$("#note-save").addEventListener("click", async () => {
  if (!selected) return;
  const body = { key: selected.key, label: $("#note-label").value, note: $("#note-text").value };
  $("#note-status").textContent = "saving…";
  try {
    const saved = await api("/api/notes", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    notes[selected.key] = saved;
    $("#note-status").textContent = "saved ✓";
    $("#detail-title").textContent = labelFor(selected.key, $("#detail-title").textContent);
    renderList();
  } catch (e) {
    $("#note-status").innerHTML = `<span class="err">${e.message}</span>`;
  }
});

// ---- serial console ------------------------------------------------------
function resetConsole(port) {
  stopConsolePolling();
  consoleSession = null;
  $("#console-out").textContent = "";
  $("#console-status").textContent = port ? "closed" : "n/a";
  $("#console-status").className = "muted";
  $("#console-open").disabled = !port;
  $("#console-close").disabled = true;
  $("#console-input").disabled = true;
  $("#console-send-btn").disabled = true;
  $("#console-open").dataset.port = port || "";
}

function appendConsole(text) {
  const out = $("#console-out");
  out.append(document.createTextNode(text));
  if ($("#autoscroll").checked) out.scrollTop = out.scrollHeight;
}

$("#console-open").addEventListener("click", async () => {
  const port = $("#console-open").dataset.port;
  if (!port) return;
  const baud = parseInt($("#baud").value, 10);
  $("#console-status").textContent = "opening…";
  try {
    const info = await api("/api/serial/open", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ port, baud }),
    });
    consoleSession = { id: info.id, since: 0 };
    $("#console-status").textContent = `open · ${baud} baud`;
    $("#console-status").className = "ok";
    $("#console-open").disabled = true;
    $("#console-close").disabled = false;
    $("#console-input").disabled = false;
    $("#console-send-btn").disabled = false;
    $("#console-input").focus();
    startConsolePolling();
  } catch (e) {
    $("#console-status").innerHTML = `<span class="err">${e.message}</span>`;
  }
});

$("#console-close").addEventListener("click", async () => {
  if (consoleSession) {
    try { await api(`/api/serial/${consoleSession.id}/close`, { method: "POST" }); } catch (_) {}
  }
  resetConsole($("#console-open").dataset.port);
});

$("#console-clear").addEventListener("click", () => { $("#console-out").textContent = ""; });

$("#console-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!consoleSession) return;
  const input = $("#console-input");
  const data = input.value;
  if (!data) return;
  try {
    await api(`/api/serial/${consoleSession.id}/write`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data, hex: $("#send-hex").checked, line_ending: $("#line-ending").value,
      }),
    });
    appendConsole(`‹ ${data}\n`);
    input.value = "";
  } catch (e) {
    appendConsole(`[send error: ${e.message}]\n`);
  }
});

function startConsolePolling() {
  stopConsolePolling();
  consoleSession.timer = setInterval(pollConsole, 350);
  pollConsole();
}
function stopConsolePolling() {
  if (consoleSession && consoleSession.timer) clearInterval(consoleSession.timer);
}
async function pollConsole() {
  if (!consoleSession) return;
  let res;
  try {
    res = await api(`/api/serial/${consoleSession.id}/read?since=${consoleSession.since}`);
  } catch (e) {
    appendConsole(`[read error: ${e.message}]\n`);
    stopConsolePolling();
    return;
  }
  for (const c of res.chunks) appendConsole(c.text);
  if (res.chunks.length) consoleSession.since = res.last_seq;
  if (res.closed) {
    appendConsole(`\n[session closed${res.error ? ": " + res.error : ""}]\n`);
    stopConsolePolling();
    $("#console-status").innerHTML = `<span class="err">closed${res.error ? ": " + res.error : ""}</span>`;
    $("#console-close").disabled = true;
    $("#console-input").disabled = true;
    $("#console-send-btn").disabled = true;
    $("#console-open").disabled = false;
  }
}

// ---- wire up -------------------------------------------------------------
$("#refresh").addEventListener("click", loadDevices);
$("#filter").addEventListener("input", renderList);
window.addEventListener("beforeunload", () => {
  if (consoleSession) navigator.sendBeacon?.(`/api/serial/${consoleSession.id}/close`);
});
loadDevices();

// ---- Brain (File Cabinet AI) -------------------------------------------------
const LABEL_CLASS = {
  "I know": "lb-know", "Filed": "lb-filed", "I think": "lb-think", "I checked": "lb-checked",
  "I remember": "lb-remember", "From my core": "lb-core",
  "I don't remember": "lb-unsure", "I'm not sure": "lb-unsure", "Command": "lb-cmd", "Removed": "lb-removed",
};
let brainStatusTimer = null;

function brainOpen(open) {
  $("#brain").classList.toggle("hidden", !open);
  if (open) { refreshBrainStatus(); $("#brain-input").focus(); }
}
$("#brain-toggle").addEventListener("click", () => brainOpen($("#brain").classList.contains("hidden")));
$("#brain-close").addEventListener("click", () => brainOpen(false));

async function refreshBrainStatus() {
  clearTimeout(brainStatusTimer);
  try {
    const s = await api("/api/brain/status");
    const parts = !s.ready
      ? [s.loading ? "loading models…" : "starting…"]
      : [s.model ? `model: ${s.model}` : "drawers and rules only (no model)",
         s.embed ? "meaning-matching on" : null, s.gpu_layers ? "GPU" : null];
    $("#brain-status").textContent = parts.filter(Boolean).join(" · ");
    $("#brain-status").title = [...(s.notes || []), `memory: ${s.memory_file}`].join("\n");
    if (!s.ready) brainStatusTimer = setTimeout(refreshBrainStatus, 1500);
  } catch (e) {
    $("#brain-status").textContent = e.message;
  }
}

function brainMessage(who, ...kids) {
  const node = el("div", { class: "msg " + who }, ...kids);
  $("#brain-log").append(node);
  node.scrollIntoView({ block: "end" });
  return node;
}

function brainReply(r) {
  const parts = [
    el("span", { class: "lb " + (LABEL_CLASS[r.label] || "lb-cmd") }, r.label),
    el("div", { class: "msg-text" }, r.text),
  ];
  if (r.route) {
    parts.push(el("details", { class: "why" },
      el("summary", {}, "why?"),
      el("div", {}, `Route: ${r.route.kind} (${r.route.depth}), because ${r.route.reason}`),
      el("div", {}, `Drawers opened: ${r.drawers.join(", ") || "none"}`),
      ...r.evidence.map((e) => el("div", { class: "ev" }, "• " + e))));
  }
  return brainMessage("bot", ...parts);
}

$("#brain-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const input = $("#brain-input");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  brainMessage("me", el("div", { class: "msg-text" }, message));
  const pending = brainMessage("bot", el("span", { class: "muted" }, "thinking…"));
  input.disabled = true;
  try {
    const r = await api("/api/brain/ask", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }),
    });
    pending.remove();
    brainReply(r);
    refreshBrainStatus();
    if (!$("#brain-facts").classList.contains("hidden")) loadFacts();  // keep drawer 1 view current
  } catch (e) {
    pending.remove();
    brainMessage("bot", el("span", { class: "err" }, e.message));
  } finally {
    input.disabled = false;
    input.focus();
  }
});

$("#brain-import").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  try {
    const r = await api("/api/brain/import", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: await file.text(),
    });
    $("#brain-foot-status").textContent = "Imported: " +
      Object.entries(r.added).map(([k, n]) => `${n} ${k.replace("_", " ")}`).join(", ");
  } catch (e) {
    $("#brain-foot-status").textContent = e.message;
  }
  ev.target.value = "";
});

// Drawer 1: see what's filed about you, and delete anything wrong.
async function loadFacts() {
  const box = $("#brain-facts");
  box.innerHTML = "";
  box.append(el("h3", {}, "Drawer 1 · what I know about you"));
  let facts;
  try { facts = await api("/api/brain/facts"); }
  catch (e) { box.append(el("p", { class: "err" }, e.message)); return; }
  if (!facts.length) { box.append(el("p", { class: "muted" }, "Nothing filed yet.")); return; }
  for (const f of facts.slice().reverse()) {
    const del = el("button", { class: "btn small", title: "Forget this", type: "button" }, "✕");
    del.addEventListener("click", async () => {
      try { await api(`/api/brain/facts/${f.id}`, { method: "DELETE" }); loadFacts(); }
      catch (e) { $("#brain-foot-status").textContent = e.message; }
    });
    box.append(el("div", { class: "fact-row" },
      el("div", { class: "fact-text" }, f.fact, el("div", { class: "fact-subject" }, `#${f.id} · ${f.subject}`)), del));
  }
}
$("#brain-facts-toggle").addEventListener("click", () => {
  const box = $("#brain-facts");
  box.classList.toggle("hidden");
  if (!box.classList.contains("hidden")) loadFacts();
});
