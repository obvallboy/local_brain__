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
| **`device-integrator/`** | The real, runnable code. Flask hardware inspector + serial console, plus the Python (`integration/`) and Node (`integration-js/`) integration stacks. |
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

## Wiring it into a local agent
The seam for a local model is the **transport-neutral brain** (`device-integrator/integration/brain.py`
and `integration-js/brain.js`) — dependency-free and testable. Feed it device telemetry plus the
guards' verdicts and let the model drive the decisions/commands, swapping the fixed thermostat/anomaly
rules for a learned policy. The Device Bench's "Ask Claude" box is the same idea in the simulator.

## Sources
Consolidated from `obvallboy/personal-windows-ai-agent` (device-integrator, device-bench) and
`obvallboy/my_piolt_pi5` (pibench); full commit history lives in those repos.
