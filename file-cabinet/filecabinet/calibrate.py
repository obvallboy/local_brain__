"""Measure where a model's confidence separates real answers from guesses.

Usage: python -m filecabinet.calibrate --model models/x.gguf

Different models are confident in different ways, so the cutoff is measured per
model and saved next to it (x.gguf.calibration.json). The cutoff is set 0.05 above
the most confident wrong or invented answer, and never below 0.5, because a small
set of questions underestimates the risk. Wrong answers matter more than missed ones.
The known questions include trick questions small models often get wrong.
These questions are separate from the scorecard in evals/.
"""

from __future__ import annotations

import argparse
import json

from .cabinet import ask_drawer2
from .model import LlamaModel, calibration_path

KNOWN = [
    ("what is the capital of italy", ["rome"]),
    ("who discovered penicillin", ["fleming"]),
    ("how many minutes are in an hour", ["60", "sixty"]),
    ("what is the smallest prime number", ["2", "two"]),
    ("who painted the starry night", ["gogh"]),
    ("what is the capital of canada", ["ottawa"]),
    ("how many strings does a standard guitar have", ["6", "six"]),
    ("what is the hardest natural substance", ["diamond"]),
    ("in which country are the pyramids of giza", ["egypt"]),
    ("what is the largest mammal", ["whale"]),
    ("who developed the theory of relativity", ["einstein"]),
    ("how many hours are in a day", ["24"]),
    ("what is the main ingredient in guacamole", ["avocado"]),
    ("what color do you get by mixing blue and yellow", ["green"]),
    ("what is the freezing point of water in celsius", ["0", "zero"]),
    ("how many players are on a soccer team on the field", ["11", "eleven"]),
    # Trick questions: a confident wrong answer here sets the cutoff.
    ("what is the capital of australia", ["canberra"]),
    ("what is the capital of turkey", ["ankara"]),
    ("what is the smallest country in the world", ["vatican"]),
    ("what is the capital of switzerland", ["bern"]),
    ("what is the largest country by area", ["russia"]),
    ("who was the second president of the united states", ["adams"]),
    ("what is the capital of brazil", ["brasilia", "brasília"]),
    ("how many bones are in the adult human body", ["206"]),
    ("what is the longest bone in the human body", ["femur"]),
    ("what is the chemical symbol for sodium", ["na"]),
    ("what year did world war two end", ["1945"]),
    ("who wrote pride and prejudice", ["austen"]),
]
MADE_UP = [
    "who was the first king of the island of morvanthe",
    "what is the capital of the nation of zelquor",
    "who wrote the opera the silver lanterns of hadrel",
    "what year was the trelmont bridge in sorvia built",
    "who discovered the mineral quellite",
    "what is the population of drannick falls minnesota",
    "who won the 1962 orbital cup",
    "what is the national dish of west kalvoria",
    "who invented the brisket engine",
    "how tall is mount ferreon",
    "what is the main export of the republic of tavressa",
    "what currency is used in the kingdom of ostrevia",
    "who painted the famous portrait lady of the amber veil",
    "what is the capital city of the province of nalmark",
    "which river runs through the city of vellacourt",
    "who founded the company brightwater dynamics in 1911",
    "what language is spoken on the island of corwenna",
    "what is the tallest building in the city of hessmoor",
    "who directed the 1974 film the pale harbor",
    "what is the state bird of the territory of lornevale",
]
FLOOR, CEILING, MARGIN = 0.5, 0.95, 0.05


def measure(model) -> dict:
    model.threshold = 0.0  # see every answer while measuring
    good, bad, refused = [], [], 0
    for question, words in KNOWN:
        reply, _ = ask_drawer2(model, question)
        if reply is None:
            refused += 1
        elif any(w in reply.text.lower() for w in words):
            good.append(reply.confidence)
        else:
            bad.append(reply.confidence)
    for question in MADE_UP:
        reply, _ = ask_drawer2(model, question)
        if reply is None:
            refused += 1
        else:
            bad.append(reply.confidence)
    threshold = min(CEILING, max(FLOOR, (max(bad) + MARGIN) if bad else FLOOR))
    return {
        "threshold": round(threshold, 3),
        "right_answers_kept": sum(c >= threshold for c in good),
        "right_answers_total": len(KNOWN),
        "wrong_or_invented_seen": len(bad),
        "said_unknown_or_repeated": refused,
        "right_confidences": sorted(round(c, 2) for c in good),
        "wrong_confidences": sorted(round(c, 2) for c in bad),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--gpu-layers", type=int, default=0)
    args = parser.parse_args()
    result = measure(LlamaModel(args.model, gpu_layers=args.gpu_layers))
    calibration_path(args.model).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"Saved to {calibration_path(args.model)}")


if __name__ == "__main__":
    main()
