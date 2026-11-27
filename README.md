# local_brain__

**The device-integration lab, consolidated into one repo** — a hands-on toolkit for
reverse-engineering and working with *your own* devices, meant to be wired into a
local AI agent (the "brain").

Three mirrored layers: a safe browser **simulator** to design and practice, the same
logic as real runnable **code** (Python + Node), and a **physical tool** (a Raspberry
Pi) to do it for real. Own-hardware scope throughout — repair, reuse, learning.

## Layout

| Path | What it is |
| --- | --- |
| **`device-integrator/`** | The real, runnable code. Flask hardware inspector + serial console + the **Brain** panel, plus the Python (`integration/`) and Node (`integration-js/`) integration stacks. |
| **`file-cabinet/`** | The local AI behind the Brain panel: a memory organized like a file cabinet, a small local model, honesty labels on every answer. Also runs on its own in a terminal. |
| **`models/`** | Not committed. The Brain's model files, downloaded with `python brain_setup.py`. |
| **`brain_setup.py`** | One-time setup per computer: downloads the Brain's models and calibrates them. |
| **`mobile/`** | **Devy for iPhone** — an Expo (React Native) app that is a phone screen for the Devy server over your LAN or Tailscale. |
| **`ROADMAP.md`** | The living plan: the vision, the unified-language design, and the phases ahead. |
| **`device-bench/`** | The browser **simulator** (snapshot of the live artifact) + runnable engine test suites (`net.js`, `sb8.js`, `cell.js`, `spiflash.js`). Live: <https://claude.ai/artifact/44dTeFdXpHKR7K7jsRbPg7> |
| **`pibench/`** | Turns a **Raspberry Pi** into a reconfigurable hardware tool via *profiles* (`spi-bios`, `i2c-eeprom`, `uart-console`, `aw15r2`) + the Alienware BIOS-unlock runbook. |
| **`.github/workflows/`** | CI for all of the above. |
| **`HANDOFF.md`** | Project pickup notes. |

### `device-integrator/integration/` (Python) and `integration-js/` (Node)
The same control logic in two languages. The **brain** runs a thermostat loop guarded by
**three layers**, each caught by a different injected fault:

| Guard | Catches | Fault |
| --- | --- | --- |
| **integrity** (range / pydantic) | out-of-range garbage (999 °C) | `fuzz` |
| **security** (real HMAC-SHA256) | forged / tampered telemetry | `tamper` |
| **anomaly** (learned, EW mean/variance → z-score) | in-range-but-abnormal readings | `glitch` |

Real libraries: paho-mqtt, pymodbus, requests, pydantic, cryptography, RPi.GPIO (Python);
mqtt, axios, johnny-five, crypto-js (Node).

## Real-world job: unlock a $12 Alienware 15 R2
Board **Compal LA-C912P**, forgotten **system/power-on password** (own hardware, right-to-repair).
BIOS chip identified on the board: **Winbond 25Q128FVSQ at silk `UH4`** (16 MB, 3.3 V, 8-pin SOIC,
top side, left of the PCH — clip-reachable, no board removal). Plan: Pi + SOIC-8 clip on UH4 →
`pibench run aw15r2 read` (verified dump) → clear the password in a copy → write it back →
reassemble. Full steps: [`pibench/runbooks/aw15r2-bios-unlock.md`](pibench/runbooks/aw15r2-bios-unlock.md).
**Status:** torn down, chip confirmed, tooling ready — blocked only on a SOIC-8 clip.

## The local AI: the Brain panel
The Device Integrator now has a **🧠 Brain** panel powered by the [File Cabinet](file-cabinet/README.md):
a local assistant whose memory is split into drawers (facts you teach it, patterns, protected core values,
and a temp drawer that checks real things). Ask "what's plugged in?" and it reads the live device list and
your device labels; every answer says where it came from. It runs fully on your machine.

Set up a computer (laptop or desktop), from the repo root:

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r device-integrator/requirements.txt -r file-cabinet/requirements.txt
python brain_setup.py --check                             # what's installed / missing, and how to fix it
python brain_setup.py --gpu-layers -1                     # models + calibration, once per computer
cd device-integrator && python app.py --gpu-layers -1     # http://127.0.0.1:5000 → 🧠 Brain
```

Each computer keeps its own memory; **Export memory** / **Import memory** in the panel copies it across.
Leave out `--gpu-layers -1` on a machine without an NVIDIA GPU. Without any model, the Brain still runs on
its drawers and rules.

On Windows, `pip install llama-cpp-python` compiles it, which needs Microsoft's "Build Tools for Visual
Studio" (C++ workload); `brain_setup.py --check` explains what's missing.

The thermostat **integration brain** (`device-integrator/integration/brain.py`, `integration-js/brain.js`)
is separate: it controls devices with fixed, tested rules and guards. Run its engine with `--log-to-brain`
and its alerts (corrupt data, forged messages, abnormal readings) go into the Brain's memory, so you can
ask the Brain panel "what went wrong with the sensor today?"

## Sources
Consolidated from `obvallboy/personal-windows-ai-agent` (device-integrator, device-bench) and
`obvallboy/my_piolt_pi5` (pibench); full commit history lives in those repos.
