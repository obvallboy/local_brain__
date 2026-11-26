// SPI NOR flash + BIOS write-protection emulator.
//
// Models the real obstacle you hit when flashing your OWN laptop's BIOS chip
// (coreboot, a modded BIOS, bricked-firmware recovery, or clearing a forgotten
// supervisor password): the "BIOS lock" is a *stack* of write protections, not
// one switch. This emulates them so you can learn exactly what blocks a flash
// and the order you clear them in. No real hardware is touched; the real-world
// counterpart is flashrom + an external SPI programmer (see device-bench/README).
//
// The protection layers, from the array outward:
//   1. WEL  — write-enable latch; every program/erase needs a WREN (06h) first.
//   2. BP   — status-register block-protect bits; protect a range of the array.
//   3. SRP+WP# — the WP# pin locks the status register so BP can't be cleared.
//   4. BLE/FLOCKDN — the chipset's in-system BIOS lock (SMM NAKs writes); an
//      EXTERNAL programmer talks to the chip directly and never sees this layer.
// Real flow to flash a locked laptop BIOS you own: attach an external programmer
// (bypasses BLE) → control WP# (deassert) → clear BP (unlock) → WREN → flash.

function spiInit() {
  return {
    chip: "W25Q64FV", mfg: "Winbond", jedec: "EF 40 17", sizeMiB: 8,
    wel: 0,          // write-enable latch (06h WREN sets it; a write clears it)
    wp: 1,           // WP# pin asserted? 1 = hardware write-protect active
    srp: 1,          // SRP0 status-register-protect bit (with WP# → SR is locked)
    bp: 3,           // BP[2:0] block-protect bits (nonzero protects the BIOS range)
    ble: 1,          // chipset BIOS Lock Enable / FLOCKDN (in-system software lock)
    external: 0,     // external SPI programmer (e.g. CH341A clip) attached?
    dirty: false, flashed: false,
    pwd: "SVC-7F3A", pwdCleared: false,   // a supervisor password stored in flash
    regions: [
      { name: "descriptor", start: 0x000000, end: 0x000FFF },
      { name: "ME",         start: 0x001000, end: 0x5FFFFF },
      { name: "BIOS",       start: 0x600000, end: 0x7FFFFF },
    ],
  };
}

function spiHex(n) { return "0x" + (n >>> 0).toString(16).toUpperCase().padStart(6, "0"); }
function spiSize(s) { return s.sizeMiB * 1024 * 1024; }
function spiRegionAt(s, addr) { return (s.regions || []).find((r) => addr >= r.start && addr <= r.end) || null; }
function spiBiosStart(s) { const b = (s.regions || []).find((r) => r.name === "BIOS"); return b ? b.start : 0x600000; }
function spiProtectedAt(s, addr) { return (s.bp || 0) > 0 && addr >= spiBiosStart(s); }   // BP covers the BIOS region
function spiSRLocked(s) { return !!(s.srp && s.wp); }   // SRP0 + WP# asserted → status register is read-only
function spiPwdAddr(s) { return spiBiosStart(s) + 0x1F0000; }   // where the supervisor password lives

function spiStatusStr(s) {
  return "SR1  WIP=0  WEL=" + (s.wel ? 1 : 0) + "  BP[2:0]=" + (s.bp & 7) + "  SRP0=" + (s.srp ? 1 : 0) +
    "\n  WP# pin        : " + (s.wp ? "ASSERTED (SR locked)" : "released") +
    "\n  array protect  : " + ((s.bp || 0) > 0 ? "BP covers " + spiHex(spiBiosStart(s)) + "–" + spiHex(spiSize(s) - 1) + " (BIOS region)" : "none (BP=0)") +
    "\n  chipset BLE    : " + (s.ble ? "LOCKED (FLOCKDN — in-system writes NAK'd)" : "open") +
    "\n  programmer     : " + (s.external ? "EXTERNAL (direct SPI — bypasses chipset BLE)" : "in-system (host CPU / SMM path)");
}

// Why a program/erase at `addr` is refused, or "" if it is allowed.
function spiWriteBlock(s, addr) {
  if (!s.wel) return "WEL not set — send WREN (06h) before any program/erase.";
  if (s.ble && !s.external) return "chipset BIOS lock active (BLE/FLOCKDN): in-system write to " + spiHex(addr) + " NAK'd by SMM. Attach an external programmer, or clear BLE before FLOCKDN at boot.";
  if (spiProtectedAt(s, addr)) return "status-register block-protect (BP=" + (s.bp & 7) + ") covers " + spiHex(addr) + " — clear BP first ('unlock').";
  return "";
}

function spiStep(state, raw) {
  const s = state && state.regions ? JSON.parse(JSON.stringify(state)) : spiInit();
  const line = String(raw == null ? "" : raw).trim();
  const out = (reply, status) => ({ state: s, reply, status });
  if (!line) return out("");
  const parts = line.split(/\s+/);
  const cmd = parts[0].toLowerCase();
  const arg = parts.slice(1);
  const hexArg = (t) => { if (t == null) return NaN; t = String(t).replace(/^0x/i, ""); return parseInt(t, 16); };

  if (cmd === "help" || cmd === "?")
    return out(
      "An SPI NOR flash chip (the laptop's BIOS lives here) + its write protections.\n" +
      "IDENTIFY: id (9Fh) · status (05h) · regions · read <addr> [len] (03h) · dump\n" +
      "WRITE:    wren (06h) · write <addr> <hex> (02h) · erase <addr> (20h) · flash <img>\n" +
      "LOCKS:    external on|off (attach SPI programmer) · wp on|off (WP# pin) · lock on|off (chipset BLE) · unlock (clear BP)\n" +
      "RECOVER:  findpass · clearpass   (clear a forgotten supervisor password on your own machine)\n" +
      "Goal: flash the BIOS while it's locked — work out the order the protections come off.");

  if (cmd === "id" || cmd === "9f" || cmd === "jedec")
    return out("RDID (9Fh) → " + s.jedec + "   = " + s.mfg + " " + s.chip + "  (" + s.sizeMiB + " MiB / " + (s.sizeMiB * 8) + " Mbit)", "read JEDEC id");

  if (cmd === "status" || cmd === "05" || cmd === "sr")
    return out("RDSR (05h):\n  " + spiStatusStr(s), "read status register");

  if (cmd === "regions" || cmd === "map" || cmd === "layout") {
    const rows = ["Flash layout (" + s.sizeMiB + " MiB):"];
    for (const r of s.regions) {
      const prot = r.name === "BIOS" && (s.bp || 0) > 0 ? "  🔒 BP-protected" : (s.ble ? "  🔒 BLE" : "");
      rows.push("  " + spiHex(r.start) + "–" + spiHex(r.end) + "  " + r.name + prot);
    }
    rows.push("supervisor password stored at " + spiHex(spiPwdAddr(s)) + " (in the BIOS region)");
    return out(rows.join("\n"));
  }

  if (cmd === "read" || cmd === "03") {
    const addr = hexArg(arg[0]); if (isNaN(addr)) return out("usage: read <addr-hex> [len]   e.g. read 0x600000 16");
    if (addr < 0 || addr >= spiSize(s)) return out("read: " + spiHex(addr) + " out of range (chip is " + s.sizeMiB + " MiB)");
    const reg = spiRegionAt(s, addr);
    // The ME region is hidden from the host in-system, but an external programmer dumps it raw.
    if (reg && reg.name === "ME" && !s.external) return out("03h ← " + spiHex(addr) + ": FF FF FF FF FF FF FF FF   (ME region reads 0xFF in-system — dump it with an external programmer)");
    if (reg && reg.name === "BIOS" && addr >= spiPwdAddr(s) && addr < spiPwdAddr(s) + 16) {
      const bytes = s.pwdCleared ? "FF FF FF FF FF FF FF FF" : Array.from(s.pwd).map((c) => c.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0")).join(" ");
      return out("03h ← " + spiHex(addr) + ": " + bytes + (s.pwdCleared ? "   (erased)" : "   ← supervisor password, in cleartext"), "read " + spiHex(addr));
    }
    return out("03h ← " + spiHex(addr) + ": " + "A5 5A " + (reg ? reg.name.slice(0, 2).toUpperCase() : "FF") + " 01 FF FF FF FF  (" + (reg ? reg.name : "unmapped") + ")", "read " + spiHex(addr));
  }

  if (cmd === "wren" || cmd === "06") { s.wel = 1; return out("WREN (06h) → WEL = 1 (one program/erase is now armed)"); }
  if (cmd === "wrdi" || cmd === "04") { s.wel = 0; return out("WRDI (04h) → WEL = 0"); }

  if (cmd === "external" || cmd === "programmer" || cmd === "ext") {
    const a = (arg[0] || "").toLowerCase(); s.external = a === "off" ? 0 : a === "on" ? 1 : s.external ? 0 : 1;
    return out(s.external
      ? "🔌 external SPI programmer (CH341A-style clip) ATTACHED. You now talk to the chip directly — the chipset BIOS lock (BLE/FLOCKDN) no longer applies. The chip's own WP#/BP still do."
      : "external programmer detached — back to the in-system (host/SMM) path.",
      s.external ? "attached external programmer" : "detached programmer");
  }

  if (cmd === "wp") {
    const a = (arg[0] || "").toLowerCase(); s.wp = a === "off" ? 0 : a === "on" ? 1 : s.wp ? 0 : 1;
    return out("WP# pin " + (s.wp ? "ASSERTED — status register is now locked (BP bits can't change)" : "released — status register is writable (you can clear BP now)") +
      (!s.wp && !s.external ? "\n  note: in a real laptop you control WP# by holding the pin on the chip — usually with the external clip." : ""),
      "WP# " + (s.wp ? "asserted" : "released"));
  }

  if (cmd === "lock") {
    const a = (arg[0] || "").toLowerCase(); s.ble = a === "off" ? 0 : a === "on" ? 1 : s.ble ? 0 : 1;
    return out("chipset BIOS lock (BLE/FLOCKDN) " + (s.ble ? "set — in-system BIOS writes are NAK'd by SMM" : "cleared — in-system writes allowed (normally only settable before FLOCKDN latches at boot)"));
  }

  if (cmd === "unlock") {
    if (spiSRLocked(s)) return out("WRSR (01h) to clear BP → DENIED: the status register is hardware-locked (SRP0=1 + WP# asserted). Release WP# first ('wp off').");
    if ((s.bp || 0) === 0) return out("BP already 0 — the array is unprotected.");
    s.bp = 0; return out("WRSR (01h) → BP[2:0] = 0. Block-protect cleared; the BIOS region is now writable.", "cleared block-protect");
  }

  if (cmd === "write" || cmd === "02") {
    const addr = hexArg(arg[0]); if (isNaN(addr)) return out("usage: write <addr-hex> <bytes-hex>   e.g. write 0x600000 DEADBEEF");
    const why = spiWriteBlock(s, addr); if (why) return out("02h page program " + spiHex(addr) + " → DENIED: " + why);
    s.wel = 0; s.dirty = true; return out("02h page program " + spiHex(addr) + " → OK (" + (arg[1] || "FF").length / 2 + " bytes); WEL auto-cleared", "programmed " + spiHex(addr));
  }

  if (cmd === "erase" || cmd === "20" || cmd === "se") {
    const addr = hexArg(arg[0]); if (isNaN(addr)) return out("usage: erase <addr-hex>   (4 KiB sector)");
    const why = spiWriteBlock(s, addr); if (why) return out("20h sector erase " + spiHex(addr) + " → DENIED: " + why);
    s.wel = 0; s.dirty = true; return out("20h sector erase " + spiHex(addr) + " → OK (4 KiB → 0xFF)", "erased " + spiHex(addr));
  }

  if (cmd === "dump" || cmd === "readback") {
    return out("reading whole chip (" + s.sizeMiB + " MiB) → bios_backup.bin\n  " + (s.external
      ? "external programmer: full raw image incl. descriptor + ME + BIOS. Always back up before you flash."
      : "in-system: ME region reads 0xFF (hidden); attach an external programmer for a complete dump."), "dumped the chip");
  }

  if (cmd === "flash" || cmd === "write-image") {
    const img = arg[0] || "bios_mod.bin";
    const why = spiWriteBlock(s, spiBiosStart(s));
    if (why) return out("flashing '" + img + "' → ABORTED at " + spiHex(spiBiosStart(s)) + ": " + why +
      "\n  (this is the 'BIOS lock'. Order to clear it: external on → wp off → unlock → wren → flash)");
    s.flashed = true; s.wel = 0; s.dirty = false;
    return out("flashing '" + img + "' …\n  erase BIOS region → write → readback verify … VERIFIED ✓\n  BIOS flashed. Power-cycle to boot the new firmware.", "flashed the BIOS");
  }

  if (cmd === "findpass") {
    return out("scanning the BIOS region for a stored supervisor password …\n  found an ASCII blob at " + spiHex(spiPwdAddr(s)) +
      (s.pwdCleared ? " — already erased (0xFF)." : ": \"" + s.pwd + "\"  (modern laptops keep the password in the SPI flash, not the CMOS battery — that's why pulling the coin cell doesn't clear it)"),
      "located the password region");
  }

  if (cmd === "clearpass") {
    const why = spiWriteBlock(s, spiPwdAddr(s));
    if (why) return out("clearing the password region at " + spiHex(spiPwdAddr(s)) + " → DENIED: " + why +
      "\n  (same lock as a flash — clear the protections first. On your own laptop a forgotten supervisor password is cleared exactly this way: dump, erase the blob, reflash.)");
    s.pwdCleared = true; s.wel = 0; s.dirty = true;
    return out("erased the password region at " + spiHex(spiPwdAddr(s)) + " → 0xFF. Supervisor password cleared; reflash and reboot.", "cleared the stored password");
  }

  return out("unknown command — type 'help'. (JEDEC opcodes work too: 9F, 05, 06, 02, 20, 03)");
}

if (typeof module !== "undefined" && module.exports) module.exports = { spiInit, spiStep, spiHex, spiProtectedAt, spiSRLocked, spiWriteBlock };

// ---------------- tests ----------------
if (typeof require !== "undefined" && require.main === module) {
  let ok = true;
  const t = (name, cond, extra) => { if (!cond) { ok = false; console.log("FAIL", name, extra || ""); } else console.log("ok  ", name); };
  const run = (s, cmd) => spiStep(s, cmd);

  // identity + status
  let s = spiInit();
  t("id reports W25Q64 / EF 40 17", run(s, "id").reply.indexOf("EF 40 17") > -1 && run(s, "9F").reply.indexOf("W25Q64") > -1);
  t("starts fully locked", s.ble === 1 && s.wp === 1 && s.bp === 3 && s.external === 0);

  // a naive in-system flash is blocked by the chipset BIOS lock
  let r = run(s, "wren"); s = r.state;
  r = run(s, "flash bios_mod.bin"); s = r.state;
  t("in-system flash blocked by BLE", r.reply.indexOf("ABORTED") > -1 && r.reply.indexOf("BIOS lock") > -1 && s.flashed === false);

  // external programmer bypasses BLE, but the chip's WP#/BP still block
  r = run(s, "external on"); s = r.state;
  r = run(s, "wren"); s = r.state;
  r = run(s, "flash bios_mod.bin"); s = r.state;
  t("external bypasses BLE but BP still blocks", r.reply.indexOf("block-protect") > -1 && s.flashed === false);

  // can't clear BP while WP# is asserted (SR hardware-locked)
  r = run(s, "unlock"); s = r.state;
  t("unlock denied while WP# asserted", r.reply.indexOf("DENIED") > -1 && s.bp === 3);

  // release WP#, clear BP, then flash succeeds
  r = run(s, "wp off"); s = r.state;
  r = run(s, "unlock"); s = r.state;
  t("BP cleared after WP# released", s.bp === 0);
  r = run(s, "wren"); s = r.state;
  r = run(s, "flash bios_mod.bin"); s = r.state;
  t("flash verifies once all locks are off", r.reply.indexOf("VERIFIED") > -1 && s.flashed === true);

  // write needs WREN each time (WEL auto-clears)
  let s2 = spiInit(); s2.ble = 0; s2.wp = 0; s2.bp = 0;   // fully open
  r = run(s2, "write 0x600000 DEADBEEF"); s2 = r.state;
  t("write without WREN is refused", r.reply.indexOf("WEL not set") > -1);
  r = run(s2, "wren"); s2 = r.state;
  r = run(s2, "write 0x600000 DEADBEEF"); s2 = r.state;
  t("write ok after WREN, WEL auto-clears", r.reply.indexOf("OK") > -1 && s2.wel === 0);

  // forgotten-password recovery: password lives in flash, cleared like any write
  let s3 = spiInit();
  t("findpass shows the password in flash", run(s3, "findpass").reply.indexOf("SVC-7F3A") > -1);
  r = run(s3, "clearpass"); s3 = r.state;
  t("clearpass blocked while locked", r.reply.indexOf("DENIED") > -1 && s3.pwdCleared === false);
  r = run(s3, "external on"); s3 = r.state; r = run(s3, "wp off"); s3 = r.state; r = run(s3, "unlock"); s3 = r.state; r = run(s3, "wren"); s3 = r.state;
  r = run(s3, "clearpass"); s3 = r.state;
  t("clearpass works once unlocked", s3.pwdCleared === true);
  t("password now reads 0xFF", run(s3, "read 0x7F0000").reply.indexOf("FF FF FF FF") > -1);

  // ME region is hidden in-system, visible via external programmer
  let s4 = spiInit();
  t("ME hidden in-system", run(s4, "read 0x001000").reply.indexOf("FF FF FF FF") > -1);
  s4.external = 1;
  t("ME visible with external programmer", run(s4, "read 0x001000").reply.indexOf("ME") > -1);

  console.log(ok ? "\nALL PASS" : "\nFAILURES");
  process.exit(ok ? 0 : 1);
}
