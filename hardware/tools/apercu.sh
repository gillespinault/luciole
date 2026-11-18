#!/bin/sh
# Aperçu 3D d'une carte. À lancer après tools/build.sh :
#
#   tools/apercu.sh v0
#
# Écrit <projet>/3d/luciole-<projet>.step, que Fusion 360 et les autres logiciels de CAO
# ouvrent tels quels, et dans <projet>/out/apercu/ un modèle compact pour le web
# (carte.glb) et une vue à plat de chaque face. Les pièces sans modèle 3D y sont des
# volumes simples : voir tools/volumes.py.
set -eu
cd "$(dirname "$0")/.."
P=$1
A=$P/out/apercu
mkdir -p "$A" "$P/3d"

tools/kicad python3 tools/volumes.py "$P/$P.kicad_pcb" "$A"
C=$A/$P-apercu.kicad_pcb

# Les modèles absents de l'image KiCad sont signalés par l'export : ils sont remplacés par
# les volumes ci-dessus, le message n'apprend rien.
tools/kicad kicad-cli pcb export step -f --subst-models -o "$P/3d/luciole-$P.step" "$C" 2>&1 \
    | grep -v -E "File not found|Could not add 3D model" || true
tools/kicad kicad-cli pcb export glb -f --subst-models --include-tracks --include-pads --include-zones \
    --include-silkscreen --include-soldermask -o "$A/complet.glb" "$C" 2>&1 \
    | grep -v -E "File not found|Could not add 3D model" || true
python3 tools/compacte.py "$A/complet.glb" "$A/carte.glb"

# Le grossissement cadre une carte de 122 x 28 mm dans une image de 3000 x 780.
for s in top bottom; do
    tools/kicad kicad-cli pcb render --side $s --quality high --background transparent \
        -w 3000 -h 780 --zoom 3.55 -o "$A/vue-$s.png" "$C" >/dev/null
done
ls -l "$P/3d/luciole-$P.step" "$A/carte.glb" "$A"/vue-*.png | awk '{print $5, $NF}'
