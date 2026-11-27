"""Guided jobs: the model does the digital part, you do the physical part.

A job is a list of steps. Each step is one of:
  - physical : something you do with your hands. The engine explains it and waits
               for you to say "done". It never pretends to do it for you.
  - auto     : a safe digital step (probe, read, diagnose). The engine runs it
               itself, reads the result, and moves on. No asking.
  - gated    : a digital step that can't be undone (write/erase a chip). The engine
               explains it in plain language and waits for you to say "go".

The engine narrates what it did, checks each result, and on a failure either stops
with advice or, for a reseat-and-try-again step, waits for you to say "retry".
Nothing is guessed: a step's success is read from what the command actually returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


# A runner takes a shell command and returns its result. Injected, so the engine
# is testable with a fake and real on the Pi with subprocess.
Runner = Callable[[str], RunResult]


class Kind(str, Enum):
    PHYSICAL = "physical"
    AUTO = "auto"
    GATED = "gated"


@dataclass(frozen=True)
class Step:
    kind: Kind
    say: str                                             # plain-language narration / instruction
    command: Optional[str] = None                        # for AUTO / GATED: a shell command
    call: Optional[Callable[[], RunResult]] = None       # or a Python helper returning a RunResult
    name: Optional[str] = None                           # how a `call` step shows in the "why" list
    check: Optional[Callable[[RunResult], tuple]] = None  # (result) -> (ok: bool, message: str)
    on_fail: str = ""                                    # plain-language recovery advice
    retryable: bool = False                              # fix it physically, then "retry" this step


@dataclass(frozen=True)
class Job:
    name: str
    goal: str
    steps: tuple[Step, ...]
    closing: str = ""   # shown when the job finishes: what you have now, what's next


@dataclass
class Turn:
    """What to show the user, and what the engine is waiting for."""
    say: str
    awaiting: Optional[str] = None   # "physical" (say done) | "confirm" (say go) | "retry" | None
    done: bool = False
    failed: bool = False
    ran: tuple = ()                  # commands actually run this turn (for the "why")


def _default_check(res: RunResult) -> tuple:
    return res.ok, (res.stdout.strip().splitlines()[-1] if res.ok and res.stdout.strip()
                    else ("done." if res.ok else "that failed."))


DONE_WORDS = {"done", "ok", "okay", "ready", "yes", "yep", "finished", "did it", "good"}
GO_WORDS = {"go", "yes", "do it", "confirm", "y", "yep", "proceed", "run it"}
STOP_WORDS = {"stop", "cancel", "quit", "abort", "no", "wait", "hold on"}
RETRY_WORDS = {"retry", "again", "try again", "redo", "done", "ok", "ready"}


@dataclass
class Session:
    job: Job
    runner: Runner
    i: int = 0
    status: str = "new"              # new | running | waiting | done | failed | stopped
    awaiting: Optional[str] = None
    log: list = field(default_factory=list)

    # ---- driving the session ------------------------------------------
    def start(self) -> Turn:
        self.status = "running"
        return self._advance([f"Starting: {self.job.goal}."])

    def user(self, text: str) -> Turn:
        """Feed the user's reply ('done' / 'go' / 'retry' / 'stop') and continue."""
        t = " ".join(text.strip().lower().split())
        if self.status in ("done", "failed", "stopped"):
            return Turn("That job is finished. Start a new one if you like.", done=True)
        if t in STOP_WORDS and self.awaiting != "confirm":
            self.status = "stopped"
            return Turn("Okay, stopped. I won't run anything else.", done=True)
        if self.awaiting == "physical":
            if t in DONE_WORDS:
                self.i += 1
                return self._advance()
            return Turn("No rush — say 'done' when that's ready, or 'stop'.", awaiting="physical")
        if self.awaiting == "confirm":
            if t in GO_WORDS:
                return self._advance()  # run the gated step now
            if t in STOP_WORDS:
                self.status = "stopped"
                return Turn("Okay, I won't do that. Stopped — nothing was written.", done=True)
            return Turn("Say 'go' to do it, or 'no' to stop.", awaiting="confirm")
        if self.awaiting == "retry":
            if t in RETRY_WORDS:
                return self._advance()  # re-run the same step
            return Turn("Fix it and say 'retry', or 'stop' to stop.", awaiting="retry")
        return self._advance()

    # ---- the engine ----------------------------------------------------
    def _advance(self, narration: Optional[list] = None) -> Turn:
        narration = list(narration or [])
        ran = []
        while self.i < len(self.job.steps):
            step = self.job.steps[self.i]

            if step.kind is Kind.PHYSICAL:
                self.awaiting, self.status = "physical", "waiting"
                return self._turn(narration, step.say, awaiting="physical", ran=ran)

            if step.kind is Kind.GATED and self.awaiting != "confirm":
                self.awaiting, self.status = "confirm", "waiting"
                prompt = f"{step.say}\n\nThis can't be undone. Say 'go' to do it, or 'no' to stop."
                return self._turn(narration, prompt, awaiting="confirm", ran=ran)

            # AUTO, or a GATED step the user just approved: run it (a shell command or a Python helper).
            if step.call is not None:
                res = step.call()
                ran.append(step.name or "(internal step)")
            else:
                res = self.runner(step.command)
                ran.append(step.command)
            ok, msg = (step.check or _default_check)(res)
            self.log.append({"step": step.say, "command": step.command, "ok": ok, "detail": msg})
            narration.append(f"{step.say} {msg}".strip())
            self.awaiting = None

            if not ok:
                if step.retryable:
                    self.awaiting, self.status = "retry", "waiting"
                    advice = step.on_fail or "That didn't work."
                    return self._turn(narration, f"{advice} Fix it and say 'retry', or 'stop'.",
                                      awaiting="retry", ran=ran)
                self.status = "failed"
                return self._turn(narration, step.on_fail or "That step failed, so I've stopped here.",
                                  failed=True, ran=ran)
            self.i += 1

        self.status = "done"
        finish = f"All done — {self.job.goal} is complete."
        if self.job.closing:
            finish += f"\n\n{self.job.closing}"
        return self._turn(narration, finish, done=True, ran=ran)

    def _turn(self, narration, say, **kw) -> Turn:
        body = "\n".join(n for n in narration if n)
        text = f"{body}\n\n{say}" if body else say
        return Turn(text, ran=tuple(kw.pop("ran", ())), **kw)
