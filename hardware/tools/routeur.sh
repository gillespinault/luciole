#!/usr/bin/env bash
# Essaie un routeur automatique sur la carte d'un projet.
#
#   tools/routeur.sh v0 freerouting
#   tools/routeur.sh v0 krt
#
# Part de <projet>/<projet>.kicad_pcb tel que carte.py l'a écrit (pistes déjà tracées
# par script comprises) et travaille sur une copie, dans <projet>/out/routage-<outil>/.
# Rien n'est écrit dans le projet : le résultat se regarde, se contrôle, puis se fige
# dans le dépôt si on le garde. Un routeur automatique ne redonne pas forcément deux
# fois le même tracé ; la construction, elle, doit rester reproductible.
#
# Les deux routeurs tournent dans un conteneur sans accès au réseau, qui ne voit que
# le dossier hardware/. Installation : tools/outils.sh.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
P="${1:?usage : tools/routeur.sh <projet> freerouting|krt}"
OUTIL="${2:?usage : tools/routeur.sh <projet> freerouting|krt}"
D="$P/out/routage-$OUTIL"
rm -rf "$D"; mkdir -p "$D"
cp "$P/$P.kicad_pcb" "$P/$P.kicad_pro" "$P/$P.kicad_sch" "$P/fp-lib-table" "$P/sym-lib-table" "$D/"
[ -f "$P/derogations.txt" ] && cp "$P/derogations.txt" "$D/"

case "$OUTIL" in
  freerouting)
    # Les pistes déjà tracées sont verrouillées : le routeur les garde telles quelles.
    tools/kicad python3 - "$D/$P" <<'EOF' 2>&1 | grep -v "memory leak"
import sys
import pcbnew
base = sys.argv[1]
b = pcbnew.LoadBoard(base + ".kicad_pcb")
locked = 0
for t in b.GetTracks():
    t.SetLocked(True)
    locked += 1
# Les plans de masse sont retirés de la copie : Freerouting les prend pour des obstacles
# et ne route presque rien au travers. La masse n'est pas routée : ses pastilles perdent
# leur réseau dans la copie, et ce sont les plans, remis par carte.py, qui la relient.
for fp in b.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname() == "GND":
            pad.SetNetCode(0)
for z in list(b.Zones()):                  # en dernier : après un retrait, pcbnew ne rend plus ses listes
    if not z.GetIsRuleArea():
        b.Remove(z)
pcbnew.SaveBoard(base + ".kicad_pcb", b)
b = pcbnew.LoadBoard(base + ".kicad_pcb")          # carte relue : l'export part de ce qui est écrit
print("export pour le routeur :", pcbnew.ExportSpecctraDSN(b, base + ".dsn"), "-", locked, "pistes verrouillées")
EOF
    docker run --rm --network none -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/$D":/work -w /work \
      --entrypoint java ghcr.io/freerouting/freerouting:2.5.0 -jar /app/freerouting-executable.jar \
      -de "/work/$P.dsn" -do "/work/$P.ses" -mp "${PASSES:-30}" --gui-enabled=false > "$D/routeur.log" 2>&1 || true
    grep -E "Auto-routing pass|Auto-routing stage completed|finished with state" "$D/routeur.log" | tail -3 | cut -c1-200
    [ -f "$D/$P.ses" ] || { echo "pas de résultat : voir $D/routeur.log"; exit 1; }
    tools/kicad python3 - "$D/$P" <<'EOF' 2>&1 | grep -v "memory leak"
import sys
import pcbnew
base = sys.argv[1]
b = pcbnew.LoadBoard(base + ".kicad_pcb")
print("import du routage :", pcbnew.ImportSpecctraSES(b, base + ".ses"), "-", len(b.GetTracks()), "pistes et vias")
pcbnew.SaveBoard(base + ".kicad_pcb", b)
EOF
    ;;
  krt)
    # Sans rétrécissement : une liaison qui ne passe pas à nos dimensions échoue.
    mv "$D/$P.kicad_pcb" "$D/$P-entree.kicad_pcb"
    timeout "${DUREE:-1200}" docker run --rm --network none -u "$(id -u):$(id -g)" -e HOME=/tmp \
      -e PYTHONPATH=/hw/tiers/pydeps -e PYTHONUNBUFFERED=1 -v "$PWD":/hw -w /hw/tiers/KiCadRoutingTools python:3.12-slim \
      python py_router/route.py "/hw/$D/$P-entree.kicad_pcb" --output "/hw/$D/$P.kicad_pcb" \
      --escalation off --track-width 0.25 --clearance 0.2 --via-size 0.6 --via-drill 0.3 \
      > "$D/routeur.log" 2>&1 || echo "le routeur s'est arrêté sur une erreur ou sur le délai : voir $D/routeur.log"
    grep -E "routed|connected|Wall time|EXIT" "$D/routeur.log" | tail -5 | cut -c1-200
    [ -f "$D/$P.kicad_pcb" ] || { echo "pas de résultat"; exit 1; }
    # Le routeur réécrit les règles dans son fichier de projet : on remet les nôtres.
    cp "$P/$P.kicad_pro" "$D/$P.kicad_pro"
    ;;
  *) echo "outil inconnu : $OUTIL"; exit 2 ;;
esac

tools/kicad bash -c "kicad-cli pcb drc --schematic-parity --severity-all --refill-zones --save-board --format json -o '$D/drc.json' '$D/$P.kicad_pcb' >/dev/null 2>&1; python3 tools/drccheck.py '$D/drc.json' '$D/derogations.txt' > '$D/drc-compte-rendu.txt' || true; head -1 '$D/drc-compte-rendu.txt'"
echo "résultat dans $D/"
