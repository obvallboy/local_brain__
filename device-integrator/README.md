# Device Integrator

[![Device Integrator CI](https://github.com/obvallboy/personal-windows-ai-agent/actions/workflows/device-integrator-ci.yml/badge.svg)](https://github.com/obvallboy/personal-windows-ai-agent/actions/workflows/device-integrator-ci.yml)

A **local, browser-based workbench for inspecting and tinkering with hardware
you own.** Plug in a dev board, a USB gadget, a serial adapter — and get a
single place to see what's attached, inspect it in depth, talk to it over a
serial console, and keep your reverse-engineering notes.

> **New to device/IoT integration?** [`LEARNING.md`](LEARNING.md) is a learning
> path tied to this project, linking out to the relevant [roadmap.sh](https://roadmap.sh) roadmaps.

It runs entirely on your own machine, binds to `localhost` by default, and
makes **no outbound network connections**. It only *reads* device information
and exchanges bytes over serial ports you explicitly open — there's no signal
transmission, no input injection, and no remote control.

```
┌──────────── your machine ────────────┐
│  browser  ⇄  Flask app  ⇄  your USB / serial / block / net devices │
└───────────────────────────────────────┘
```

## What it does

- **Discover** everything attached right now:
  - Serial ports (`/dev/ttyUSB*`, `/dev/ttyACM*`, `COM*`) with VID/PID and descriptor strings
  - USB devices — vendor/product IDs, device class, bus/address, serial number
  - Storage / block devices and their mount points & capacity
  - Network interfaces and their addresses
- **Inspect** a device in depth (Linux): full sysfs attribute tree, its USB
  interfaces, the bound kernel driver, and the `dmesg` lines it produced.
- **Serial console** — open a live terminal to a dev board: pick the baud rate,
  send text or raw hex, choose the line ending, and watch incoming bytes
  stream in. The core loop for probing an unknown UART protocol on your own gear.
- **Notes & labels** — give each device a friendly name and keep free-text
  reverse-engineering notes (pinouts, baud rates, decoded bytes). Stored in a
  local JSON file.
- **Export** a JSON snapshot of everything discovered plus your notes.
- **Devy** — the local AI panel (the [File Cabinet](../file-cabinet)). Ask "what's plugged in?" or "is my
  arduino connected?" and it checks the real device list, including the labels you gave devices in Notes.
  Tell it things ("my brother's name is leo") and it remembers them. Every answer is labelled with where it
  came from (*I know*, *I checked*, *I think*, *I remember*, *I'm not sure*), with a "why?" to expand.
  **📁 Drawer 1** shows everything it has filed about you, with a ✕ to delete anything wrong (or just say
  "forget my locker code"). It also **recognizes dev boards**: plug one in and ask "what is this?" or
  "how do I program my Pico?" and it names the board, chip, voltage, baud rate and the tools and languages
  to use — from an offline USB-id list, so it works with no internet. The model runs on your machine; nothing
  is sent anywhere.

## Install & run

```bash
cd device-integrator
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>.

### Turning on the Brain's model (optional)

Without a model the Brain still works on its drawers and rules (facts you teach it, memories, device checks).
For general questions and better understanding, add a local model:

```bash
pip install -r ../file-cabinet/requirements.txt   # llama-cpp-python
python ../brain_setup.py --gpu-layers -1          # download + calibrate the models, once per computer
python app.py --gpu-layers -1
```

`brain_setup.py` puts the models in the repo's `models/` folder, which the app checks automatically, and
calibrates the chat model. `--gpu-layers -1` runs the model on an NVIDIA GPU (needs a CUDA build of llama-cpp-python; see the
File Cabinet README). The models load in the background, so the page opens right away; the Brain panel shows
when they're ready. Its memory is `~/.device-integrator/cabinet.db` on each computer; use **Export memory** /
**Import memory** in the panel to copy it between your laptop and desktop.

Options:

```bash
python app.py --port 8080          # choose a port
python app.py --host 0.0.0.0       # expose on your LAN (opt-in; you'll be warned)
python app.py --gpu-layers -1      # Brain model on the GPU
python app.py --models D:/models   # Brain models from another folder (or --model / --embed for exact files)
```

The same settings can come from the environment: `FILE_CABINET_MODELS`, `FILE_CABINET_MODEL`,
`FILE_CABINET_EMBED`, `FILE_CABINET_GPU_LAYERS`.

### Dependencies

`Flask` is the only hard requirement. `pyserial`, `psutil` and `pyusb` are
optional — without them the app falls back to reading `/sys`, `lsusb` and
device-node globbing, and the serial console needs `pyserial`. The header of
the UI shows which back-ends are active.

> **Permissions (Linux):** reading full USB details and the kernel log may need
> privileges. If `dmesg` is empty, your kernel likely has
> `kernel.dmesg_restrict` on — run the app with the right permissions or add
> your user to the `dialout` group for serial access
> (`sudo usermod -aG dialout $USER`, then log out/in).

## Bringing devices into Glass Box

[Glass Box](https://claude.ai/artifact/44dTeFdXpHKR7K7jsRbPg7) is a shared
claude.ai sandbox where you and Claude can talk through what to do with your
hardware. A browser page can't reach USB or serial ports, so **this local app
does the hardware access** and hands Glass Box a snapshot to reason about.

Export a snapshot without even starting the server:

```bash
python -m integrator.snapshot            # pretty JSON
python -m integrator.snapshot --compact  # single line, easy to copy
python -m integrator.snapshot -o devices.json
```

Then in Glass Box open the **Devices → Import** panel and paste the JSON (or
upload `devices.json`). The running server's `GET /api/export` returns the same
shape if you'd rather download it from the web UI. Once imported, ask Claude
"what can we do with these?" — it reads your real inventory and suggests how to
probe or use each device with this tool (serial console, descriptor inspection,
and so on). Nothing is controlled remotely; Glass Box is for seeing and planning.

## Real integration stack (`integration/`)

The [Device Bench](https://claude.ai/artifact/44dTeFdXpHKR7K7jsRbPg7) simulates a
networked fleet and an automation "brain" in the browser. `integration/` is the
**production counterpart**: the same logic, written against the real libraries
you'd use on actual hardware.

| Concern | Library |
| --- | --- |
| MQTT telemetry | **paho-mqtt** |
| Modbus/TCP PLC registers | **pymodbus** |
| HTTP / REST devices | **requests** |
| Physical GPIO (on a Pi) | **RPi.GPIO** |
| Data-integrity validation | **pydantic** |
| Signed telemetry | **cryptography** |

The control logic (`integration/brain.py`) is pure stdlib and transport-neutral —
the thermostat loop and the data-integrity guard from the Bench, as real code.
The library adapters (`transports.py`, `models.py`, `security.py`, `gpio.py`)
import their dependency lazily, so the package loads and the **simulator runs
with no libraries and no hardware**:

```bash
python -m integration.engine --sim --ticks 24 --fuzz-after 8
```

That prints the control loop tick by tick, then injects corrupt data and shows
the integrity guard rejecting it (holding the last good value) instead of acting
on a 999 °C reading.

The brain runs **two guards** in order:

1. **Integrity** (`integration/models.py`, pydantic) — rejects *out-of-range*
   garbage like 999 °C or NaN.
2. **Learned anomaly** (`integration/anomaly.py`, pure stdlib) — a lightweight
   online detector (EW mean/variance → z-score) that learns the sensor's normal
   behaviour and flags readings that are *in range but abnormal for this sensor*.
   A fixed threshold can't catch a 45 °C glitch on a sensor that normally sits at
   25 °C; this does, and holds last-good instead of opening the vent on it:

   ```bash
   python -m integration.engine --sim --ticks 30 --anomaly-at 20            # caught
   python -m integration.engine --sim --ticks 30 --anomaly-at 20 --no-anomaly  # fools the brain
   ```

   Add `--log-to-brain` and the alerts are also written into the Brain's memory, so the Brain panel can
   answer "what went wrong with the sensor today?" from what actually happened:

   ```bash
   python -m integration.engine --sim --fuzz-after 8 --log-to-brain
   ```

   It's the honest first step toward the learned models on the ML/MLOps tracks in
   [`LEARNING.md`](LEARNING.md) — same `check() → (is_anomaly, score)` interface if
   you later swap in a trained model. Mirrored in Node as `integration-js/anomaly.js`.

To drive **real** devices, install the stack and point the transports at your
broker / PLC / camera:

```bash
pip install -r requirements-integration.txt
```

```python
from integration.brain import Brain, BrainConfig
from integration.transports import MqttTransport, ModbusTransport

sensor = MqttTransport(host="192.168.1.10", topic="site/temp"); sensor.connect()
plc = ModbusTransport(host="192.168.1.11"); plc.connect()
brain = Brain(BrainConfig())

while True:
    for cmd in brain.step(sensor.read_sensor()):
        if cmd.action == "write_register":
            plc.write_register(cmd.args["register"], cmd.args["value"])
```

> The browser artifact can't run any of this — Python, real sockets, and GPIO
> need a real machine. The Bench is for designing and fault-testing the logic;
> this package is for running it. Every push runs the integration tests against
> the real libraries in CI
> ([`integration-ci.yml`](../.github/workflows/integration-ci.yml)).

### Node twin (`integration-js/`)

The same engine in Node, for JavaScript shops:

| Concern | Library |
| --- | --- |
| MQTT telemetry | **mqtt** |
| HTTP / REST devices | **axios** |
| Board / Arduino GPIO | **johnny-five** |
| Signed telemetry | **crypto-js** |

```bash
cd integration-js
node engine.js --sim --ticks 24 --fuzz-after 8   # no install needed for the sim
npm install && npm test                           # install the real libs + run tests
```

`crypto-js` is the one library here that also runs in the browser, so the Device
Bench itself uses it to sign and verify telemetry on-screen. Node CI:
[`integration-js-ci.yml`](../.github/workflows/integration-js-ci.yml).

## Layout

```
device-integrator/
├── app.py                     Flask app + JSON API
├── integrator/
│   ├── discovery.py           enumerate serial / USB / storage / network (read-only)
│   ├── details.py             sysfs attribute trees + dmesg filtering
│   ├── serialconsole.py       serial session manager (injectable transport)
│   ├── notes.py               per-device notes/labels (JSON persistence)
│   └── assistant.py           hosts the File Cabinet AI (the Brain panel)
├── templates/index.html       dashboard shell
├── static/                    styles.css, app.js
└── tests/                     pytest suite (serial console exercised over a PTY)
```

## API

| Method   | Route                      | Purpose                                    |
| -------- | -------------------------- | ------------------------------------------ |
| `GET`    | `/api/devices`             | Full discovery snapshot                    |
| `GET`    | `/api/capabilities`        | Which back-ends are available              |
| `GET`    | `/api/usb/detail`          | sysfs attrs, interfaces, driver, dmesg     |
| `GET`    | `/api/dmesg?token=…`       | Filtered kernel-log lines                  |
| `GET/POST/DELETE` | `/api/notes`      | Read / set / delete device notes           |
| `POST`   | `/api/serial/open`         | Open a serial session `{port, baud}`       |
| `GET`    | `/api/serial/<id>/read`    | Poll new bytes since a sequence number     |
| `POST`   | `/api/serial/<id>/write`   | Send text or hex `{data, hex, line_ending}`|
| `POST`   | `/api/serial/<id>/close`   | Close a session                            |
| `GET`    | `/api/export`              | Download a JSON snapshot + notes           |
| `GET`    | `/api/brain/status`        | Brain model, meaning-matching, memory file |
| `POST`   | `/api/brain/ask`           | Ask or tell Devy `{message}`; slash commands work too |
| `GET`    | `/api/brain/serial-scan`   | Find a serial port's baud and recognize what's answering `{port}` |
| `GET`    | `/api/brain/facts`         | What's filed in drawer 1                   |
| `DELETE` | `/api/brain/facts/<id>`    | Forget one drawer-1 fact                   |
| `GET`    | `/api/brain/export`        | Download what the Brain has learned        |
| `POST`   | `/api/brain/import`        | Merge in an export (core memories wait for approval) |

### Guided jobs (the model does the digital part)

A **guided job** is a hardware task where you do the physical steps and the Brain does the digital
ones. The first is dumping the Alienware BIOS chip (`integrator/hardware_jobs.py`, built on the pibench
`aw15r2` profile). The engine (`filecabinet/jobs.py`) runs the safe digital steps itself — probe, read
twice, verify, back up — and only stops to ask you for a **physical** action ("clip the chip, say done")
or a plain-language **"go"** before anything irreversible (writing a chip). It narrates every step, and
catches a bad read instead of trusting it. Try the walkthrough with a simulated flasher:

```python
from integrator.hardware_jobs import SimFlashrom, bios_dump_job
from filecabinet.jobs import Session
s = Session(bios_dump_job(), SimFlashrom()); print(s.start().say)
```

### Serial console helper

Devy can look at a serial port and tell you its baud rate and what's answering (a MicroPython `>>>`
prompt, a Linux login, U-Boot, an ESP boot log, a GPS...), with a plain next step. The logic is in
`filecabinet/serialscan.py` (offline, tested); `integrator/serial_help.scan(port)` runs it on a real
port with pyserial. `GET /api/brain/serial-scan?port=/dev/ttyUSB0` returns the summary.

## Tests

```bash
pip install -r requirements.txt
pytest
```

The serial console is tested against a PTY-backed transport, so the full
open → read → write → close lifecycle runs without any physical device.

Every push and pull request runs the full suite (including the Flask API
tests) on Python 3.11 / 3.12 / 3.13 via GitHub Actions — see
[`.github/workflows/device-integrator-ci.yml`](../.github/workflows/device-integrator-ci.yml).

## Scope

This tool is deliberately for working with **your own** hardware: observing,
inspecting, and conversing over serial. It does not do RF/signal transmission,
HID/keystroke injection, or any remote operation.
