"""Écrit le dossier de revue d'un routage : la carte en clair, pour un relecteur.

    tools/kicad python3 tools/dossier.py v0/v0.kicad_pcb v0/revue

Un fichier .kicad_pcb pèse plus d'un mégaoctet, dont l'essentiel est le remplissage des
plans. Ce dossier en tire ce qu'il faut pour relire un routage sans KiCad : règles,
composants, et pour chaque réseau ses pastilles, ses pistes mises bout à bout, ses vias.
Il ne contient aucun avis : le relecteur part des faits.

Écrit <dossier>/routage.md. Les images se font avec tools/vue.py (voir le README).
Cotes en millimètres depuis le coin haut gauche de la carte, face avant vue de dessus ;
le dos est vu par transparence, donc dans le même repère.
"""
import sys

import pcbnew

ORIGINE = (100.0, 100.0)       # origine de la carte dans le fichier (pcbkit.Board)


def main():
    path, out = sys.argv[1], sys.argv[2]
    b = pcbnew.LoadBoard(path)
    mm = pcbnew.ToMM

    def xy(p):
        return f"({mm(p.x) - ORIGINE[0]:.2f},{mm(p.y) - ORIGINE[1]:.2f})"

    def face(layer):
        return "avant" if layer == pcbnew.F_Cu else "dos"

    box = b.GetBoardEdgesBoundingBox()
    ds = b.GetDesignSettings()
    L = []
    L.append(f"# Dossier de revue du routage : {b.GetTitleBlock().GetTitle() or path}")
    L.append("")
    L.append(f"Tiré de `{path}`. Cotes en millimètres depuis le coin haut gauche, face avant vue de dessus ; "
             "le dos est donné dans le même repère (vu par transparence). x va vers la droite, y vers le bas.")
    L.append("")
    L.append("## Carte")
    L.append("")
    L.append(f"- Contour : {mm(box.GetWidth()):.1f} × {mm(box.GetHeight()):.1f} mm, deux couches de cuivre (avant F.Cu, dos B.Cu).")
    L.append(f"- Règles du projet : isolement minimal {mm(ds.m_MinClearance):.2f} mm, piste minimale {mm(ds.m_TrackMinWidth):.2f} mm, "
             f"via {mm(ds.m_ViasMinSize):.2f} mm percé à {mm(ds.m_MinThroughDrill):.2f} mm, cuivre à {mm(ds.m_CopperEdgeClearance):.2f} mm du bord.")
    tracks = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    fps = sorted(b.GetFootprints(), key=lambda f: (f.GetReference().rstrip("0123456789"), int("".join(c for c in f.GetReference() if c.isdigit()) or 0)))
    L.append(f"- {len(fps)} composants ({sum(1 for f in fps if not f.IsFlipped())} en face avant, {sum(1 for f in fps if f.IsFlipped())} au dos), "
             f"{len(tracks)} segments de piste, {len(vias)} vias.")
    for z in b.Zones():
        if z.GetIsRuleArea():
            zb = z.GetBoundingBox()
            L.append(f"- Zone interdite « {z.GetZoneName()} » : x {mm(zb.GetLeft()) - ORIGINE[0]:.2f} à {mm(zb.GetRight()) - ORIGINE[0]:.2f}, "
                     f"y {mm(zb.GetTop()) - ORIGINE[1]:.2f} à {mm(zb.GetBottom()) - ORIGINE[1]:.2f} (pistes, vias, cuivre et composants).")
            continue
        lid = z.GetFirstLayer()
        polys = z.GetFilledPolysList(lid)
        areas = sorted((abs(polys.Outline(k).Area()) / 1e12 for k in range(polys.OutlineCount())), reverse=True)
        L.append(f"- Plan {z.GetNetname()} en face {face(lid)} : {len(areas)} morceau(x) après remplissage, "
                 f"{sum(areas):.0f} mm² en tout ; les plus grands : {', '.join(f'{a:.0f}' for a in areas[:6])} mm². "
                 f"Isolement du plan {mm(z.GetLocalClearance().value() if hasattr(z.GetLocalClearance(), 'value') else z.GetLocalClearance()):.2f} mm.")
    L.append("")
    L.append("## Composants")
    L.append("")
    L.append("| Repère | Valeur | Empreinte | Face | x | y | Angle |")
    L.append("|---|---|---|---|---|---|---|")
    for f in fps:
        p = f.GetPosition()
        L.append(f"| {f.GetReference()} | {f.GetValue()} | {f.GetFPID().GetLibItemName()} | {'dos' if f.IsFlipped() else 'avant'} | "
                 f"{mm(p.x) - ORIGINE[0]:.2f} | {mm(p.y) - ORIGINE[1]:.2f} | {f.GetOrientationDegrees():.0f} |")
    L.append("")
    L.append("## Réseaux")
    L.append("")
    L.append("Pour chaque réseau : ses pastilles (repère.broche, face, centre), ses pistes mises bout à bout "
             "(face, largeur, suite de points), ses vias (traversants, pastille de 0,6 mm). "
             "Les pistes de masse sont rares : la masse passe par les deux plans.")
    L.append("")
    pads = {}
    for f in fps:
        for pad in f.Pads():
            name = pad.GetNetname().lstrip("/")
            if not name:
                continue
            sides = "+".join(face(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu) if pad.IsOnLayer(l))
            pads.setdefault(name, []).append(f"{f.GetReference()}.{pad.GetNumber()} {sides} {xy(pad.GetPosition())}")
    by_net = {}
    for t in tracks:
        by_net.setdefault(t.GetNetname().lstrip("/"), []).append(t)
    via_net = {}
    for v in vias:
        via_net.setdefault(v.GetNetname().lstrip("/"), []).append(v)
    for name in sorted(set(pads) | set(by_net) | set(via_net)):
        segs = by_net.get(name, [])
        long_f = sum(mm(t.GetLength()) for t in segs if t.GetLayer() == pcbnew.F_Cu)
        long_b = sum(mm(t.GetLength()) for t in segs if t.GetLayer() == pcbnew.B_Cu)
        widths = sorted(set(round(mm(t.GetWidth()), 2) for t in segs))
        L.append(f"### {name}")
        L.append("")
        L.append(f"{len(pads.get(name, []))} pastille(s) ; pistes : {long_f:.1f} mm en face avant, {long_b:.1f} mm au dos"
                 + (f", largeurs {', '.join(f'{w:g}' for w in widths)} mm" if widths else "")
                 + f" ; {len(via_net.get(name, []))} via(s).")
        L.append("")
        if name in pads:
            L.append("Pastilles : " + " ; ".join(pads[name]) + ".")
            L.append("")
        # Pistes bout à bout : par face et largeur, on prolonge une suite tant qu'un segment s'y raccorde.
        groups = {}
        for t in segs:
            groups.setdefault((t.GetLayer(), t.GetWidth()), []).append(((t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)))
        for (lid, w), rest in sorted(groups.items()):
            rest = list(rest)
            while rest:
                a, e = rest.pop(0)
                chain = [a, e]
                grown = True
                while grown:
                    grown = False
                    for k, (p, q) in enumerate(rest):
                        if p == chain[-1]:
                            chain.append(q)
                        elif q == chain[-1]:
                            chain.append(p)
                        elif q == chain[0]:
                            chain.insert(0, p)
                        elif p == chain[0]:
                            chain.insert(0, q)
                        else:
                            continue
                        rest.pop(k)
                        grown = True
                        break
                L.append(f"- {face(lid)}, {mm(w):g} mm : " + " > ".join(
                    f"({mm(x) - ORIGINE[0]:.2f},{mm(y) - ORIGINE[1]:.2f})" for x, y in chain))
        if name in via_net:
            L.append("- vias : " + " ".join(xy(v.GetPosition()) for v in via_net[name]))
        L.append("")
    with open(f"{out}/routage.md", "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("écrit", f"{out}/routage.md", f"({sum(len(x) + 1 for x in L) // 1024} ko, {len(L)} lignes)")


main()
