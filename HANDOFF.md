# Handoff — Device Integrator / Device Bench

Written 2026-11-04 to continue this project in a fresh session (prior session's
context was full). Everything below is already built, pushed, and verified.

## 1. What this project is

Two halves that mirror each other:

1. **Device Bench** — a browser **simulator/emulator lab** (a claude.ai Artifact).
   Build virtual devices, put them on a virtual network, run an automation
   "brain", and inject faults — all safe, nothing real. For *designing and
   fault-testing* integration logic.
2. **`device-integrator/`** — the **real code** (this repo). A local hardware
   tool plus Python and Node **integration stacks** using the production
   libraries. For *running* the logic against real brokers / PLCs / hardware.

The honest boundary that drove every design decision: **the Artifact runs in a
locked browser sandbox** — no Python, no real network sockets, no hardware, no
`fetch` to arbitrary hosts (CDN scripts only). So real libraries and real device
access live in the repo, not the page.

## 2. Where everything is

- **Repo:** `obvallboy/personal-windows-ai-agent`
- **Branch:** `claude/device-integrator-app-7gucmh` (all work is here; `main`
  is untouched; no PR opened yet)
- **Device Bench artifact (live):** <https://claude.ai/artifact/44dTeFdXpHKR7K7jsRbPg7>
  (private to the owner; capabilities `sample`, `db`, `user`; currently **Version 15**)

```
device-integrator/
  app.py, integrator/, static/, templates/   # local hardware inspector + serial console (Flask)
  integrator/snapshot.py                      # `python -m integrator.snapshot` → JSON of attached devices
  integration/        # Python stack: paho-mqtt, pymodbus, requests, pydantic, cryptography, RPi.GPIO
  integration-js/     # Node stack: mqtt, axios, johnny-five, crypto-js
  tests/              # pytest (incl. test_integration_*.py)
  requirements.txt, requirements-integration.txt
device-bench/
  device-bench.html   # snapshot of the live Artifact's source (source of truth is the Artifact)
  engines/            # sb8.js (CPU), cell.js (GSM modem), net.js (network+brain) — runnable test suites
  README.md           # Device Bench architecture + edit/verify workflow
.github/workflows/
  device-integrator-ci.yml   # Flask app tests, py 3.11/3.12/3.13
  integration-ci.yml         # installs the REAL python libs, runs integration tests, py 3.11/3.12
  integration-js-ci.yml      # installs the REAL node libs, runs node tests, node 20/22
HANDOFF.md (this file)
```

All three CI workflows were **green** at last push.

## 3. The Device Bench — current state

Device types (each = a `TEMPLATES[type]` behavior + a `FACES[type]` visual):
`net, mcu (CPU emulator), sensor, usb, wifi, cell (GSM emulator), windows, gps,
motor, i2c`. See `device-bench/README.md` for the architecture.

The **`net` device** ("Lab network") is the centerpiece and has the most logic:
- Virtual LAN: gateway, DHCP, DNS, ARP, ping, traceroute, topology map.
- Mixed fleet: **MQTT** sensor (`temp-01`), **Modbus** PLC (`plc-01`, reg 40001 =
  vent), **HTTP** camera (`cam-01`).
- **Integration brain**: toggleable rules (`rules`, `rule on|off <id>`, `tick`,
  `run <n>`). A real **thermostat control loop** (opens/closes the vent to hold
  24–28 °C) plus offline + motion rules.
- **Fault injection**:
  - `fuzz <host> on|off` → corrupt data (999 °C, NaN, malformed). The
    **`integrity`** guard (pydantic-style range check) rejects it, raises an
    INTEGRITY alert, holds last-good — never acts on garbage, never crashes.
  - `tamper <host> on|off` → forge the message so its **HMAC** (crypto-js,
    real `CryptoJS.HmacSHA256`) no longer verifies. The **`security`** guard
    rejects it with a SECURITY alert.
  - (repo stacks) a third **learned anomaly guard** sits beside integrity: a
    stdlib online detector (`integration/anomaly.py`, `integration-js/anomaly.js`;
    EW mean/variance → z-score) that catches *in-range-but-abnormal* readings the
    range check misses — `python -m integration.engine --sim --anomaly-at 20`.
    Not yet surfaced in the Bench `net` engine (possible next step).
  - Both guards are toggleable (`rule off integrity` / `rule off security`), so
    you can demonstrate the failure mode (brain gets fooled) vs. the defense.

Milestones completed, in order: device types → turned simulators into real
**emulators** (SB8 CPU runs real machine code; cell modem is a real state
machine) → **mobile layout fix** (on phones the device *screen* leads, list
below) → **virtual network** → **brain** (automations) → **fuzz + data-integrity
guard** → **tamper + HMAC security guard** → **repo integration stacks**.

### How to continue editing the Bench

The source of truth is the **live Artifact**. To change it:
1. `Artifact` `action:"read"` the URL → returns the HTML (you're a writer).
2. Edit in scratchpad; keep the single-file structure (inline CSS/JS).
3. Verify: `node --check` the `<script>`; run `device-bench/engines/*.js`; build a
   Playwright render harness (mock `window.claude.use("db")` returning fixed
   `sim_devices` docs) and screenshot. Details in `device-bench/README.md`.
4. `Artifact` publish same `url`, **omit `capabilities`** (keeps sample/db/user),
   omit `icon`.
5. **Drive a demo live:** extract the engine from the HTML into a Node module,
   add `global.CryptoJS = {HmacSHA256:(m,k)=>({toString:()=>require("crypto").createHmac("sha256",String(k)).update(String(m)).digest("hex")})}`
   so the HMAC runs, drive `netStep(state, cmd, now)` through a command sequence,
   then write the resulting `{name,type,state,log}` to `sim_devices/net1` with
   `ArtifactData` (pin `if_version` — read it first; it was **version 4** after
   the tamper demo). The page's `onSnapshot` shows it instantly.

### Gotchas
- **Device doc writes need `if_version`** (read current version first; the live
  page bumps it when the user interacts). `board1` was deleted by the user early
  on; the CPU device is `cpu1`; the net device is `net1`.
- Mobile: `@media (max-width:820px)` makes the layout natural-scroll with
  `.bench` first and selecting a device `scrollIntoView`s it. Don't revert to the
  fixed-height grid on phones.
- crypto-js is a CDN `<script>` — in an **offline** Playwright harness it won't
  load, so the security guard no-ops there (fine; the UI still renders tamper
  state from the doc).

## 4. The repo integration stacks

- **Python** (`device-integrator/integration/`): `brain.py` (stdlib, testable),
  `transports.py` (SimTransport + paho/pymodbus/requests adapters, lazy import),
  `models.py` (pydantic validation = the integrity guard), `security.py`
  (cryptography HMAC), `gpio.py` (RPi.GPIO), `engine.py`
  (`python -m integration.engine --sim --fuzz-after 8`).
- **Node** (`device-integrator/integration-js/`): same shape with mqtt / axios /
  johnny-five / crypto-js; `node engine.js --sim`; `node --test`.
- Pure logic (brain/engine) is testable with no libraries; pydantic/cryptography
  (Python) and crypto-js (Node) tests **skip locally, run in CI** (CI installs the
  real libs and proves they work). In THIS sandbox you can't `pip install` /
  `npm install` (registries blocked) — rely on the stdlib tests + CI.

## 5. Open threads / where the user may go next

The user has been driving this incrementally and likes: build → verify (tests +
screenshot) → drive a live demo → explain. Offered next steps not yet taken:
- Open a **PR** for the branch into `main` (user hasn't said yes yet).
- A **docker-compose** (Mosquitto + a Modbus simulator) to exercise the Node/Python
  transports against a real local broker.
- **Key-rotation** scenario for the HMAC security layer.
- More device types / protocols (CoAP, SNMP, OPC-UA, BACnet) — the brain rules are
  metric-based so new protocols drop in.
- A **rules editor** in the Bench (write `if/then` automations in the UI).

## 6. Conventions
- Commit footer (per session reminder):
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01XN2mYg4dbdcpWVLSLUPPDH`.
- Push with `git push -u origin claude/device-integrator-app-7gucmh` (retry with
  backoff on network errors). Don't push to other branches/repos. **No PR unless
  the user asks.**
- GitHub ops go through the `mcp__github__*` MCP tools (load via ToolSearch).
