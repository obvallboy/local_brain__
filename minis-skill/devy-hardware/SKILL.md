---
name: devy-hardware
description: Talk to a Devy (Device Integrator) server on the user's Raspberry Pi or computer over the network — ask about plugged-in hardware, scan a serial port's baud rate, identify a device on the Wi-Fi by IP, and use Devy's memory. Use when the user asks about their own hardware, dev boards, serial ports, or network devices, or mentions Devy or their Pi.
---

# Devy hardware bridge

Devy runs on the user's Raspberry Pi or computer — not on the phone. It sees the hardware
plugged into that machine, recognizes dev boards, scans serial ports and network devices,
and remembers facts the user tells it. This skill lets you (the Minis agent) call Devy over
the network and relay its answers. You are the voice; Devy is the hardware brain.

## Setup (once)

Devy must be running on the Pi/computer, reachable from this phone:
- On the Pi/computer: `cd device-integrator && python app.py --host 0.0.0.0`
- In this Linux sandbox: `export DEVY_URL=http://<pi-ip>:5000` (the user's Tailscale or LAN
  IP), and `apk add curl` if curl is missing.

Confirm it: `sh scripts/devy.sh status`. JSON back = connected. A timeout = tell the user to
check the address, that Devy runs with `--host 0.0.0.0`, and that this phone can reach it
(same Wi-Fi, or Tailscale on both).

## Commands (each returns JSON)

- `sh scripts/devy.sh status` — is Devy up, and which model it's running.
- `sh scripts/devy.sh devices` — everything plugged into the Devy computer.
- `sh scripts/devy.sh ask "<message>"` — ask or tell Devy. The reply has a **label**
  (I know / I think / I checked / I remember / I'm not sure / Filed) and **text**.
- `sh scripts/devy.sh serial-scan <port>` — a serial port's baud rate and what's answering
  (e.g. `/dev/ttyUSB0`, a MicroPython prompt, a boot log).
- `sh scripts/devy.sh net-scan <ip>` — identify a device on the Wi-Fi by IP (ESP32, router,
  camera, printer...).

## Rules

- **Always show Devy's label with its answer** — it says how sure Devy is. Never drop it.
- Devy does the thinking about its own hardware. Relay its `text`; do not invent hardware
  facts yourself. If the label is "I'm not sure" or "I don't remember", say so honestly.
- **You cannot touch the hardware from the phone.** Only Devy (on the Pi) reads chips and
  ports. Physical steps — clipping a chip, wiring a board — are the user's to do by hand.
- For a hardware job (dumping a BIOS chip, reading an EEPROM), tell the user Devy runs these
  as guided jobs on the Pi; a live back-and-forth job runner is being added there.
