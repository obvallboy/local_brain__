# File Cabinet AI

A local, offline assistant whose memory works like a file cabinet. Built from the
File Cabinet AI design doc. Everything stays on your machine.

In this repo it is the **Brain** panel of the Device Integrator (`../device-integrator`), where its temp
drawer can also see the hardware plugged into your computer. It also runs on its own in a terminal.

| Part | What it does |
| --- | --- |
| Front desk | Decides what kind of question it is and opens only the drawers needed |
| Drawer 1 | Facts and opinions you teach it. Answers labelled **I know** |
| Drawer 2 | Patterns: the local model and filed references. Answers labelled **I think** |
| Drawer 3 | Protected core values and core memories. Changes need your approval |
| Temp drawer | Real checks on the task at hand: network checks, and (inside the Device Integrator) the devices plugged in right now — recognized by their USB id (board, chip, voltage, how to program). Answers labelled **I checked** |
| Episode log | What happened, for recall by cue. **I remember** or **I don't remember** |

## Rules it follows

- The front desk runs safety rules first (crisis and deep emotion); nothing can overrule them. Clear patterns
  come next. Everything else is classified by the local model into a fixed set of kinds, and its choice must
  pass sanity checks (for example, "recall" needs a sign of a shared past such as "we" or "that").
- You can just talk. "my brother's name is leo" is filed in drawer 1; "we just saw a red car at the park" is
  logged as a memory. A newer fact replaces an older one about the same thing. Natural lead-ins work too:
  "remember that my locker code is 4312", "fyi my dentist is dr patel", "leo is my brother",
  "i'm allergic to peanuts". If the rules don't recognize how a fact was said, the model may rewrite it, but
  only with your words: its subject must come from your sentence and so must most of the fact, or nothing is filed.
- You can make it forget: "forget my locker code" takes that fact (and any older versions of it) out of
  drawer 1. `/facts` lists drawer 1 and `/forget <id>` removes by number. Core memories can't be removed this
  way; drawer 3 is append-only.
- With the optional embedding model, words match by meaning: "automobile" finds "car", "sibling" finds "sister".
  Related but different words ("car" and "truck") do not match.
- Drawer 1 comes first: a question it can already answer never reaches the model (0.1 s instead of about 5 s on a CPU).
- If one drawer misses, it steps to the next: a past-tense question checks the episode log, and recall checks
  drawer 1 before saying "I don't remember".
- Crisis phrases ("ending it all", "i dont want to be here anymore") always add a support line. Figures of speech
  ("this traffic is killing me") do not.
- Emotional replies are checked for shape: at most three sentences and one gentle question.
- The label comes from which part answered, never from what the model claims.
- Questions about your personal life are answered only from drawer 1. The model never guesses them.
- Drawer 2 asks the model for only the answer (a name, number or few words) or "unknown". An answer that just
  repeats the question is rejected, and so is one whose own words fall below the model's confidence cutoff.
  The cutoff is measured per model with `python -m filecabinet.calibrate` (see below), because each model is
  confident in a different way.
- Time phrases narrow the search: "this morning", "three days ago", "on monday", "last weekend", "this week".
  "What did we do on monday?" lists what was logged that day; "did we go hiking on monday?" won't match a
  Saturday hike.
- A memory only counts if it is found in the episode log. If a first look fails, it asks itself
  "Where were we?", rebuilds that scene, and looks again. Only a strong match can start that search;
  one shared word ("red") is not a memory.
- On a network problem it runs real checks first, and never claims a cause the checks contradict.
- After a task, `/done <fix>` files what was learned: fixed facts to drawer 1, the problem's pattern to drawer 2.
  A repeated lesson strengthens the existing reference instead of making a copy.
- Same input, same output: rules plus a model run at temperature 0 with a fixed seed.

## Setup

Python 3.10 or newer.

```bash
python -m venv .venv
# Linux / WSL / macOS:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Getting models (optional, recommended)

One command downloads the chat model and the embedding model into `models/` and calibrates the chat model:

```bash
python -m filecabinet.fetch               # 3B chat model (about 2.1 GB) + embedding model (67 MB)
python -m filecabinet.fetch --size 1.5b   # smaller chat model (1.1 GB, Apache 2.0)
python -m filecabinet.fetch --gpu-layers -1   # calibrate on the GPU (faster)
```

Files already there are skipped. `python -m filecabinet.fetch --check` (or `python brain_setup.py --check`
from the repo root) downloads nothing and reports what's installed, whether llama-cpp-python can use your
GPU, and exactly what to do about anything missing.

On Windows: PyPI only has llama-cpp-python's source code, so `pip install` builds it on your computer. That
needs Microsoft's "Build Tools for Visual Studio" with the "Desktop development with C++" workload. The
llama-cpp-python project also publishes ready-built packages on its own site (see its README).

To get the models by hand instead:

The embedding model for matching by meaning: `https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf`,
file `bge-small-en-v1.5-f16.gguf` (MIT license, 67 MB). Pass it with `--embed`.

The main model:

Any instruct model in GGUF format works. Tested here with Qwen2.5 1.5B Instruct (Apache 2.0, 1.1 GB):
`https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF`, file `qwen2.5-1.5b-instruct-q4_k_m.gguf`.
On a GTX 1660 (6 GB) a 3B model (`Qwen/Qwen2.5-3B-Instruct-GGUF`, about 2 GB) also fits.

To use the GPU, build llama-cpp-python with CUDA (needs the NVIDIA CUDA toolkit installed):

```bash
# Linux / WSL
CMAKE_ARGS="-DGGML_CUDA=on" pip install --force-reinstall --no-cache-dir llama-cpp-python
# Windows PowerShell
$env:CMAKE_ARGS="-DGGML_CUDA=on"; pip install --force-reinstall --no-cache-dir llama-cpp-python
```

Then pass `--gpu-layers -1`.

### Calibrate each model once

```bash
python -m filecabinet.calibrate --model models/qwen2.5-3b-instruct-q4_k_m.gguf
```

`fetch` does this for you. It asks 28 questions with known answers (12 of them trick questions small models often
get wrong) and 20 about made-up things, sets the confidence cutoff 0.05 above the most confident wrong or invented
answer (never below 0.5), and saves it next to the model (`<model>.gguf.calibration.json`). The cutoff is picked up
automatically after that. Run it again whenever you switch models.

## Run it

```bash
python -m filecabinet --models models     # picks the biggest chat model and the embedding model in the folder
python -m filecabinet --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf --embed models/bge-small-en-v1.5-f16.gguf
python -m filecabinet --model models/qwen2.5-3b-instruct-q4_k_m.gguf --embed models/bge-small-en-v1.5-f16.gguf --gpu-layers -1
python -m filecabinet                      # no model: drawers and rules only
python -m filecabinet --network dns        # practise with a simulated broken network
```

Type `/help` for commands: `/fact`, `/like`, `/dislike`, `/log`, `/done`, `/core`, `/approve`,
`/pending`, `/why`, `/wrong`, `/facts`, `/forget`, `/export`, `/import`. Data is saved in `~/.file_cabinet/cabinet.db`.

### Two computers

Each computer keeps its own memory file. To copy what one has learned to the other, export it and import it
there (`/export brain.json`, `/import brain.json`, or the buttons in the Device Integrator's Brain panel).
Importing skips anything already there. Core memories arrive as proposals and wait for your `/approve`, so
nothing reaches drawer 3 without you.

`python demo.py models/<model>.gguf models/<embedding-model>.gguf` runs a scripted session that shows every part.

## Tests

```bash
python -m pytest                                              # 110 tests, no model needed
FILECABINET_MODEL=models/<model>.gguf python -m pytest        # adds 5 tests on the real model
```

## Efficiency

Measured with the 3B model on a 4-core CPU (no GPU):

| Change | Before | After |
| --- | --- | --- |
| Record each token's probability as it is picked, instead of keeping scores for the whole context | 3.0 s per call, 4.6 GB peak RAM | 2.2 s per call, 4.0 GB |
| Check drawer 1 before asking the model to classify a question | 5.0 s | 0.1 s |
| Ask for only the answer (a name or number), at most 40 tokens | long sentences | one or a few words |

A prompt cache was tried and left out: 12% faster, but 1.4 GB more RAM. On a GPU (`--gpu-layers -1`) model
calls are much faster than these CPU numbers.

## Scorecard

`evals/` holds 112 cases in casual, everyday wording, split in half: a practice half used while improving,
and a held-out half for checking. `python -m evals.run_evals --split holdout --model ... --embed ...` reruns it.

Held-out half:

| Version | Score | Wrong answers given | Invented memories |
| --- | --- | --- | --- |
| First version, 1.5B model | 57% (32/56) | 0 | 0 |
| Now, no model (rules and drawers only) | 95% (36/38; knowledge questions need a model) | 0 | 0 |
| Now, 1.5B model + embeddings | 88% (49/56) | 0 | 0 |
| Now, 3B model + embeddings | 91% (51/56) | 1 | 0 |

By category with the 3B model: routing 92%, learning facts from conversation 100%, reworded recall 100%,
remembering events told in chat 100%, crisis support line 100%, general knowledge 80%, made-up questions
refused 80%, emotional reply shape 100%. The 1.5B model answers fewer knowledge questions (50%) but gave no
wrong answers.

The held-out half is not perfectly unseen: two bug fixes (a question being treated as small talk, and an
over-long fact pattern) came from its failures, and its totals hinted that the rules should run before the model.

### Round 2

32 more cases, written before the round-2 changes: facts said naturally ("remember that…", "leo is my
brother"), forgetting on request, device questions that should and shouldn't check the hardware, and time
phrases ("on monday", "three days ago"). Held-out half:

| Version | New categories | Whole scorecard | Wrong answers | Invented memories |
| --- | --- | --- | --- | --- |
| Before round 2, no model | 10/13 device questions only; 0% natural wording, 0% forgetting, 67% time | 82% (42/51) | 0 | 1 |
| After round 2, no model | 13/13 (100%) | 96% (49/51) | 0 | 0 |
| After round 2, 1.5B model | 13/13 (100%) | 90% (62/69) | 0 | 0 |
| After round 2, 3B model | 13/13 (100%) | 93% (64/69) | 1 | 0 |

(The model rows include the general-knowledge questions, which the no-model rows can't answer.)

## Differences from the design doc

- Two labels were added: **I remember** (found in the episode log or core memories) and
  **From my core** (deep emotional answers guided by drawer 3).
- Personal-fact questions never reach the model, and model answers must clear a confidence cutoff
  calibrated for each model. In testing, the model invented "Buddy" for "What was the name of my first dog?"
  and marked it as known.
- Milestone 7 (nightly adapter training) is not built yet. Corrections from `/wrong` are saved for it.

## Known limits

- Unusual wording can still be misrouted (92% routing on the held-out scorecard). `/why` shows the route.
- The confidence check lowers wrong answers but is not perfect: the 3B model still answered one made-up
  question ("Bismarck" for a fictional admiral's ship) above its calibrated cutoff.
- Fact extraction from conversation is rules only; sentences it doesn't recognize are not filed (it says so).
- Network checks are Linux (`ip`, `ping`) and Windows (`ipconfig`, `ping`); the Windows parsing expects
  English output and has only been tested against sample output. Anything that can't run is reported as
  "could not check", never guessed.
- Recall understands color, place, time and who. Other details are only found if the words match.
