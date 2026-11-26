# Device & IoT Integration — a learning roadmap

A path from "I can poke a simulated device" to "I can integrate real devices on
a real network, safely." It's organized around **what this project already
builds**, so each stage has something concrete to play with:

- the **[Device Bench](../device-bench)** simulator (virtual devices, a network, an automation brain, fault injection)
- the real **[`integration/`](integration)** (Python) and **[`integration-js/`](integration-js)** (Node) stacks
- the local **[Device Integrator](.)** hardware tool

Each stage links to a community roadmap on **[roadmap.sh](https://roadmap.sh)**
for breadth, plus a primary spec/resource for the thing we actually used.
roadmap.sh doesn't have a dedicated IoT/embedded track, so this doc is the
device-integration overlay on top of the general ones.

> Credit & license: the roadmaps linked below are **[roadmap.sh](https://roadmap.sh)**
> by Kamran Ahmed and contributors ([kamranahmedse/developer-roadmap](https://github.com/kamranahmedse/developer-roadmap)).
> Their content is copyrighted; this file only **links** to them (which their
> license allows) and contains no copied roadmap content. Follow the links for
> the real thing — go contribute to them, too.

---

## 0 · Foundations

Before devices, the ground they stand on.

- **Computer science basics** → <https://roadmap.sh/computer-science>
- **Linux** (everything here runs on it; the Pi target especially) → <https://roadmap.sh/linux>
- **Git & GitHub** (this repo's branch/PR/CI flow) → <https://roadmap.sh/git-github>

*In this project:* the `device-integrator` Flask app and the CI workflows under
`.github/workflows/` are a working example of the Git + Linux + CI loop.

## 1 · A language for integration

Pick one to start; this project ships both.

- **Python** → <https://roadmap.sh/python>  ·  used in [`integration/`](integration)
- **Node.js** → <https://roadmap.sh/nodejs>  ·  used in [`integration-js/`](integration-js)
- **Backend** (the general shape of a service) → <https://roadmap.sh/backend>

*In this project:* `integration/brain.py` and `integration-js/brain.js` are the
same control logic in each language — a good compare-and-contrast.

## 2 · Networking (how devices find and reach each other)

This is the heart of the Device Bench's **Lab network** device.

- **Network engineer** → <https://roadmap.sh/network-engineer>
  — IP/subnets, **DHCP**, **DNS**, **ARP**, **ICMP/ping**, traceroute, routing.

*In this project:* the `net` engine ([`device-bench/engines/net.js`](../device-bench/engines/net.js))
implements a tiny version of each — `discover`, `dhcp`, `ping`, `nslookup`,
`arp`, `trace`, `map`. Read it after the roadmap and the names will click.

## 3 · Device & application protocols

roadmap.sh covers HTTP/REST well; the industrial/IoT ones you learn from their specs.

- **API design** (REST, the camera's HTTP interface) → <https://roadmap.sh/api-design>
- **MQTT** — the pub/sub protocol for the sensor. Spec: <https://mqtt.org/> · OASIS MQTT 5.0.
  Library: [Eclipse Paho](https://eclipse.dev/paho/) (`paho-mqtt`, used in `integration/transports.py`).
- **Modbus** — the industrial register protocol for the PLC. Spec: <https://modbus.org/specs.php>.
  Library: [pymodbus](https://pymodbus.readthedocs.io/) (used in `integration/transports.py`).
- **Serial / UART** — the Device Integrator's serial console; see [pySerial](https://pyserial.readthedocs.io/).

*In this project:* `net poll temp-01|plc-01|cam-01` shows a representative
exchange for each; the real adapters in `transports.py` / `transports.js` speak
them for real.

## 4 · Architecture (turning devices into a system)

The "integration engine / brain" is a system-design exercise.

- **System design** → <https://roadmap.sh/system-design>
- **Software architecture** → <https://roadmap.sh/software-architect> · <https://roadmap.sh/software-design-architecture>

*In this project:* the brain is transport-neutral (logic separate from I/O) —
`brain.py`/`brain.js` know nothing about MQTT or Modbus. That separation is the
lesson. Automations: the thermostat control loop in the `net` engine.

## 5 · Reliability & testing

Why this project screenshots, unit-tests, and runs CI on every change.

- **QA / automation testing** → <https://roadmap.sh/qa>
- **Code review** → <https://roadmap.sh/code-review>

*In this project:* `tests/` (pytest), `integration-js/test/` (node:test), the
runnable engine suites in `device-bench/engines/`, and the three CI workflows.
The **data-integrity guard** (reject 999 °C, hold last-good) is defensive-coding
made concrete — mirrored by the pydantic model in `integration/models.py`.

## 6 · Running it for real (deployment)

- **DevOps** → <https://roadmap.sh/devops>
- **Docker** → <https://roadmap.sh/docker> · **Kubernetes** → <https://roadmap.sh/kubernetes>

*Next step for this project:* a `docker-compose` with [Mosquitto](https://mosquitto.org/)
(MQTT broker) + a Modbus simulator so the `integration/` transports run against
real services locally. (Noted in [HANDOFF.md](../HANDOFF.md) as an open thread.)

## 7 · Security (don't trust the wire)

- **Cyber security** → <https://roadmap.sh/cyber-security>
- **DevSecOps** → <https://roadmap.sh/devsecops>

*In this project:* three guards in the brain — **data integrity** (is the value
plausible?), **authenticity** (is the message signed?), and a **learned anomaly**
check (is it normal for this sensor?). The second is real **HMAC-SHA256**:
`crypto-js` in the Device Bench, `cryptography` in `integration/security.py`,
`crypto-js` in `integration-js/security.js`. Try `tamper temp-01 on` in the Bench
and watch the HMAC verify fail. Natural next topic: key management & rotation.

**Firmware / BIOS security (your own hardware).** The Bench's **`spiflash`**
device models the SPI NOR chip that holds a laptop's BIOS and its write-protection
stack (status-register block-protect, the WP# pin, the chipset's BLE/FLOCKDN
lock). It's for the legitimate reasons you reflash your *own* machine — recovering
bricked firmware, installing [coreboot](https://coreboot.org/), or clearing a
forgotten supervisor password. On real hardware the tool is
[flashrom](https://www.flashrom.org/) with an external SPI programmer (a CH341A
clip, or a Pi via `linux_spi`): `flashrom -p <programmer> -r backup.bin` to dump,
`-w new.bin` to write. Back up first; only touch hardware you own.

---

## 8 · Going deeper — networking, AI, security

The three threads this project leans on hardest, with the roadmaps worth the time.

### Networking (beyond the basics)

- **Network engineer** (revisit for depth: TLS, VPNs, firewalls, NAT) → <https://roadmap.sh/network-engineer>
- **System design** (message queues, distributed delivery, back-pressure) → <https://roadmap.sh/system-design>
- **Cloud computing** → <https://roadmap.sh/cloud-computing> · **AWS** → <https://roadmap.sh/aws>

*Tie-in:* the next realistic step for the fleet is **MQTT-over-TLS** to a broker
and, in production, a cloud ingestion point (AWS IoT Core speaks MQTT). The
`net` engine already models the LAN; TLS + a broker is the missing transport
layer. See [Mosquitto](https://mosquitto.org/) for a local broker to practice on.

### AI / ML for devices

The brain uses fixed thresholds today; the obvious upgrade is a *learned* model.

- **Machine learning** → <https://roadmap.sh/machine-learning>
- **MLOps** (train → deploy → monitor a model) → <https://roadmap.sh/mlops>
- **Inference engineering** (run it at the edge — quantization, latency) → <https://roadmap.sh/inference-engineering>
- **Data engineer** (the telemetry pipeline that feeds the model) → <https://roadmap.sh/data-engineer>
- **AI agents** (planning/tool-use agents) → <https://roadmap.sh/ai-agents> · **AI engineer** → <https://roadmap.sh/ai-engineer>

*Tie-ins, concrete:*
- **Built:** a learned **anomaly detector** now runs as a third guard beside the
  range check — [`integration/anomaly.py`](integration/anomaly.py) (Node:
  [`integration-js/anomaly.js`](integration-js/anomaly.js)). It learns `temp-01`'s
  normal behaviour (EW mean/variance → z-score) and catches an *in-range* glitch
  (45 °C on a 25 °C sensor) the fixed range check waves through:
  `python -m integration.engine --sim --ticks 30 --anomaly-at 20`. This is the
  simplest honest form; the roadmaps above scale the same `check()` interface up to
  isolation forests / autoencoders, with the `fuzz`/`anomaly` faults as the test set.
- The Device Bench's **"Ask Claude"** box (the `sample` capability) is already a
  tool-using **agent** driving the fleet — the agents roadmap is what's behind it.
- Edge inference target: run the model inside the `integration/` engine on a Pi.

### Security (depth, incl. AI)

- **Cyber security** → <https://roadmap.sh/cyber-security> · **DevSecOps** → <https://roadmap.sh/devsecops>
- **AI red teaming** (adversarial inputs, model abuse — where AI meets security) → <https://roadmap.sh/ai-red-teaming>

*Tie-in:* the Bench's **`fuzz`** (corrupt data) and **`tamper`** (break the HMAC)
faults *are* adversarial-input testing. AI red teaming extends the same idea to a
learned model — can you craft inputs that fool the anomaly detector the way
`tamper` fools a brain with its security guard off? Pair it with real **key
management / rotation** for the HMAC signing keys (the obvious hardening of
`security.py`).

---

### Suggested order

Foundations → one language → **networking** → protocols → architecture →
testing → deployment → security. But you can also just open the Device Bench,
break something, and follow the thread back to whichever stage it touches.
