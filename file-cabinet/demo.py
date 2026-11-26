"""A scripted session that shows every part of the File Cabinet working.

Usage: python demo.py [path/to/model.gguf] [path/to/embedding-model.gguf]
Without a model, drawer 2 relies on stored references only.
"""

import sys
from datetime import datetime, timedelta

from filecabinet import FileCabinet, Store
from filecabinet.__main__ import handle
from filecabinet.model import LlamaModel
from filecabinet.temp import SCENARIOS

model = LlamaModel(sys.argv[1]) if len(sys.argv) > 1 else None
embedder = None
if len(sys.argv) > 2:
    from filecabinet.embed import Embedder
    embedder = Embedder(sys.argv[2])
store = Store()
cab = FileCabinet(store=store, model=model, network=SCENARIOS["dns"], embedder=embedder)

# Things that happened today, logged as separate moments.
now = datetime.now().replace(second=0, microsecond=0)
store.log_episode("Riverside Park", "walking", "We saw a car parked by the gate.", ts=now - timedelta(hours=2))
store.log_episode("Riverside Park", "walking", "It was bright red with a white stripe.", ts=now - timedelta(hours=2) + timedelta(minutes=2))

script = [
    ("Learning from normal conversation", [
        "my sister's name is maya",
        "i work as a network technician",
        "/like blue | It's calm.",
    ]),
    ("Drawer 1: I know", ["whats my sisters name", "what do i do for work", "do u think blue is pretty"]),
    ("Personal facts are never guessed", ["What was the name of my first dog?"]),
    ("Drawer 2: general knowledge from the model, with a confidence check", [
        "What is the capital of France?",
        "How many legs does a spider have?",
        "Who was the mayor of the village of Xylophone Creek in 1890?",
    ]),
    ("Recall by cue, and matching by meaning", [
        "Do you remember what color the car was that we saw earlier?",
        "/why",
        "do you remember the automobile we spotted earlier",
        "Do you remember the boat we saw earlier?",
        "just had lunch with sam at the noodle bar",
        "who did we have lunch with",
    ]),
    ("Temp drawer: check before assuming", [
        "Websites won't load but the wifi says connected",
        "/done Restarted the router after its nightly update",
        "Pages are not loading in my browser",
    ]),
    ("Emotional depth and safety", [
        "Is this funny?",
        "My best friend and I had a big fight and we're not talking.",
        "this traffic is killing me",
        "sometimes i think about ending it all",
    ]),
    ("Protected core", [
        "/core Grandpa taught me to fish at Lake Tahoe the summer before he died.",
        "/approve 1",
        "Do you remember the summer before grandpa died?",
    ]),
]

for title, lines in script:
    print(f"\n=== {title} ===")
    for line in lines:
        print(f"you> {line}")
        print(handle(cab, line))
