"""Carte Luciole² v0 : placement et routage par script.

    tools/kicad python3 v0/carte.py

Lit v0/out/v0.net (exportée du schéma par KiCad) et écrit v0/v0.kicad_pcb.
Cotes en millimètres depuis le coin haut gauche, face avant vue de dessus.

EN COURS. Tous les composants sont posés. La structure est tracée par script et passe le
contrôle des règles : rangée de LED, convertisseur, chemin de la batterie, alimentations,
liaisons longues, traversées, sorties des boîtiers à pas fin. Les petits composants sont
posés par le poseur (tools/pose.py), au plus près de ce qu'ils relient.

Restent les liaisons courtes. Le routeur sur grille en laisse entre 23 et 34 selon les
essais, surtout dans la bande du bas côté module et autour du chargeur : ces deux blocs
sont trop denses pour une seule face libre. Aucun tracé n'est donc figé pour l'instant.

Plan du routage :

- Face avant, la barre d'alimentation des LED et la donnée, qui passe d'une LED à la
  suivante, coupent la carte en deux bandes sur toute sa longueur. D'une bande à l'autre
  on passe par le dos, ou par le couloir à droite de la dernière LED.
- Dos, sous la batterie : les liaisons longues entre la zone des accès et le module
  forment un faisceau le long du bord bas, dans l'ordre des contacts du module, pour ne
  pas se croiser. VSYS longe le bord haut jusqu'au régulateur. Le reste du dos est un
  plan de masse plein, convertisseur compris.
- Le courant de la batterie reste au dos, du connecteur aux transistors de protection,
  puis monte une seule fois en face avant, vers le partage de charge et le convertisseur.

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
import json
import os
import sys

from maille import Router
from pcbkit import Board
from pose import Placer

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
          title="Luciole² : carte v0", rev="0.2", date="2026-11-17")
b.outline(0, 0, W, H)

# Largeurs de piste par réseau. Chemins de puissance : 0,5 mm, sur des longueurs de
# quelques centimètres (2 A en pointe côté batterie). 3,3 V : 0,4 mm. La barre des LED,
# tracée par script, fait 1 mm.
b.netclass("Puissance", ["VBUS", "VBAT", "VSYS", "BATP", "BATN", "VCHG", "VBIN", "SW", "VLED", "VPORT"], 0.5)
b.netclass("Alimentation", ["+3V3", "V3IN", "VBUS_AMORTI", "DW_VCC"], 0.4)
# La masse a sa classe : les routeurs automatiques l'ignorent, les plans la relient.
b.netclass("Masse", ["GND"], 0.4)

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
# plan du dos par un via là où le dos est un plan : sous la batterie, hors de la zone où
# sortent les contacts du module.
# La donnée passe d'une LED à la suivante en Z, par l'intervalle de 2,7 mm entre pastilles.
Y_BUS = YC - 2.55              # axe de la barre VLED : 0,75 mm au-dessus des pastilles
Y_CAP = Y_BUS - 1.6            # axe des condensateurs, debout au-dessus de la barre
X_BUS_DEBUT, X_BUS_FIN = 14.5, X_LED_FIN + 1.55
SIG, STUB, PWR = 0.25, 0.4, 1.0    # largeurs : données, dérivations, barre d'alimentation
X_EVENTAIL = 96.0              # à droite : traversées, puis éventail des contacts du module

b.track("VLED", [(X_BUS_DEBUT, Y_BUS), (X_BUS_FIN, Y_BUS)], PWR)
for i in range(N_LED):
    ref, cap, x = f"D{i + 1}", f"C{17 + i}", X_LED_FIN - i * PITCH
    vdd, gnd, din, dout = (b.pad(ref, n) for n in ("2", "4", "1", "3"))
    b.place(cap, vdd[0], Y_CAP, rot=ROT_CONDENSATEUR)
    c_vled, c_gnd = b.pad(cap, "1"), b.pad(cap, "2")
    assert abs(c_vled[0] - vdd[0]) < 0.01 and c_gnd[1] < c_vled[1] < Y_BUS, f"{cap} mal tourné"
    b.track("VLED", [vdd, (vdd[0], Y_BUS), c_vled], STUB)
    if X_BAT_DEBUT + 0.7 < x < X_EVENTAIL:
        b.track("GND", [gnd, b.via("GND", gnd[0], gnd[1] + 1.25)], STUB)
    if i + 1 < N_LED:
        # De la sortie de cette LED (en haut à gauche) à l'entrée de la suivante, à gauche.
        nxt = b.pad(f"D{i + 2}", "1")
        xm = x - PITCH / 2
        b.track(f"LED_D{i + 1}", [dout, (xm, dout[1]), (xm, nxt[1]), nxt], SIG)

HAUT1, HAUT2 = 0.5, 5.6        # bande du haut, face avant, au-dessus des condensateurs des LED
BAS1, BAS2 = 13.9, 21.3        # bande du bas, face avant
X_FIN = X_SANS_CUIVRE - 0.15   # rien au-delà : zone de l'antenne
V, VR = -90, 90                # composant à deux bornes debout : borne 1 en haut, ou en bas


def P(ref, n):
    return b.pad(ref, n)


# Petits composants posés par le poseur (tools/pose.py), une fois la structure tracée :
# chacun va au plus près de ce que ses pastilles relient. (repères, rectangles, au dos)
POSE = []


def sorties(ref, beyond=0.45, w=0.15):
    """Boîtier à pas fin, pastilles au pourtour : une courte piste sort de chaque pastille
    reliée, droit vers l'extérieur. Le routeur sur grille repart du bout de ces pistes ;
    il ne sait pas entrer entre deux pastilles espacées de 0,15 mm."""
    x1, y1, x2, y2 = b.extent(ref)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    fp = b.fps[ref]
    layer = "B.Cu" if fp.IsFlipped() else "F.Cu"
    for pad in fp.Pads():
        net = pad.GetNetname().lstrip("/")
        if not net or net.startswith("unconnected-"):
            continue
        (px1, py1, px2, py2), = [bx for bx in b.boxes(ref, pad.GetNumber())][:1]
        px, py = (px1 + px2) / 2, (py1 + py2) / 2
        if abs(px - cx) > abs(py - cy):
            end = (px1 - beyond, py) if px < cx else (px2 + beyond, py)
        else:
            end = (px, py1 - beyond) if py < cy else (px, py2 + beyond)
        b.track(net, [(px, py), end], w, layer=layer)


def gnd_via(x, y, frm=None, w=0.3):
    """Via vers le plan de masse du dos, relié à `frm` par une piste courte."""
    v = b.via("GND", x, y)
    if frm is not None:
        b.track("GND", [frm, v], w)
    return v


# --------------------------------------- convertisseur des LED, face avant
# Disposition de la fiche du TPS61023 (figure 10-1), tournée d'un quart de tour : la
# rangée VOUT, SW, GND regarde la barre des LED, les condensateurs de sortie sont juste
# dessous, la bobine est à gauche. SW repart sous la puce puis entre les pastilles du
# condensateur d'entrée, qui relie VIN et GND au plus court. La boucle à courant haché
# (VOUT, condensateur de sortie, GND) fait moins de 6 mm et reste en face avant.
XU, YU = 60.0, 2.2
b.place("U8", XU, YU, rot=-90)
vin, en, fb, gnd8, sw, vout = (P("U8", n) for n in "321456")
assert vin[0] < en[0] < fb[0] and vin[1] < YU, "U8 : VIN, EN, FB en haut, de gauche à droite"
assert gnd8[0] < sw[0] < vout[0] and sw[1] > YU, "U8 : GND, SW, VOUT en bas, de gauche à droite"
b.place("C13", XU - 1.83, YU, rot=V)
assert P("C13", "1")[1] < YU < P("C13", "2")[1]
b.place("L1", XU - 5.55, YU + 0.9)
assert P("L1", "1")[0] < P("L1", "2")[0]
b.place("C14", XU, YU + 2.555, rot=180)
b.place("C15", XU, YU + 4.605, rot=180)
assert P("C14", "2")[0] < XU < P("C14", "1")[0] and P("C15", "2")[0] < XU < P("C15", "1")[0]
# SW : 0,24 mm de large sur 3,4 mm, pour passer à 0,2 mm des pastilles qu'il longe.
b.track("SW", [sw, (XU, YU), (P("L1", "2")[0] + 0.3, YU)], 0.24)
b.track("VBIN", [vin, (P("C13", "1")[0], vin[1])], 0.24)
b.track("VBIN", [(P("C13", "1")[0], YU - 0.95), (P("L1", "1")[0], YU - 0.95), (P("L1", "1")[0], YU - 0.2)], 0.4)
b.track("GND", [gnd8, (P("C13", "2")[0], gnd8[1])], 0.24)
b.track("GND", [gnd8, (gnd8[0], YU + 1.3), (P("C14", "2")[0] + 0.1, YU + 1.95)], 0.24)
b.track("VLED", [vout, (vout[0], YU + 1.3), (P("C14", "1")[0] - 0.1, YU + 1.95)], 0.24)
b.track("VLED", [P("C14", "1"), (P("C14", "1")[0], Y_BUS)], PWR)
b.track("GND", [P("C14", "2"), P("C15", "2")], PWR)
for y in (YU + 2.3, YU + 3.2):
    gnd_via(XU - 2.3, y, (P("C14", "2")[0] - 0.3, y), 0.5)
b.track("GND", [P("C13", "2"), (P("C13", "2")[0], YU + 2.3)], 0.5)
# Pont de mesure de la sortie, à droite, loin de SW et de la bobine. Quatre composants
# debout : en haut le nœud FB, en ligne avec sa broche.
for k, (ref, rot) in enumerate((("R25", VR), ("C37", VR), ("R26", V), ("R27", V))):
    b.place(ref, XU + 1.6 + 1.05 * k, fb[1] + 0.51, rot=rot)
assert abs(P("R25", "2")[1] - fb[1]) < 0.01 and abs(P("R27", "1")[1] - fb[1]) < 0.01
b.track("FB", [fb, P("R27", "1")], 0.2)
b.track("VLED", [P("C37", "1"), P("R25", "1"), (P("R25", "1")[0], YU + 1.3), (P("C14", "1")[0] + 0.25, YU + 1.95)], 0.25)
gnd_via(P("R26", "2")[0], YU + 1.35, P("R26", "2"))
b.place("Q5", XU + 7.25, YU + 0.4, rot=180)
assert P("Q5", "3")[0] < P("Q5", "1")[0], "Q5 : drain à gauche"
b.track("FB_X", [P("R27", "2"), P("Q5", "3")], 0.2)
b.place("R28", XU + 9.76, YU + 1.4, rot=VR)        # VSEL en bas, vers sa liaison
b.track("VSEL", [P("Q5", "1"), (P("Q5", "1")[0] + 0.75, P("R28", "1")[1]), P("R28", "1")], 0.2)
b.track("GND", [P("Q5", "2"), (P("Q5", "2")[0] + 0.8, P("Q5", "2")[1]), (P("R28", "2")[0], P("R28", "2")[1] - 0.6),
                P("R28", "2")], 0.3)
b.place("R24", XU + 10.9, YU - 0.2, rot=V)         # BOOST_EN en haut
b.track("GND", [P("R28", "2"), (P("R24", "2")[0], YU + 1.35)], 0.3)
# EN contourne la rangée du haut par le bord de carte.
b.track("BOOST_EN", [en, (en[0], 0.7), (P("R24", "1")[0], 0.7), P("R24", "1")], 0.2)
gnd_via(P("R24", "2")[0], YU + 1.35, P("R24", "2"))
# Entrée : pont de mesure du courant, condensateur d'entrée du rail.
b.place("JP3", XU - 10.17, YU + 0.9)
assert P("JP3", "1")[0] < P("JP3", "2")[0]
b.track("VBIN", [P("JP3", "2"), P("L1", "1")], 0.8)
b.place("C5", XU - 12.7, YU + 0.9, rot=V)
b.track("VSYS", [P("C5", "1"), (P("JP3", "1")[0] - 0.2, P("C5", "1")[1]), P("JP3", "1")], 0.8)
gnd_via(P("C5", "2")[0], YU + 3.0, P("C5", "2"), 0.5)

# ------------------------------------------- liaisons longues, au dos
# Faisceau du bord bas : une voie tous les 0,5 mm, pistes de 0,2 mm. L'ordre, de bas en
# haut, est celui des contacts du module en tournant autour de son coin bas gauche :
# rangée du bas, puis colonne de gauche de bas en haut. Les liaisons qui partent d'un
# composant de la face avant s'ajoutent par le haut du faisceau.
LANE = 0.2
Y_BTN, Y_CC, Y_VBAT_S, Y_VBUS_D, Y_DN, Y_DP, Y_ISET = 21.3, 20.7, 20.2, 19.7, 19.1, 18.6, 18.1
Y_P1X, Y_P2X, Y_PBUF, Y_CHRG, Y_CE = 17.6, 17.1, 16.6, 16.1, 15.6
X_G = 24.5                     # fin du faisceau côté accès, à gauche du connecteur de batterie


def back(net, pts, w=LANE):
    b.track(net, pts, w, layer="B.Cu")


# Colonne de gauche du module : chaque contact sort vers la gauche, descend, puis rejoint
# sa voie. Les verticales s'emboîtent : le contact le plus haut passe le plus à gauche.
# Côté accès, sous le connecteur de batterie, les voies s'écartent (x < X_J2) : celle de la
# mesure de batterie peut alors monter en face avant par un via.
X_J2, X_J2B = 34.2, 35.0
Y_DP2, Y_DN2, Y_VBUS_D2, Y_VBAT_S2 = 18.0, 18.5, 19.1, 19.9
X_COL = {"USB_DP_R": 10.4, "USB_DN_R": 9.9, "VBUS_DET": 9.4, "CC_SENSE": 8.9}     # remontée vers l'USB
Y_COL = 11.2
col = {}
for k, (pad, net, x, y_end) in enumerate((
        ("16", "VBUS_DET", 104.2, Y_VBUS_D), ("17", "USB_DN_R", 103.7, Y_DN), ("18", "USB_DP_R", 103.2, Y_DP),
        ("19", "ISET", 102.7, Y_ISET), ("20", "PORT_PU", 102.0, 15.8), ("22", "STRAP8", 101.2, 15.0),
        ("23", "BOOT", 100.4, 15.8), ("24", "LED_DATA", 99.6, 15.0))):
    p = P("U6", pad)
    col[net] = (x, y_end)
    back(net, [p, (x, p[1]), (x, y_end)])
for net in ("PORT_PU", "STRAP8", "BOOT", "LED_DATA"):
    b.via(net, *col[net])                      # vers la bande du bas, face avant
Y_ACC, Y_BOOST = 14.25, 13.6                   # deux liaisons en face avant, vers leurs traversées
p = P("U6", "15")
back("ACC_INT", [p, (105.3, p[1]), b.via("ACC_INT", 104.9, Y_ACC)])
p = P("U6", "13")
back("IO1", [p, (105.3, p[1]), b.via("IO1", 104.9, 15.2)])
p = P("U6", "12")
back("VBAT_SENSE", [p, (105.2, p[1]), (105.2, Y_VBAT_S), (32.8, Y_VBAT_S), (32.8 - (Y_VBAT_S - Y_VBAT_S2), Y_VBAT_S2),
                    (30.4, Y_VBAT_S2), b.via("VBAT_SENSE", 30.0, Y_VBAT_S2)])
# Chaque voie change de hauteur 0,8 mm plus à gauche que celle du dessus.
for k, (net, y, y2) in enumerate((("USB_DP_R", Y_DP, Y_DP2), ("USB_DN_R", Y_DN, Y_DN2), ("VBUS_DET", Y_VBUS_D, Y_VBUS_D2))):
    x, xj = X_COL[net], X_J2B - 0.8 * k
    back(net, [col[net], (xj, y), (xj - (y - y2), y2), (x + 0.4, y2), (x, y2 - 0.4), (x, Y_COL)])
X_ISET = 36.3                  # ISET s'arrête à droite du connecteur de batterie, où est Q1
back("ISET", [col["ISET"], (X_ISET, Y_ISET)])
# Rangée du bas : les liaisons locales montent en face avant par un via, sous le module,
# puis partent vers la gauche, chacune à sa hauteur.
X_BANDE = 105.8                # où ces liaisons entrent dans la bande du bas
bas = {}
for pad, net, y in (("10", "BOOST_EN", 18.1), ("8", "EN", 18.9), ("6", "BTN_IO", 18.1), ("5", "IO2", 18.9)):
    p = P("U6", pad)
    bas[net] = b.via(net, p[0], y)
    back(net, [p, bas[net]])
b.track("EN", [bas["EN"], (X_BANDE, 18.9)], 0.2)
b.track("BTN_IO", [bas["BTN_IO"], (bas["BTN_IO"][0] - 0.4, 18.5), (bas["BTN_IO"][0] - 0.4, 19.3),
                   (bas["BTN_IO"][0] - 0.8, 19.7), (X_BANDE, 19.7)], 0.2)
b.track("IO2", [bas["IO2"], (bas["IO2"][0], 19.9), (bas["IO2"][0] - 0.4, 20.3), (X_BANDE, 20.3)], 0.2)
b.track("BOOST_EN", [bas["BOOST_EN"], (bas["BOOST_EN"][0], Y_BOOST + 0.4), (bas["BOOST_EN"][0] - 0.4, Y_BOOST),
                     (95.7, Y_BOOST)], 0.2)
b.track("ACC_INT", [(104.9, Y_ACC), (96.6, Y_ACC)], 0.2)
p = P("U6", "9")
x = X_COL["CC_SENSE"]
back("CC_SENSE", [p, (p[0], Y_CC), (x + 0.4, Y_CC), (x, Y_CC - 0.4), (x, Y_COL)])
p = P("U6", "3")
for dx in (-0.45, 0.45):
    back("+3V3", [p, (p[0], 18.0), b.via("+3V3", p[0] + dx, 18.6)], 0.4)
# Le bouton rejoint le faisceau par le bas, depuis sa résistance en face avant, et va
# jusqu'au bouton, au dos, le long du bord.
sw3 = min(b.pads("SW3", "1"), key=lambda q: -q[1])
back("BTN", [b.via("BTN", 104.0, 21.3), (4.9, Y_BTN), (4.5, Y_BTN - 0.4), (4.5, sw3[1] + 0.8), (sw3[0] + 0.6, sw3[1])])
# Port : trois voies ajoutées par le haut, de la bande du bas côté module à celle côté accès.
for net, y, x1, x2 in (("PORT_1X", Y_P1X, 97.6, 39.6), ("PORT_2X", Y_P2X, 96.5, 40.8), ("PORT_BUF_R", Y_PBUF, 95.4, 42.0)):
    back(net, [b.via(net, x1, y - 0.4), (x1 - 0.4, y), (x2 + 0.4, y), b.via(net, x2, y - 0.4)])
# Rangée du haut du module. Quatre contacts montent en face avant par un via, en
# quinconce : le choix de tension, le bus de l'accéléromètre, la liaison série.
for pad, net, y in (("26", "VSEL", 4.25), ("28", "ACC_SDA", 3.05), ("29", "ACC_SCL", 4.0),
                    ("30", "RXD0", 4.0), ("31", "TXD0", 3.3)):
    p = P("U6", pad)
    back(net, [p, b.via(net, p[0], y)])
# Bord haut : VSYS, du partage de charge au régulateur du 3,3 V. Sous le convertisseur,
# la liaison passe sous la piste d'entrée de la bobine, au même potentiel continu, et non
# sous la piste de commutation.
Y_VSYS, Y_VSYS_VIA = 1.3, 2.8
X_VSYS1, X_VSYS2 = 46.0, 73.0
for dx in (0.0, 0.8):
    b.via("VSYS", X_VSYS1 - dx, Y_VSYS_VIA)
    b.via("VSYS", X_VSYS2 + dx, Y_VSYS_VIA)
back("VSYS", [(X_VSYS1 - 0.8, Y_VSYS_VIA), (X_VSYS1, Y_VSYS_VIA), (X_VSYS1 + 1.5, Y_VSYS),
              (X_VSYS2 - 1.5, Y_VSYS), (X_VSYS2, Y_VSYS_VIA), (X_VSYS2 + 0.8, Y_VSYS_VIA)], 0.6)
b.track("VSYS", [(X_VSYS1 - 0.8, Y_VSYS_VIA), (X_VSYS1, Y_VSYS_VIA), P("C5", "1")], 0.8)
# Traversées de la rangée de LED par le dos, entre D5 et D3, là où le dos est libre.
# Elles montent jusqu'à 4,4 mm : leurs vias arrivent au-dessus des deux liaisons qui
# longent le bas de la bande du haut.
#   92,6  3,3 V, du régulateur vers les composants de la bande du bas ;
#   93,5  ordre d'arrêt de la charge, du module vers son transistor ;
#   94,4  état de charge, du module vers le faisceau puis le chargeur ;
#   95,3  commande du convertisseur ; 96,2 interruption de l'accéléromètre ;
#   98,5  rail des LED, de la barre vers le tampon du port.
Y_TRAV = 4.4
back("VLED", [b.via("VLED", 98.5, Y_BUS), b.via("VLED", 98.5, 15.2)], 0.3)
back("+3V3", [b.via("+3V3", 92.6, 13.9), b.via("+3V3", 92.6, Y_TRAV)], 0.3)
back("BOOST_EN", [b.via("BOOST_EN", 95.3, Y_BOOST), b.via("BOOST_EN", 95.3, Y_TRAV)])
back("ACC_INT", [b.via("ACC_INT", 96.2, Y_ACC), b.via("ACC_INT", 96.2, Y_TRAV)])
b.track("BOOST_EN", [(95.7, Y_BOOST), (95.3, Y_BOOST)], 0.2)
b.track("ACC_INT", [(96.6, Y_ACC), (96.2, Y_ACC)], 0.2)
p = P("U6", "27")
back("CHG_INH", [p, (p[0], 3.0), (93.5, 3.0), b.via("CHG_INH", 93.5, 13.9)])
X_CE2, X_CHRG2 = 53.2, 52.0    # arrivée côté accès, face avant, bande du bas
p = P("U6", "25")
back("CHRG", [p, (p[0], 3.5), (94.4, 3.5), (94.4, Y_CHRG - 0.3), (94.1, Y_CHRG), (X_CHRG2 + 0.4, Y_CHRG),
              b.via("CHRG", X_CHRG2, Y_CHRG - 0.4)])
b.via("CHRG", 94.4, 14.9)                      # vers la résistance de rappel, face avant
back("CE", [b.via("CE", 91.0, Y_CE - 0.4), (90.6, Y_CE), (X_CE2 + 0.4, Y_CE), b.via("CE", X_CE2, Y_CE - 0.4)])
# La commande du convertisseur et le choix de tension longent le bas de la bande du haut,
# en face avant, jusqu'au convertisseur. Le choix de tension finit par 4 mm au dos, pour
# passer sous la commande.
b.track("BOOST_EN", [(95.3, Y_TRAV), (95.3, 5.2), (P("R24", "1")[0] + 0.9, 5.2),
                     (P("R24", "1")[0] + 0.9, P("R24", "1")[1]), P("R24", "1")], 0.2)
p = P("U6", "26")
b.track("VSEL", [(p[0], 4.25), (p[0], 5.7), (74.4, 5.7), b.via("VSEL", 74.0, 6.0)], 0.2)
back("VSEL", [(74.0, 6.0), b.via("VSEL", P("R28", "1")[0], 5.0)])
b.track("VSEL", [(P("R28", "1")[0], 5.0), P("R28", "1")], 0.2)
# Couloir à droite de la dernière LED : le rail des LED descend vers le tampon des LED,
# le 3,3 V vers le contact d'alimentation du module.
X_COULOIR, X_COULOIR2 = 114.65, 115.45

# ----------------------------------------------- face avant, bande du haut
# Côté accès : fusible du port, au départ de la barre des LED. Le rail du port descend
# entre le connecteur Grove et la dernière LED.
b.place("F1", 14.6, 1.75, rot=180)
assert P("F1", "2")[0] < P("F1", "1")[0]
b.track("VLED", [P("F1", "1"), (P("F1", "1")[0], Y_BUS)], 0.5)
b.place("C32", 12.9, 3.98, rot=V)
b.place("R30", 12.9, 6.6, rot=VR)
b.track("VPORT", [P("F1", "2"), P("C32", "1")], 0.4)
b.track("VPORT", [P("F1", "2"), (11.68, 3.3), (11.68, 9.37), (10.6, 9.37)], 0.3)
b.track("LED_D15", [P("D15", "3"), (P("R30", "1")[0] - 0.3, 9.0), P("R30", "1")], SIG)
# Partage de charge entre l'USB et la batterie. VBAT monte du dos par trois vias, VBUS
# par deux ; VSYS part vers le convertisseur, et vers le régulateur par le dos.
X_VBAT, Y_VBAT = 33.2, 5.6     # trois vias de VBAT, au pas de 0,9 mm
b.place("Q4", 32.3, 2.4, rot=180)
assert P("Q4", "3")[0] < P("Q4", "2")[0] and P("Q4", "2")[1] < P("Q4", "1")[1], "Q4 : drain à gauche, source en haut"
b.place("D16", 38.2, 1.75, rot=180)
b.place("D22", 38.2, 4.2, rot=180)
assert P("D22", "2")[0] < P("D22", "1")[0], "D22 : anode à gauche"
b.place("TP2", 28.9, 2.4)
b.place("TP3", 42.8, 1.85)
b.place("TP18", 22.2, 2.6)
b.place("TP15", 19.2, 2.2)
b.place("TP5", 25.6, 2.4)
b.track("VLED", [P("TP15", "1"), (P("TP15", "1")[0], Y_BUS)], 0.5)
b.track("VLED", [P("TP5", "1"), (P("TP5", "1")[0], Y_BUS)], 0.4)
for k in range(3):
    b.via("VBAT", X_VBAT + 0.9 * k, Y_VBAT)
b.track("VBAT", [P("TP2", "1"), P("Q4", "3"), (P("Q4", "3")[0], Y_VBAT), (X_VBAT + 1.8, Y_VBAT)], 0.8)
b.track("VBAT", [(X_VBAT + 1.8, Y_VBAT), (P("D22", "2")[0] - 0.2, P("D22", "2")[1] + 0.3), P("D22", "2")], 0.8)
for k in range(2):
    b.via("VBUS", 34.75 + 0.85 * k, 1.6)
b.track("VBUS", [P("Q4", "1"), (34.75, 2.45), (34.75, 1.6), (35.6, 1.6), P("D16", "2")], 0.5)
b.track("VSYS", [P("Q4", "2"), (P("Q4", "2")[0] + 0.5, 0.72), (40.6, 0.72), (40.6, P("D16", "1")[1]), P("D16", "1")], 0.5)
b.track("VSYS", [P("D16", "1"), P("D22", "1")], 1.0)
b.track("VSYS", [P("D22", "1"), (41.2, 2.8), (X_VSYS1 - 0.8, 2.8)], 1.0)
b.track("VSYS", [P("TP3", "1"), (P("TP3", "1")[0], 2.8)], 0.5)

# Côté module : régulateur du 3,3 V. Condensateur d'entrée à gauche, de sortie à droite ;
# la broche de validation rejoint l'entrée par la gauche du boîtier.
b.place("JP2", 75.6, 2.4)
b.place("C6", 78.15, 2.675, rot=V)
b.place("U4", 81.05, 2.85)
b.place("C7", 83.95, 2.675, rot=V)
b.place("C35", 85.3, 2.4, rot=V)
u4in, u4gnd, u4en, u4out = (P("U4", n) for n in "1235")
assert u4in[0] < u4out[0] and u4in[1] < u4gnd[1] < u4en[1], "U4 : entrée en haut à gauche, sortie en haut à droite"
b.track("VSYS", [(X_VSYS2 + 0.8, Y_VSYS_VIA), P("JP2", "1")], 0.6)
b.track("V3IN", [P("JP2", "2"), (P("C6", "1")[0] - 0.4, u4in[1]), u4in], 0.5)
b.track("V3IN", [(78.94, u4in[1]), (78.94, u4en[1]), u4en], 0.2)
b.track("+3V3", [u4out, P("C7", "1"), P("C35", "1")], 0.5)
b.track("GND", [u4gnd, (82.9, u4gnd[1]), (P("C7", "2")[0] - 0.3, P("C7", "2")[1])], 0.3)
gnd_via(P("C7", "2")[0], 4.5, P("C7", "2"), 0.4)
gnd_via(P("C6", "2")[0], 4.5, P("C6", "2"), 0.4)
gnd_via(P("C35", "2")[0] + 0.9, P("C35", "2")[1] + 0.5, P("C35", "2"))
# Le 3,3 V longe le bord haut, descend par le couloir de droite jusqu'au contact
# d'alimentation du module, et rejoint la bande du bas par une traversée.
Y_33 = 0.7
# Accéléromètre, au-dessus du module. Tourné pour que son bus regarde les deux vias qui
# montent du module, à droite, et son interruption la traversée, à gauche.
b.place("U7", 106.9, 2.75, rot=180)
b.place("C36", 104.3, 2.9, rot=V)
b.place("C12", 103.0, 2.9, rot=V)
b.place("R22", 109.2, 1.9, rot=V)
b.place("R23", 110.25, 1.9, rot=V)
b.place("TP8", 113.6, 1.95)
b.place("TP9", 113.6, 4.5)
b.place("TP4", 89.0, 2.9)
sda, scl, irq = P("U7", "4"), P("U7", "1"), P("U7", "12")
assert sda[0] > 106.9 and scl[0] > 106.9 and sda[1] < scl[1], "U7 : SDA en haut à droite, SCL en bas à droite"
assert irq[1] > 2.75 and abs(P("U7", "9")[1] - P("U7", "2")[1]) < 0.01, "U7 : interruption en bas, 3,3 V face à face"
sorties("U7")
b.track("+3V3", [P("U7", "9"), P("U7", "2")], 0.15)        # sous le boîtier
for a, c in (("2", "3"), ("9", "10")):
    b.track("+3V3", [P("U7", a), P("U7", c)], 0.15)
for a, c in (("7", "8"), ("5", "6")):
    b.track("GND", [P("U7", a), P("U7", c)], 0.15)
v_sda, v_scl = (P("U6", "28")[0], 3.05), (P("U6", "29")[0], 4.0)
b.track("ACC_SDA", [sda, (P("R22", "2")[0] - 0.5, sda[1]), P("R22", "2"), v_sda], 0.15)
b.track("ACC_SCL", [scl, (scl[0] + 0.65, scl[1]), (scl[0] + 0.8, 3.65), (v_scl[0] - 0.4, 3.65), v_scl], 0.15)
b.track("ACC_SCL", [P("R23", "2"), (v_scl[0] + 0.05, P("R23", "2")[1] + 0.5), v_scl], 0.15)
b.track("ACC_INT", [irq, (irq[0], 4.55), (96.6, 4.55), (96.2, Y_TRAV)], 0.15)
for ref in ("R22", "R23", "C36", "C12", "TP4"):
    b.track("+3V3", [P(ref, "1"), (P(ref, "1")[0], Y_33)], 0.3)
b.track("+3V3", [(92.6, Y_TRAV), (92.6, Y_33)], 0.3)
b.track("TXD0", [(P("U6", "31")[0], 3.3), (112.6, 2.45), P("TP8", "1")], 0.2)
b.track("RXD0", [(P("U6", "30")[0], 4.0), (112.3, 4.5), P("TP9", "1")], 0.2)

# ------------------------------------------------ face avant, bande du bas
# Côté accès : protection du port, puis le chargeur. Il est en face avant pour laisser le
# dos, derrière l'USB-C, aux composants de l'USB ; ses pastilles de test sont à côté.
b.via("CC_SENSE", 12.5, Y_CC)                 # vers sa pastille de test, face avant
POSE.append((["U11", "C41", "TP12"], [(11.9, 13.3, 19.6, BAS2)], False))
b.place("U2", 23.5, 17.3)
assert P("U2", "4")[0] < P("U2", "5")[0] and P("U2", "1")[1] < P("U2", "4")[1]
POSE.append((["R8", "R9", "R11", "R12", "R42", "JP1", "Q1", "C2", "C40", "D25", "R44", "R10", "R41"],
             [(12.0, 14.6, 39.0, BAS2)], False))
# Arrivée des trois liaisons du port : résistances série et pont du tampon.
POSE.append((["JP4", "R31", "R32", "TP1", "TP17", "TP13", "TP14"], [(39.2, 14.6, 53.6, BAS2)], False))
# Pont de mesure de la batterie : là où il reste de la place, près de son via.
POSE.append((["R16", "R17", "C4"], [(12.0, 14.6, 39.0, BAS2), (39.2, 14.6, 53.6, BAS2)], False))
# Au milieu : boutons internes, pastilles de masse.
POSE.append((["TP16", "TP6", "TP7"], [(54.0, 14.2, 61.8, BAS2)], False))
# Côté module : adaptateurs de niveau et tampon du port, rappels de démarrage.
BAS_MODULE = [(78.1, 14.7, 105.6, BAS2)]
POSE.append((["U10", "Q8", "Q9", "Q7", "U5"], BAS_MODULE, False))
POSE.append((["R33", "R34", "R35", "C33", "R36", "R47", "R13", "R19", "R20", "R18", "C10", "R40", "R21"], BAS_MODULE, False))
POSE.append((["SW1", "SW2", "TP10", "TP11"], [(62.0, 14.7, 105.6, BAS2)], False))
# Sous les traversées : transistor de l'arrêt de la charge, rappel de l'état de charge,
# résistance série du tampon.
# Superviseur, redémarrage, bouton.
# Tampon des LED, sous la première LED : sa sortie monte droit dans l'entrée de D1.
b.place("R29", 113.5, 14.05, rot=VR)
X_U9 = 110.85
b.place("U9", X_U9, 16.2)
b.place("C16", 114.0, 16.75, rot=V)
u9a, u9gnd, u9y, u9vcc = (P("U9", n) for n in "2345")
assert u9a[0] < u9vcc[0] and u9vcc[1] < u9y[1], "U9 : entrée à gauche, alimentation en haut à droite"
assert P("R29", "2")[1] < P("R29", "1")[1]
b.track("LED_D0", [P("R29", "2"), (P("R29", "2")[0], P("D1", "1")[1])], SIG)
b.track("LED_BUF", [P("R29", "1"), (X_U9, P("R29", "1")[1]), (X_U9, u9y[1]), u9y], 0.2)
b.track("VLED", [(X_BUS_FIN, Y_BUS), (X_COULOIR, Y_BUS), (X_COULOIR, u9vcc[1]), u9vcc], 0.3)
b.track("VLED", [(P("C16", "1")[0], u9vcc[1]), P("C16", "1")], 0.3)
# Découplage du module, à côté des deux vias de son contact d'alimentation.
b.place("C9", 115.2, 18.6)
b.place("C8", 113.9, 20.3)
assert P("C9", "1")[0] < P("C9", "2")[0] and P("C8", "1")[0] < P("C8", "2")[0]
b.track("+3V3", [P("C35", "1"), (P("C35", "1")[0], Y_33), (X_COULOIR2, Y_33), (X_COULOIR2, 17.3),
                 (P("C9", "1")[0], 18.0), P("C9", "1")], 0.4)
u63 = P("U6", "3")
b.track("+3V3", [P("C9", "1"), (u63[0] + 0.45, 18.6), (u63[0] - 0.45, 18.6), (u63[0] - 0.45, 19.6), P("C8", "1")], 0.4)
b.track("+3V3", [P("C8", "1"), (P("C8", "1")[0] - 0.7, 20.9), (X_BANDE, 20.9)], 0.3)
gnd_via(115.75, 20.3, P("C8", "2"), 0.4)
b.track("GND", [P("C9", "2"), (115.75, 19.4), (115.75, 20.3)], 0.3)

# ------------------------------------------------------- dos, zone des accès
# Connecteur de batterie : ouverture vers la batterie, à 4,8 mm de son bord.
b.place("J2", X_BAT_DEBUT - 4.8 - 4.45, YC, rot=ROT_BATTERIE, bottom=True)
assert min(x for x, _ in b.pads("J2", "MP")) > b.pad("J2", "1")[0], "J2 doit s'ouvrir vers la batterie"
# Au-dessus du connecteur de batterie : les deux transistors contre l'inversion. Le pôle
# positif monte à gauche du connecteur ; VBAT repart à droite, vers ses trois vias.
X_BATP = 23.2
b.place("Q2", 26.0, 4.5, rot=180, bottom=True)
b.place("Q6", 31.3, 4.5, rot=180, bottom=True)
q2d, q2s, q6s = P("Q2", "3"), P("Q2", "2"), P("Q6", "2")
assert q2d[0] < q2s[0] and q2s[1] > 4.5 and q6s[1] > 4.5, "Q2, Q6 : drain à gauche, source en bas à droite"
j21, j22 = P("J2", "1"), P("J2", "2")
back("BATP", [(j21[0] - 1.2, j21[1]), (X_BATP, j21[1]), (X_BATP, q2d[1]), q2d], 0.8)
back("VBAT", [q2s, (q2s[0] + 0.5, Y_VBAT), (X_VBAT + 1.8, Y_VBAT)], 0.8)
back("VBAT", [q6s, (q6s[0], Y_VBAT)], 0.5)
back("BATP", [(X_BATP, q2d[1]), (X_BATP + 0.5, 2.95), (33.4, 2.95)], 0.2)        # vers R45, R46
POSE.append((["R45", "R46", "R43"], [(24.0, 2.75, 37.6, 6.3)], True))
# VBAT redescend entre les pastilles du connecteur, vers le pont du chargeur en face avant.
X_VBAT2 = 28.6
back("VBAT", [(X_VBAT2, Y_VBAT), (X_VBAT2, 16.4)], 0.8)
for y in (15.6, 16.4):
    b.via("VBAT", X_VBAT2, y)
# VBUS : du dos de l'USB-C aux deux vias du partage de charge, le long du bord haut.
back("VBUS", [(20.5, 1.6), (35.6, 1.6)], 0.8)
# À gauche du connecteur : protection de la cellule. Le pôle négatif entre dans le double
# transistor, qui rend la masse au plan du dos sans via.
b.place("Q3", 20.0, 12.6, rot=180, bottom=True)
b.place("U3", 15.6, 12.6, rot=180, bottom=True)
q3s1, q3s2 = P("Q3", "1"), P("Q3", "3")
assert q3s1[0] > 20.0 and q3s1[1] < q3s2[1], "Q3 : source de la batterie en haut à droite, masse en bas à droite"
assert P("U3", "1")[0] > 15.6 and abs(P("U3", "1")[1] - P("Q3", "6")[1]) < 0.01, "U3 : OD face à la grille 1 de Q3"
back("BATN", [(j22[0] - 1.2, j22[1] - 0.2), (q3s1[0], j22[1] - 0.2), q3s1], 0.6)
back("DW_OD", [P("U3", "1"), P("Q3", "6")], 0.2)
back("DW_OC", [P("U3", "3"), P("Q3", "4")], 0.2)
back("PROT_D", [P("Q3", "2"), P("Q3", "5")], 0.4)
# Pastille de test du pôle négatif, en face avant : une piste fine remonte entre le
# transistor et la piste du pôle positif.
back("BATN", [(22.2, j22[1] - 0.2), (22.2, 5.0)], 0.25)
b.track("BATN", [b.via("BATN", 22.2, 5.0), P("TP18", "1")], 0.25)
back("VBAT", [(X_VBAT2, 16.4), (X_VBAT2 - 0.5, 16.9), (12.0, 16.9)], 0.25)             # vers R14
POSE.append((["C3", "R14", "R15"], [(11.6, 10.6, 21.2, 16.4)], True))
# Thermistance au bord de la zone de la batterie, pas dessous.
b.place("TH1", 36.0, 12.0, rot=V, bottom=True)
# USB-C, pastilles au pas de 0,5 mm. Chaque signal a deux pastilles, une par sens de
# la fiche, entrelacées avec celles de l'autre : D+ se relie du côté du connecteur, D- du
# côté de la carte, et tout sort vers la carte par une piste courte.
def j1(n):
    (x, y), = set(b.pads("J1", n))
    return x, y


X_IN, X_OUT, X_SORTIE = 6.2, 8.35, 8.95
dp1, dp2, dn1, dn2 = j1("B6"), j1("A6"), j1("A7"), j1("B7")
assert dp1[1] < dn1[1] < dp2[1] < dn2[1], "USB-C : D+ et D- entrelacés, D+ en premier"
back("USB_DP", [dp1, (X_IN, dp1[1]), (X_IN, dp2[1]), dp2])
back("USB_DN", [dn1, (X_OUT, dn1[1]), (X_OUT, dn2[1]), dn2])
back("USB_DP", [dp1, (X_SORTIE, dp1[1])])
back("USB_DN", [(X_OUT, dp2[1]), (X_SORTIE, dp2[1])])
back("CC1", [j1("A5"), (X_SORTIE - 0.15, j1("A5")[1])])
back("CC2", [j1("B5"), (X_SORTIE - 0.15, j1("B5")[1])])
for n in ("A4", "A9"):
    back("VBUS", [j1(n), (X_SORTIE, j1(n)[1])], 0.5)
# Derrière l'USB-C : protection, entrée, lecture des broches CC, présence de l'USB.
POSE.append((["U1", "R39", "C1", "D24", "C39", "R1", "R2", "R3", "R4", "R37", "R38", "C34", "R5", "R6", "R7", "C38"],
             [(9.4, 2.7, 20.8, 10.8)], True))
# Sous l'USB-C, à côté du bouton : sa protection, et le pont de mesure de la batterie.
POSE.append((["D19", "C11"], [(4.15, 13.6, 8.4, 20.3)], True))

# ------------------------------------------------------- liaisons courtes
# Tout ce qui précède est la structure de la carte. Les liaisons courtes qui restent sont
# tracées par le routeur sur grille (tools/maille.py), puis figées dans routage.json :
#
#     tools/kicad python3 v0/carte.py --router
#
# La construction normale rejoue ce fichier. Sa signature dit pour quelle carte il a été
# calculé : après un changement de placement ou de structure, il faut relancer le routeur.
INTERDIT = [("F.Cu", X_SANS_CUIVRE, -1, W + 1, H + 1), ("B.Cu", X_SANS_CUIVRE, -1, W + 1, H + 1),
            # pas de piste nouvelle sous le module
            ("B.Cu", X_MODULE - MODULE_ARRIERE, YC - 6.6, W + 1, YC + 6.6)]
poseur = Placer(b, Router(b, forbid=INTERDIT))
for refs, regions, bottom in POSE:
    poseur.auto(refs, regions, bottom)
print("non posés :", sorted(set(b.comps) - set(b.fps)))
print("batterie : x de", round(X_BAT_DEBUT, 2), "à", round(X_BAT_FIN, 2), "; sans cuivre au-delà de x =", X_SANS_CUIVRE)

ROUTAGE = "v0/routage.json"
signature = b.signature()
if "--router" in sys.argv:
    r = Router(b, forbid=INTERDIT,
               # le dos, sous la batterie, reste un plan de masse : y passer coûte trois fois plus
               costly=[("B.Cu", X_BAT_DEBUT, 0, X_EVENTAIL, H, 3)])
    seuls = [a.split("=")[1].split(",") for a in sys.argv if a.startswith("--reseaux=")]
    # Les alimentations d'abord, tant que la place est libre : ce sont les pistes larges.
    r.route(skip=("GND",), only=seuls[0] if seuls else None,
            order=["VBUS", "VBAT", "VSYS", "BATP", "BATN", "VCHG", "V3IN", "+3V3", "VLED", "VPORT"])
    r.save(ROUTAGE, signature)
    for name, groupes in r.failed:
        print("non relié :", name)
        for g in groupes:
            print("    ", g)
elif os.path.exists(ROUTAGE) and "--sans-trace" not in sys.argv:
    with open(ROUTAGE, encoding="utf-8") as f:
        figee = json.load(f)["signature"]
    if figee != signature:
        message = f"{ROUTAGE} a été calculé pour une autre carte : relancer v0/carte.py --router"
        if "--brouillon" not in sys.argv:
            sys.exit(message)
        print("alerte :", message)
    else:
        print("tracé rejoué :", b.replay(ROUTAGE))

# Plans de masse sur les deux faces. Celui du dos est continu sous la batterie.
EDGE = 0.4
b.zone("GND", "F.Cu", EDGE, EDGE, W - EDGE, H - EDGE)
b.zone("GND", "B.Cu", EDGE, EDGE, W - EDGE, H - EDGE)

b.save(draft="--brouillon" in sys.argv)
