"""The local model behind drawer 2.

Every call is deterministic (temperature 0, fixed seed) and forced into a JSON
shape. Confidence is measured from the probabilities of the answer's own
tokens, because the model's self-reported confidence was found to be useless:
in testing it marked an invented answer ("Buddy" for "my first dog") as known.

Memory: those probabilities are recorded one token at a time as the model picks
them (see ChosenTokenProbs), instead of asking llama.cpp to keep scores for every
position in the context. With a 152k-word vocabulary that saves over 1 GB of RAM.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


@dataclass(frozen=True)
class ModelReply:
    text: str
    confidence: float  # lowest token probability inside the answer text, 0..1


class Model(Protocol):
    def ask(self, system: str, user: str, max_tokens: int = 120) -> ModelReply | None: ...


class NoModel:
    """Used when no model file is configured. Drawer 2 then relies on stored references only."""

    def ask(self, system: str, user: str, max_tokens: int = 120) -> ModelReply | None:
        return None


def answer_confidence(token_logprobs: list[dict]) -> float:
    """Lowest probability among the tokens that make up the "answer" string value."""
    text, spans = "", []
    for tok in token_logprobs:
        start = len(text)
        text += tok["token"]
        spans.append((start, len(text), math.exp(tok["logprob"])))
    match = re.search(r'"answer"\s*:\s*"', text)
    if not match:
        return 0.0
    value_start = value_end = match.end()
    while value_end < len(text) and not (text[value_end] == '"' and text[value_end - 1] != "\\"):
        value_end += 1
    probs = [p for s, e, p in spans if s < value_end and e > value_start]
    return min(probs) if probs else 0.0


def find_models(folder: str | Path) -> tuple[str | None, str | None]:
    """Pick the chat model and the embedding model from a folder of .gguf files.

    The embedding model is the file whose name mentions bge/embed; the chat model is
    the largest of the rest (so a 3B model wins over a 1.5B one if both are there)."""
    files = sorted(Path(folder).glob("*.gguf")) if Path(folder).is_dir() else []
    embed = [f for f in files if "bge" in f.name.lower() or "embed" in f.name.lower()]
    chat = [f for f in files if f not in embed]
    pick_chat = max(chat, key=lambda f: f.stat().st_size, default=None)
    return (str(pick_chat) if pick_chat else None, str(embed[0]) if embed else None)


def calibration_path(model_path: str) -> Path:
    return Path(str(model_path) + ".calibration.json")


def load_threshold(model_path: str, default: float = 0.35) -> float:
    """The confidence cutoff measured for this model by `python -m filecabinet.calibrate`."""
    try:
        return float(json.loads(calibration_path(model_path).read_text())["threshold"])
    except (OSError, ValueError, KeyError):
        return default


class ChosenTokenProbs:
    """Records the probability the model gave each token it actually emitted.

    llama.cpp calls this once per generated token with the raw scores for the
    next token. The token that was chosen shows up at the end of the next
    call's input, so its probability is read from the previous step's softmax.
    """

    def __init__(self):
        self.prev = None
        self.records: list[tuple[int, float]] = []

    def __call__(self, input_ids, scores):
        import numpy as np

        if self.prev is not None:
            token = int(input_ids[-1])
            self.records.append((token, float(self.prev[token])))
        z = np.exp(scores - np.max(scores))
        self.prev = z / z.sum()
        return scores


class LlamaModel:
    """A GGUF model run on this machine through llama.cpp."""

    def __init__(self, path: str, n_ctx: int = 2048, seed: int = 42, threads: int | None = None, gpu_layers: int = 0):
        """gpu_layers=-1 puts the whole model on the GPU (needs llama-cpp-python built with CUDA)."""
        from llama_cpp import Llama  # imported here so the rest works without it

        self.seed = seed
        self.threshold = load_threshold(path)
        self.llm = Llama(
            model_path=path, n_ctx=n_ctx, seed=seed, n_threads=threads, n_gpu_layers=gpu_layers,
            verbose=False,
        )

    def ask(self, system: str, user: str, max_tokens: int = 120) -> ModelReply | None:
        # Say the format in the prompt too. Forcing JSON on a model that wasn't told about it made
        # the 3B model pick tokens it would never choose (log-probability around -31) and answer garbage.
        system = f'{system}\nRespond only with JSON in this form: {{"answer": "..."}}'
        out = self.llm.create_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.0,
            seed=self.seed,
            max_tokens=max_tokens,
            response_format={"type": "json_object", "schema": ANSWER_SCHEMA},
            logits_processor=self._processors(recorder := ChosenTokenProbs()),
        )
        choice = out["choices"][0]
        if choice.get("finish_reason") == "length":
            return None  # cut off mid-answer: treat as no answer
        try:
            answer = str(json.loads(choice["message"]["content"]).get("answer", "")).strip()
        except (json.JSONDecodeError, AttributeError):
            return None
        if not answer:
            return None
        tokens = [
            {"token": self.llm.detokenize([t]).decode("utf-8", errors="ignore"), "logprob": math.log(max(p, 1e-12))}
            for t, p in recorder.records
        ]
        return ModelReply(answer, answer_confidence(tokens))

    @staticmethod
    def _processors(*fns):
        from llama_cpp import LogitsProcessorList

        return LogitsProcessorList(list(fns))

    def ask_json(self, system: str, user: str, schema: dict, max_tokens: int = 60) -> dict | None:
        """A short structured decision, such as the front desk's classification."""
        system = f"{system}\nRespond only with JSON matching this schema: {json.dumps(schema)}"
        out = self.llm.create_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.0,
            seed=self.seed,
            max_tokens=max_tokens,
            response_format={"type": "json_object", "schema": schema},
        )
        try:
            data = json.loads(out["choices"][0]["message"]["content"])
        except (json.JSONDecodeError, KeyError, IndexError):
            return None
        return data if isinstance(data, dict) else None
