#!/usr/bin/env bash
# flash.sh — flashe un NanoC6 ou un AtomS3 Lite et affiche sa console quelques
# secondes. La puce est détectée sur chaque port (esp32c6 → build/, esp32s3 →
# build-esp32s3/).
#
# Piège géré : le conteneur limn-adopt-bridge tient les ports série ouverts et
# corrompt tout flash long ("Invalid head of packet", "chip stopped responding").
# On l'arrête le temps du flash et on le relance après.
#
# Usage : ./flash.sh [/dev/ttyACMx | --all] [--no-build] [--watch S]
#   port par défaut : le seul /dev/serial/by-id/usb-Espressif* présent
#   --all          : flashe tous les /dev/serial/by-id/usb-Espressif* (hub)
#   --watch S      : durée de lecture de la console après le flash (défaut 12)
set -euo pipefail
cd "$(dirname "$0")"
PORT=""; BUILD=1; WATCH=12; ALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --all) ALL=1; shift;;
    --no-build) BUILD=0; shift;;
    --watch) WATCH="$2"; shift 2;;
    *) PORT="$1"; shift;;
  esac
done
mapfile -t C < <(ls /dev/serial/by-id/usb-Espressif* 2>/dev/null || true)
if [ "$ALL" = 1 ]; then
  [ "${#C[@]}" -ge 1 ] || { echo "aucun appareil Espressif branché" >&2; exit 1; }
  PORTS=("${C[@]}")
elif [ -z "$PORT" ]; then
  [ "${#C[@]}" -eq 1 ] || { echo "ports Espressif trouvés : ${C[*]:-aucun} — précise le port ou --all" >&2; exit 1; }
  PORTS=("${C[0]}")
else
  PORTS=("$PORT")
fi
# shellcheck disable=SC1090
source "${IDF_EXPORT:-$HOME/esp/esp-idf-v5.5/export.sh}" >/dev/null 2>&1
[ "$BUILD" = 1 ] && { idf.py build | tail -2; idf.py -B build-esp32s3 -D SDKCONFIG=build-esp32s3/sdkconfig set-target esp32s3 build | tail -2; }

BRIDGE_RUNNING=false
if docker inspect limn-adopt-bridge >/dev/null 2>&1; then
  BRIDGE_RUNNING="$(docker inspect -f '{{.State.Running}}' limn-adopt-bridge)"
fi
restart_bridge() { [ "$BRIDGE_RUNNING" = true ] && docker start limn-adopt-bridge >/dev/null && echo "limn-adopt-bridge relancé"; }
trap restart_bridge EXIT
[ "$BRIDGE_RUNNING" = true ] && { docker stop limn-adopt-bridge >/dev/null; echo "limn-adopt-bridge arrêté le temps du flash"; sleep 1; }

# Un NanoC6 sous firmware d'usine inonde la console et fait rater le premier
# esptool ("Invalid head of packet", "chip stopped responding") : on réessaie.
FAILED=()
for P in "${PORTS[@]}"; do
  PORT="$(readlink -f "$P")"
  NAME="${P##*unit_}"; NAME="${NAME%-if00}"
  OK=0; CHIP=""; DIR=""
  for TRY in 1 2 3; do
    CHIP="$(python -m esptool --chip auto -p "$PORT" -b 115200 --before default_reset --after no_reset chip_id 2>/dev/null \
            | sed -n 's/^Chip is \(ESP32-[CS][0-9]\).*/\1/p' | head -1 | tr 'A-Z' 'a-z' | tr -d -)"
    [ -n "$CHIP" ] && break; sleep 2
  done
  case "$CHIP" in
    esp32c6) DIR=build;;
    esp32s3) DIR=build-esp32s3;;
    *) echo "=== $PORT ($NAME) : puce non reconnue (« $CHIP »), ignoré"; FAILED+=("$NAME"); continue;;
  esac
  [ -f "$DIR/flash_args" ] || { echo "=== $PORT ($NAME) : $CHIP mais pas de $DIR/flash_args, compile d'abord"; FAILED+=("$NAME"); continue; }
  for TRY in 1 2 3 4 5; do
    BAUD=460800; [ "$TRY" -gt 1 ] && BAUD=115200   # plus lent, mais tient sur un hub capricieux
    echo "=== flash $PORT ($NAME, $CHIP) essai $TRY à $BAUD bauds"
    if (cd "$DIR" && python -m esptool --chip "$CHIP" -p "$PORT" -b "$BAUD" --before default_reset --after hard_reset \
        write_flash "@flash_args") > /tmp/luciole-flash.log 2>&1; then
      grep -E "Wrote .* at 0x00010000" /tmp/luciole-flash.log || true; OK=1; break
    fi
    grep -E "rror|fatal" /tmp/luciole-flash.log | tail -1; sleep 2
  done
  [ "$OK" = 1 ] || FAILED+=("$NAME")
done
[ "${#FAILED[@]}" -eq 0 ] || echo "ÉCHEC après 5 essais : ${FAILED[*]}"

for P in "${PORTS[@]}"; do
  PORT="$(readlink -f "$P")"
  echo "=== console $PORT pendant $WATCH s"
  python - "$PORT" "$WATCH" <<'PY'
import serial, sys, time
s = serial.Serial(sys.argv[1], 115200, timeout=0.5)
s.rts = True; time.sleep(0.1); s.rts = False   # pulse RTS : reset pour capter le boot
end = time.time() + float(sys.argv[2]); buf = b''
while time.time() < end: buf += s.read(4096)
for l in buf.decode('utf-8', 'replace').splitlines():
    if 'luciole' in l or 'ESPNOW' in l or 'rror' in l or 'abort' in l or 'Guru' in l: print(l)
PY
done
