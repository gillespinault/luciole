#!/usr/bin/env bash
# Relance les simulations et n'affiche que les lignes de résultat.
#
#   v0/simu-signaux/lancer.sh                 tous les cas
#   v0/simu-signaux/lancer.sh a2_ruban.cir    un seul
#
# Le journal complet de ngspice reste dans v0/simu-signaux/sorties/<cas>.log.
# Une ligne « ALERTE » signale un calcul que ngspice n'a pas mené au bout :
# le résultat de ce cas ne vaut alors rien.
set -euo pipefail
ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HW="$(cd "$ICI/../.." && pwd)"
mkdir -p "$ICI/sorties"
cd "$HW"
if [ $# -eq 0 ]; then
  set -- modeles/essai_bss138.cir a1_i2c_niveaux.cir a1_i2c_fronts.cir a2_ruban.cir \
         a3_rail_coupe.cir a4_carte_eteinte.cir b_donnee_led.cir c_reset.cir \
         d_bouton.cir e_pont_retour.cir
fi
for f in "$@"; do
  nom="$(basename "$f" .cir)"
  log="$ICI/sorties/$nom.log"
  echo "== $f"
  tools/kicad ngspice -b "v0/simu-signaux/$f" > "$log" 2> "$log.err" || echo "ALERTE ngspice a rendu une erreur, voir $log"
  grep -a "^RESULTAT" "$log" || echo "ALERTE aucun résultat, voir $log"
  grave="timestep too small|singular matrix|no convergence|aborted|interrupted|fatal|source stepping failed|transient op started|syntax error|unknown|undefined|cannot|no such|not found"
  if grep -a -i -E "$grave" "$log" "$log.err" > /dev/null; then
    echo "ALERTE ngspice signale un calcul non abouti ou une erreur :"
    grep -a -i -h -E "$grave" "$log" "$log.err" | sort | uniq -c | head -10
  fi
  n="$(grep -a -c -E "^ *meas .* failed" "$log" || true)"
  if [ "$n" != "0" ]; then
    echo "note : $n mesure(s) sans résultat, c'est-à-dire un niveau jamais atteint (valeur -1 dans les lignes ci-dessus)"
  fi
done
