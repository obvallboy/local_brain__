"""The File Cabinet AI, hosted inside the Device Integrator.

* One cabinet is shared by all of the web server's threads (it serializes questions itself).
* Models load in the background when the app starts, so the page opens instantly.
* If no model is found, or it fails to load, the cabinet still runs on its drawers and
  rules, and the status says why.
* The cabinet's temp drawer can see what is plugged in (discovery) and the names you gave
  devices (notes), so "is my arduino connected?" is answered from real data.

Everything stays on this machine. The memory file lives in the app's data folder, so the
laptop and the desktop each keep their own; export/import copies it between them.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def import_filecabinet():
    """Import the File Cabinet package, from an install or from this repo's file-cabinet/ folder."""
    try:
        import filecabinet  # noqa: F401
    except ImportError:
        path = os.path.join(REPO_ROOT, "file-cabinet")
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
        import filecabinet  # noqa: F401
    return sys.modules["filecabinet"]


@dataclass
class AssistantConfig:
    db_path: str
    models_dir: Optional[str] = None
    model: Optional[str] = None
    embed: Optional[str] = None
    gpu_layers: int = 0

    @classmethod
    def from_env(cls, data_dir: str, **overrides: Any) -> "AssistantConfig":
        env = os.environ
        cfg = cls(
            db_path=os.path.join(data_dir, "cabinet.db"),
            models_dir=env.get("FILE_CABINET_MODELS") or os.path.join(REPO_ROOT, "models"),
            model=env.get("FILE_CABINET_MODEL") or None,
            embed=env.get("FILE_CABINET_EMBED") or None,
            gpu_layers=int(env.get("FILE_CABINET_GPU_LAYERS") or 0),
        )
        for key, value in overrides.items():
            if value is not None:
                setattr(cfg, key, value)
        return cfg


@dataclass
class Assistant:
    cfg: AssistantConfig
    devices: Optional[Callable[[], Dict[str, Any]]] = None
    labels: Optional[Callable[[], Dict[str, Any]]] = None
    cabinet_obj: Any = None  # inject a ready cabinet (tests)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _loading: bool = False
    _notes: list = field(default_factory=list)
    _model_path: Optional[str] = None
    _embed_path: Optional[str] = None

    # -- loading ---------------------------------------------------------
    def cabinet(self):
        with self._lock:
            if self.cabinet_obj is None:
                self._loading = True
                try:
                    self.cabinet_obj = self._build()
                finally:
                    self._loading = False
            return self.cabinet_obj

    def warm_up_async(self) -> None:
        threading.Thread(target=self.cabinet, name="cabinet-warm-up", daemon=True).start()

    def _build(self):
        fc = import_filecabinet()
        from filecabinet.model import find_models

        found_model, found_embed = find_models(self.cfg.models_dir) if self.cfg.models_dir else (None, None)
        model_path, embed_path = self.cfg.model or found_model, self.cfg.embed or found_embed
        model = embedder = None
        if model_path:
            try:
                from filecabinet.model import LlamaModel
                model = LlamaModel(model_path, gpu_layers=self.cfg.gpu_layers)
                self._model_path = model_path
            except Exception as exc:  # missing llama-cpp-python, bad file, out of memory...
                self._notes.append(f"model not loaded ({type(exc).__name__}: {exc})")
        else:
            self._notes.append("no model found; put a .gguf file in models/ (python -m filecabinet.fetch)")
        if embed_path:
            try:
                from filecabinet.embed import Embedder
                embedder = Embedder(embed_path)
                self._embed_path = embed_path
            except Exception as exc:
                self._notes.append(f"meaning-matching off ({type(exc).__name__}: {exc})")
        os.makedirs(os.path.dirname(self.cfg.db_path) or ".", exist_ok=True)
        return fc.FileCabinet(store=fc.Store(self.cfg.db_path), model=model, embedder=embedder,
                              devices=self.devices, labels=self.labels)

    # -- what the web app calls ---------------------------------------------
    def status(self) -> Dict[str, Any]:
        ready = self.cabinet_obj is not None
        model = getattr(self.cabinet_obj, "model", None) if ready else None
        return {
            "ready": ready,
            "loading": self._loading,
            "model": os.path.basename(self._model_path) if self._model_path else None,
            "embed": os.path.basename(self._embed_path) if self._embed_path else None,
            "confidence_cutoff": getattr(model, "threshold", None),
            "gpu_layers": self.cfg.gpu_layers,
            "memory_file": self.cfg.db_path,
            "notes": list(self._notes),
        }

    def ask(self, message: str) -> Dict[str, Any]:
        cab = self.cabinet()
        if message.startswith("/"):
            from filecabinet.commands import run_command
            return {"label": "Command", "text": run_command(cab, message)}
        a = cab.ask(message)
        return {
            "label": a.label.value,
            "text": a.text,
            "route": {"kind": a.route.kind, "depth": a.route.depth, "reason": a.route.reason},
            "drawers": list(a.drawers_opened),
            "evidence": list(a.evidence),
        }

    def export(self) -> Dict[str, Any]:
        cab = self.cabinet()
        with cab.lock:
            return cab.store.export_data()

    def import_(self, data: Dict[str, Any]) -> Dict[str, int]:
        cab = self.cabinet()
        with cab.lock:
            return cab.store.import_data(data)
