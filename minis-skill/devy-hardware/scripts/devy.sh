#!/bin/sh
# Devy bridge — call a Device Integrator ("Devy") server over the network from the
# Minis Linux sandbox (or any shell). The model/hardware stay on the Pi/computer.
#
# Set the address first:   export DEVY_URL=http://<your-pi-ip>:5000
# Then:
#   devy.sh status                     # is Devy up, which model
#   devy.sh devices                    # what's plugged into the Devy computer
#   devy.sh ask "what's plugged in?"   # ask/tell Devy (answers carry a label)
#   devy.sh serial-scan /dev/ttyUSB0   # a serial port's baud + what's answering
#   devy.sh net-scan 192.168.1.50      # identify a device on your Wi-Fi
#   devy.sh facts                      # what Devy has filed about you
#
# Needs only `curl`. In Minis' Alpine sandbox:  apk add curl
set -eu

BASE="${DEVY_URL:-http://raspberrypi.local:5000}"
cmd="${1:-help}"

get()  { curl -fsS --max-time 30 "$BASE$1"; }
getq() { curl -fsSG --max-time 40 "$BASE$1" --data-urlencode "$2"; }

case "$cmd" in
  status)      get /api/brain/status ;;
  devices)     get /api/devices ;;
  facts)       get /api/brain/facts ;;
  ask)
    shift
    msg="$*"
    # minimal JSON-string escaping of the message (backslash, then double-quote)
    esc=$(printf '%s' "$msg" | sed 's/\\/\\\\/g; s/"/\\"/g')
    curl -fsS --max-time 60 -H 'Content-Type: application/json' \
      -d "{\"message\":\"$esc\"}" "$BASE/api/brain/ask"
    ;;
  serial-scan) getq /api/brain/serial-scan "port=${2:?usage: devy.sh serial-scan <port>}" ;;
  net-scan)    getq /api/brain/net-scan "host=${2:?usage: devy.sh net-scan <host>}" ;;
  *)
    echo "usage: devy.sh {status|devices|facts|ask <message>|serial-scan <port>|net-scan <host>}" >&2
    echo "DEVY_URL is currently: $BASE" >&2
    exit 1
    ;;
esac
