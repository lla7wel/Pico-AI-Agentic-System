"use strict";
// Pico Agent Console — vanilla SPA. Talks to /api/* with a bearer token.

let TOKEN = localStorage.getItem("agent_token") || "";
let logTimer = null;

// ---- API helper ----------------------------------------------------------
async function api(path, opts = {}) {
  opts.headers = Object.assign(
    { "Content-Type": "application/json" },
    opts.headers || {},
    TOKEN ? { Authorization: "Bearer " + TOKEN } : {}
  );
  if (opts.body && typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
  const res = await fetch("/api" + path, opts);
  if (res.status === 401) { showLogin(); throw new Error("unauthorized"); }
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) throw new Error((data && (data.detail || data.error)) || res.statusText);
  return data;
}

function toast(msg, isErr) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  setTimeout(() => (t.className = "toast"), 2600);
}

// ---- Auth ----------------------------------------------------------------
function showLogin() {
  document.getElementById("app").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");
}
function showApp() {
  document.getElementById("login").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  boot();
}
async function doLogin() {
  const pw = document.getElementById("loginPw").value;
  try {
    const res = await fetch("/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "login failed");
    TOKEN = data.token;
    localStorage.setItem("agent_token", TOKEN);
    showApp();
    if (data.must_change) toast("Using default password — change it in Config & Admin", true);
  } catch (e) {
    document.getElementById("loginErr").textContent = e.message;
  }
}
function logout() {
  api("/logout", { method: "POST" }).catch(() => {});
  TOKEN = ""; localStorage.removeItem("agent_token");
  showLogin();
}

// ---- Tab navigation ------------------------------------------------------
document.querySelectorAll("nav button[data-tab]").forEach((b) => {
  b.onclick = () => switchTab(b.dataset.tab);
});
function switchTab(name) {
  document.querySelectorAll("nav button[data-tab]").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((s) =>
    s.classList.toggle("active", s.id === name));
  const loaders = {
    overview: loadStatus, providers: loadSettings, behavior: loadSettings,
    devices: loadDevices, conversations: loadConversations,
    integrations: loadIntegrations, logs: loadLogs, events: loadEvents,
  };
  if (loaders[name]) loaders[name]();
}

// ---- Boot ----------------------------------------------------------------
async function boot() {
  try {
    await api("/session");
    loadStatus();
    loadSettings();
    setInterval(refreshOnlineDot, 5000);
    refreshOnlineDot();
  } catch (e) { /* showLogin already called on 401 */ }
}

async function refreshOnlineDot() {
  try {
    const s = await api("/status");
    document.getElementById("onlineDot").textContent = "● devices online: " + s.online_devices;
    document.getElementById("navStatus").textContent = "v" + s.version + " · up " +
      Math.floor(s.uptime_seconds / 60) + "m";
  } catch (e) {}
}

// ---- Overview ------------------------------------------------------------
async function loadStatus() {
  const s = await api("/status");
  const p = s.providers;
  document.getElementById("statusBody").innerHTML = `
    <table>
      <tr><td>LLM provider</td><td>${p.llm_provider}</td></tr>
      <tr><td>Model</td><td>${p.model}</td></tr>
      <tr><td>OpenAI key</td><td>${badge(p.openai_configured)}</td></tr>
      <tr><td>Deepgram key</td><td>${badge(p.deepgram_configured)}</td></tr>
      <tr><td>Devices online</td><td>${s.online_devices}</td></tr>
      <tr><td>Uptime</td><td>${Math.floor(s.uptime_seconds/60)} min</td></tr>
    </table>`;
  const warn = document.getElementById("warnBanner");
  const problems = [];
  if (!p.openai_configured) problems.push("OpenAI key not set");
  if (!p.deepgram_configured) problems.push("Deepgram key not set");
  warn.innerHTML = problems.length
    ? `<div class="card"><span class="warn">⚠ ${problems.join(" · ")} — set them in Providers &amp; Keys.</span></div>` : "";
}
function badge(ok) {
  return ok ? '<span class="pill on">configured</span>' : '<span class="pill err">missing</span>';
}

// ---- Settings (providers + behavior) ------------------------------------
let SETTINGS = {};
async function loadSettings() {
  SETTINGS = await api("/settings");
  set("openai_model", SETTINGS.openai_model);
  set("openai_base_url", SETTINGS.openai_base_url);
  set("deepgram_model", SETTINGS.deepgram_model);
  set("system_prompt", SETTINGS.system_prompt);
  set("temperature", SETTINGS.temperature);
  set("max_tokens", SETTINGS.max_tokens);
  set("max_response_chars", SETTINGS.max_response_chars);
  set("history_turns", SETTINGS.history_turns);
  hint("openai_hint", SETTINGS.openai_api_key);
  hint("deepgram_hint", SETTINGS.deepgram_api_key);
}
function set(id, v) { const el = document.getElementById(id); if (el && v !== undefined && v !== null) el.value = v; }
function val(id) { return document.getElementById(id).value; }
function hint(id, secret) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = secret && secret.set ? "stored: " + secret.hint : "not set";
}

async function saveProviders() {
  const body = {
    openai_api_key: val("openai_api_key"),
    openai_model: val("openai_model"),
    openai_base_url: val("openai_base_url"),
    deepgram_api_key: val("deepgram_api_key"),
    deepgram_model: val("deepgram_model"),
  };
  await api("/settings", { method: "PUT", body });
  document.getElementById("openai_api_key").value = "";
  document.getElementById("deepgram_api_key").value = "";
  await loadSettings();
  toast("Providers saved");
}

async function saveBehavior() {
  const body = {
    system_prompt: val("system_prompt"),
    temperature: parseFloat(val("temperature")),
    max_tokens: parseInt(val("max_tokens")),
    max_response_chars: parseInt(val("max_response_chars")),
    history_turns: parseInt(val("history_turns")),
  };
  await api("/settings", { method: "PUT", body });
  toast("Behavior saved");
}

// ---- Provider tests ------------------------------------------------------
async function testOpenAI(fetchModels) {
  const out = document.getElementById("testOut");
  if (out) out.textContent = "testing OpenAI…";
  try {
    const r = await api("/test/openai", { method: "POST" });
    if (r.ok) {
      if (fetchModels && r.models) {
        const dl = document.getElementById("modelList");
        dl.innerHTML = r.models.map((m) => `<option value="${m}">`).join("");
        toast(`OpenAI OK — ${r.models.length} models loaded`);
      } else {
        toast("OpenAI OK" + (r.model_available === false ? " (chosen model not in list!)" : ""));
      }
    } else { toast("OpenAI: " + r.error, true); }
    if (out) out.textContent = JSON.stringify(r).slice(0, 300);
  } catch (e) { toast("OpenAI test failed: " + e.message, true); }
}
async function testDeepgram() {
  const out = document.getElementById("testOut");
  if (out) out.textContent = "testing Deepgram…";
  try {
    const r = await api("/test/deepgram", { method: "POST" });
    r.ok ? toast("Deepgram OK (" + r.model + ")") : toast("Deepgram: " + r.error, true);
    if (out) out.textContent = JSON.stringify(r).slice(0, 300);
  } catch (e) { toast("Deepgram test failed: " + e.message, true); }
}

// ---- Devices -------------------------------------------------------------
async function loadDevices() {
  const rows = await api("/devices");
  const sel = document.getElementById("conv_device");
  sel.innerHTML = '<option value="">All devices</option>' +
    rows.map((d) => `<option value="${d.device_id}">${d.device_id}</option>`).join("");
  document.getElementById("devTable").innerHTML = rows.length ? `
    <table><tr><th>Device</th><th>Name</th><th>Status</th><th>Last seen</th><th>Token</th><th></th></tr>
    ${rows.map((d) => `
      <tr>
        <td>${d.device_id}</td>
        <td>${esc(d.name)}</td>
        <td>${d.online ? '<span class="pill on">online</span>' : '<span class="pill off">offline</span>'}</td>
        <td class="muted">${d.last_seen || "never"}</td>
        <td class="muted">${d.token_hint || ""}</td>
        <td>
          <button class="btn small ghost" onclick="rotate('${d.device_id}')">Rotate</button>
          <button class="btn small danger" onclick="delDevice('${d.device_id}')">Delete</button>
        </td>
      </tr>`).join("")}</table>` : '<span class="muted">No devices yet.</span>';
}
async function createDevice() {
  try {
    const r = await api("/devices", { method: "POST", body: {
      name: val("dev_name"), device_id: val("dev_id"), wifi_ssid: val("dev_wifi") } });
    showToken(r.device_id, r.token);
    document.getElementById("dev_name").value = "";
    document.getElementById("dev_id").value = "";
    loadDevices();
  } catch (e) { toast(e.message, true); }
}
function showToken(deviceId, token) {
  document.getElementById("newTokenBox").innerHTML = `
    <div class="hint">Token for <b>${deviceId}</b> — copy into <code>secrets.h</code> now; it won't be shown again:</div>
    <code class="token">#define DEVICE_ID        "${deviceId}"
#define PICO_AUTH_TOKEN  "${token}"</code>`;
}
async function rotate(id) {
  if (!confirm("Rotate token for " + id + "? The device must be reflashed with the new token.")) return;
  const r = await api("/devices/" + id + "/rotate", { method: "POST" });
  showToken(id, r.token);
  loadDevices();
}
async function delDevice(id) {
  if (!confirm("Delete device " + id + "?")) return;
  await api("/devices/" + id, { method: "DELETE" });
  loadDevices();
}

// ---- Conversations -------------------------------------------------------
async function loadConversations() {
  const dev = document.getElementById("conv_device").value;
  const rows = await api("/conversations" + (dev ? "?device_id=" + encodeURIComponent(dev) : ""));
  document.getElementById("convTable").innerHTML = rows.length
    ? rows.reverse().map((r) => `<div class="logline"><span class="muted">[${r.device_id}] ${r.created_at}</span>
        <b class="${r.role === "assistant" ? "ok" : "warn"}">${r.role}:</b> ${esc(r.content)}</div>`).join("")
    : '<span class="muted">No conversation history.</span>';
}
async function clearConversations() {
  const dev = document.getElementById("conv_device").value;
  if (!confirm("Clear conversation history" + (dev ? " for " + dev : " for ALL devices") + "?")) return;
  await api("/conversations" + (dev ? "?device_id=" + encodeURIComponent(dev) : ""), { method: "DELETE" });
  loadConversations();
  toast("History cleared");
}

// ---- Integrations --------------------------------------------------------
async function loadIntegrations() {
  const rows = await api("/integrations");
  document.getElementById("intTable").innerHTML = `
    <table><tr><th>Tool</th><th>Category</th><th>Enabled</th><th>Authorized</th><th>Active</th><th>Notes</th></tr>
    ${rows.map((t) => `
      <tr>
        <td><b>${t.name}</b><div class="muted">${esc(t.description)}</div></td>
        <td>${t.category}</td>
        <td><input type="checkbox" style="width:auto" ${t.enabled ? "checked" : ""}
             onchange="setInt('${t.name}','enabled',this.checked)"></td>
        <td>${t.requires_auth
              ? `<input type="checkbox" style="width:auto" ${t.authorized ? "checked" : ""} onchange="setInt('${t.name}','authorized',this.checked)">`
              : '<span class="muted">n/a</span>'}</td>
        <td>${t.active ? '<span class="pill on">active</span>' : '<span class="pill off">inactive</span>'}</td>
        <td class="muted">${esc(t.note)}</td>
      </tr>`).join("")}</table>`;
}
async function setInt(name, key, value) {
  const body = {}; body[key] = value;
  await api("/integrations/" + name, { method: "PATCH", body });
  loadIntegrations();
}

// ---- Logs & events -------------------------------------------------------
async function loadLogs() {
  const q = new URLSearchParams();
  if (val("log_level")) q.set("level", val("log_level"));
  if (val("log_cat")) q.set("category", val("log_cat"));
  const rows = await api("/logs?" + q.toString());
  document.getElementById("logBody").innerHTML = rows.length
    ? rows.map((r) => `<div class="logline ${r.level}"><span class="lvl">${r.level}</span>
        <span class="muted">${fmtTs(r.ts)}</span> [${r.category}${r.device_id ? "/" + r.device_id : ""}] ${esc(r.message)}</div>`).join("")
    : '<span class="muted">No log lines.</span>';
  clearInterval(logTimer);
  if (document.getElementById("log_auto").checked) logTimer = setInterval(loadLogs, 3000);
}
async function loadEvents() {
  const q = new URLSearchParams();
  if (val("ev_level")) q.set("level", val("ev_level"));
  const rows = await api("/events?" + q.toString());
  document.getElementById("evBody").innerHTML = rows.length
    ? rows.map((r) => `<div class="logline ${r.level}"><span class="lvl">${r.level}</span>
        <span class="muted">${r.created_at}</span> [${r.category}${r.device_id ? "/" + r.device_id : ""}] ${esc(r.message)}</div>`).join("")
    : '<span class="muted">No events.</span>';
}

// ---- Config export / import ---------------------------------------------
async function exportConfig() {
  const inc = document.getElementById("exp_secrets").checked;
  const data = await api("/config/export?include_secrets=" + inc);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "agent-config.json";
  a.click();
}
async function importConfig(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  const text = await file.text();
  try {
    const parsed = JSON.parse(text);
    await api("/config/import", { method: "POST", body: parsed });
    await loadSettings();
    toast("Config imported");
  } catch (e) { toast("Import failed: " + e.message, true); }
  ev.target.value = "";
}

// ---- Admin password ------------------------------------------------------
async function changePassword() {
  const pw = val("new_pw");
  try {
    await api("/password", { method: "POST", body: { new_password: pw } });
    document.getElementById("new_pw").value = "";
    toast("Password updated");
  } catch (e) { toast(e.message, true); }
}

// ---- utils ---------------------------------------------------------------
function esc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function fmtTs(t) { return new Date(t * 1000).toLocaleTimeString(); }

document.getElementById("loginPw").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });

// ---- start ---------------------------------------------------------------
if (TOKEN) { showApp(); } else { showLogin(); }
