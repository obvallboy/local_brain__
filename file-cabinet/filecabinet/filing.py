"""Filing: what happens to the temp drawer when a task ends.

The rule is one question: "Will this be exactly the same next time?"
  yes, a fixed fact        -> drawer 1
  no, details will vary    -> drawer 2, as a reference (the pattern, not a copy)
  it changed who I am      -> a proposal for drawer 3, waiting for the owner
  none of these            -> discarded
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .similarity import similarity
from .store import Case, Store


@dataclass(frozen=True)
class FileItem:
    kind: str  # fixed_fact | varies | core | discard
    description: str
    payload: dict = field(default_factory=dict)


def file_items(store: Store, items: list[FileItem]) -> list[str]:
    report = []
    for item in items:
        p = item.payload
        if item.kind == "fixed_fact":
            if store.has_fact(p["subject"]):
                report.append(f"{item.description}: already in drawer 1")
            else:
                fid = store.add_fact(p["subject"], p["fact"], source="filed after a task")
                report.append(f"{item.description}: drawer 1 (fact #{fid})")
        elif item.kind == "varies":
            same = _same_reference(store.cases(), p["signature"], p["fix"])
            if same:
                store.reinforce_case(same.id)
                report.append(f"{item.description}: drawer 2, strengthened reference #{same.id} \"{same.title}\"")
            else:
                cid = store.add_case(p["title"], p["symptoms"], p["signature"], p["fix"])
                report.append(f"{item.description}: drawer 2 (new reference #{cid})")
        elif item.kind == "core":
            pid = store.propose_core(p["memory"])
            report.append(f"{item.description}: waiting for owner approval (core proposal #{pid})")
        else:
            report.append(f"{item.description}: discarded")
    return report


def _same_reference(cases: list[Case], signature: dict, fix: str) -> Case | None:
    """A reference with the same pattern and a similar fix is strengthened instead of copied."""
    for case in cases:
        if case.signature == signature and similarity(case.fix, fix) >= 0.3:
            return case
    return None


def match_cases(cases: list[Case], observed: dict, text: str):
    """Rank references against what was observed.

    Returns (confirmed, unconfirmed). A confirmed reference matches every part
    of its signature against real observations; a reference that contradicts
    any observation is dropped entirely.
    """
    confirmed, unconfirmed = [], []
    for case in cases:
        sig = case.signature
        if any(k in observed and observed[k] != v for k, v in sig.items()):
            continue
        matched = sum(1 for k, v in sig.items() if observed.get(k) == v)
        text_score = similarity(text, f"{case.title} {case.symptoms}")
        if sig and matched == len(sig):
            confirmed.append((case, matched, text_score))
        else:
            unconfirmed.append((case, matched, text_score))
    # Most specific pattern first, then the one seen most often, then the closest description.
    confirmed.sort(key=lambda r: (-r[1], -r[0].times_seen, -r[2], r[0].id))
    unconfirmed.sort(key=lambda r: (-r[2], -r[1], r[0].id))
    return [r[0] for r in confirmed], [(r[0], r[2]) for r in unconfirmed]
