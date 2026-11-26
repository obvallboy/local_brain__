"""Device Integrator — local web app.

A workbench for inspecting and tinkering with hardware you own: discover
attached devices, inspect them in depth, open a serial console to a dev
board, and keep reverse-engineering notes. It binds to localhost by default
and performs no outbound network access.

Run:
    python app.py                 # http://127.0.0.1:5000
    python app.py --port 8080
    python app.py --host 0.0.0.0  # expose on your LAN (opt-in)
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict

from flask import Flask, jsonify, request, send_from_directory

from integrator import discovery, details
from integrator.notes import NotesStore
from integrator.serialconsole import SessionManager

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.environ.get(
    "DEVICE_INTEGRATOR_DATA",
    os.path.join(os.path.expanduser("~"), ".device-integrator"),
)


def create_app(data_dir: str = DEFAULT_DATA_DIR,
               session_manager: SessionManager | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    os.makedirs(data_dir, exist_ok=True)
    app.config["NOTES"] = NotesStore(os.path.join(data_dir, "notes.json"))
    app.config["SERIAL"] = session_manager or SessionManager()

    # -- static UI --------------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(os.path.join(HERE, "templates"), "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(os.path.join(HERE, "static"), filename)

    # -- discovery --------------------------------------------------------
    @app.get("/api/devices")
    def api_devices():
        snap = discovery.snapshot()
        # Attach stable keys to serial ports for the notes feature.
        for p in snap["serial"]:
            p["key"] = "serial:" + (p.get("device") or p.get("name") or "")
        return jsonify(snap)

    @app.get("/api/capabilities")
    def api_capabilities():
        return jsonify(discovery.capabilities())

    # -- device detail ----------------------------------------------------
    @app.get("/api/usb/detail")
    def api_usb_detail():
        sysfs_path = request.args.get("sysfs_path") or None
        vid = request.args.get("vid") or None
        pid = request.args.get("pid") or None
        tty = request.args.get("tty") or None
        # Only allow sysfs paths under the real USB tree — no arbitrary FS reads.
        if sysfs_path and not os.path.realpath(sysfs_path).startswith("/sys/"):
            return jsonify({"error": "sysfs_path must be under /sys"}), 400
        return jsonify(details.usb_detail(sysfs_path, vid, pid, tty))

    @app.get("/api/dmesg")
    def api_dmesg():
        tokens = [t for t in request.args.getlist("token") if t]
        return jsonify(details.dmesg_lines(tokens))

    # -- notes ------------------------------------------------------------
    @app.get("/api/notes")
    def api_notes_all():
        return jsonify(app.config["NOTES"].all())

    @app.post("/api/notes")
    def api_notes_set():
        body = request.get_json(silent=True) or {}
        key = (body.get("key") or "").strip()
        if not key:
            return jsonify({"error": "key is required"}), 400
        entry = app.config["NOTES"].set(
            key, note=body.get("note"), label=body.get("label")
        )
        return jsonify({"key": key, **entry})

    @app.delete("/api/notes")
    def api_notes_delete():
        key = (request.args.get("key") or "").strip()
        if not key:
            return jsonify({"error": "key is required"}), 400
        deleted = app.config["NOTES"].delete(key)
        return jsonify({"deleted": deleted})

    # -- serial console ---------------------------------------------------
    @app.post("/api/serial/open")
    def api_serial_open():
        body = request.get_json(silent=True) or {}
        port = (body.get("port") or "").strip()
        if not port:
            return jsonify({"error": "port is required"}), 400
        baud = int(body.get("baud", 115200))
        mgr: SessionManager = app.config["SERIAL"]
        try:
            session = mgr.open(port, baudrate=baud, label=body.get("label"))
        except ImportError:
            return jsonify({"error": "pyserial is not installed; run: pip install pyserial"}), 503
        except Exception as exc:
            return jsonify({"error": f"could not open {port}: {exc}"}), 502
        return jsonify(session.info())

    @app.get("/api/serial")
    def api_serial_list():
        return jsonify(app.config["SERIAL"].list())

    @app.get("/api/serial/<sid>/read")
    def api_serial_read(sid: str):
        session = app.config["SERIAL"].get(sid)
        if session is None:
            return jsonify({"error": "no such session"}), 404
        since = int(request.args.get("since", 0))
        return jsonify(session.read_since(since))

    @app.post("/api/serial/<sid>/write")
    def api_serial_write(sid: str):
        session = app.config["SERIAL"].get(sid)
        if session is None:
            return jsonify({"error": "no such session"}), 404
        body = request.get_json(silent=True) or {}
        line_ending = body.get("line_ending", "none")
        try:
            if body.get("hex"):
                raw = bytes.fromhex("".join((body.get("data") or "").split()))
            else:
                raw = (body.get("data") or "").encode("utf-8")
            n = session.write(raw, line_ending=line_ending)
        except ValueError as exc:
            return jsonify({"error": f"bad hex input: {exc}"}), 400
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409
        except Exception as exc:
            return jsonify({"error": str(exc)}), 502
        return jsonify({"written": n})

    @app.post("/api/serial/<sid>/close")
    def api_serial_close(sid: str):
        closed = app.config["SERIAL"].close(sid)
        return jsonify({"closed": closed})

    # -- export -----------------------------------------------------------
    @app.get("/api/export")
    def api_export():
        import platform
        import socket
        try:
            host = socket.gethostname() or "this machine"
        except Exception:
            host = "this machine"
        payload: Dict[str, Any] = {"source": f"{host} ({platform.system()})"}
        payload.update(discovery.snapshot())
        payload["notes"] = app.config["NOTES"].all()
        resp = jsonify(payload)
        resp.headers["Content-Disposition"] = "attachment; filename=device-snapshot.json"
        return resp

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Device Integrator — local hardware workbench")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default localhost; use 0.0.0.0 to expose on LAN)")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app()
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"⚠️  Binding to {args.host} — the console will be reachable by other "
              "machines on your network. Only do this on a network you trust.")
    print(f"Device Integrator → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
