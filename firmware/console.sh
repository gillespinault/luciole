#!/usr/bin/env bash
# console.sh — lit la console d'un NanoC6 pendant N secondes (défaut 30), sans le flasher.
# Arrête limn-adopt-bridge le temps de la lecture (il tient les ports) et le relance.
# Usage : ./console.sh [/dev/ttyACMx] [secondes] [--all]
set -u
cd "$(dirname "$0")"
PORT=""; SECS=30; ALL=0
for a in "$@"; do case "$a" in --all) ALL=1;; /dev/*) PORT="$a";; *) SECS="$a";; esac; done
mapfile -t C < <(ls /dev/serial/by-id/usb-Espressif* 2>/dev/null || true)
if [ "$ALL" = 1 ]; then PORTS=("${C[@]}"); elif [ -n "$PORT" ]; then PORTS=("$PORT"); else
  [ "${#C[@]}" -eq 1 ] || { echo "ports : ${C[*]:-aucun} — précise le port ou --all" >&2; exit 1; }; PORTS=("${C[0]}"); fi
# shellcheck disable=SC1090
source "${IDF_EXPORT:-$HOME/esp/esp-idf-v5.5/export.sh}" >/dev/null 2>&1
WAS=false; docker inspect limn-adopt-bridge >/dev/null 2>&1 && WAS="$(docker inspect -f '{{.State.Running}}' limn-adopt-bridge)"
[ "$WAS" = true ] && docker stop limn-adopt-bridge >/dev/null
trap '[ "$WAS" = true ] && docker start limn-adopt-bridge >/dev/null' EXIT
python - "$SECS" "${PORTS[@]}" <<'PY'
import serial, sys, time, os
secs=float(sys.argv[1]); ports=[os.path.realpath(p) for p in sys.argv[2:]]
ss={p: serial.Serial(p,115200,timeout=0.05) for p in ports}
end=time.time()+secs; bufs={p:b'' for p in ports}
while time.time()<end:
    for p,s in ss.items():
        d=s.read(4096)
        if not d: continue
        bufs[p]+=d
        while b'\n' in bufs[p]:
            line,_,bufs[p]=bufs[p].partition(b'\n')
            l=line.decode('utf-8','replace').rstrip()
            if 'luciole' in l: print(f"[{p[-7:]}] {l}", flush=True)
PY
