"""Carte Luciole² v0 : placement et routage par script.

    tools/kicad python3 v0/carte.py

Lit v0/out/v0.net (exportée du schéma par KiCad) et écrit v0/v0.kicad_pcb.
Cotes en millimètres depuis le coin haut gauche, face avant vue de dessus.

EN COURS. Tous les composants sont posés, la rangée de LED est routée. Le reste du
routage est à faire.

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
ROT_BATTERIE = -90                  # connecteur de batterie, au dos
ROT_CONDENSATEUR = 90               # condensateurs des LED : borne de masse vers le haut
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

# Largeurs de piste par réseau. Chemins de puissance : 0,6 mm (1 A à 1,5 A). 3,3 V : 0,4 mm.
b.netclass("Puissance", ["VBUS", "VBAT", "VSYS", "BATP", "BATN", "VCHG", "VBIN", "SW", "VLED", "VPORT"], 0.6)
b.netclass("Alimentation", ["+3V3", "V3IN", "VBUS_AMORTI", "DW_VCC"], 0.4)

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
# Au-dessus de la rangée, la barre d'alimentation des LED, puis un condensateur par LED,
# debout : sa borne VLED descend dans la barre, sa borne de masse donne sur le plan de
# masse de la bande du haut. La masse des LED rejoint le plan de la bande du bas, et le
# plan du dos par un via là où le dos est libre : sous la batterie et le module, pas dans
# la zone des accès, où le dos porte des composants.
# La donnée passe d'une LED à la suivante en Z, par l'intervalle de 2,7 mm entre pastilles.
Y_BUS = YC - 2.55              # axe de la barre VLED : 0,75 mm au-dessus des pastilles
Y_CAP = Y_BUS - 1.6            # axe des condensateurs, debout au-dessus de la barre
X_BUS_DEBUT, X_BUS_FIN = 12.4, X_LED_FIN + 1.55
SIG, STUB, PWR = 0.25, 0.4, 1.0    # largeurs : données, dérivations, barre d'alimentation

b.track("VLED", [(X_BUS_DEBUT, Y_BUS), (X_BUS_FIN, Y_BUS)], PWR)
for i in range(N_LED):
    ref, cap, x = f"D{i + 1}", f"C{17 + i}", X_LED_FIN - i * PITCH
    vdd, gnd, din, dout = (b.pad(ref, n) for n in ("2", "4", "1", "3"))
    b.place(cap, vdd[0], Y_CAP, rot=ROT_CONDENSATEUR)
    c_vled, c_gnd = b.pad(cap, "1"), b.pad(cap, "2")
    assert abs(c_vled[0] - vdd[0]) < 0.01 and c_gnd[1] < c_vled[1] < Y_BUS, f"{cap} mal tourné"
    b.track("VLED", [vdd, (vdd[0], Y_BUS), c_vled], STUB)
    if x > X_BAT_DEBUT + 0.7:
        b.track("GND", [gnd, b.via("GND", gnd[0], gnd[1] + 1.25)], STUB)
    if i + 1 < N_LED:
        # De la sortie de cette LED (en haut à gauche) à l'entrée de la suivante, à gauche.
        nxt = b.pad(f"D{i + 2}", "1")
        xm = x - PITCH / 2
        b.track(f"LED_D{i + 1}", [dout, (xm, dout[1]), (xm, nxt[1]), nxt], SIG)

# ------------------------------------------------- placement des autres blocs
# Premier placement, par rangement automatique dans des rectangles. Face avant : deux
# bandes libres, au-dessus de la barre VLED et sous les vias de masse des LED. Dos : la
# zone des accès, entre l'USB-C et la batterie. Le milieu de la carte reste libre pour
# les liaisons qui vont d'une extrémité à l'autre, et pour les pastilles de test.
HAUT1, HAUT2 = 0.5, 5.6        # bande du haut, face avant, au-dessus des condensateurs des LED
BAS1, BAS2 = 13.9, 21.3        # bande du bas, face avant
X_FIN = X_SANS_CUIVRE - 0.6    # rien au-delà : zone de l'antenne

# Connecteur de batterie, au dos : ouverture vers la batterie, à 4,8 mm de son bord.
b.place("J2", X_BAT_DEBUT - 4.8 - 4.45, 5.9, rot=ROT_BATTERIE, bottom=True)
assert min(x for x, _ in b.pads("J2", "MP")) > b.pad("J2", "1")[0], "J2 doit s'ouvrir vers la batterie"
# Thermistance au bord de la zone de la batterie, pas dessous.
b.place("TH1", X_BAT_DEBUT - 1.2, 16.0, rot=90, bottom=True)

# Dos, derrière l'USB-C : protection, entrée, présence de l'USB, partage de charge, arrêt
# de la charge. Dans chaque rectangle, les pièces hautes viennent d'abord : le rangement
# se fait par rangées, et une rangée prend la hauteur de sa plus grande pièce.
b.flow(["U1", "Q4", "JP1", "D16", "D22", "C1", "C5", "R39", "D24", "C38", "R1", "R2",
        "C39", "R5", "R6", "R7", "R37", "R38", "C34", "R44", "C40", "R41", "R42"],
       8.6, 0.7, 23.2, 13.4, bottom=True)
# Dos, à côté du bouton : chargeur, et protection du bouton.
b.flow(["U2", "Q1", "D19", "C2", "C11", "R8", "R9", "R10", "R11", "R12"],
       5.4, 13.9, 23.2, 21.3, bottom=True)
# Dos, sous le connecteur de batterie : inversion et protection de cellule.
b.flow(["Q2", "Q6", "U3", "Q3", "R43", "R45", "R46", "R14", "C3", "R15", "R16", "R17"],
       23.7, 11.4, X_BAT_DEBUT - 2.4, 21.3, bottom=True)

# Face avant, côté accès, bande du haut : convertisseur des LED, dans l'ordre du courant.
x, _ = b.flow(["JP3", "C13", "L1", "U8", "C14", "C15"], 12.6, HAUT1, 46.0, HAUT2)
x, _ = b.flow(["R25", "C37", "R26", "R27"], x + 0.25, HAUT1, x + 4.6, HAUT2)
x, _ = b.flow(["Q5"], x + 0.25, HAUT1, x + 4.6, HAUT2)
b.flow(["R28", "R24"], x + 0.25, HAUT1, x + 2.4, HAUT2)
# Face avant, côté accès, bande du bas : port Grove, fin de la chaîne de LED.
b.flow(["U11", "U10", "F1", "JP4", "TP14", "C32", "C41", "R31", "R32", "R33", "R34", "C33", "R36", "R30"],
       11.9, BAS1, 36.0, BAS2)

# Face avant, côté module, bande du haut : régulateur, superviseur, redémarrage.
b.flow(["U4", "U5", "JP2", "C6", "C7", "C8", "C35", "C9", "R18", "C10", "R19", "R20"],
       86.0, HAUT1, X_FIN, HAUT2)
# Face avant, côté module, bande du bas : boutons internes, accéléromètre, limitation des
# broches du port, puis le tampon des LED, au plus près de la première LED.
b.flow(["SW1", "SW2", "D20", "D21", "Q7", "U7", "C36", "C12", "R22", "R23", "R13", "R21", "R40", "R3", "R4",
        "C4", "R35", "R47"],
       78.0, BAS1, 107.5, BAS2)
b.flow(["U9", "C16", "R29"], 108.0, BAS1, X_FIN, BAS2)

# Pastilles de test, face avant, au milieu de la carte : côté accès celles des réseaux de
# la charge, côté module celles de la puce. TP15 et TP16 : injection sur le rail des LED.
b.flow(["TP1", "TP2", "TP18", "TP3", "TP17", "TP13", "TP12"], 37.0, BAS2 - 2.6, 60.0, BAS2)
b.flow(["TP4", "TP10", "TP11", "TP8", "TP9", "TP6"], 60.5, BAS2 - 2.6, 77.8, BAS2)
b.flow(["TP15", "TP16", "TP5", "TP7"], 60.0, HAUT1, 80.0, HAUT2)

for ref in ("J3", "D15", "D1", "U6", "J1", "SW3", "J2"):
    print(ref, b.extent(ref))
print("non posés :", sorted(set(b.comps) - set(b.fps)))
print("batterie : x de", round(X_BAT_DEBUT, 2), "à", round(X_BAT_FIN, 2), "; sans cuivre au-delà de x =", X_SANS_CUIVRE)
# Plans de masse sur les deux faces. Celui du dos est continu sous la batterie.
EDGE = 0.4
b.zone("GND", "F.Cu", EDGE, EDGE, W - EDGE, H - EDGE)
b.zone("GND", "B.Cu", EDGE, EDGE, W - EDGE, H - EDGE)

b.save(draft="--brouillon" in sys.argv)
