"""Carte Luciole² v0 : placement et routage par script.

    tools/kicad python3 v0/carte.py

Lit v0/out/v0.net (exportée du schéma par KiCad) et écrit v0/v0.kicad_pcb.
Cotes en millimètres depuis le coin haut gauche, face avant vue de dessus.

EN COURS. Seuls les éléments imposés par la mécanique sont posés ; le reste du
placement et le routage viennent après la relecture du schéma.

Contraintes mécaniques, verrouillées avant tout placement (spécification du
wiki, page « Carte Luciole² v0 ») :

    x = 0                                                              x = 122
    extrémité des accès                                     extrémité de l'antenne
    face avant : Grove J3, puis 15 LED au pas de 7 mm, de x = 14 à x = 112
    dos :        USB-C J1 et bouton SW3 | zone nue de la batterie, 67 mm | module U6

Le module est au dos, antenne au bord de la carte, dans une zone sans cuivre
sur les deux faces. La batterie repose sur le dos entre la zone des accès et le
module : aucun composant n'y est posé. Aucune LED sous l'antenne.
"""
import sys

from pcbkit import Board

W, H = 122.0, 22.0             # largeur nominale de 22 mm, décision du 17 novembre 2026
YC = H / 2                     # axe de la carte et de la rangée de LED
ROT_MODULE, ROT_USB = 90, 90   # angles au dos, validés par les assertions de placement
Y_USB = YC - 3.0               # axe de l'USB-C, décalé pour dégager les pattes du Grove
Y_BOUTON, ROT_BOUTON = 16.5, 90     # bouton utilisateur, au dos
PITCH, N_LED = 7.0, 15
X_LED_FIN = 112.0              # centre de la LED la plus proche du module (D1)
X_LED_DEBUT = X_LED_FIN - PITCH * (N_LED - 1)      # 14,0 : centre de D15, côté Grove

# Module ESP32-C6-MINI-1 : 13,2 × 16,6 mm. L'origine de l'empreinte de KiCad est au centre
# du champ de pastilles ; le boîtier va de 5,65 mm d'un côté à 11,05 mm du côté de l'antenne.
# L'empreinte porte sa propre zone interdite au cuivre, sur toutes les couches, à partir
# de 5,6 mm de l'origine côté antenne.
MODULE_ANTENNE, MODULE_ARRIERE = 11.05, 5.65
X_MODULE = W - MODULE_ANTENNE       # origine de l'empreinte : antenne au ras du bord droit
X_SANS_CUIVRE = X_MODULE + 5.6      # 116,55 : plus de cuivre au-delà, sur les deux faces
BATTERIE = 67.0                     # zone nue du dos, pour une cellule de 65 mm
X_BAT_FIN = X_MODULE - MODULE_ARRIERE - 0.5     # la batterie s'arrête avant le module
X_BAT_DEBUT = X_BAT_FIN - BATTERIE

b = Board("v0", "v0", "v0/out/v0.net", fp_libs={"luciole": "lib/luciole.pretty"},
          title="Luciole² : carte v0", rev="0.1", date="2026-11-17")
b.outline(0, 0, W, H)

# ----------------------------------------------------------------- face avant
# Grove : ouverture vers la gauche, au bord, comme sur la carte d'essai.
b.place("J3", 5.85, YC, rot=-90)
assert all(x < b.pad("J3", "1")[0] for x, _ in b.pads("J3", "MP")), "J3 doit s'ouvrir vers la gauche"
assert b.pad("J3", "4")[1] < b.pad("J3", "1")[1], "J3 : la masse doit être en haut"

# La chaîne part du module : D1 est la LED la plus à droite, D15 la plus à gauche. À 0°,
# l'entrée DIN est en bas à droite et la sortie DOUT en haut à gauche : la donnée avance
# de droite à gauche, et le tampon de niveau reste près du module.
for i in range(N_LED):
    ref, x = f"D{i + 1}", X_LED_FIN - i * PITCH
    b.place(ref, x, YC, rot=0)
    din, dout = b.pad(ref, "1"), b.pad(ref, "3")
    assert din[0] > x > dout[0] and din[1] > YC > dout[1], "orientation de la LED"
assert abs(b.pad("D15", "3")[0] - (X_LED_DEBUT - 1.4)) < 0.01
assert b.extent("D15")[0] - b.extent("J3")[2] >= 0.5, "D15 trop près du connecteur Grove"

# ------------------------------------------------------------------------ dos
# Module : antenne vers la droite, au bord de la carte. Sa rangée de contacts 12 à 23 est
# à l'opposé de l'antenne : elle doit être la plus à gauche.
b.place("U6", X_MODULE, YC, rot=ROT_MODULE, bottom=True)
assert b.pad("U6", "12")[0] < b.pad("U6", "1")[0] < b.pad("U6", "36")[0], "U6 : antenne vers la droite"
assert b.extent("U6")[2] < X_SANS_CUIVRE, "U6 : une pastille dans la zone sans cuivre"
assert b.extent("D1")[2] + 1.0 < X_SANS_CUIVRE, "D1 trop près de l'antenne"

# USB-C : ouverture vers la gauche. Plan de HRO : le bord de carte est à 5,79 mm de l'
# axe des trous de centrage, soit 3,19 mm devant l'origine de l'empreinte (relevé à l'aveugle).
#
# L'USB-C et le Grove sont dos à dos à la même extrémité. Les quatre pattes du blindage de
# l'USB-C traversent la carte : centrées, elles déboucheraient dans les pattes de fixation
# du Grove, soudées en face avant. L'USB-C est donc décalé de 3 mm vers le haut.
b.place("J1", 3.19, Y_USB, rot=ROT_USB, bottom=True)
assert b.pad("J1", "A6")[0] > max(x for x, _ in b.pads("J1", "SH")), "J1 doit s'ouvrir vers la gauche"

# Bouton utilisateur, à côté de l'USB-C : poussoir vers la gauche, dans l'axe de la carte.
# Plan d'Alps : les appuis du capot vont jusqu'à 1,5 mm devant l'axe des ergots, et le
# poussoir jusqu'à 2,0 mm. Avec l'axe des ergots à 1,8 mm du bord, le cuivre reste à
# 0,3 mm du bord et le poussoir dépasse de 0,2 mm. Sa position en largeur est contrainte
# des deux côtés : par l'USB-C au-dessus, et par la patte de fixation du Grove, en face
# avant, que ses deux ergots traversants doivent éviter.
b.place("SW3", 1.8, Y_BOUTON, rot=ROT_BOUTON, bottom=True)
assert max(x for x, _ in b.pads("SW3", "MP")) < b.pad("SW3", "2")[0], "SW3 : poussoir vers la gauche"
assert b.extent("SW3")[0] >= 0.3, "SW3 : cuivre trop près du bord"


def gap(a, c):
    """Écart entre deux rectangles (x1, y1, x2, y2) ; négatif s'ils se recouvrent."""
    return max(a[0] - c[2], c[0] - a[2], a[1] - c[3], c[1] - a[3])


for number in ("MP", "1", "2", "3", "4"):
    for grove in b.boxes("J3", number):
        for leg in b.boxes("J1", "SH"):
            assert gap(grove, leg) >= 0.5, f"patte du blindage USB sous la pastille {number} du Grove"

# ------------------------------------------------- rangée de LED, face avant
# Au-dessus de la rangée : la barre d'alimentation des LED et un condensateur par LED,
# posé au droit de la pastille VDD. Au-dessous : la masse, par un via vers le plan du dos.
# La donnée passe d'une LED à la suivante en Z, par l'intervalle de 2,7 mm entre pastilles.
Y_BUS = YC - 3.9               # axe de la barre VLED
Y_CAP = YC - 2.55              # axe des condensateurs
X_BUS_DEBUT, X_BUS_FIN = 12.4, X_LED_FIN + 1.55
SIG, STUB, PWR = 0.25, 0.4, 1.0    # largeurs : données, dérivations, barre d'alimentation

b.track("VLED", [(X_BUS_DEBUT, Y_BUS), (X_BUS_FIN, Y_BUS)], PWR)
for i in range(N_LED):
    ref, cap, x = f"D{i + 1}", f"C{17 + i}", X_LED_FIN - i * PITCH
    vdd, gnd, din, dout = (b.pad(ref, n) for n in ("2", "4", "1", "3"))
    # Condensateur tourné de 180° : sa borne VLED (1) tombe au-dessus de la pastille VDD.
    b.place(cap, x + 0.57, Y_CAP, rot=180)
    c_vled, c_gnd = b.pad(cap, "1"), b.pad(cap, "2")
    assert abs(c_vled[0] - vdd[0]) < 0.1 and c_gnd[0] < c_vled[0], f"{cap} mal tourné"
    b.track("VLED", [vdd, c_vled, (c_vled[0], Y_BUS)], STUB)
    b.track("GND", [c_gnd, b.via("GND", c_gnd[0] - 0.9, c_gnd[1])], STUB)
    b.track("GND", [gnd, b.via("GND", gnd[0], gnd[1] + 1.25)], STUB)
    if i + 1 < N_LED:
        # De la sortie de cette LED (en haut à gauche) à l'entrée de la suivante, à gauche.
        nxt = b.pad(f"D{i + 2}", "1")
        xm = x - PITCH / 2
        b.track(f"LED_D{i + 1}", [dout, (xm, dout[1]), (xm, nxt[1]), nxt], SIG)

for ref in ("J3", "D15", "D1", "U6", "J1", "SW3"):
    print(ref, b.extent(ref))
print("batterie : x de", round(X_BAT_DEBUT, 2), "à", round(X_BAT_FIN, 2), "; sans cuivre au-delà de x =", X_SANS_CUIVRE)
# Plans de masse sur les deux faces. Celui du dos est continu sous la batterie.
EDGE = 0.4
b.zone("GND", "F.Cu", EDGE, EDGE, W - EDGE, H - EDGE)
b.zone("GND", "B.Cu", EDGE, EDGE, W - EDGE, H - EDGE)

b.save(draft="--brouillon" in sys.argv)
