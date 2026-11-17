#!/usr/bin/env bash
# Reconstruit un projet de bout en bout et s'arrête à la première vérification qui échoue.
#
#   tools/build.sh essai
#
# Le projet est un dossier contenant circuit.py (schéma), netlist_voulue.txt
# (connexions voulues, écrites à la main) et carte.py (placement et routage).
# Tout ce qui est produit va dans <projet>/out/.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
P="${1:?usage : tools/build.sh <projet>}"

if ! command -v kicad-cli >/dev/null; then      # hors de l'image : on y entre
  exec tools/kicad bash tools/build.sh "$P"
fi

OUT="$P/out"; FAB="$OUT/fab"
rm -rf "$OUT"; mkdir -p "$FAB/gerbers"
# Les fichiers KiCad du projet sont des produits de la construction : on les supprime
# avant de les régénérer. Le fichier de projet garde sinon les réglages faits à la main
# dans KiCad, dont la désactivation d'un contrôle, et la construction passerait à tort
# (défaut trouvé par la revue du 17 novembre 2026, cas « controle_desactive » du banc).
rm -f "$P/$P.kicad_pro" "$P/$P.kicad_prl" "$P/$P.kicad_sch" "$P/$P.kicad_pcb"
step() { printf '\n== %s\n' "$*"; }

step "Bibliothèque du projet"
python3 lib/build_lib.py

step "Schéma"
python3 "$P/circuit.py"

step "Contrôle électrique du schéma (ERC)"
kicad-cli sch erc --severity-all --exit-code-violations --format report -o "$OUT/erc.rpt" "$P/$P.kicad_sch"

step "Connexions : liste voulue contre liste exportée par KiCad"
kicad-cli sch export netlist --format kicadsexpr -o "$OUT/$P.net" "$P/$P.kicad_sch" >/dev/null
python3 tools/netcheck.py "$P/netlist_voulue.txt" "$OUT/$P.net"

step "Carte"
python3 "$P/carte.py"

step "Contrôle des règles de dessin (DRC) et cohérence avec le schéma"
kicad-cli pcb drc --schematic-parity --severity-all --exit-code-violations --format report -o "$OUT/drc.rpt" "$P/$P.kicad_pcb"

step "Fichiers de fabrication"
kicad-cli pcb export gerbers --no-x2 --no-netlist --subtract-soldermask --precision 6 \
  -l F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
  -o "$FAB/gerbers/" "$P/$P.kicad_pcb" >/dev/null
kicad-cli pcb export drill --format excellon --drill-origin absolute --excellon-units mm \
  --excellon-zeros-format decimal --excellon-oval-format alternate --excellon-separate-th \
  -o "$FAB/gerbers/" "$P/$P.kicad_pcb" >/dev/null
kicad-cli pcb export pos --format csv --units mm --side both --exclude-dnp \
  -o "$OUT/$P-pos-kicad.csv" "$P/$P.kicad_pcb" >/dev/null
python3 tools/jlc.py "$OUT/$P.net" "$OUT/$P-pos-kicad.csv" "$FAB/gerbers" "$FAB" "$P"

step "Documents de relecture"
kicad-cli sch export pdf -o "$OUT/$P-schema.pdf" "$P/$P.kicad_sch" >/dev/null
kicad-cli pcb export pdf --mode-single -l F.Cu,F.SilkS,F.Fab,Edge.Cuts -o "$OUT/$P-trace-dessus.pdf" "$P/$P.kicad_pcb" >/dev/null
kicad-cli pcb export pdf --mode-single -l B.Cu,B.SilkS,B.Fab,Edge.Cuts -o "$OUT/$P-trace-dessous.pdf" "$P/$P.kicad_pcb" >/dev/null
kicad-cli pcb render --side top --quality high --background opaque -w 2000 -h 1100 -o "$OUT/$P-rendu-dessus.png" "$P/$P.kicad_pcb" >/dev/null
kicad-cli pcb render --side bottom --quality high --background opaque -w 2000 -h 1100 -o "$OUT/$P-rendu-dessous.png" "$P/$P.kicad_pcb" >/dev/null
kicad-cli pcb export step --subst-models --force -o "$OUT/$P.step" "$P/$P.kicad_pcb" >/dev/null 2>&1 || echo "export STEP : échec (non bloquant)"

step "Terminé : fichiers dans $OUT/"
ls "$FAB"
