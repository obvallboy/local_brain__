// Virtual network + integration engine + automation "brain" + fault injection.
// Adds `fuzz <host>` (corrupts a device's data: out-of-range, malformed, latency)
// and a data-integrity guard: the brain validates readings, rejects corrupt ones,
// raises an integrity alert, and holds the last-good value instead of acting on
// garbage. The guard is a toggleable rule so you can watch it get fooled without it.
// Pure, time-injected, tested.

function netInit(now) {
  now = now || Date.now();
  return {
    subnet: "10.0.0.0/24", gateway: "10.0.0.1", me: "10.0.0.50", last: null,
    tick: 0, disabled: [], alerts: [], lastGoodTemp: 22, rejected: 0, anomalies: 0, anom: { n: 0, mean: 0, var: 1 },
    nodes: [
      { ip: "10.0.0.1", name: "gateway", type: "router", up: true },
      { ip: "10.0.0.2", name: "core", type: "server", up: true, svc: "DNS + MQTT broker" },
      { ip: "10.0.0.21", name: "temp-01", type: "mqtt", up: true, topic: "site/temp", base: 22, temp: 22 },
      { ip: "10.0.0.22", name: "plc-01", type: "modbus", up: true, regs: { "40001": 0, "40002": 1 } },
      { ip: "10.0.0.23", name: "cam-01", type: "http", up: true, res: "1920x1080", motion: false, snap: 0 },
    ],
  };
}
function netPad(s, n) { s = String(s); return s.length >= n ? s + " " : s + " ".repeat(n - s.length); }
function netProto(t) { return t === "mqtt" ? "MQTT" : t === "modbus" ? "Modbus" : t === "http" ? "HTTP" : t === "server" ? "server" : t === "router" ? "router" : t; }
function netMac(ip) { const o = +ip.split(".")[3]; const h = (x) => ("0" + (x % 256).toString(16)).slice(-2); return "02:00:00:00:" + h(o) + ":" + h(o * 7 + 11); }
function netResolve(s, tok) { tok = String(tok || "").trim().toLowerCase(); if (!tok) return null; const byIp = s.nodes.find((n) => n.ip === tok); if (byIp) return byIp.ip; const nm = tok.replace(/\.lab$/, ""); const byName = s.nodes.find((n) => n.name === nm); return byName ? byName.ip : null; }
function netNode(s, ip) { return s.nodes.find((n) => n.ip === ip); }
function netTemp(s) { const t = s.nodes.find((n) => n.type === "mqtt"); return t ? (t.temp != null ? t.temp : (t.base || 22)) : null; }
function netBrainTemp(s) { return s.lastGoodTemp != null ? s.lastGoodTemp : netTemp(s); }
function netVent(s) { const p = s.nodes.find((n) => n.type === "modbus"); return p ? p.regs["40001"] : null; }
function netSetVent(s, v) { const p = s.nodes.find((n) => n.type === "modbus"); if (p) p.regs["40001"] = v; }
function netCam(s) { return s.nodes.find((n) => n.type === "http"); }
function netRuleOff(s, id) { return (s.disabled || []).indexOf(id) >= 0; }
function netValidTemp(v) { return typeof v === "number" && isFinite(v) && v >= -20 && v <= 60; }
function netFmt(v) { return typeof v === "number" ? (isFinite(v) ? String(v) + "°C" : "NaN") : String(v); }
function netCorruptTemp(s) { const seq = [999, "0x8F3A", 1500, -273.1, "NaN"]; return seq[(s.tick || 0) % seq.length]; }
const NET_KEY = "lab-shared-key-2024";
function netSign(v) { return (typeof CryptoJS !== "undefined") ? CryptoJS.HmacSHA256(String(v), NET_KEY).toString() : "nosig"; }
function netVerify(v, sig) { if (typeof CryptoJS === "undefined") return true; return netSign(v) === sig; }

// Learned anomaly guard: an online detector that models the sensor's normal
// behaviour (exponentially-weighted mean/variance) and scores each reading as a
// z-score. It catches values that are IN RANGE but abnormal for this sensor — the
// kind of fault the range check (netValidTemp) waves through. Mirror of
// integration/anomaly.py + integration-js/anomaly.js. Only {n,mean,var} is stored
// in state (JSON-serializable); the config lives here.
const NET_GLITCH_TEMP = 45;   // passes the -20..60 range check, abnormal for a ~25°C sensor
const NET_ANOM = { warmup: 10, threshold: 4, alpha: 0.3 };
function netAnomUpdate(a, x) { a.n = (a.n || 0) + 1; if (a.n === 1) { a.mean = x; return; } const diff = x - a.mean; const incr = NET_ANOM.alpha * diff; a.mean += incr; a.var = (1 - NET_ANOM.alpha) * ((a.var || 1) + diff * incr); }
function netAnomScore(a, x) { if ((a.n || 0) < 2) return 0; const sd = (a.var > 0) ? Math.sqrt(a.var) : 0; if (sd < 1e-9) return Math.abs(x - a.mean) < 1e-9 ? 0 : Infinity; return Math.abs(x - a.mean) / sd; }
function netAnomCheck(a, x) { if ((a.n || 0) < NET_ANOM.warmup) { netAnomUpdate(a, x); return { anomaly: false, score: 0 }; } const score = netAnomScore(a, x); const anomaly = score > NET_ANOM.threshold; if (!anomaly) netAnomUpdate(a, x); return { anomaly, score }; }

const NET_RULES = [
  { id: "integrity", builtin: true, desc: "validate sensor data; reject out-of-range / corrupt readings" },
  { id: "security", builtin: true, desc: "verify HMAC signatures; reject tampered / unsigned telemetry" },
  { id: "anomaly", builtin: true, desc: "learned guard: flag in-range readings abnormal for this sensor (z-score)" },
  { id: "therm-hi", desc: "temp-01 ≥ 28°C → open PLC vent (40001=1)", fires: (s) => netBrainTemp(s) != null && netBrainTemp(s) >= 28 && netVent(s) !== 1, act: (s) => { netSetVent(s, 1); return "opened vent (plc-01 40001=1)"; } },
  { id: "therm-lo", desc: "temp-01 ≤ 24°C → close PLC vent (40001=0)", fires: (s) => netBrainTemp(s) != null && netBrainTemp(s) <= 24 && netVent(s) !== 0, act: (s) => { netSetVent(s, 0); return "closed vent (plc-01 40001=0)"; } },
  { id: "offline", desc: "any device offline → raise an alert", fires: (s) => s.nodes.some((n) => n.type !== "router" && n.type !== "server" && !n.up && !n._alerted), act: (s) => { const n = s.nodes.find((x) => x.type !== "router" && x.type !== "server" && !x.up && !x._alerted); n._alerted = true; return "ALERT: " + n.name + " (" + n.ip + ") is offline"; } },
  { id: "motion", desc: "cam-01 motion detected → take a snapshot", fires: (s) => { const c = netCam(s); return c && c.up && c.motion && !c._snapped; }, act: (s) => { const c = netCam(s); c.snap = (c.snap || 0) + 1; c._snapped = true; return "motion → snapshot IMG_" + (1000 + c.snap); } },
];

function netTick(s, now) {
  s.tick = (s.tick || 0) + 1;
  const t = s.nodes.find((n) => n.type === "mqtt");
  // true physics: vent cools, closed heats
  if (t && t.up) { const vent = netVent(s); const drift = vent === 1 ? -0.9 : 0.8; const base = t.temp != null ? t.temp : (t.base || 22); t.temp = Math.round((base + drift + (Math.random() - 0.5) * 0.3) * 10) / 10; }
  // sensor read + guards: authenticity (HMAC) then plausibility (range)
  if (t && t.up) {
    const reported = t.fuzz ? netCorruptTemp(s) : (t.glitch ? NET_GLITCH_TEMP : t.temp);
    const sig = t.tamper ? netSign(String(reported) + "!") : netSign(reported);   // tamper = invalid signature
    const numeric = typeof reported === "number" && isFinite(reported);
    const secOn = !netRuleOff(s, "security") && typeof CryptoJS !== "undefined";
    const intOn = !netRuleOff(s, "integrity");
    const anomOn = !netRuleOff(s, "anomaly");
    const secFail = secOn && !netVerify(reported, sig);
    const intFail = intOn && !netValidTemp(reported);
    // guards in order: authenticity (HMAC) → plausibility (range) → learned anomaly
    if (secFail || intFail) {
      s.rejected = (s.rejected || 0) + 1;
      if (secFail) { s._badReading = "unsigned/tampered"; if (!s._secAlerted) { s.alerts = (s.alerts || []).concat("t" + s.tick + " SECURITY: temp-01 failed HMAC verify — rejected, holding " + s.lastGoodTemp + "°C").slice(-10); s._secAlerted = true; } }
      else { s._badReading = netFmt(reported); if (!s._integrityAlerted) { s.alerts = (s.alerts || []).concat("t" + s.tick + " INTEGRITY: temp-01 sent " + netFmt(reported) + " — rejected, holding " + s.lastGoodTemp + "°C").slice(-10); s._integrityAlerted = true; } }
    } else if (numeric) {
      s.anom = s.anom || { n: 0, mean: 0, var: 1 };
      const res = anomOn ? netAnomCheck(s.anom, reported) : { anomaly: false, score: 0 };
      if (res.anomaly) {
        s.rejected = (s.rejected || 0) + 1; s.anomalies = (s.anomalies || 0) + 1;
        s._badReading = netFmt(reported) + " abnormal";
        if (!s._anomAlerted) { s.alerts = (s.alerts || []).concat("t" + s.tick + " ANOMALY: temp-01 read " + netFmt(reported) + " — abnormal for this sensor (z=" + res.score.toFixed(1) + "), rejected, holding " + s.lastGoodTemp + "°C").slice(-10); s._anomAlerted = true; }
      } else { s.lastGoodTemp = reported; s._badReading = null; }
    }
    if (!t.fuzz) s._integrityAlerted = false;
    if (!t.tamper) s._secAlerted = false;
    if (!t.glitch) s._anomAlerted = false;
  }
  s.nodes.forEach((n) => { if (n.up) n._alerted = false; });
  const cam = netCam(s); if (cam && !cam.motion) cam._snapped = false;
  const fired = [];
  for (const r of NET_RULES) { if (r.builtin || netRuleOff(s, r.id)) continue; if (r.fires(s)) { const msg = r.act(s); fired.push({ id: r.id, msg }); if (/^ALERT/.test(msg)) { s.alerts = (s.alerts || []).concat("t" + s.tick + " " + msg).slice(-10); } } }
  return fired;
}

function netPoll(s, n, now) {
  if (n.fuzz) {
    if (n.type === "mqtt") return 'MQTT   ← SUB ' + n.topic + '  payload {"tempC":999.0}   ⚠ out-of-range (sensor fault)';
    if (n.type === "modbus") return "Modbus ✗ exception 03 (illegal data value), CRC mismatch — packet dropped";
    if (n.type === "http") return "HTTP 500 ← GET /api/status  {malformed JSON…  ⚠ latency 4200ms → timeout}";
  }
  if (n.type === "mqtt") { const v = n.temp != null ? n.temp : (n.base + Math.sin(now / 5000) * 1.5); return 'MQTT   ← SUB ' + n.topic + '  payload {"tempC":' + (+v).toFixed(1) + '}   (QoS0, retained)'; }
  if (n.type === "modbus") { return "Modbus ← FC03 read holding  40001=" + n.regs["40001"] + " (vent)  40002=" + n.regs["40002"]; }
  if (n.type === "http") { return 'HTTP 200 ← GET /api/status  {"online":true,"res":"' + n.res + '","motion":' + n.motion + "}"; }
  if (n.type === "server") return "core: DNS :53 up, MQTT broker :1883 up";
  if (n.type === "router") return "gateway: NAT up, DHCP serving 3 leases";
  return "no pollable service";
}
function netPollShort(s, n, now) { if (n.fuzz) return "⚠ corrupt"; if (n.type === "mqtt") { const v = n.temp != null ? n.temp : n.base; return (+v).toFixed(1) + " C"; } if (n.type === "modbus") return "vent=" + (n.regs["40001"] === 1 ? "OPEN" : "closed"); if (n.type === "http") return "online " + n.res + (n.motion ? " MOTION" : ""); return "ok"; }

function netStep(state, raw, now) {
  now = now || Date.now();
  const s = (state && Array.isArray(state.nodes)) ? JSON.parse(JSON.stringify(state)) : netInit(now);
  const line = String(raw == null ? "" : raw).trim();
  if (!line) return { state: s, reply: "" };
  const parts = line.split(/\s+/); const cmd = parts[0].toLowerCase(); const arg = parts.slice(1);
  const out = (r, status) => ({ state: s, reply: r, status });
  const tbl = (rows) => rows.join("\n");
  if (cmd === "help" || cmd === "?") return out("NETWORK: discover | dhcp | arp | ping <host> | nslookup <host> | trace <host> | map\nFLEET:   poll <host>|all | write <plc> <reg> <val> | snapshot <cam> | motion <cam> on|off\nBRAIN:   brain | rules | rule on|off <id> | tick | run <n> | alerts\nFAULTS:  down <host> | up <host> | fuzz <host> on|off | tamper <host> on|off | glitch <host> on|off");
  if (cmd === "discover" || cmd === "scan") { const rows = ["Scanning " + s.subnet + " …", netPad("IP", 14) + netPad("NAME", 11) + netPad("PROTO", 8) + "STATUS"]; for (const n of s.nodes) rows.push(netPad(n.ip, 14) + netPad(n.name, 11) + netPad(netProto(n.type), 8) + (n.up ? (n.fuzz ? "up ⚡" : "up") : "DOWN")); return out(tbl(rows), "discovered the fleet"); }
  if (cmd === "dhcp") { const rows = ["DHCP leases (pool 10.0.0.20–10.0.0.99):"]; for (const n of s.nodes.filter((x) => +x.ip.split(".")[3] >= 20)) rows.push("  " + netPad(n.ip, 14) + n.name); rows.push("  " + netPad(s.me, 14) + "this-console"); return out(tbl(rows)); }
  if (cmd === "arp") { const rows = [netPad("Address", 14) + "HWaddress"]; for (const n of s.nodes) rows.push(netPad(n.ip, 14) + netMac(n.ip) + (n.up ? "" : "  (incomplete)")); return out(tbl(rows)); }
  if (cmd === "nslookup") { const ip = netResolve(s, arg[0]); if (!ip) return out("** can't find " + (arg[0] || "") + ": NXDOMAIN"); const n = netNode(s, ip); return out("Name:    " + n.name + ".lab\nAddress: " + ip); }
  if (cmd === "ping") { const ip = netResolve(s, arg[0]); if (!ip) return out("ping: cannot resolve '" + (arg[0] || "") + "': unknown host"); const n = netNode(s, ip); s.last = ip; if (!n.up) return out("PING " + n.name + ".lab (" + ip + ")\nRequest timed out.\nRequest timed out.\n--- " + ip + " ping statistics ---\n4 transmitted, 0 received, 100% packet loss"); const rows = ["PING " + n.name + ".lab (" + ip + ") 56 bytes"]; for (let i = 0; i < 4; i++) rows.push("64 bytes from " + ip + ": icmp_seq=" + i + " ttl=64 time=" + (0.3 + Math.random() * 0.9).toFixed(2) + " ms"); rows.push("--- " + ip + " ping statistics ---\n4 transmitted, 4 received, 0% loss"); return out(tbl(rows), "pinged " + n.name); }
  if (cmd === "poll") {
    if ((arg[0] || "").toLowerCase() === "all") { s.last = null; const rows = ["Integration engine — polling fleet:", netPad("HOST", 11) + netPad("PROTO", 8) + "VALUE"]; for (const n of s.nodes) { if (n.type === "router" || n.type === "server") continue; rows.push(netPad(n.name, 11) + netPad(netProto(n.type), 8) + (n.up ? netPollShort(s, n, now) : "— offline —")); } return out(tbl(rows), "polled the fleet"); }
    const ip = netResolve(s, arg[0]); if (!ip) return out("poll: unknown host '" + (arg[0] || "") + "'"); const n = netNode(s, ip); s.last = ip; if (!n.up) return out("poll " + n.name + ": host unreachable (offline)"); return out(netPoll(s, n, now), "polled " + n.name); }
  if (cmd === "write") { const ip = netResolve(s, arg[0]); const n = ip && netNode(s, ip); if (!n || n.type !== "modbus") return out("write: '" + (arg[0] || "") + "' is not a Modbus device"); const reg = arg[1], val = parseInt(arg[2], 10); if (!reg || isNaN(val)) return out("usage: write <plc> <reg> <value>"); n.regs[reg] = val; s.last = ip; return out("Modbus → FC06 write single  " + reg + "=" + val + "   OK", "wrote " + reg + "=" + val + " to " + n.name); }
  if (cmd === "snapshot") { const ip = netResolve(s, arg[0]); const n = ip && netNode(s, ip); if (!n || n.type !== "http") return out("snapshot: '" + (arg[0] || "") + "' is not an HTTP camera"); if (!n.up) return out("camera offline"); n.snap = (n.snap || 0) + 1; s.last = ip; return out('HTTP 200 ← POST /api/snapshot  {"id":"IMG_' + (1000 + n.snap) + '","res":"' + n.res + '"}', "snapshot from " + n.name); }
  if (cmd === "motion") { const ip = netResolve(s, arg[0]); const n = ip && netNode(s, ip); if (!n || n.type !== "http") return out("motion: '" + (arg[0] || "") + "' is not a camera"); n.motion = (arg[1] || "").toLowerCase() === "on"; s.last = ip; return out("HTTP 200 ← motion detection " + (n.motion ? "ENABLED" : "disabled")); }
  if (cmd === "fuzz") { const ip = netResolve(s, arg[0]); const n = ip && netNode(s, ip); if (!n) return out("fuzz: unknown host '" + (arg[0] || "") + "'"); const a = (arg[1] || "").toLowerCase(); n.fuzz = a === "off" ? false : a === "on" ? true : !n.fuzz; if (!n.fuzz) { s._integrityAlerted = false; s._badReading = null; } s.last = ip; return out("⚡ fault injection on " + n.name + ": " + (n.fuzz ? "ENABLED — data now corrupted (out-of-range / malformed / latency)" : "disabled"), (n.fuzz ? "fuzzing " : "un-fuzzed ") + n.name); }
  if (cmd === "tamper") { const ip = netResolve(s, arg[0]); const n = ip && netNode(s, ip); if (!n) return out("tamper: unknown host '" + (arg[0] || "") + "'"); const a = (arg[1] || "").toLowerCase(); n.tamper = a === "off" ? false : a === "on" ? true : !n.tamper; if (!n.tamper) s._secAlerted = false; s.last = ip; return out("🔓 message tampering on " + n.name + ": " + (n.tamper ? "ENABLED — signatures now invalid (simulated MITM)" : "disabled"), (n.tamper ? "tampering " : "un-tampered ") + n.name); }
  if (cmd === "glitch") { const ip = netResolve(s, arg[0]); const n = ip && netNode(s, ip); if (!n) return out("glitch: unknown host '" + (arg[0] || "") + "'"); if (n.type !== "mqtt") return out("glitch: only temp-01 has a learned anomaly model"); const a = (arg[1] || "").toLowerCase(); n.glitch = a === "off" ? false : a === "on" ? true : !n.glitch; if (!n.glitch) { s._anomAlerted = false; s._badReading = null; } s.last = ip; return out("📈 in-range glitch on " + n.name + ": " + (n.glitch ? "ENABLED — now reports " + NET_GLITCH_TEMP + "°C: passes the range check, abnormal for this sensor (needs ≥" + NET_ANOM.warmup + " clean ticks first so the model is trained)" : "disabled"), (n.glitch ? "glitching " : "un-glitched ") + n.name); }
  if (cmd === "down") { const ip = netResolve(s, arg[0]); const n = ip && netNode(s, ip); if (!n) return out("down: unknown host"); n.up = false; return out("[sim] " + n.name + " (" + ip + ") is now OFFLINE", "took " + n.name + " offline"); }
  if (cmd === "up") { const ip = netResolve(s, arg[0]); const n = ip && netNode(s, ip); if (!n) return out("up: unknown host"); n.up = true; n._alerted = false; return out("[sim] " + n.name + " (" + ip + ") is back ONLINE", "brought " + n.name + " online"); }
  if (cmd === "trace") { const ip = netResolve(s, arg[0]); if (!ip) return out("traceroute: unknown host"); const n = netNode(s, ip); s.last = ip; return out("traceroute to " + n.name + ".lab (" + ip + ")\n 1  " + s.me + "  0.10 ms\n 2  " + s.gateway + " (gateway)  0.40 ms\n 3  " + ip + " (" + n.name + ")  0.90 ms"); }
  if (cmd === "map" || cmd === "topology") { const rows = ["[ gateway " + s.gateway + " ]", "       |", "   [ switch ]"]; for (const n of s.nodes.filter((x) => x.type !== "router")) rows.push("       ├─ " + netPad(n.ip, 12) + n.name + " (" + netProto(n.type) + ")" + (n.up ? (n.fuzz ? "  ⚡fuzzed" : "") : "  ✗ down")); return out(tbl(rows)); }
  if (cmd === "brain") { const on = NET_RULES.filter((r) => !netRuleOff(s, r.id)).length; const fz = s.nodes.filter((n) => n.fuzz).map((n) => n.name).join(", ") || "none"; const tp = s.nodes.filter((n) => n.tamper).map((n) => n.name).join(", ") || "none"; const gl = s.nodes.filter((n) => n.glitch).map((n) => n.name).join(", ") || "none"; const am = s.anom || { n: 0 }; const amStr = netRuleOff(s, "anomaly") ? "OFF" : (am.n >= NET_ANOM.warmup ? "ON — trained (μ=" + am.mean.toFixed(1) + "°C σ=" + Math.sqrt(am.var || 0).toFixed(1) + ", n=" + am.n + ")" : "ON — learning (" + (am.n || 0) + "/" + NET_ANOM.warmup + " ticks)"); return out("Integration brain\n  rules enabled : " + on + "/" + NET_RULES.length + "\n  ticks run     : " + (s.tick || 0) + "\n  temp (brain)  : " + netBrainTemp(s) + "°C" + (s._badReading ? "   ⚠ last reading rejected (" + s._badReading + ")" : "") + "\n  vent (40001)  : " + (netVent(s) === 1 ? "OPEN" : "closed") + "\n  integrity     : " + (netRuleOff(s, "integrity") ? "OFF — trusting raw data!" : "ON — validating range") + "\n  security(HMAC): " + (netRuleOff(s, "security") ? "OFF" : "ON — verifying signatures") + "\n  anomaly(learn): " + amStr + "\n  fuzz/tamper/glitch: " + fz + " / " + tp + " / " + gl + "\n  rejected/alerts: " + (s.rejected || 0) + " / " + (s.alerts || []).length); }
  if (cmd === "rules") { const rows = ["Automation rules (the brain):"]; for (const r of NET_RULES) rows.push((netRuleOff(s, r.id) ? "[ off ] " : "[ ON  ] ") + netPad(r.id, 10) + r.desc); rows.push("toggle: rule on <id> | rule off <id>"); return out(tbl(rows)); }
  if (cmd === "rule") { const a = (arg[0] || "").toLowerCase(), id = arg[1]; if (!NET_RULES.find((r) => r.id === id)) return out("unknown rule '" + (id || "") + "' — see 'rules'"); s.disabled = s.disabled || []; if (a === "off") { if (s.disabled.indexOf(id) < 0) s.disabled.push(id); return out("rule " + id + " disabled", "disabled " + id); } if (a === "on") { s.disabled = s.disabled.filter((x) => x !== id); return out("rule " + id + " enabled", "enabled " + id); } return out("usage: rule on|off <id>"); }
  if (cmd === "tick") { const fired = netTick(s, now); let r = "tick " + s.tick + "   temp(brain)=" + netBrainTemp(s) + "°C" + (s._badReading ? " ⚠rej(" + s._badReading + ")" : "") + "   vent=" + (netVent(s) === 1 ? "OPEN" : "closed"); r += fired.length ? ("\n  fired: " + fired.map((f) => f.id + " → " + f.msg).join("\n         ")) : "\n  (no rules fired)"; return out(r, "brain tick " + s.tick); }
  if (cmd === "run") { let n = parseInt(arg[0], 10); if (isNaN(n)) n = 10; n = Math.max(1, Math.min(50, n)); const rows = ["Running the brain for " + n + " ticks:"]; for (let i = 0; i < n; i++) { const fired = netTick(s, now + i * 1000); rows.push("t" + netPad(s.tick, 3) + "temp=" + netPad(netBrainTemp(s) + "°C", 8) + "vent=" + netPad(netVent(s) === 1 ? "OPEN" : "closed", 8) + (s._badReading ? "⚠ " : "") + (fired.length ? ("| " + fired.map((f) => f.id).join(",")) : "")); } rows.push("done."); return out(tbl(rows), "ran the brain " + n + " ticks"); }
  if (cmd === "alerts") { const a = s.alerts || []; return out(a.length ? ("Recent alerts:\n" + a.map((x) => "  ⚠ " + x).join("\n")) : "no alerts"); }
  return out("unknown command — type 'help'");
}

// ---------------- tests ----------------
let ok = true;
const t = (name, cond, extra) => { if (!cond) { ok = false; console.log("FAIL", name, extra || ""); } else console.log("ok  ", name); };
const T = 1000000;

// Stand in for the browser's crypto-js with Node's crypto so the security guard runs.
const _nc = require("crypto");
global.CryptoJS = { HmacSHA256: (m, k) => ({ toString: () => _nc.createHmac("sha256", String(k)).update(String(m)).digest("hex") }) };

// netValidTemp unit
t("validate: 25 ok", netValidTemp(25) === true);
t("validate: 999 bad", netValidTemp(999) === false);
t("validate: string bad", netValidTemp("0x8F") === false);
t("validate: NaN bad", netValidTemp(NaN) === false);
t("validate: -300 bad", netValidTemp(-300) === false);

// guard ON: fuzz does not open vent, raises integrity alert, no crash
let s = netInit(T); s.lastGoodTemp = 25; s.nodes.find((n) => n.type === "mqtt").temp = 25;
let r = netStep(s, "fuzz temp-01 on", T); s = r.state;
r = netStep(s, "run 8", T); s = r.state;
t("guard on: vent NOT opened by garbage", netVent(s) !== 1, "vent=" + netVent(s));
t("guard on: integrity alert raised", (s.alerts || []).some((a) => a.indexOf("INTEGRITY") > -1));
t("guard on: last-good held (not 999)", s.lastGoodTemp === 25);
t("guard on: engine did not crash", typeof netBrainTemp(s) === "number");

// guard OFF: brain gets fooled → opens vent on 999
let s2 = netInit(T); s2.lastGoodTemp = 25; s2.nodes.find((n) => n.type === "mqtt").temp = 25;
r = netStep(s2, "fuzz temp-01 on", T); s2 = r.state;
r = netStep(s2, "rule off integrity", T); s2 = r.state;
r = netStep(s2, "run 10", T); s2 = r.state;
t("guard off: brain fooled, vent OPEN on garbage", netVent(s2) === 1, "vent=" + netVent(s2) + " temp=" + netBrainTemp(s2));

// un-fuzz recovers clean operation
let s3 = netInit(T); s3.nodes.find((n) => n.type === "mqtt").temp = 30;
r = netStep(s3, "run 15", T); s3 = r.state;
t("control loop still works (settled in band)", netBrainTemp(s3) >= 22 && netBrainTemp(s3) <= 30);

// offline alert still fires once
let s4 = netInit(T);
r = netStep(s4, "down cam-01", T); s4 = r.state; r = netStep(s4, "tick", T); s4 = r.state;
const before = s4.alerts.length;
r = netStep(s4, "tick", T); s4 = r.state;
t("offline alert fires once", s4.alerts.length === before && before > 0);

// --- crypto-js signing / tamper guard ---
t("sign+verify roundtrip", netVerify(25.4, netSign(25.4)) === true);
t("tamper breaks verify", netVerify(25.4, netSign("25.4!")) === false);

let sx = netInit(T); sx.lastGoodTemp = 25; sx.nodes.find((n) => n.type === "mqtt").temp = 25;
r = netStep(sx, "tamper temp-01 on", T); sx = r.state;
r = netStep(sx, "run 5", T); sx = r.state;
t("tamper: security rejects", sx.rejected > 0 && (sx.alerts || []).some((a) => a.indexOf("SECURITY") > -1), JSON.stringify(sx.alerts));
t("tamper: last-good held, vent not forced open", sx.lastGoodTemp === 25 && netVent(sx) !== 1);

let sc = netInit(T); sc.nodes.find((n) => n.type === "mqtt").temp = 26;
r = netStep(sc, "run 5", T); sc = r.state;
t("clean signed telemetry passes", !(sc.alerts || []).some((a) => a.indexOf("SECURITY") > -1));

r = netStep(sx, "rule off security", T); sx = r.state;
r = netStep(sx, "run 3", T); sx = r.state;
t("security OFF: tampered data now trusted", sx.lastGoodTemp !== 25);

// --- learned anomaly guard (in-range but abnormal) ---
// unit: the detector warms up, flags an in-range outlier, won't learn it, tracks drift
let anomA = { n: 0, mean: 0, var: 1 };
for (let i = 0; i < NET_ANOM.warmup; i++) netAnomCheck(anomA, 25 + (i % 2 ? 0.1 : -0.1));
t("anom: warm-up learned", anomA.n === NET_ANOM.warmup);
t("anom: in-range 45 flagged", netAnomCheck(anomA, 45).anomaly === true);
t("anom: does not learn the anomaly", anomA.n === NET_ANOM.warmup);
t("anom: normal reading passes + is learned", (() => { const b = anomA.n; const res = netAnomCheck(anomA, 25.1); return res.anomaly === false && anomA.n === b + 1; })());
let anomD = { n: 0, mean: 0, var: 1 }; let dv = 25; for (let i = 0; i < NET_ANOM.warmup; i++) { dv += 0.1; netAnomCheck(anomD, dv); } let drifted = 0; for (let i = 0; i < 20; i++) { dv += 0.1; if (netAnomCheck(anomD, dv).anomaly) drifted++; }
t("anom: slow drift tracked, not flagged", drifted === 0, "flagged=" + drifted);

// engine: glitch on with the guard → 45°C caught, last-good held, vent not driven by it
let sg = netInit(T); sg.lastGoodTemp = 25; sg.nodes.find((n) => n.type === "mqtt").temp = 25;
r = netStep(sg, "run 12", T); sg = r.state;            // warm the model on clean data
r = netStep(sg, "glitch temp-01 on", T); sg = r.state;
r = netStep(sg, "run 5", T); sg = r.state;
t("glitch: anomaly guard rejects in-range 45", (sg.anomalies || 0) >= 1, "anomalies=" + sg.anomalies);
t("glitch: ANOMALY alert raised", (sg.alerts || []).some((x) => x.indexOf("ANOMALY") > -1));
t("glitch: last-good not polluted by 45", sg.lastGoodTemp < 40, "lastGood=" + sg.lastGoodTemp);

// engine: same glitch with the guard OFF → the in-range 45 fools the brain
let sh = netInit(T); sh.lastGoodTemp = 25; sh.nodes.find((n) => n.type === "mqtt").temp = 25;
r = netStep(sh, "run 12", T); sh = r.state;
r = netStep(sh, "rule off anomaly", T); sh = r.state;
r = netStep(sh, "glitch temp-01 on", T); sh = r.state;
r = netStep(sh, "run 3", T); sh = r.state;
t("glitch guard off: 45 absorbed (brain fooled)", sh.lastGoodTemp === 45, "lastGood=" + sh.lastGoodTemp);

// composition: out-of-range fuzz is still caught by integrity, never reaches the model
let si = netInit(T); si.lastGoodTemp = 25; si.nodes.find((n) => n.type === "mqtt").temp = 25;
r = netStep(si, "run 12", T); si = r.state;
r = netStep(si, "fuzz temp-01 on", T); si = r.state;
r = netStep(si, "run 5", T); si = r.state;
t("fuzz still caught by integrity, not the anomaly model", (si.anomalies || 0) === 0 && (si.alerts || []).some((x) => x.indexOf("INTEGRITY") > -1));

console.log(ok ? "\nALL PASS" : "\nFAILURES");
process.exit(ok ? 0 : 1);
