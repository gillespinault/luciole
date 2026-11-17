"""Fige le tracé d'un routeur automatique dans un fichier du dépôt.

    tools/kicad python3 tools/gel.py <carte routée> <carte de départ> <projet>/routage.json

Écrit les pistes et les vias que le routeur a ajoutés à la carte de départ, en
millimètres depuis le coin haut gauche de la carte. carte.py les rejoue avec
Board.replay() : la construction redonne alors toujours la même carte, sans
relancer le routeur. Après un changement de placement, on relance le routeur
(tools/routeur.sh) et on fige de nouveau.
"""
import json
import sys

import pcbnew

ORIGIN = (100.0, 100.0)        # origine des cartes écrites par pcbkit


def items(path):
    board = pcbnew.LoadBoard(path)
    out = set()
    for t in board.GetTracks():
        net = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            out.add(("via", net, round(pcbnew.ToMM(p.x) - ORIGIN[0], 4), round(pcbnew.ToMM(p.y) - ORIGIN[1], 4),
                     round(pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)), 4), round(pcbnew.ToMM(t.GetDrill()), 4)))
        else:
            a, b = t.GetStart(), t.GetEnd()
            pa = (round(pcbnew.ToMM(a.x) - ORIGIN[0], 4), round(pcbnew.ToMM(a.y) - ORIGIN[1], 4))
            pb = (round(pcbnew.ToMM(b.x) - ORIGIN[0], 4), round(pcbnew.ToMM(b.y) - ORIGIN[1], 4))
            pa, pb = sorted((pa, pb))
            out.add(("piste", net, board.GetLayerName(t.GetLayer()), pa[0], pa[1], pb[0], pb[1],
                     round(pcbnew.ToMM(t.GetWidth()), 4)))
    return out


def main(routed, base, out_path):
    added = sorted(items(routed) - items(base))
    tracks = [dict(net=i[1], layer=i[2], a=[i[3], i[4]], b=[i[5], i[6]], width=i[7]) for i in added if i[0] == "piste"]
    vias = [dict(net=i[1], at=[i[2], i[3]], diameter=i[4], drill=i[5]) for i in added if i[0] == "via"]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write('{\n "pistes": [\n')
        f.write(",\n".join("  " + json.dumps(t, ensure_ascii=False) for t in tracks))
        f.write('\n ],\n "vias": [\n')
        f.write(",\n".join("  " + json.dumps(v, ensure_ascii=False) for v in vias))
        f.write("\n ]\n}\n")
    print(f"figé dans {out_path} : {len(tracks)} pistes, {len(vias)} vias")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
