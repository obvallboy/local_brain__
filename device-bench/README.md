# Device Bench

The **Device Bench** is a browser-based virtual lab: build *simulated/emulated*
devices, put them on a *virtual network*, and run an *automation brain* over
them — all safely, with nothing touching real hardware. It's the design &
fault-testing counterpart to the real code in [`../device-integrator`](../device-integrator).

- **Live artifact (the real thing):** <https://claude.ai/artifact/44dTeFdXpHKR7K7jsRbPg7>
- **Source:** [`device-bench.html`](device-bench.html) — a single self-contained
  file (all CSS/JS inline). This file in git is a **snapshot**; the live artifact
  is the source of truth. To edit, read the current version back first (see below).

It's a **claude.ai Artifact**, not a hostable web app — it needs the claude.ai
runtime for its capabilities (`sample`, `db`, `user`), so you can't just open
`device-bench.html` in a browser and have it work. Opened standalone it shows a
"static preview" empty state.

## Architecture (inside `device-bench.html`)

One IIFE. The important pieces:

- **Engines** (module scope): `sb8*` (a real 8-bit CPU emulator), `cell*` (GSM
  modem state machine), `net*` (virtual network + integration brain + fault
  injection + three guards: integrity, HMAC security, and a **learned anomaly
  detector** — `fuzz`/`tamper`/`glitch` exercise each), and `spi*` (an SPI NOR
  flash / BIOS chip with its real write-protection stack — see below). Mirrored
  as standalone test files in [`engines/`](engines) — run `node engines/net.js`,
  `node engines/spiflash.js`, etc. (each has its own assertions and exits
  non-zero on failure).
- **`TEMPLATES`** — per device *type*: `{label, icon, commands, banner, init,
  summary, handle(state, raw)}`. `handle` is the device's behavior (command →
  reply + new state). Types: `net, mcu (CPU), spiflash (BIOS flash), sensor,
  usb, wifi, cell, windows, gps, motor, i2c`.
- **`FACES`** — per device type: `{render(state) -> html, controls(state) ->
  [{label, cmd|fill}]}`. The visual "screen" + quick buttons.
- **UI pipeline**: `renderStage()` → `renderScreen()` (face) + `renderControls()`
  + `renderLog()`. Devices live in the `sim_devices` db collection.
- **crypto-js** is loaded from cdnjs (`<script src=...crypto-js/4.2.0...>`) and
  used by the `net` engine for HMAC-signed telemetry. Guarded by
  `typeof CryptoJS !== "undefined"` so the engines still run under Node (no crypto
  → security guard no-ops).

## BIOS / SPI flash (the `spiflash` device)

A model of the SPI NOR flash chip that holds a laptop's BIOS, for learning
**firmware flashing on your own hardware** — recovering bricked firmware,
installing coreboot, or clearing a *forgotten* supervisor password. The "BIOS
lock" that blocks a flash is a stack of real write protections, and the emulator
makes you clear them in order:

| Layer | What it is | How you clear it (emulator ↔ real) |
| --- | --- | --- |
| **WEL** | write-enable latch | `wren` (06h) before every program/erase |
| **BP** | status-register block-protect bits | `unlock` (clears BP via 01h) |
| **WP# + SRP0** | the WP# pin locks the status register | `wp off` — hold the pin (usually with the clip) |
| **BLE / FLOCKDN** | the chipset's in-system BIOS lock (SMM NAKs writes) | `external on` — an external programmer talks to the chip directly and never sees this layer |

So the real "flash a locked BIOS you own" flow — which the emulator reproduces —
is `external on → wp off → unlock → wren → flash`. The takeaway it teaches: an
**external SPI programmer** (a CH341A clip, or a Raspberry Pi via `linux_spi`)
bypasses the chipset software lock because it reads/writes the chip's pins
directly; the chip's *own* WP#/BP still apply until you control the WP pin.

**Real-hardware counterpart:** none of this runs in a browser — on real gear you
use [`flashrom`](https://www.flashrom.org/) with a programmer (`flashrom -p ch341a_spi -r backup.bin`
to dump, `-w new.bin` to write). Back up first, keep the original, and only do it
to hardware you own. (Modern laptops store the supervisor password *in the SPI
flash*, which is why pulling the CMOS coin cell doesn't clear it — `findpass` /
`clearpass` demonstrate the dump-edit-reflash recovery.)

## Shared database (the `db` capability)

- `sim_devices` — one doc per device: `{name, type, state, log:[{t,dir,who,text}], t, createdBy}`.
  `t` orders the sidebar (net is `-1`, first). The page renders a device from its
  `state` via `TEMPLATES[type]` + `FACES[type]`.
- `notes` — pinned notes. `state/status` — Claude's status line.

**"Driving a device live"** = writing to its `sim_devices` doc with the
`ArtifactData` tool. The page subscribes with `onSnapshot`, so writes appear
instantly. To generate a realistic run, extract the engine from the HTML, drive
it in Node, and write the resulting `{state, log}` (see HANDOFF.md for the recipe).

## Editing & verifying (the workflow used to build this)

1. **Get current source:** `Artifact` tool `action:"read"` on the URL (writer →
   returns the HTML), or start from `device-bench.html` here.
2. **Edit** the file (scratchpad copy), then **publish**: `Artifact` publish with
   the same `url`. Omit `capabilities` to keep `sample`/`db`/`user`.
3. **Verify before publishing:**
   - `node --check` on the extracted `<script>`.
   - Run the standalone engine tests (`engines/*.js`).
   - **Render check**: build a tiny harness that injects a mock `window.claude`
     (a `db` whose `onSnapshot` returns fixed device docs) and screenshot with
     the preinstalled Playwright/Chromium (`deviceScaleFactor: 2`). This is the
     only way to see the real faces with data, since the artifact can't load in a
     plain browser. (Offline, the crypto-js CDN won't load — security no-ops in
     the screenshot, which is fine; the tamper UI still renders from state.)
4. **Then** drive a demo via `ArtifactData` and `Artifact` `action:"open"`.
