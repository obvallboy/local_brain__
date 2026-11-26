# Runbook — Alienware 15 R2 BIOS system-password removal

Own hardware (a $12 garage-sale unit with a forgotten **system / power-on password**).
Board: **Compal LA-C912P**. BIOS chip: **Winbond W25Q128FVSQ, 16 MB, SOIC-8, 3.3 V, silk `UH4`**.
Tool: a **Raspberry Pi** (3.3 V SPI) + a **SOIC-8 clip** + `flashrom`, driven by `pibench`
(profile `aw15r2`).

> The dump is the easy half. **Clearing the password inside the dump** is the real
> puzzle and is model-specific (community tool or a paid `.bin`-cleaning service).
> This runbook gets you a clean, verified dump and safely writes the cleared copy
> back. Keep the untouched original forever.

## 0. Gear check
- [ ] Raspberry Pi with Pi OS on the (known-good) SD card
- [ ] SOIC-8 test clip + female-female jumpers
- [ ] `flashrom` installed, SPI enabled (`sudo raspi-config` → Interface Options → SPI → reboot)
- [ ] This repo on the Pi: `python3 pibench/pibench.py list` shows `aw15r2`

## 1. Teardown (done — for reference / reassembly)
Battery **connector unplugged** first. Then: RAM → M.2 SSD → 2.5" HDD → WLAN (white→MAIN,
black→AUX) → KB screws incl. the one under the DIMM → keyboard + palm-rest (pop ribbon ZIF
locks). Organize screws by length (M2.5×4 / M2.5×6 / KB). Follow the
[Dell 15 R2 service manual](https://dl.dell.com/manuals/all-products/esuprt_laptop/esuprt_alienware_laptops/alienware-15-r2_service%20manual_en-us.pdf).

## 2. Find the chip — DONE (confirmed on this board)
- **UH4 = `winbond 25Q128FVSQ`**, 8-pin SOIC, **top side**, **immediately LEFT of the Intel PCH**
  (the big teal chip), beside silk **ON6/QN6** and the **JSSD1** M.2 slot. Reachable with a clip —
  the board does **not** need to come out.
- **Not** `UT5` nearby (the smaller 25Q80 EC — leave it alone).
- Find **pin 1**: the dot/divot in one corner of the Winbond chip. With the "winbond 25Q128FVSQ"
  text upright, pin 1 is the bottom-left pin. **Photograph the clip seated on UH4 and confirm pin-1
  orientation before powering the Pi** — reversing it can kill the chip. Chip pin 1 (CS#) → Pi pin 24.

## 3. Wire the clip  (`pibench wiring aw15r2`)
Clip the 8 pins of UH4 to the Pi header, matching pin 1 on both. 3.3 V only; tie WP#/HOLD# high.

## 4. Dump + verify  — the safe part
```bash
python3 pibench/pibench.py run aw15r2 probe        # expect: Winbond W25Q128.V
python3 pibench/pibench.py run aw15r2 read         # dumps twice, verifies they match -> aw15r2.bin
cp aw15r2.bin aw15r2.ORIGINAL.bin                  # <-- never touch this one
```
If `probe` finds nothing or the two reads differ: reseat the clip, check pin 1, and lower the
speed — `--set spispeed=128`. In-circuit sometimes can't get a clean read; if so the board
has to be fully out (nothing else powered on the SPI bus).

## 5. Clear the password  — the research step (with the dump in hand)
Work on a **copy**, never `aw15r2.ORIGINAL.bin`:
```bash
cp aw15r2.ORIGINAL.bin aw15r2.clean.bin
```
This is the model-specific part we figure out together once you have the dump — the system
password on these Dell/Alienware boards lives in the NVRAM/ME area and isn't a single obvious
byte. Options, in order of preference: a known community tool/patch for the LA-C912P, or a
reputable `.bin`-cleaning service. **Preserve the flash descriptor + ME region** — only the
password/NVRAM area changes.

## 6. Write it back + verify
```bash
python3 pibench/pibench.py run aw15r2 write --set image=aw15r2.clean.bin --yes
python3 pibench/pibench.py run aw15r2 verify --set image=aw15r2.clean.bin
```

## 7. Reassemble & test
Reverse the teardown (ribbons seated + ZIF locks down, antennas white→MAIN/black→AUX, right
screws in right holes, battery last). Power on — no system password prompt = win.

---
*If anything reads wrong or won't verify, STOP and re-flash `aw15r2.ORIGINAL.bin` — that's why
you kept it.*
