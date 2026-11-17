"""Carte d'essai Luciole² : placement et routage par script.

    tools/kicad python3 essai/carte.py

Lit essai/out/essai.net (exportée du schéma par KiCad) et écrit
essai/essai.kicad_pcb. Cotes en millimètres depuis le coin haut gauche.

Disposition, vue de dessus :

    J1 (entrée)   R1   D1    D2    D3   R2   J2 (sortie)
    ouverture à gauche      pas de 7 mm       ouverture à droite

Le dos est un plan de masse continu, sauf un pont de 4 mm pour l'entrée de
données, qui doit croiser la piste d'alimentation.
"""
from pcbkit import Board

W, H = 46.0, 22.0              # carte : 46 × 22 mm (22 mm = largeur prévue de la carte v0)
YC = H / 2                     # axe de la rangée de LED
PITCH = 7.0                    # pas des LED, comme sur la carte v0
X0 = 16.0                      # centre de la première LED
N = 3
BUS_Y = YC + 3.8               # piste d'alimentation, sous la rangée
EDGE = 0.4                     # retrait des plans de masse par rapport au bord
SIG, STUB, PWR = 0.25, 0.4, 0.6    # largeurs : données, dérivation d'alimentation, alimentation

b = Board("essai", "essai", "essai/out/essai.net",
          fp_libs={"luciole": "lib/luciole.pretty"},
          title="Luciole² : tronçon d'essai, 3 LED", rev="0.1", date="2026-11-17")
b.outline(0, 0, W, H)

# ---------------------------------------------------------------- placement
# Connecteurs : la face d'ouverture est à 0,7 mm en retrait du bord, pour garder
# 0,4 mm de cuivre libre entre les pattes de fixation et le bord de carte.
JX = 5.85                      # centre de l'empreinte ; la rangée de broches est à 9,8 du bord
b.place("J1", JX, YC, rot=-90)             # ouverture vers la gauche
b.place("J2", W - JX, YC, rot=90)          # ouverture vers la droite
assert all(x < b.pad("J1", "1")[0] for x, _ in b.pads("J1", "MP")), "J1 doit s'ouvrir vers la gauche"
assert all(x > b.pad("J2", "1")[0] for x, _ in b.pads("J2", "MP")), "J2 doit s'ouvrir vers la droite"
# Vu de dessus, ouverture vers soi, la masse d'un Grove est à gauche. Ouverture
# tournée vers la gauche de la carte, la masse se retrouve en haut ; vers la droite, en bas.
assert b.pad("J1", "4")[1] < b.pad("J1", "1")[1], "J1 : la masse doit être en haut"
assert b.pad("J2", "4")[1] > b.pad("J2", "1")[1], "J2 : la masse doit être en bas"

for i in range(N):
    x = X0 + i * PITCH
    # À 180°, l'entrée DIN est en haut à gauche et la sortie DOUT en bas à droite :
    # la chaîne avance de gauche à droite.
    b.place(f"D{i + 1}", x, YC, rot=180)
    b.place(f"C{i + 1}", x - 0.6, YC + 2.6)
    din, dout = b.pad(f"D{i + 1}", "1"), b.pad(f"D{i + 1}", "3")
    assert din[0] < x < dout[0] and din[1] < YC < dout[1], "orientation de la LED"

b.place("R1", 14.0, YC - 3.0)
b.place("R2", 33.4, YC - 2.2)

# ------------------------------------------------------------------ données
# Sur le connecteur d'entrée, l'alimentation (broche 3) est au-dessus de la donnée
# (broche 2), alors que la LED a son entrée en haut et son alimentation en bas.
# La donnée passe donc au dos sur 4 mm pour croiser la piste d'alimentation.
j1d = b.pad("J1", "2")
r1a, r1b = b.pad("R1", "1"), b.pad("R1", "2")
va = (12.1, j1d[1])
vb = (12.1, r1a[1])
b.track("DIN", [j1d, va], SIG)
b.via("DIN", *va)
b.track("DIN", [va, vb], SIG, layer="B.Cu")
b.via("DIN", *vb)
b.track("DIN", [vb, r1a], SIG)
din = b.pad("D1", "1")
b.track("LED_D0", [r1b, (r1b[0], din[1]), din], SIG)

for i in range(1, N):
    # De la sortie d'une LED (en bas à droite) à l'entrée de la suivante (en haut à
    # gauche), en Z par le milieu de l'intervalle de 2,7 mm entre les pastilles.
    dout, din = b.pad(f"D{i}", "3"), b.pad(f"D{i + 1}", "1")
    xm = X0 + (i - 0.5) * PITCH
    b.track(f"LED_D{i}", [dout, (xm, dout[1]), (xm, din[1]), din], SIG)

# Sortie : elle remonte à droite de la dernière LED jusqu'à la résistance, puis
# rejoint la broche 2 du connecteur de sortie, au-dessus de l'alimentation.
dout = b.pad(f"D{N}", "3")
r2a, r2b = b.pad("R2", "1"), b.pad("R2", "2")
xs = dout[0] + 1.2
b.track(f"LED_D{N}", [dout, (xs, dout[1]), (xs, r2a[1]), r2a], SIG)
j2d = b.pad("J2", "2")
b.track("DOUT", [r2b, (r2b[0], j2d[1]), j2d], SIG)

# ------------------------------------------------------------- alimentation
j1v, j2v = b.pad("J1", "3"), b.pad("J2", "3")
XL, XR = 13.2, 33.6            # descente à gauche, remontée à droite
b.track("VLED", [j1v, (XL, j1v[1]), (XL, BUS_Y), (XR, BUS_Y), (XR, j2v[1]), j2v], PWR)
for i in range(N):
    vdd, c1 = b.pad(f"D{i + 1}", "2"), b.pad(f"C{i + 1}", "1")
    b.track("VLED", [(c1[0], vdd[1]), c1, (c1[0], BUS_Y)], STUB)

# -------------------------------------------------------------------- masse
for i in range(N):
    gnd, c2 = b.pad(f"D{i + 1}", "4"), b.pad(f"C{i + 1}", "2")
    b.track("GND", [gnd, b.via("GND", gnd[0], gnd[1] - 1.2)], STUB)
    b.track("GND", [c2, b.via("GND", c2[0] + 0.87, c2[1])], STUB)

j1g, j2g = b.pad("J1", "4"), b.pad("J2", "4")
b.track("GND", [j1g, b.via("GND", j1g[0], j1g[1] - 1.7)], STUB)
b.track("GND", [j2g, b.via("GND", j2g[0], j2g[1] + 1.7)], STUB)
for ref, dx in (("J1", 2.6), ("J2", -2.6)):
    for mp in b.pads(ref, "MP"):
        b.track("GND", [mp, b.via("GND", mp[0] + dx, mp[1])], STUB)

b.zone("GND", "F.Cu", EDGE, EDGE, W - EDGE, H - EDGE)
b.zone("GND", "B.Cu", EDGE, EDGE, W - EDGE, H - EDGE)

# -------------------------------------------------------------- sérigraphie
b.text("Luciole² essai 0.1", W / 2, 2.6, size=1.2)
b.text("entrée", 7.0, H - 2.4, size=1.0)
b.text("sortie", W - 7.0, H - 2.4, size=1.0)

b.save()
