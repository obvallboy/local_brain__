# The Devy dev build (for Bluetooth and the on-phone model)

Two features use **native code** that Expo Go can't load:
- **Bluetooth** (scan/connect to BLE devices like an ESP32).
- **A real on-phone model** (llama.cpp running a small model on the phone).

To use them you need a **development build** — a custom build of the Devy app that
includes that native code. Everything else (Chat, Devices, Reference, the on-phone
*rules* Devy) works in plain Expo Go with no build.

## The honest catch on iOS

Installing a custom build on a **physical iPhone** is gated by Apple, not by us:
- **With a Mac:** free — Xcode signs it with your free Apple ID (re-sign every 7 days).
- **Without a Mac (cloud build with EAS):** you need the **Apple Developer Program**
  ($99/year). EAS builds iOS in the cloud, but Apple still requires a paid account to
  register a device and install a development build on it.
- **Android** dev builds are free and easy — but this is for your iPhone.

So: the features are built and ready, but putting them on your iPhone needs **a Mac or a
paid Apple Developer account**. There's no way around Apple's signing rules.

## Build it (cloud, no Mac — needs the paid Apple account)

On any computer (your Pi works), from `mobile/`:

```bash
npm install -g eas-cli      # or use npx eas-cli
eas login                   # free account at expo.dev
eas init                    # links this project to your Expo account
eas device:create           # register your iPhone (opens a link to install a profile)
eas build --profile development --platform ios
```

EAS will ask about Apple credentials — sign in with your Apple ID and let EAS manage
signing (this is where the paid Developer account is required). When the build finishes,
EAS gives a link/QR to install the **Devy** app on your phone. Make sure iOS
**Developer Mode** is on (Settings → Privacy & Security → Developer Mode).

## Run it

Install the dev build once. Then, each time:

```bash
cd mobile
npx expo start --dev-client
```

Open the installed **Devy** app (not Expo Go), it connects to the dev server, and the
**Bluetooth** tab plus the **on-phone model** (in Chat → On-phone → "Enable a real
on-phone model") now work.

## The on-phone model

In Chat's **On-phone** mode, tap **"Enable a real on-phone model"**. It downloads a small
model once (Qwen 2.5 0.5B, ~400 MB) to the phone and loads it. After that, On-phone mode
answers general questions too (labelled "I think"), still fully offline. It's small, so
expect modest quality; the first load is slow.

## Status (honest)

Bluetooth and the on-phone model are **written, typecheck, and bundle**, but they have
**not been run on a physical iPhone** from this repo — a dev build (and the Apple account
above) is needed to try them. If something misbehaves on your device, tell me what you see.
