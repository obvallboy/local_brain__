"""Slash commands, shared by the terminal chat and any app that hosts the cabinet."""

from __future__ import annotations

import json
from pathlib import Path

HELP = """Commands:
  /fact <subject> = <fact>        put a fact in drawer 1      e.g. /fact sister = Your sister's name is Maya.
  /like <item> [| reason]         put an opinion in drawer 1   e.g. /like blue | It's calm.
  /dislike <item> [| reason]
  /log <place> | <activity> | <details> [| people]   log something that happened
  /done <what fixed it>           end the current task and file what was learned
  /core <memory>                  propose a core memory (needs /approve)
  /approve <id>                   approve a core memory proposal
  /pending                        list core proposals waiting for approval
  /why                            show how the last answer was produced
  /wrong <what was wrong>         save a correction for later learning
  /facts [word]                   list what's in drawer 1 (optionally only facts with a word)
  /forget <id>                    remove a drawer-1 fact by its number (or just say "forget my locker code")
  /export <file.json>             save everything learned (to copy to your other computer)
  /import <file.json>             merge in an export (core memories wait for /approve)
  /help, /quit
Anything else is a question or message. You can also just talk: "my brother's name is leo"
is filed in drawer 1, and "we just saw a red car at the park" is logged as a memory."""


def run_command(cab, line: str, owner: str = "owner") -> str:
    """Run one slash command against a FileCabinet and return what to show."""
    cmd, _, rest = line.strip().partition(" ")
    rest = rest.strip()
    with cab.lock:
        if cmd == "/help":
            return HELP
        if cmd == "/quit":
            return "Bye."
        if cmd == "/fact" and "=" in rest:
            subject, fact = (p.strip() for p in rest.split("=", 1))
            return f"Filed in drawer 1 (fact #{cab.store.add_fact(subject, fact)})."
        if cmd in ("/like", "/dislike") and rest:
            item, _, reason = (p.strip() for p in rest.partition("|"))
            cab.store.set_preference(item, "like" if cmd == "/like" else "dislike", reason)
            return f"Filed in drawer 1: {cmd[1:]} {item}."
        if cmd == "/log" and rest.count("|") >= 2:
            parts = [p.strip() for p in rest.split("|")]
            place, activity, details = parts[:3]
            people = parts[3] if len(parts) > 3 else ""
            return f"Logged episode #{cab.store.log_episode(place, activity, details, people)}."
        if cmd == "/done":
            return "\n".join(cab.finish_task(rest))
        if cmd == "/core" and rest:
            return f"Core proposal #{cab.store.propose_core(rest)} is waiting for /approve."
        if cmd == "/approve" and rest.isdigit():
            try:
                return f"Approved. Core memory #{cab.core.approve(int(rest), owner)} is in drawer 3."
            except KeyError as exc:
                return str(exc)
        if cmd == "/pending":
            pending = cab.store.pending_core()
            return "\n".join(f"#{pid}: {m}" for pid, m in pending) or "Nothing is waiting."
        if cmd == "/why":
            return cab.last.why() if cab.last else "Nothing asked yet."
        if cmd == "/wrong" and rest:
            return f"Saved correction #{cab.correct(rest)}."
        if cmd == "/facts":
            facts = [f for f in cab.store.facts() if not rest or rest.lower() in f"{f.subject} {f.fact}".lower()]
            return "\n".join(f"#{f.id} {f.subject}: {f.fact}" for f in facts) or "Drawer 1 has nothing matching that."
        if cmd == "/forget" and rest.lstrip("#").isdigit():
            fid = int(rest.lstrip("#"))
            return f"Removed fact #{fid} from drawer 1." if cab.store.delete_fact(fid) else f"There's no fact #{fid}."
        if cmd == "/export" and rest:
            Path(rest).write_text(json.dumps(cab.store.export_data(), indent=2))
            return f"Saved everything learned to {rest}."
        if cmd == "/import" and rest:
            try:
                added = cab.store.import_data(json.loads(Path(rest).read_text()))
            except (OSError, ValueError) as exc:
                return f"Couldn't import {rest}: {exc}"
            return "Imported: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in added.items())
    return "I didn't understand that command. Type /help."


def handle(cab, line: str, owner: str = "owner") -> str:
    """Terminal-style handling: commands run, anything else is asked."""
    if line.startswith("/"):
        return run_command(cab, line, owner)
    return "cabinet> " + cab.ask(line).render()
