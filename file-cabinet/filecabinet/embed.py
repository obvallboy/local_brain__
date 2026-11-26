"""A small embedding model for matching words by meaning ("automobile" finds "car").

Tested with bge-small-en-v1.5 (MIT license, 67 MB). Measured on that model:
true synonyms score about 0.86-0.95 (automobile/car 0.91, sibling/sister 0.88),
related but different words about 0.74-0.83 (car/truck 0.74), so the cutoff is 0.85.
"""

from __future__ import annotations

import math


class Embedder:
    def __init__(self, path: str):
        from llama_cpp import Llama

        self.llm = Llama(model_path=path, embedding=True, verbose=False)
        self._cache: dict[str, list[float]] = {}

    def vector(self, text: str) -> list[float]:
        key = text.strip().lower()
        if key not in self._cache:
            v = self.llm.embed(key)
            if v and isinstance(v[0], list):
                v = v[0]
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            self._cache[key] = [x / norm for x in v]
        return self._cache[key]

    def similarity(self, a: str, b: str) -> float:
        return sum(x * y for x, y in zip(self.vector(a), self.vector(b)))
