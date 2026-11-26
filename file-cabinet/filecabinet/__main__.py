"""Chat with the File Cabinet from a terminal: python -m filecabinet"""

from __future__ import annotations

import argparse
from pathlib import Path

from .cabinet import FileCabinet
from .commands import HELP, handle  # noqa: F401  (handle is re-exported for older scripts)
from .model import LlamaModel, find_models
from .store import Store
from .temp import SCENARIOS, RealNetwork


def main() -> None:
    parser = argparse.ArgumentParser(description="File Cabinet AI")
    parser.add_argument("--db", default=str(Path.home() / ".file_cabinet" / "cabinet.db"))
    parser.add_argument("--models", help="folder of .gguf files; the chat and embedding models are picked from it")
    parser.add_argument("--model", help="path to a GGUF chat model (overrides --models)")
    parser.add_argument("--embed", help="path to a GGUF embedding model (overrides --models)")
    parser.add_argument("--gpu-layers", type=int, default=0,
                        help="model layers to put on the GPU; -1 for all (needs a CUDA build of llama-cpp-python)")
    parser.add_argument("--network", choices=["real", *SCENARIOS], default="real",
                        help="check the real network, or use a simulated scenario")
    parser.add_argument("--owner", default="owner", help="name recorded when approving core memories")
    args = parser.parse_args()

    found_model, found_embed = find_models(args.models) if args.models else (None, None)
    model_path, embed_path = args.model or found_model, args.embed or found_embed

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    model = LlamaModel(model_path, gpu_layers=args.gpu_layers) if model_path else None
    network = RealNetwork() if args.network == "real" else SCENARIOS[args.network]
    embedder = None
    if embed_path:
        from .embed import Embedder
        embedder = Embedder(embed_path)
    cab = FileCabinet(store=Store(args.db), model=model, network=network, embedder=embedder)
    print("File Cabinet AI. Everything stays on this machine. Type /help for commands.")
    print(f"Model: {model_path or 'none'} | meaning-matching: {embed_path or 'off'}")

    while True:
        try:
            line = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        print(handle(cab, line, args.owner))
        if line == "/quit":
            break


if __name__ == "__main__":
    main()
