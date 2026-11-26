# pibench — the Pi as a reconfigurable hardware tool

Turn a Raspberry Pi into whatever bench instrument the job needs — a **SPI/BIOS
flasher**, an **I²C EEPROM** reader, a **UART console** — by selecting a
*profile*. It's the physical counterpart to the [Device Bench](https://claude.ai/artifact/44dTeFdXpHKR7K7jsRbPg7)
simulator in the `personal-windows-ai-agent` repo: the Bench *simulates* a chip
and its locks; the Pi, through a profile, does the real read/verify/write.

Everything is **your own hardware**, 3.3 V-native (no CH341A 5 V risk), stdlib-only
(profiles are TOML, read by Python 3.11+'s built-in `tomllib`), and **safe by
default** — destructive actions are gated and every command is inspectable with
`--dry-run` before it touches anything.

## Use it

```bash
python3 pibench.py list                      # every profile
python3 pibench.py show spi-bios             # wiring + setup + actions
python3 pibench.py wiring spi-bios           # just the pin map
python3 pibench.py run spi-bios probe        # detect the chip (safe)
python3 pibench.py run spi-bios read --set image=aw15r2.bin     # dump + verify (safe)
python3 pibench.py run spi-bios write --set image=aw15r2.clean.bin --yes   # write (needs --yes)
python3 pibench.py run spi-bios read --dry-run                  # print commands, run nothing
```

- **Reads are safe** and run directly. **Writes are `[write]`** and refuse to run
  without `--yes`.
- `--dry-run` prints the exact shell commands with your variables filled in and
  executes nothing — always look first.
- `--set key=value` overrides a profile variable (image name, bus, address, baud…).

## Profiles

| Profile | Tool | For |
| --- | --- | --- |
| **spi-bios** | `flashrom` (`linux_spi`) | Dump/verify/reflash a 25-series SPI BIOS chip. The laptop-BIOS job. |
| **i2c-eeprom** | `i2c-tools` | Scan/dump a 24Cxx I²C EEPROM — where some boards keep the BIOS password. |
| **uart-console** | `tio`/`picocom` | Open a serial console to a board, or scan for its baud rate. |

A profile is a plain TOML file in [`profiles/`](profiles): `title`, optional
`setup` (packages + interface to enable + notes), a `wiring` table (chip pin → Pi
header pin), `vars` (defaults, override with `--set`), and named `actions` (each a
`desc` + one or more `commands`, optionally `destructive = true`). Copy one and
edit it to add your own job — the CI lints that every action renders with no
leftover `{tokens}`.

## On the Pi

1. Enable the bus the profile names (`raspi-config` → Interface Options → SPI / I²C
   / Serial), then reboot.
2. `sudo apt install -y <the profile's packages>` (shown by `pibench show`).
3. Wire per `pibench wiring <profile>` — **match pin 1 on both sides**, 3.3 V only.
4. `pibench run <profile> probe` → `read` → (edit a copy) → `write --yes`.

> Golden rule for flashing: get a verified dump **first** and keep it untouched;
> edit a **copy** and write the copy back. Only ever on hardware you own.

## Tests

```bash
python3 -m pytest -q tests
```

Runs entirely in dry-run — no hardware, no `flashrom`, no Pi required. CI runs the
same suite and lints every profile on each push (`.github/workflows/pibench.yml`).
