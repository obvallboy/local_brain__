"""Download the models and calibrate them, in one step.

Usage:
  python -m filecabinet.fetch --check         # what's installed, what's missing, and how to fix it
  python -m filecabinet.fetch                 # 3B chat model + embedding model into ./models
  python -m filecabinet.fetch --size 1.5b     # the smaller chat model instead
  python -m filecabinet.fetch --dest D:/models --no-calibrate

Files already downloaded are skipped, so it is safe to run again.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
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


INSTALL_TIPS = {
    "Windows": [
        "PyPI only has llama-cpp-python's source code, so pip builds it on your computer. On Windows that needs",
        "Microsoft's 'Build Tools for Visual Studio' with the 'Desktop development with C++' workload (and CMake).",
        "Then: pip install llama-cpp-python",
        "For the GPU, also install NVIDIA's CUDA Toolkit, then in PowerShell:",
        '  $env:CMAKE_ARGS="-DGGML_CUDA=on"; pip install --force-reinstall --no-cache-dir llama-cpp-python',
        "The llama-cpp-python project also publishes ready-built packages on its own site; see its README.",
    ],
    "default": [
        "pip install llama-cpp-python   (it builds from source; needs a C++ compiler and CMake)",
        'GPU (NVIDIA, with the CUDA toolkit): CMAKE_ARGS="-DGGML_CUDA=on" pip install --force-reinstall '
        "--no-cache-dir llama-cpp-python",
    ],
}


def check(dest: Path) -> int:
    """Report what the Brain needs on this computer and what's missing. Returns 0 if ready."""
    from .model import calibration_path, find_models

    ready = True
    system = platform.system()
    print(f"Python {platform.python_version()} on {system}")
    try:
        import llama_cpp

        gpu = bool(getattr(llama_cpp, "llama_supports_gpu_offload", lambda: False)())
        print(f"  ok   llama-cpp-python {llama_cpp.__version__} ({'can use the GPU' if gpu else 'CPU only'})")
        if not gpu and shutil.which("nvidia-smi"):
            print("  note An NVIDIA GPU is here, but this build can't use it. To use it, reinstall with CUDA:")
            print("       " + INSTALL_TIPS.get(system, INSTALL_TIPS["default"])[-2 if system == "Windows" else -1].strip())
    except ImportError:
        ready = False
        print("  MISSING llama-cpp-python: without it the Brain runs on its drawers and rules only.")
        for line in INSTALL_TIPS.get(system, INSTALL_TIPS["default"]):
            print("       " + line)
    chat, embed = find_models(dest)
    if chat:
        size = Path(chat).stat().st_size / 2**30
        print(f"  ok   chat model {Path(chat).name} ({size:.1f} GB)")
        try:
            cal = json.loads(calibration_path(chat).read_text())
            print(f"  ok   calibrated: confidence cutoff {cal['threshold']}")
        except (OSError, ValueError, KeyError):
            print("  todo not calibrated yet: run python brain_setup.py (it reuses the downloaded files)")
    else:
        ready = False
        print(f"  MISSING no chat model in {dest}: run python brain_setup.py")
    print(f"  {'ok  ' if embed else 'todo'} {'embedding model ' + Path(embed).name if embed else 'no embedding model (meaning-matching off): run python brain_setup.py'}")
    print("Ready." if ready else "Not ready yet: see above.")
    return 0 if ready else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and calibrate the File Cabinet models")
    parser.add_argument("--size", choices=sorted(CHAT), default="3b")
    parser.add_argument("--dest", default="models")
    parser.add_argument("--no-calibrate", action="store_true")
    parser.add_argument("--gpu-layers", type=int, default=0, help="for calibration; -1 puts the model on the GPU")
    parser.add_argument("--check", action="store_true", help="report what's installed and what's missing; download nothing")
    args = parser.parse_args()

    dest = Path(args.dest)
    if args.check:
        sys.exit(check(dest))
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
    print("Calibrating (a minute or two on a CPU, faster on a GPU)...")
    result = measure(LlamaModel(str(chat), gpu_layers=args.gpu_layers))
    calibration_path(str(chat)).write_text(json.dumps(result, indent=2))
    print(f"Done. Confidence cutoff {result['threshold']}: kept {result['right_answers_kept']} of "
          f"{result['right_answers_total']} right answers, blocked every wrong or invented one it saw.")


if __name__ == "__main__":
    main()
