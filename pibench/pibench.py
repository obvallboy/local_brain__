#!/usr/bin/env python3
"""pibench — turn a Raspberry Pi into a reconfigurable hardware tool via *profiles*.

Each profile (a .toml file in ./profiles) describes one job — SPI/BIOS flashing,
an I2C EEPROM, a UART console — with its wiring, the packages/interfaces it needs,
and a set of named, safe commands. This is the physical counterpart to the Device
Bench: the Bench simulates the chip, the Pi (through a profile) does the real work.

    pibench list                      # every profile
    pibench show spi-bios             # wiring + setup + actions for one
    pibench wiring spi-bios           # just the pin map
    pibench run spi-bios probe        # run an action (reads are safe)
    pibench run spi-bios read --set image=aw15r2.bin
    pibench run spi-bios write --set image=aw15r2.clean.bin --yes   # destructive → needs --yes
    pibench run spi-bios read --dry-run   # print the exact commands, run nothing

Design goals: pure stdlib (tomllib ships with Python 3.11+, incl. Pi OS Bookworm),
safe by default (destructive actions are gated, dumps are double-read + verified),
and everything is inspectable before it runs (`--dry-run`). Only hardware you own.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict, List

PROFILE_DIR = Path(os.environ.get("PIBENCH_PROFILES", Path(__file__).resolve().parent / "profiles"))


# ---- loading -----------------------------------------------------------------
def profile_path(name: str) -> Path:
    return PROFILE_DIR / (name + ".toml")


def list_profiles() -> List[str]:
    if not PROFILE_DIR.is_dir():
        return []
    return sorted(p.stem for p in PROFILE_DIR.glob("*.toml"))


def load_profile(name: str) -> Dict[str, Any]:
    path = profile_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"no profile '{name}' in {PROFILE_DIR} (try: pibench list)")
    with path.open("rb") as fh:
        prof = tomllib.load(fh)
    prof.setdefault("name", name)
    for key in ("title", "actions"):
        if key not in prof:
            raise ValueError(f"profile '{name}' is missing required key '{key}'")
    return prof


def resolve_vars(prof: Dict[str, Any], overrides: List[str]) -> Dict[str, str]:
    vars_: Dict[str, str] = {k: str(v) for k, v in (prof.get("vars") or {}).items()}
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"--set expects key=value, got '{item}'")
        k, v = item.split("=", 1)
        vars_[k.strip()] = v
    return vars_


def render(cmd: str, vars_: Dict[str, str]) -> str:
    """Substitute {var} tokens from vars_ (literal replacement — shell $(...) is left alone)."""
    for k, v in vars_.items():
        cmd = cmd.replace("{" + k + "}", v)
    return cmd


# ---- rendering (human output) ------------------------------------------------
def fmt_wiring(prof: Dict[str, Any]) -> str:
    rows = prof.get("wiring") or []
    if not rows:
        return "  (no wiring table in this profile)"
    head = ("pin", "signal", "→ Pi pin", "Pi function")
    data = [(str(r.get("chip", "")), str(r.get("signal", "")), str(r.get("pi", "")), str(r.get("pi_label", ""))) for r in rows]
    widths = [max(len(head[i]), *(len(d[i]) for d in data)) for i in range(4)]
    line = lambda cols: "  " + "  ".join(cols[i].ljust(widths[i]) for i in range(4))
    out = [line(head), line(tuple("-" * w for w in widths))]
    out += [line(d) for d in data]
    return "\n".join(out)


def show_profile(prof: Dict[str, Any]) -> str:
    out = [f"{prof['name']} — {prof['title']}"]
    if prof.get("summary"):
        out.append("  " + prof["summary"])
    if prof.get("device"):
        out.append(f"  device    : {prof['device']}")
    if prof.get("interface"):
        out.append(f"  interface : {prof['interface']}")
    setup = prof.get("setup") or {}
    if setup.get("packages"):
        out.append("\nSetup — packages: sudo apt install -y " + " ".join(setup["packages"]))
    for e in setup.get("enable", []):
        out.append("  enable: " + e)
    for n in setup.get("notes", []):
        out.append("  note: " + n)
    out.append("\nWiring (match pin 1 on both — the dot/notch):")
    out.append(fmt_wiring(prof))
    out.append("\nActions:")
    for key, act in prof["actions"].items():
        tag = "  [write]" if act.get("destructive") else ""
        out.append(f"  {key:<10} {act.get('desc', '')}{tag}")
    vars_ = prof.get("vars") or {}
    if vars_:
        out.append("\nVariables (override with --set key=value):")
        for k, v in vars_.items():
            out.append(f"  {k} = {v}")
    return "\n".join(out)


# ---- running -----------------------------------------------------------------
def action_commands(prof: Dict[str, Any], action: str) -> List[str]:
    acts = prof["actions"]
    if action not in acts:
        raise KeyError(f"profile '{prof['name']}' has no action '{action}' (have: {', '.join(acts)})")
    act = acts[action]
    cmds = act.get("commands")
    if isinstance(cmds, str):
        cmds = [cmds]
    if not cmds:
        raise ValueError(f"action '{action}' defines no commands")
    return list(cmds)


def run_action(prof: Dict[str, Any], action: str, vars_: Dict[str, str],
               dry_run: bool, assume_yes: bool) -> int:
    cmds_raw = action_commands(prof, action)  # raises a friendly KeyError if the action is unknown
    act = prof["actions"][action]
    cmds = [render(c, vars_) for c in cmds_raw]
    destructive = bool(act.get("destructive"))

    print(f"» {prof['name']} :: {action} — {act.get('desc', '')}")
    if destructive:
        print("  ⚠ DESTRUCTIVE (writes to the chip). Have a verified backup first "
              f"(e.g. `pibench run {prof['name']} read`). Only on hardware you own.")
    for c in cmds:
        print("  $ " + c)

    if dry_run:
        print("  (dry-run — nothing executed)")
        return 0
    if destructive and not assume_yes:
        print("  refusing to run a destructive action without --yes.")
        return 2

    for c in cmds:
        rc = subprocess.run(["bash", "-c", c]).returncode
        if rc != 0:
            print(f"  ✗ command failed (exit {rc}); stopping.")
            return rc
    print("  ✓ done")
    return 0


# ---- CLI ---------------------------------------------------------------------
def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pibench", description="Profile-driven Pi hardware tool.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list available profiles")
    for name in ("show", "wiring"):
        sp = sub.add_parser(name, help=f"{name} a profile")
        sp.add_argument("profile")
    rp = sub.add_parser("run", help="run a profile action")
    rp.add_argument("profile")
    rp.add_argument("action")
    rp.add_argument("--set", action="append", default=[], metavar="key=value", help="override a profile variable")
    rp.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
    rp.add_argument("--yes", action="store_true", help="confirm a destructive action")
    args = p.parse_args(argv)

    try:
        if args.cmd == "list":
            names = list_profiles()
            if not names:
                print(f"no profiles found in {PROFILE_DIR}")
                return 0
            print("profiles:")
            for n in names:
                prof = load_profile(n)
                print(f"  {n:<14} {prof['title']}")
            return 0
        if args.cmd == "wiring":
            prof = load_profile(args.profile)
            print(f"{prof['name']} — wiring (match pin 1 on both):")
            print(fmt_wiring(prof))
            return 0
        if args.cmd == "show":
            print(show_profile(load_profile(args.profile)))
            return 0
        if args.cmd == "run":
            prof = load_profile(args.profile)
            vars_ = resolve_vars(prof, args.set)
            return run_action(prof, args.action, vars_, args.dry_run, args.yes)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print("error: " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
