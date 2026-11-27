# Devy skill for Minis

A [Minis](https://github.com/OpenMinis) skill that lets the **Minis app on your iPhone** drive
**Devy** (the Device Integrator) running on your Raspberry Pi or computer. The phone is the
brain and voice; the Pi is the hands. No laptop, and no separate Expo app — if it works on
your Minis (see the one unknown below).

## How it fits

- **Minis** runs an agent (and a small Alpine Linux sandbox) on your phone. Its model is
  remote by default (your own Claude/GPT/Gemini key, or any OpenAI-compatible endpoint).
- This skill's script (`devy-hardware/scripts/devy.sh`) uses `curl` to call Devy's HTTP
  endpoints over your network: `status`, `devices`, `ask`, `serial-scan`, `net-scan`.
- Devy still does all the hardware work on the Pi. The phone never touches a chip.

## The one thing to test first

Minis' docs don't say whether its Linux sandbox can reach your network. That decides whether
this works. In Minis, ask its agent to run (with Devy running on the Pi via
`python app.py --host 0.0.0.0`):

```
curl -s http://<your-pi-ip>:5000/api/brain/status
```

- **JSON back** → you're good; import this skill.
- **Can't connect / no network** → Minis can't reach the Pi; use the Expo app instead
  (`../mobile`), which definitely can.

## Install

1. In Minis' sandbox: `export DEVY_URL=http://<your-pi-ip>:5000` (Tailscale or LAN IP), and
   `apk add curl` if needed.
2. Import the `devy-hardware/` folder as a skill (Minis reads the `SKILL.md` format). Copy it
   into Minis' skills location, or submit/share it however Minis imports skills — see its docs.
3. Ask Minis something like "what's plugged into my Pi?" or "scan 192.168.1.50". It should run
   `devy.sh` and relay Devy's answer with its honesty label.

## Keep it private (optional)

Minis defaults to a cloud model. To keep everything local like the rest of this project, point
Minis at a **local OpenAI-compatible endpoint** — e.g. llama.cpp's server
(`llama-server`) running on your Pi/desktop — instead of a cloud provider. Then the model,
the memory, and the hardware all stay on your machines.

## Status

- `devy.sh` is **tested against a running Devy server** (status, ask, serial-scan, net-scan all
  work, including quoting).
- The skill has **not** been tried inside a real Minis install from here — the sandbox-network
  test above is the first real check. If the import or a call misbehaves, tell me what you see.
