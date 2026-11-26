"""Answers and their honesty labels.

The label on an answer is decided by which part of the system produced it
(the code path), never by what the model says about itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Label(str, Enum):
    KNOW = "I know"                    # drawer 1 lookup hit
    THINK = "I think"                  # drawer 2: patterns or the model, unchecked
    CHECKED = "I checked"              # temp drawer: confirmed against observed data
    REMEMBER = "I remember"            # found in the episode log or core memories
    DONT_REMEMBER = "I don't remember"  # recall searched and found nothing
    CORE = "From my core"              # deep emotional answer, guided by drawer 3
    FILED = "Filed"                    # something you told me was filed in a drawer or the log
    NOT_SURE = "I'm not sure"          # nothing reliable to answer from


@dataclass(frozen=True)
class Route:
    """What the front desk decided about a question."""

    kind: str                  # opinion | fact | recall | task | emotional | chat | teach | event | devices
    depth: str                 # surface | deep
    drawers: tuple[str, ...]   # drawers to open, in order
    reason: str                # which rule fired
    recall: bool = False       # the question asks to remember something
    crisis: bool = False       # possible self-harm: a support line is always added


@dataclass(frozen=True)
class Answer:
    label: Label
    text: str
    route: Route
    drawers_opened: tuple[str, ...]
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def render(self) -> str:
        return f"[{self.label.value}] {self.text}"

    def why(self) -> str:
        lines = [
            f"Route: {self.route.kind} ({self.route.depth}) because {self.route.reason}",
            f"Drawers opened: {', '.join(self.drawers_opened) or 'none'}",
            f"Label: {self.label.value}",
        ]
        if self.evidence:
            lines.append("Evidence:")
            lines.extend(f"  - {item}" for item in self.evidence)
        return "\n".join(lines)
