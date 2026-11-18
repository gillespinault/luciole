"""Dessine une zone d'une carte, avec le nom des réseaux, pour comprendre un blocage.

    tools/kicad python3 tools/vue.py v0/out/v0-28-dos3-ecart0.2-g3.kicad_pcb 92 13 117 28
    tools/kicad python3 tools/vue.py CARTE X1 Y1 X2 Y2 [--face=F|B] [--zoom=50] [--sortie=v0/out/vue.png]
                                     [--reseaux=PORT_PU,IO2]

Cotes en millimètres depuis le coin haut gauche de la carte, comme dans carte.py.
Face avant en rouge, dos en bleu, vias en vert. Avec --reseaux, ces réseaux sont dessinés
en couleurs vives et le reste en pâle. Avec --plans, le cuivre des plans de masse est
dessiné en fond (vert pâle en face avant, jaune pâle au dos) : un morceau isolé s'y voit. Le nom du réseau est écrit sur chaque pastille, le
repère du composant au centre de son boîtier.
"""
import sys

import pcbnew
from PIL import Image, ImageDraw, ImageFont

ORIGINE = (100.0, 100.0)       # origine de la carte dans le fichier (pcbkit.Board)
VIFS = [(230, 0, 230), (0, 170, 0), (255, 140, 0), (0, 160, 200), (150, 80, 255), (120, 120, 0)]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    path, (x1, y1, x2, y2) = args[0], map(float, args[1:5])
    zoom, face = float(opts.get("zoom", 50)), opts.get("face", "FB")
    sortie = opts.get("sortie", "v0/out/vue.png")
    vifs = {n: VIFS[k % len(VIFS)] for k, n in enumerate(opts.get("reseaux", "").split(",")) if n}

    board = pcbnew.LoadBoard(path)
    mm = pcbnew.ToMM
    img = Image.new("RGB", (int((x2 - x1) * zoom), int((y2 - y1) * zoom)), "white")
    d = ImageDraw.Draw(img, "RGBA")
    petit = ImageFont.load_default(size=max(9, int(zoom * 0.22)))
    gros = ImageFont.load_default(size=max(11, int(zoom * 0.3)))

    def px(x, y):
        return ((x - ORIGINE[0] - x1) * zoom, (y - ORIGINE[1] - y1) * zoom)

    def teinte(net, layer):
        if net in vifs:
            return vifs[net] + (255,)
        base = (220, 40, 40) if layer == "F.Cu" else (40, 80, 220)
        return base + ((60 if vifs else 150),)

    # Quadrillage au millimètre, cotes tous les 2 mm.
    for k in range(int(x1), int(x2) + 1):
        d.line([((k - x1) * zoom, 0), ((k - x1) * zoom, img.height)], fill=(0, 0, 0, 25))
        if k % 2 == 0:
            d.text(((k - x1) * zoom + 2, 1), str(k), fill=(90, 90, 90, 255), font=petit)
    for k in range(int(y1), int(y2) + 1):
        d.line([(0, (k - y1) * zoom), (img.width, (k - y1) * zoom)], fill=(0, 0, 0, 25))
        if k % 2 == 0:
            d.text((1, (k - y1) * zoom + 1), str(k), fill=(90, 90, 90, 255), font=petit)

    faces = [L for L in ("B.Cu", "F.Cu") if L[0] in face]
    if "--plans" in sys.argv:
        for layer in faces:
            lid = pcbnew.F_Cu if layer == "F.Cu" else pcbnew.B_Cu
            teinte_plan = (150, 220, 150, 255) if layer == "F.Cu" else (240, 225, 130, 255)
            for z in board.Zones():
                if z.GetIsRuleArea() or not z.IsOnLayer(lid):
                    continue
                polys = z.GetFilledPolysList(lid)
                for k in range(polys.OutlineCount()):
                    o = polys.Outline(k)
                    d.polygon([px(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())], fill=teinte_plan)
                    for h in range(polys.HoleCount(k)):
                        t = polys.Hole(k, h)
                        d.polygon([px(mm(t.CPoint(i).x), mm(t.CPoint(i).y)) for i in range(t.PointCount())], fill=(255, 255, 255, 255))
    for layer in faces:                                   # le dos d'abord, la face avant par-dessus
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetLayerName() != layer:
                continue
            a, e = t.GetStart(), t.GetEnd()
            w = max(1, int(mm(t.GetWidth()) * zoom))
            d.line([px(mm(a.x), mm(a.y)), px(mm(e.x), mm(e.y))], fill=teinte(t.GetNetname().lstrip("/"), layer), width=w)
        lid = pcbnew.F_Cu if layer == "F.Cu" else pcbnew.B_Cu
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if not pad.IsOnLayer(lid):
                    continue
                box = pad.GetBoundingBox()
                p1, p2 = px(mm(box.GetLeft()), mm(box.GetTop())), px(mm(box.GetRight()), mm(box.GetBottom()))
                net = pad.GetNetname().lstrip("/")
                d.rectangle([p1, p2], fill=teinte(net, layer)[:3] + (110 if net not in vifs else 255,),
                            outline=teinte(net, layer)[:3] + (255,))
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        p = t.GetPosition()
        cx, cy = px(mm(p.x), mm(p.y))
        r = mm(t.GetWidth(pcbnew.F_Cu)) * zoom / 2
        net = t.GetNetname().lstrip("/")
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=vifs.get(net, (60, 150, 60)) + (255,), outline=(0, 0, 0, 255))
        d.ellipse([cx - r / 2, cy - r / 2, cx + r / 2, cy + r / 2], fill=(255, 255, 255, 255))
        if net != "GND":
            d.text((cx + r + 1, cy - r), net, fill=(0, 90, 0, 255), font=petit)
    for fp in board.GetFootprints():
        dos = fp.IsFlipped()
        if ("B" if dos else "F") not in face:
            continue
        for pad in fp.Pads():
            c = pad.GetPosition()
            net = pad.GetNetname().lstrip("/")
            if net and not net.startswith("unconnected-"):
                d.text(px(mm(c.x), mm(c.y)), net, fill=(0, 0, 0, 255), font=petit, anchor="mm")
        c = fp.GetPosition()
        d.text(px(mm(c.x), mm(c.y)), fp.GetReference(), fill=(0, 0, 150, 255) if dos else (150, 0, 0, 255),
               font=gros, anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
    img.save(sortie)
    print("écrit", sortie, img.size)


main()
