# local_brain__ — Roadmap

A living plan for the project. Like the language it describes, it is **never finished**:
we change it as we learn. Edit it directly, reorder the phases, cross things out.

Last updated: 2026-11-27.

---

## 1. The vision

Own your devices completely, and be able to reach into, tinker with, and program **any**
of them — from a locked laptop's BIOS chip to a microcontroller to a Chromebook — from one
place, in one consistent way, with a local AI helping and nothing leaving your machines.

Two halves that are really one goal:

- **The hardware reach.** A Raspberry Pi plus the right adapter can read and rewrite chips,
  open serial consoles, and unlock firmware on hardware you own. The app already does the
  safe version of this (`pibench`, the Device Integrator).
- **The unified language.** Every device speaks its own language. One way to say what you
  want, that *adapts to each device's real language* — and keeps learning new ones — is the
  same thing as "program any device." The devices keep the language honest: a program either
  runs on the chip or it doesn't.

---

## 2. Principles (these do not change; everything else does)

1. **Never finished, always adapting.** The structure stays fixed; what it knows always grows.
   The File Cabinet's drawers never change, only their contents. The language is the same: a
   fixed core, an ever-growing set of languages and skills it has learned.
2. **Measure everything.** Every change gets test cases written *first*, and a held-out
   scorecard is the judge. We keep the numbers in the repo. 57% → 90s is how the Brain got
   good; the same method runs the whole project.
3. **Honesty over fluency.** Every answer says where it came from (*I know* / *I think* /
   *I checked* / *I remember* / *I'm not sure*). Code is the same: *I ran it and it worked*
   is not *I think this compiles*. Correctness is checked by running, never trusted from a model.
4. **Safety and your approval on top.** Nothing overrules the crisis rules. Nothing that
   changes the real world — a serial write, flashing a chip, importing memory — happens without
   showing you exactly what will run and getting your yes first. Back up before you overwrite.
5. **Local-first, yours.** Models run on your machines. Your data stays on your machines unless
   you choose to move it. Own-hardware scope throughout.

---

## 3. The machines

```
   Desktop (Windows, RTX 3060 Ti 8 GB, 32 GB RAM)      the strong brain
     - runs a 7-8B model on the GPU
     - later: overnight training of model add-ons
            |
            |  Tailscale (already set up)
            |
   Laptop (CachyOS / Arch, GTX 1660 6 GB)              the field brain
     - runs its own 3-4B model
     - borrows the desktop's bigger model when reachable; falls back to its own
            |
            |
   Raspberry Pi                                        the hardware tool
     - reads/writes chips (flashrom), serial consoles, I2C  (pibench)
     - the thing that actually touches the hardware
            |
   Chromebook                                          another device to own
     - unlock job, not a limitation (see 7.3)
     - usable as a thin screen that drives the Pi/desktop over Tailscale
```

Each machine runs the Device Integrator for whatever is plugged into **it**; over Tailscale,
one machine can see and use another's devices.

---

## 4. The unified language — honest design

What's real now vs what's frontier, so we build the useful core and grow toward the dream
instead of pretending a small local model can do all of it today.

### Buildable and measurable now
- **An intent layer.** You describe what a device should do, in one consistent form. You don't
  learn each board's dialect.
- **Translate to the target's real language, then run it.** The Brain turns your intent into
  MicroPython, Arduino C++, shell, AT commands, assembly — whatever the device speaks — and
  **compiles or runs it to check**. The result is labelled *I ran it* vs *I think*.
- **Language cards.** When it meets a language it doesn't know well, you give it a small spec
  and a few examples. That becomes drawer-2 knowledge it uses next time. This is the realistic
  form of "adapts to new languages it sees": it learns from examples and keeps what works.
- **Approve → run → file.** Every program is shown, approved by you, run, and what worked is
  saved as a reference. Same loop as flashing a chip.

### The Wikipedia seed (your idea), done honestly
Seed a **language registry** from the [List of programming languages](https://en.wikipedia.org/wiki/List_of_programming_languages)
(~700 languages — a list of names and links, not how-to). This maps straight onto the drawers:
- **Knowing a language exists = a drawer-1 fact** ("I know Rust exists, it's compiled, systems").
  Cheap, and we can seed all ~700 at once.
- **Being able to *write* it = a drawer-2 skill**, learned from examples and **proven by
  running code**. This is never seeded wholesale; it grows one checked language card at a time.

Keeping those two apart is what stops the language from bluffing: it can always tell you the
difference between a language it has *heard of* and one it can *actually write and has tested*.
(The list page isn't reachable from the cloud build environment; we seed the registry on a
machine with normal internet — the laptop or desktop.)

### Frontier (years, not weeks; not from a 3-8B local model)
- A language that *is* an AI and rewrites itself.
- Learning an arbitrary new language perfectly with no examples.
- Being correct without running the code.

We don't promise these. We build toward them one checked step at a time, and the scorecard
(does it compile? does it run? does it do the right thing?) tells us when we've actually moved.

---

## 5. How we work on every change

1. Write new test cases **first**, split into a practice half and a held-out half.
2. Measure the current version on both.
3. Make the change, tuning only on the practice half.
4. Re-measure. Keep the change only if the held-out half holds or improves. Roll back if not.
5. For code generation, "the scorecard" means **actually compiling/running** the output.

---

## 6. Status (done)

- **File Cabinet AI** — local assistant, memory in drawers, honesty labels. 148 tests.
  Held-out scorecard ~90% (1.5B) / ~93% (3B), zero invented memories.
- **Brain panel** in the Device Integrator — ask about hardware, teach it facts, forget facts,
  export/import memory between machines. 66 app tests.
- **Efficiency** — token probabilities recorded as picked (3B on CPU: 3.0 → 2.2 s/call,
  4.6 → 4.0 GB); drawer 1 answered before the model (5.0 → 0.1 s).
- **pibench** — Pi as a reconfigurable tool (SPI/BIOS, I2C EEPROM, UART), safe by default.
- **Alienware 15 R2 runbook** — chip located, wiring mapped, read/verify/write ready.

---

## 7. Phases (hardware-first)

### Phase 0 — Setup on the real machines
- **Laptop (CachyOS/Arch):** make `brain_setup.py --check` Arch-aware — `base-devel` + `cmake`
  from pacman, a CUDA or Vulkan GPU build, the `uucp` group for serial ports (not `dialout`).
  Add a start script and optional start-at-login.
- **Desktop (Windows):** C++ Build Tools + CUDA; a 7-8B model sized for 8 GB VRAM.
- **Fix the Windows device-discovery gaps** (USB detail is thinner than on Linux; serial works).
- **Measure real GPU speed and run the scorecard on each machine.**
- *Build now:* the CachyOS/Windows setup checks and scripts. *Run later:* on your machines.

### Phase 1 — The hardware Brain (core goal; fully testable here with simulated devices)
1. **Board recognition.** [DONE] Plug in a device → it names the board, chip, voltage, baud rate, tool
   and language, from an offline USB-ID list (`file-cabinet/filecabinet/data/usb_ids.json`). Ask "what is
   this?" or "how do I program my Pico?"; known boards are named even when not attached.
2. **Pi "bench" Brain.** [engine DONE] The Brain runs a job's digital steps itself and only pauses
   for a physical step ("clip the chip, say done") or a plain-language "go" before anything irreversible.
   It narrates every step and catches a bad read instead of trusting it. The engine
   (`file-cabinet/filecabinet/jobs.py`) and the Alienware BIOS-dump job
   (`device-integrator/integrator/hardware_jobs.py`) are built and tested with a simulated flasher.
   TODO: run the real flasher on the Pi, and wire the guided session into the Brain chat panel.
3. **Serial console help.** [DONE, offline logic] Auto-detect baud; recognize what's answering
   (MicroPython `>>>`, CircuitPython, U-Boot, a Linux login/shell, an ESP boot log, a GPS, an AT modem)
   and suggest a next step. `file-cabinet/filecabinet/serialscan.py` + `device-integrator/integrator/serial_help.py`
   (GET /api/brain/serial-scan). TODO: verify live on a board; add a "scan" button to the console tab.
4. **The Alienware walkthrough** as the first end-to-end real job (once the clip arrives).

### Phase 2 — The unified language, first end to end
1. **Seed the language registry** from the List of programming languages (names → drawer-1
   "exists" facts).
2. **The intent → target → run → file loop**, with **MicroPython on the Pico as the first
   language card** (easiest target).
3. **A code scorecard:** does the generated program compile/run and do the expected thing.

### Phase 3 — The Tailscale link
1. **Secure first:** the app listens only on the Tailscale address; a pairing code gates
   anything that changes something (serial writes, memory import, flashing).
2. **Two-way memory sync, including deletions** (a "forget" on one machine stays forgotten).
3. **Laptop borrows the desktop's bigger model** when reachable.
4. **Use the other machine's devices** (open a console on a board plugged into the desktop,
   from the laptop).

### Phase 4 — Programming devices, with approval every time
1. **Toolchains:** detect what you have; support each language's usual tool (MicroPython,
   Arduino, ESP32, Pico, AVR, STM32).
2. **Flow:** you (or the Brain) write code → it shows tool + port + file → you approve → it runs
   → it files what worked.
3. **Back up first** where the tool can read the chip (the pibench golden rule, everywhere).
4. **Better code model** on the desktop (a code-focused 7B), picked by the code scorecard.

### Phase 5 — Learning over time (desktop GPU)
Overnight training of a small model add-on from your corrections and what worked. The scorecard
decides whether to keep it; it rolls back if anything gets worse; it's shared to the laptop over
Tailscale. 8 GB VRAM makes this realistic on the desktop. Biggest and riskiest step — it comes
after the rest works on your machines.

### Ongoing / polish (fits around the phases)
The Brain panel is named **Devy** in the UI.
Streaming answers (word by word); a "that's wrong" button that fixes a fact in place; automatic
daily backups of each machine's memory (pull this **early** — it's the only copy per machine);
approve/reject buttons for core-memory proposals; a people/things view ("what do you know about
Maya?"); the "sleep" step that proposes lessons for your approval.

---

## 8. Hardware inventory

| Device | Role | Status |
| --- | --- | --- |
| Raspberry Pi | The hardware tool (chips, serial, I2C) | Have it |
| Desktop — HP Omen 25L, Windows, RTX 3060 Ti 8 GB, 32 GB | Main brain; later, training | Have it |
| Laptop — CachyOS/Arch, GTX 1660 6 GB | Field brain | Have it |
| Alienware 15 R2 (board LA-C912P) | First real unlock job; broken, forgotten BIOS password | Have it; blocked on the clip |
| Chromebook | Another device to own (unlock), or a thin screen | Have it; model TBD |
| **SOIC-8 test clip** (+ jumpers) | Clips onto the BIOS chip so the Pi reads it | **Need to buy.** Ships to an Airbnb once back at work |

**The clip:** a "SOIC-8 / SOP8 test clip with jumper wires," ~$8-15. No CH341A and no level
shifter needed — the Pi is 3.3 V native. That one part unblocks the Alienware job.

---

## 9. Open questions

- [ ] **Chromebook model?** Intel/AMD can usually be fully freed (MrChromebox firmware → full
      Linux, after disabling write-protection — same genre as the Alienware). ARM usually can't.
      The exact model decides the path.
- [ ] **"Program any device" scope:** program each device in *its own* language via one intent
      layer (the plan above), with the registry always learning more languages. Confirmed.
- [ ] **Which boards first** beyond the Alienware and the Pi? (Pico / ESP32 / Arduino would make
      good first language cards.)
- [ ] **Memory sync:** automatic over Tailscale, with a pairing code — confirmed direction.

---

## 10. Safety notes carried from the existing work

- Only ever your own hardware.
- Flashing: get a verified dump first, keep the original untouched, edit a copy, write the copy.
- Confirm the chip and pin 1 from a clear board photo before powering the Pi — reversing it can
  kill the chip. (The runbook is for the **R2**; confirm the broken unit is an R2 from a photo.)
- Every real-world action is shown and approved before it runs.
