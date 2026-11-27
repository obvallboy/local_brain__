"""Device Integrator — local web app.

A workbench for inspecting and tinkering with hardware you own: discover
attached devices, inspect them in depth, open a serial console to a dev
board, and keep reverse-engineering notes. It binds to localhost by default
and performs no outbound network access.

Run:
    python app.py                 # http://127.0.0.1:5000
    python app.py --port 8080
    python app.py --host 0.0.0.0  # expose on your LAN (opt-in)
    python app.py --gpu-layers -1 # run the Brain's model on the GPU

The Brain panel is the File Cabinet AI (../file-cabinet). It finds its models in
../models (download them with: python -m filecabinet.fetch) and runs locally.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict

from flask import Flask, jsonify, request, send_from_directory

from integrator import discovery, details
from integrator.assistant import Assistant, AssistantConfig
from integrator.notes import NotesStore
from integrator.serialconsole import SessionManager

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.environ.get(
    "DEVICE_INTEGRATOR_DATA",
    os.path.join(os.path.expanduser("~"), ".device-integrator"),
)


def create_app(data_dir: str = DEFAULT_DATA_DIR,
               session_manager: SessionManager | None = None,
               assistant: Assistant | None = None,
               notes: NotesStore | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    os.makedirs(data_dir, exist_ok=True)
    app.config["NOTES"] = notes or NotesStore(os.path.join(data_dir, "notes.json"))
    app.config["SERIAL"] = session_manager or SessionManager()
    app.config["ASSISTANT"] = assistant or Assistant(
        AssistantConfig.from_env(data_dir),
        devices=discovery.snapshot,
        labels=app.config["NOTES"].all,
    )

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

    # -- brain (File Cabinet AI) ------------------------------------------
    @app.get("/api/brain/status")
    def api_brain_status():
        return jsonify(app.config["ASSISTANT"].status())

    @app.post("/api/brain/ask")
    def api_brain_ask():
        body = request.get_json(silent=True) or {}
        message = (body.get("message") or "").strip()
        if not message:
            return jsonify({"error": "message is required"}), 400
        if len(message) > 2000:
            return jsonify({"error": "message is too long (2000 characters max)"}), 400
        try:
            return jsonify(app.config["ASSISTANT"].ask(message))
        except RuntimeError as exc:  # e.g. the core values file was changed on disk
            return jsonify({"error": str(exc)}), 409

    @app.get("/api/brain/facts")
    def api_brain_facts():
        return jsonify(app.config["ASSISTANT"].facts())

    @app.delete("/api/brain/facts/<int:fact_id>")
    def api_brain_forget(fact_id: int):
        if not app.config["ASSISTANT"].forget(fact_id):
            return jsonify({"error": f"no fact #{fact_id}"}), 404
        return jsonify({"deleted": fact_id})

    @app.get("/api/brain/serial-scan")
    def api_brain_serial_scan():
        port = (request.args.get("port") or "").strip()
        if not port:
            return jsonify({"error": "port is required"}), 400
        from integrator.serial_help import scan
        return jsonify(scan(port))

    @app.get("/api/brain/net-scan")
    def api_brain_net_scan():
        host = (request.args.get("host") or "").strip()
        if not host:
            return jsonify({"error": "host is required"}), 400
        from integrator.network_help import scan
        return jsonify(scan(host))

    @app.get("/api/brain/export")
    def api_brain_export():
        resp = jsonify(app.config["ASSISTANT"].export())
        resp.headers["Content-Disposition"] = "attachment; filename=brain-memory.json"
        return resp

    @app.post("/api/brain/import")
    def api_brain_import():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "send the exported JSON as the request body"}), 400
        try:
            return jsonify({"added": app.config["ASSISTANT"].import_(body)})
        except (ValueError, KeyError, TypeError) as exc:
            return jsonify({"error": f"not a File Cabinet export: {exc}"}), 400

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
    parser.add_argument("--models", help="folder of .gguf files for the Brain (default: ../models)")
    parser.add_argument("--model", help="the Brain's chat model file (overrides --models)")
    parser.add_argument("--embed", help="the Brain's embedding model file (overrides --models)")
    parser.add_argument("--gpu-layers", type=int, default=None,
                        help="Brain model layers on the GPU; -1 for all (needs a CUDA build of llama-cpp-python)")
    args = parser.parse_args()

    data_dir = DEFAULT_DATA_DIR
    os.makedirs(data_dir, exist_ok=True)
    notes = NotesStore(os.path.join(data_dir, "notes.json"))
    assistant = Assistant(
        AssistantConfig.from_env(data_dir, models_dir=args.models, model=args.model,
                                 embed=args.embed, gpu_layers=args.gpu_layers),
        devices=discovery.snapshot,
        labels=notes.all,
    )
    assistant.warm_up_async()  # load the models in the background; the page opens right away
    app = create_app(data_dir, assistant=assistant, notes=notes)  # one notes store for the page and the Brain
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"⚠️  Binding to {args.host} — the console and the Brain (including Export memory, "
              "with everything it knows about you) will be reachable by other machines on your "
              "network. Only do this on a network you trust.")
    print(f"Device Integrator → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
