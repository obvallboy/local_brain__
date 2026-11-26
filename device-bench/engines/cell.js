// Cellular modem emulator engine: a real registration state machine + SMS
// store + call state, advanced by elapsed time. Pure functions (time injected)
// so it is testable. Tested at the bottom.

const CELL_REG_MS = 6000;

function cellInit(now) {
  now = now || Date.now();
  return {
    radio: true, pin: "ready",            // pin: "ready" | "sim_pin" | "no_sim"
    reg: "searching", searchStart: now,
    operator: "SimTel",
    textMode: false,
    msgs: [], nextIdx: 1,
    smsPending: null,
    call: "idle", callNum: null,
    incomingAt: now + 21000,              // an unsolicited text arrives ~21s after power-on
    sig: 22,
  };
}

function cellRegStat(s) {
  if (!s.radio || s.pin !== "ready") return 0;
  if (s.reg === "home") return 1;
  if (s.reg === "roaming") return 5;
  if (s.reg === "denied") return 3;
  if (s.reg === "searching") return 2;
  return 0;
}
function cellRegWord(st) { return st === 1 ? "registered, home" : st === 5 ? "roaming" : st === 2 ? "searching…" : st === 3 ? "registration denied" : "not registered"; }
function cellSummary(s) { try { return (s.reg || "?") + " · sig " + (s.sig != null ? s.sig : "?"); } catch (_) { return "modem"; } }

function cellAdvance(s, now) {
  let urc = "";
  if (s.radio && s.pin === "ready" && s.reg === "searching" && now - s.searchStart >= CELL_REG_MS) s.reg = "home";
  s.sig = (s.radio && s.reg !== "none" && s.reg !== "searching") ? 14 + Math.floor((Math.sin(now / 7000) + 1) * 8) : (s.reg === "searching" ? 8 : 0);
  if (s.incomingAt && now >= s.incomingAt && s.radio && (s.reg === "home" || s.reg === "roaming")) {
    const idx = s.nextIdx++;
    s.msgs.push({ idx, dir: "recv", num: "+15559876543", text: "Welcome to SimTel! Reply STOP to opt out.", read: false });
    s.incomingAt = null;
    urc = '+CMTI: "SM",' + idx;
  }
  return urc;
}

function cellStep(state, raw, now) {
  now = now || Date.now();
  const s = (state && typeof state.reg === "string") ? JSON.parse(JSON.stringify(state)) : cellInit(now);
  const line = String(raw == null ? "" : raw).trim();
  const urc = cellAdvance(s, now);
  const pre = urc ? urc + "\n" : "";
  const out = (r, status) => ({ state: s, reply: pre + r, status });
  if (!line) return { state: s, reply: urc };
  const U = line.toUpperCase();
  let m;

  // Awaiting SMS body (the ">" prompt state)
  if (s.smsPending && !U.startsWith("AT")) {
    if (U === "ESC" || line === ".") { s.smsPending = null; return out("(message cancelled)"); }
    const idx = s.nextIdx++;
    s.msgs.push({ idx, dir: "sent", num: s.smsPending, text: line, read: true });
    const to = s.smsPending; s.smsPending = null;
    return out("+CMGS: " + idx + "\nOK   (simulated — no real text sent)", "sent SMS #" + idx + " to " + to);
  }

  if (line.toLowerCase() === "help" || line === "?") return out("AT | AT+CPIN? | AT+CFUN=0/1 | AT+CSQ | AT+CREG? | AT+COPS? | AT+CMGF=1 | AT+CMGS=\"+num\" | AT+CMGL=\"ALL\" | AT+CMGR=n | AT+CMGD=n | ATD+num; | ATH | AT+CLCC | simrx");
  if (line.toLowerCase() === "simrx") { const idx = s.nextIdx++; s.msgs.push({ idx, dir: "recv", num: "+15551112222", text: "Test inbound message.", read: false }); return out('+CMTI: "SM",' + idx + '   (simulated inbound)'); }

  if (!s.radio && U !== "AT+CFUN=1" && U !== "AT") return out("ERROR   (radio off — AT+CFUN=1 to enable)");
  if (U === "AT") return out("OK");
  if (U === "ATE0" || U === "ATE1") return out("OK");
  if (U === "AT+CFUN=0") { s.radio = false; s.reg = "none"; return out("OK   (radio off)", "radio off"); }
  if (U === "AT+CFUN=1") { s.radio = true; s.reg = "searching"; s.searchStart = now; return out("OK   (radio on — searching for network…)", "radio on, searching"); }
  if (U === "AT+CPIN?") return out(s.pin === "ready" ? "+CPIN: READY\nOK" : s.pin === "sim_pin" ? "+CPIN: SIM PIN\nOK" : "+CME ERROR: SIM not inserted");
  if ((m = U.match(/^AT\+CPIN=(\d{4})$/))) { if (s.pin === "ready") return out("OK   (already unlocked)"); if (m[1] === "1234") { s.pin = "ready"; s.reg = "searching"; s.searchStart = now; return out("OK", "SIM unlocked"); } return out("+CME ERROR: incorrect PIN"); }
  if (U === "AT+CSQ") return out("+CSQ: " + s.sig + ",0\nOK");
  if (U === "AT+CREG?") { const st = cellRegStat(s); return out("+CREG: 0," + st + "\nOK   (" + cellRegWord(st) + ")"); }
  if (U === "AT+COPS?") { const st = cellRegStat(s); return out((st === 1 || st === 5) ? '+COPS: 0,0,"' + s.operator + '"\nOK' : "+COPS: 0\nOK   (not registered yet — check AT+CREG?)"); }
  if (U === "AT+COPS=?") return out('+COPS: (2,"SimTel","SimTel","310260"),(1,"FauxMobile","Faux","310410"),(1,"TestNet","TN","311480"),,(0,1,4),(0,1,2)\nOK');
  if (U === "AT+CGSN") return out("490154203237518\nOK");
  if (U === "AT+CIMI") return out("310260000000001\nOK");
  if (U === "AT+CGMM" || U === "AT+GMR") return out("SIMCOM SIM800-sim\nRevision 1.0\nOK");
  if (U === "AT+CMGF=1") { s.textMode = true; return out("OK   (SMS text mode)"); }
  if (U === "AT+CMGF=0") { s.textMode = false; return out("OK   (PDU mode)"); }
  if ((m = line.match(/^AT\+CMGS="?(\+?\d[\d\s-]*)"?$/i))) {
    if (!s.textMode) return out("ERROR   (set text mode first: AT+CMGF=1)");
    const st = cellRegStat(s); if (st !== 1 && st !== 5) return out("ERROR   (not registered — check AT+CREG?)");
    s.smsPending = m[1].replace(/[\s-]/g, "");
    return out("> enter the message text on the next line (or 'ESC' to cancel)");
  }
  if (U === 'AT+CMGL="ALL"' || U === "AT+CMGL=ALL") {
    if (!s.msgs.length) return out("OK   (no messages stored)");
    const lines = s.msgs.map((mm) => '+CMGL: ' + mm.idx + ',"' + (mm.dir === "recv" ? (mm.read ? "REC READ" : "REC UNREAD") : "STO SENT") + '","' + mm.num + '"\n' + mm.text);
    return out(lines.join("\n") + "\nOK");
  }
  if ((m = U.match(/^AT\+CMGR=(\d+)$/))) { const mm = s.msgs.find((x) => x.idx === +m[1]); if (!mm) return out("+CME ERROR: invalid memory index"); mm.read = true; return out('+CMGR: "' + (mm.dir === "recv" ? "REC READ" : "STO SENT") + '","' + mm.num + '"\n' + mm.text + "\nOK"); }
  if ((m = U.match(/^AT\+CMGD=(\d+)$/))) { const i = s.msgs.findIndex((x) => x.idx === +m[1]); if (i < 0) return out("+CME ERROR: invalid memory index"); s.msgs.splice(i, 1); return out("OK   (deleted)"); }
  if (/^ATD\+?\d[\d\s-]*;?$/i.test(line)) { const st = cellRegStat(s); if (st !== 1 && st !== 5) return out("NO CARRIER   (not registered)"); s.call = "active"; s.callNum = line.replace(/^ATD/i, "").replace(/;$/, "").trim(); return out("OK   (call connected — simulated, no real call)", "call to " + s.callNum); }
  if (U === "ATH") { if (s.call === "idle") return out("OK   (no active call)"); const n = s.callNum; s.call = "idle"; s.callNum = null; return out("OK   (hung up)", "ended call" + (n ? " to " + n : "")); }
  if (U === "AT+CLCC") return out(s.call === "active" ? '+CLCC: 1,0,0,0,0,"' + (s.callNum || "") + '",129\nOK' : "OK   (no active calls)");
  return out("ERROR");
}

// ---------------- tests ----------------
let ok = true;
const t = (name, cond, extra) => { if (!cond) { ok = false; console.log("FAIL", name, extra || ""); } else console.log("ok  ", name); };

const T0 = 1000000;
let st = cellInit(T0);

// 1) handshake
t("AT -> OK", cellStep(st, "AT", T0).reply === "OK");

// 2) registration over time
t("searching before 6s", cellStep(st, "AT+CREG?", T0 + 1000).reply.indexOf("+CREG: 0,2") === 0);
let r = cellStep(st, "AT+CREG?", T0 + 7000);
st = r.state;
t("home after 6s", r.reply.indexOf("+CREG: 0,1") === 0, r.reply);

// 3) SMS requires text mode + registration
t("CMGS before textmode errors", cellStep(st, 'AT+CMGS="+15551234567"', T0 + 8000).reply.indexOf("ERROR") === 0);
r = cellStep(st, "AT+CMGF=1", T0 + 8000); st = r.state;
r = cellStep(st, 'AT+CMGS="+15551234567"', T0 + 8100); st = r.state;
t("CMGS prompts with >", r.reply.indexOf(">") === 0, r.reply);
r = cellStep(st, "Hello world", T0 + 8200); st = r.state;
t("body stores + CMGS idx", r.reply.indexOf("+CMGS: 1") === 0, r.reply);
r = cellStep(st, 'AT+CMGL="ALL"', T0 + 8300); st = r.state;
t("CMGL lists sent msg", r.reply.indexOf('+CMGL: 1,"STO SENT","+15551234567"') === 0 && r.reply.indexOf("Hello world") > 0, r.reply);
r = cellStep(st, "AT+CMGR=1", T0 + 8400); st = r.state;
t("CMGR reads msg", r.reply.indexOf("Hello world") > 0, r.reply);
r = cellStep(st, "AT+CMGD=1", T0 + 8500); st = r.state;
t("CMGD deletes", r.reply.indexOf("OK") === 0 && st.msgs.length === 0, r.reply);

// 4) incoming SMS arrives over time (scheduled at init+21s)
r = cellStep(st, "AT", T0 + 22000); st = r.state;
t("incoming URC +CMTI", r.reply.indexOf('+CMTI: "SM",') === 0, r.reply);
r = cellStep(st, 'AT+CMGL="ALL"', T0 + 22100); st = r.state;
t("incoming is REC UNREAD", r.reply.indexOf("REC UNREAD") > 0, r.reply);

// 5) PIN flow
let p = cellInit(T0); p.pin = "sim_pin"; p.reg = "none";
t("CPIN? locked", cellStep(p, "AT+CPIN?", T0).reply.indexOf("+CPIN: SIM PIN") === 0);
r = cellStep(p, "AT+CPIN=0000", T0); t("wrong PIN", r.reply.indexOf("incorrect PIN") > 0, r.reply);
r = cellStep(p, "AT+CPIN=1234", T0); t("right PIN unlocks", r.reply.indexOf("OK") === 0 && r.state.pin === "ready", r.reply);

// 6) call state machine
r = cellStep(st, "ATD+15551234567;", T0 + 23000); st = r.state;
t("dial connects", r.reply.indexOf("OK") === 0 && st.call === "active", r.reply);
r = cellStep(st, "AT+CLCC", T0 + 23100); t("CLCC shows call", r.reply.indexOf("+CLCC: 1") === 0, r.reply);
r = cellStep(st, "ATH", T0 + 23200); st = r.state; t("hangup", r.reply.indexOf("hung up") > 0 && st.call === "idle", r.reply);

// 7) radio off blocks, back on re-searches
r = cellStep(st, "AT+CFUN=0", T0 + 24000); st = r.state; t("radio off", st.radio === false);
t("blocked when off", cellStep(st, "AT+CSQ", T0 + 24100).reply.indexOf("ERROR") === 0);
r = cellStep(st, "AT+CFUN=1", T0 + 24200); st = r.state; t("radio on re-searches", st.reg === "searching");

console.log(ok ? "\nALL PASS" : "\nFAILURES");
process.exit(ok ? 0 : 1);
