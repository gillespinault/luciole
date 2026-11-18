#!/usr/bin/env bash
# Relance les simulations et range les tableaux dans v0/simu/resultats/.
#   v0/simu/lancer.sh              toutes
#   v0/simu/lancer.sh b_partage    une seule (nom du fichier sans .cir)
#
# Pour chaque fichier X.cir :
#   resultats/X.txt           les tableaux, sans le bavardage de ngspice
#   resultats/journaux/X.log  la sortie complète
# Le script signale tout calcul qui n'a pas convergé. Un tableau issu d'un
# calcul signalé n'est pas un résultat.
set -euo pipefail
SIMU="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HW="$(cd "$SIMU/../.." && pwd)"
cd "$HW"
mkdir -p "$SIMU/resultats/journaux"

if [ "$#" -gt 0 ]; then
  liste=("$@")
else
  liste=(00_modeles a_inversion a5_branchement a5_corrections b_partage b3_debranchement c_chargeur)
fi

bruit='^[[:space:]]*$|Doing analysis|SPARSE|KLU|No\. of Data|^Circuit:|Reference value|Reset re-loads|^Note: |Warning: (Dynamic|True) gmin|Initial Transient|^-+$|Transient Analysis|^ngspice-|^(vb0|vs0|tdev|i30|i40|tbas|thaut|thaut2|t80|t82|t45|t43|[a-g])[[:space:]]+='
alerte='Transient op started|[Tt]imestep too small|^Error|singular matrix|source stepping failed|no such|Fatal'

echec=0
for f in "${liste[@]}"; do
  f="${f%.cir}"
  journal="$SIMU/resultats/journaux/$f.log"
  echo "== $f"
  tools/kicad stdbuf -o0 -e0 ngspice -b "v0/simu/$f.cir" >"$journal" 2>&1 || true
  grep -v -E "$bruit" "$journal" >"$SIMU/resultats/$f.txt" || true
  if grep -q -E "$alerte" "$journal"; then
    echo "   ATTENTION : calcul non convergé ou erreur, voir $journal"
    grep -n -E "$alerte" "$journal" | head -5 | sed 's/^/   /'
    echec=1
  else
    echo "   ok : $(wc -l <"$SIMU/resultats/$f.txt") lignes dans resultats/$f.txt"
  fi
done
exit "$echec"
