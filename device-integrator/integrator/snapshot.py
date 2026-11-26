"""Print a device snapshot as JSON — the bridge out of this machine.

The Device Integrator runs locally and does the real hardware access; this
command dumps what it sees as a single JSON document you can take elsewhere
(for example, Import it into the "Glass Box" claude.ai sandbox to talk through
what to do with each device). The browser sandbox can't reach USB/serial
itself, so this snapshot is how the device list gets there.

    python -m integrator.snapshot            # pretty JSON to stdout
    python -m integrator.snapshot --compact  # single line (easy to copy/paste)
    python -m integrator.snapshot -o devices.json
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
from typing import Any, Dict, List, Optional

from integrator import discovery


def build_snapshot() -> Dict[str, Any]:
    """A discovery snapshot tagged with where it came from."""
    try:
        host = socket.gethostname() or "this machine"
    except Exception:
        host = "this machine"
    snap: Dict[str, Any] = {"source": f"{host} ({platform.system()})"}
    snap.update(discovery.snapshot())
    return snap


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Print a Device Integrator snapshot as JSON"
    )
    parser.add_argument("--compact", action="store_true",
                        help="emit single-line JSON (easy to copy/paste)")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="write to FILE instead of stdout")
    args = parser.parse_args(argv)

    snap = build_snapshot()
    if args.compact:
        text = json.dumps(snap, default=str, separators=(",", ":"))
    else:
        text = json.dumps(snap, default=str, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"Wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
