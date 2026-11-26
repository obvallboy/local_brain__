"""Download the models and calibrate them, in one step.

Usage:
  python -m filecabinet.fetch                 # 3B chat model + embedding model into ./models
  python -m filecabinet.fetch --size 1.5b     # the smaller chat model instead
  python -m filecabinet.fetch --dest D:/models --no-calibrate

Files already downloaded are skipped, so it is safe to run again.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

HF = "https://huggingface.co"
CHAT = {
    "3b": (f"{HF}/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
           "about 2.1 GB; Qwen research license: fine for personal use, not for commercial products"),
    "1.5b": (f"{HF}/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
             "about 1.1 GB; Apache 2.0 license"),
}
EMBED = (f"{HF}/CompendiumLabs/bge-small-en-v1.5-gguf/resolve/main/bge-small-en-v1.5-f16.gguf",
         "about 67 MB; MIT license")


def download(url: str, dest: Path) -> Path:
    target = dest / url.rsplit("/", 1)[-1]
    if target.exists() and target.stat().st_size > 0:
        print(f"  already have {target.name}")
        return target
    part = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url) as response, open(part, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done, shown = 0, -1
        while chunk := response.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total and (pct := done * 100 // total) // 10 != shown:
                shown = pct // 10
                print(f"  {target.name}: {pct}%", flush=True)
    part.replace(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and calibrate the File Cabinet models")
    parser.add_argument("--size", choices=sorted(CHAT), default="3b")
    parser.add_argument("--dest", default="models")
    parser.add_argument("--no-calibrate", action="store_true")
    parser.add_argument("--gpu-layers", type=int, default=0, help="for calibration; -1 puts the model on the GPU")
    args = parser.parse_args()

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    url, note = CHAT[args.size]
    print(f"Chat model ({note}):")
    chat = download(url, dest)
    print(f"Embedding model ({EMBED[1]}):")
    download(EMBED[0], dest)

    if args.no_calibrate:
        print("Skipped calibration. Run this again without --no-calibrate to calibrate (files already here are reused).")
        return
    try:
        from .calibrate import measure
        from .model import LlamaModel, calibration_path
    except ImportError as exc:
        sys.exit(f"Downloaded. To calibrate, install llama-cpp-python first ({exc}).")
    import json

    print("Calibrating (a minute or two on a CPU, faster on a GPU)...")
    result = measure(LlamaModel(str(chat), gpu_layers=args.gpu_layers))
    calibration_path(str(chat)).write_text(json.dumps(result, indent=2))
    print(f"Done. Confidence cutoff {result['threshold']}: kept {result['right_answers_kept']} of "
          f"{result['right_answers_total']} right answers, blocked every wrong or invented one it saw.")


if __name__ == "__main__":
    main()
