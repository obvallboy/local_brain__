# Devy for iPhone (Expo)

A phone **screen** for Devy. It runs no model and touches no hardware — it talks over your
network to the Devy server (the Device Integrator) running on your computer or Pi. Everything
still happens on that machine; the phone just asks and shows the answers, with the same honesty
labels (*I know*, *I checked*, *I think*, *I remember*, *I'm not sure*) and a "why?" on each.

Built with Expo SDK 58 (React Native). Run it on your iPhone with **Expo Go** — no Mac or App
Store build needed.

## 1. Start the Devy server on your computer

On your laptop/desktop/Pi, from the repo:

```bash
cd device-integrator
python app.py --host 0.0.0.0        # add --gpu-layers -1 to run the model on the GPU
```

`--host 0.0.0.0` lets your phone reach it. Note the machine's address:

- **Same Wi-Fi:** its LAN IP, e.g. `192.168.1.50`.
- **Tailscale (recommended, works anywhere):** its Tailscale IP, `100.x.y.z` (run `tailscale ip`).
  Install the Tailscale app on the iPhone and sign in, so the phone is on your tailnet too.

So the server address is like `http://192.168.1.50:5000` or `http://100.x.y.z:5000`.

## 2. Run the app and open it on the iPhone

On your computer:

```bash
cd mobile
npm install
npx expo start
```

Install **Expo Go** from the App Store on your iPhone, then scan the QR code in the terminal
with the Camera app. The app loads on your phone. (Phone and computer must be able to reach each
other — same Wi-Fi, or both on Tailscale. `npx expo start --tunnel` also works if the QR/LAN
connection is fussy.)

## 3. Point it at your server

Tap the ⚙︎ in the app, enter your server address from step 1, and Save & connect. The header
shows the connection (the model it's running, or "not connected" with the reason). The address is
remembered. Then ask Devy anything, or tap a quick button.

## Notes and limits

- **It's a client.** The model, your memory file, and all hardware access stay on the computer.
  Two phones pointing at the same server share that one Devy and its memory.
- **HTTP in Expo Go is fine.** The server has no HTTPS, and Expo Go allows plain HTTP in
  development. A later standalone build would need an HTTPS server or an iOS ATS exception.
- **This hasn't been run on a physical iPhone from here** — it typechecks and bundles cleanly
  (`npx tsc --noEmit`, `npx expo export`), but the first real-device run is yours to try. If
  anything's off, tell me what you see.
- **Two tabs:** **Chat** (ask/tell Devy) and **Devices** (what's plugged into the server, with a **Scan**
  button on each serial port that finds its baud rate and recognizes what's answering). Guided jobs in the
  app are the next follow-up.
