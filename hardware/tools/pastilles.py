"""Dessine la carte des pastilles de test et des ponts de soudure d'une carte.

    tools/kicad python3 tools/pastilles.py v0/v0.kicad_pcb v0/revue/pastilles.png

La carte ne porte aucune inscription à côté de ses pastilles : elle est trop étroite. Ce
plan les remplace pendant les mesures. Chaque pastille de test (TP) et chaque pont (JP)
est dessiné à sa place, avec son repère et le nom de son réseau. Les autres pièces de la
même face sont en gris, avec leur repère quand la place le permet, pour se situer.
Une image par face qui porte des pastilles ou des ponts ; face avant vue de dessus, dos
vu de dos (gauche et droite inversées, comme la carte retournée dans la main).
"""
import sys

import pcbnew
from PIL import Image, ImageDraw, ImageFont

ORIGINE = (100.0, 100.0)
Z = 16                      # pixels par millimètre
MARGE = 14                  # millimètres de marge, pour les étiquettes


def main():
    path, out = sys.argv[1], sys.argv[2]
    b = pcbnew.LoadBoard(path)
    mm = pcbnew.ToMM
    box = b.GetBoardEdgesBoundingBox()
    W, H = mm(box.GetWidth()), mm(box.GetHeight())
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except OSError:
        font = small = ImageFont.load_default()
    faces = []
    for back in (False, True):
        marks = [f for f in b.GetFootprints() if f.IsFlipped() == back and f.GetReference().rstrip("0123456789") in ("TP", "JP")]
        if marks:
            faces.append((back, marks))
    img = Image.new("RGB", (int((W + 2 * 3) * Z), int((H + 2 * MARGE) * Z) * len(faces)), "white")
    d = ImageDraw.Draw(img)
    for k, (back, marks) in enumerate(faces):
        oy = k * int((H + 2 * MARGE) * Z)

        def xy(p, back=back, oy=oy):
            x, y = mm(p.x) - ORIGINE[0], mm(p.y) - ORIGINE[1]
            if back:
                x = W - x
            return (3 + x) * Z, oy + (MARGE + y) * Z

        d.rectangle([3 * Z, oy + MARGE * Z, (3 + W) * Z, oy + (MARGE + H) * Z], outline="black", width=2, fill=(238, 244, 238))
        d.text((3 * Z, oy + 6), "Dos, vu de dos (carte retournée de gauche à droite)" if back else "Face avant, vue de dessus", font=font, fill="black")
        for f in b.GetFootprints():
            if f.IsFlipped() != back or f in marks:
                continue
            bb = f.GetBoundingBox(False)
            x1, y1 = xy(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop()))
            x2, y2 = xy(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
            x1, x2 = min(x1, x2), max(x1, x2)
            d.rectangle([x1, y1, x2, y2], outline=(170, 170, 170), fill=(222, 222, 222))
            ref = f.GetReference()
            if (x2 - x1) >= 26 and (y2 - y1) >= 16 and ref.rstrip("0123456789") not in ("R", "C"):
                d.text((x1 + 2, y1 + 1), ref, font=small, fill=(110, 110, 110))
        # Étiquettes : au-dessus de la carte pour la moitié haute, au-dessous pour la moitié
        # basse, rangées de gauche à droite sans se chevaucher, reliées par un trait.
        for haut in (True, False):
            rang = sorted((f for f in marks if (mm(f.GetPosition().y) - ORIGINE[1] < H / 2) == haut), key=lambda f: xy(f.GetPosition())[0])
            libre = [0.0, 0.0, 0.0]                     # fin de la dernière étiquette de chaque ligne
            for f in rang:
                x, y = xy(f.GetPosition())
                net = sorted({p.GetNetname().lstrip("/") for p in f.Pads() if p.GetNetname()})
                label = f.GetReference() + " " + (" | ".join(net) if f.GetReference().startswith("JP") else net[0] if net else "")
                w = d.textlength(label, font=font)
                line = next((i for i in range(3) if libre[i] <= x - w / 2), min(range(3), key=lambda i: libre[i]))
                lx = max(x - w / 2, libre[line])
                libre[line] = lx + w + 10
                ly = oy + (MARGE * Z - 26 - 22 * line if haut else (MARGE + H) * Z + 8 + 22 * line)
                couleur = (0, 90, 170) if f.GetReference().startswith("TP") else (170, 90, 0)
                d.line([x, y, lx + w / 2, ly + (18 if haut else 0)], fill=couleur, width=1)
                r = 0.9 * Z if f.GetReference().startswith("TP") else 0.7 * Z
                d.ellipse([x - r, y - r, x + r, y + r], outline=couleur, width=3)
                d.text((lx, ly), label, font=font, fill=couleur)
    img.save(out)
    print("écrit", out, img.size)


main()
