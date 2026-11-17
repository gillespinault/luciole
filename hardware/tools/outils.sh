#!/usr/bin/env bash
# Installe les outils tiers de la chaîne, à version figée, hors du suivi git.
#
#   tools/outils.sh
#
# Deux routeurs automatiques, à comparer sur la carte v0 (règle 7 de la page de
# conception du wiki) :
#   - Freerouting 2.5.0, image Docker ;
#   - KiCadRoutingTools 0.24.1, dans tiers/, avec ses dépendances Python dans tiers/pydeps.
# Tous deux tournent dans un conteneur qui ne voit que le dossier hardware/.
#
# Le garde-fou de Claude Code refuse l'installation de KiCadRoutingTools (paquets PyPI
# et binaire téléchargé) : ce script se lance à la main.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

FREEROUTING="ghcr.io/freerouting/freerouting:2.5.0"
KRT_URL="https://github.com/drandyhaas/KiCadRoutingTools.git"
KRT_COMMIT="0c93c129c0f9f11429bcef279ff3034335ffe90d"      # version 0.24.1, 17 novembre 2026
KRT_TAG="v0.24.1"
PYTHON_IMAGE="python:3.12-slim"

echo "== Freerouting"
docker image inspect "$FREEROUTING" >/dev/null 2>&1 || docker pull "$FREEROUTING"

echo "== KiCadRoutingTools"
mkdir -p tiers
[ -d tiers/KiCadRoutingTools ] || git clone --quiet "$KRT_URL" tiers/KiCadRoutingTools
git -C tiers/KiCadRoutingTools fetch --quiet origin
git -C tiers/KiCadRoutingTools checkout --quiet "$KRT_COMMIT"

docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp/home -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -v "$PWD":/hw -w /hw/tiers/KiCadRoutingTools "$PYTHON_IMAGE" bash -c "
    mkdir -p /tmp/home
    pip install --quiet --target /hw/tiers/pydeps -r requirements.txt
    PYTHONPATH=/hw/tiers/pydeps python build_router.py --tag $KRT_TAG
    PYTHONPATH=/hw/tiers/pydeps python py_router/route.py --help | head -5
  "
echo "== Terminé : outils dans tiers/"
