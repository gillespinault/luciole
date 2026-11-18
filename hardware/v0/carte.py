"""Carte Luciole² v0 : placement et routage par script.

    tools/kicad python3 v0/carte.py

Lit v0/out/v0.net (exportée du schéma par KiCad) et écrit v0/v0.kicad_pcb.
Cotes en millimètres depuis le coin haut gauche, face avant vue de dessus.

La carte est tracée en entier depuis le 18 novembre 2026. La structure est tracée par
script : rangée de LED, convertisseur, chemin de la batterie, alimentations, liaisons
longues, traversées, sorties des boîtiers à pas fin, et les blocs où plusieurs signaux se
partagent quelques composants (port côté module, USB, protecteur du port, chargeur). Les
autres petits composants sont posés par le poseur (tools/pose.py), au plus près de ce
qu'ils relient. Les liaisons courtes qui restent, environ soixante-dix, sont tracées par
le routeur sur grille et figées dans v0/routage.json ; la construction les rejoue, coud
les plans de masse et retire le cuivre resté sans emploi.

La carte fait 28 mm de large : à 22 mm, le routeur laissait 26 à 34 liaisons. Avec la
structure actuelle, douze ordres de passage sur douze donnent un tracé complet ; celui
du projet est l'ordre par défaut, sans graine. Les options d'essai sont décrites plus bas
et dans hardware/README.md.

Plan du routage :

- Face avant, la barre d'alimentation des LED et la donnée, qui passe d'une LED à la
  suivante, coupent la carte en deux bandes sur toute sa longueur. D'une bande à l'autre
  on passe par le dos, ou par le couloir à droite de la dernière LED.
- Dos, sous la batterie : les liaisons longues entre la zone des accès et le module
  forment un faisceau le long du bord bas, dans l'ordre des contacts du module, pour ne
  pas se croiser. La commande du convertisseur y a sa voie : en face avant, devant le
  module, elle enfermait la donnée des LED. VSYS longe le bord haut jusqu'au régulateur.
  Le reste du dos est un plan de masse plein, convertisseur compris.
- Côté accès, chaque voie du faisceau finit là où est son composant. Des voies qui
  remontent côte à côte forment un nid : de l'intérieur, seule la plus intérieure est
  accessible.
- L'alimentation USB est tracée d'un bout à l'autre : au dos le long du bord haut, puis
  une descente à gauche de la batterie, puis en face avant jusqu'au chargeur, par sa
  droite. Le pont de température du chargeur est au dos, contre la thermistance.
- L'USB-C et le Grove sont dos à dos : entre eux, presque aucun via n'est possible. Le
  bloc de l'USB est posé et relié par script pour s'en passer. Ses seuls vias sont au nord
  du Grove et sous son bord, là où la face avant est libre.
- Les deux lignes du port passent au dos sous le chargeur, du connecteur à leurs
  résistances série.
- Le courant de la batterie reste au dos, du connecteur aux transistors de protection,
  puis monte une seule fois en face avant, vers le partage de charge et le convertisseur.
- Devant le coin bas gauche du module, le bloc du port universel est posé et relié par
  script, tout en face avant : ses signaux arrivent du module par la droite et par le
  haut, ses trois sorties repartent par le faisceau du dos.
- Sous le coin du module, entre le faisceau et la zone de l'antenne, les deux faces sont
  libres. Le redémarrage et le bouton y descendent au dos, vers leurs composants, au lieu
  de traverser le bloc du port en face avant.

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
import shutil
import sys

from maille import Router
from pcbkit import Board
from pose import Placer

W, H = 122.0, 28.0             # largeur de 28 mm, décision du 18 novembre 2026 (22 mm jusque-là)
# Essais, écrits dans v0/out/ sans toucher au projet :
#   --largeur=24  la carte s'élargit par le bas. La rangée de LED, le module et les
#                 connecteurs gardent leur place ; la bande du bas et les liaisons longues
#                 du dos descendent avec le bord ;
#   --dos=1       surcoût d'une piste nouvelle au dos, sous la batterie (3 par défaut : le
#                 dos y est le plan de masse, le routeur n'y passe qu'à défaut d'autre chemin).
def option(nom, defaut):
    for a in sys.argv:
        if a.startswith(f"--{nom}="):
            return float(a.split("=")[1])
    return defaut


#   --sans=SW1,SW2  ne pose pas ces composants (parmi ceux du poseur), pour mesurer ce que
#                 leur retrait libère sans toucher au schéma.
#   --ecart=0.35  écart que le poseur laisse entre deux composants (0,2 mm par défaut).
#   --graine=7    bouscule l'ordre de passage du routeur ; chaque graine donne un autre tracé.
ESSAI = any(a.startswith(("--largeur=", "--dos=", "--sans=", "--ecart=")) for a in sys.argv)
H, COUT_DOS, ECART = option("largeur", H), int(option("dos", 3)), option("ecart", 0.2)
GRAINE = option("graine", None)
SANS = sorted(set(r for a in sys.argv if a.startswith("--sans=") for r in a.split("=")[1].split(",")))
PLUS = H - 22.0                # ce que la carte a gagné en largeur depuis le premier dessin, côté bas
YC = 11.0                      # axe de la rangée de LED : à 11 mm du bord haut
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

DOSSIER, NOM = ("v0/out", f"v0-{H:g}-dos{COUT_DOS}-ecart{ECART:g}" + "".join(f"-sans{r}" for r in SANS)
                + ("" if GRAINE is None else f"-g{int(GRAINE)}")) if ESSAI else ("v0", "v0")
if ESSAI:
    shutil.copy("v0/v0.kicad_pro", f"{DOSSIER}/{NOM}.kicad_pro")       # mêmes règles que le projet
b = Board(DOSSIER, NOM, "v0/out/v0.net", fp_libs={"luciole": "lib/luciole.pretty"},
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
BAS1, BAS2 = 13.9, 21.3 + PLUS # bande du bas, face avant
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
# Les deux liaisons de la boucle s'élargissent dès qu'elles ont quitté les broches : le
# cuivre des broches est aussi ce qui refroidit la puce.
b.track("GND", [(gnd8[0] - 0.25, YU + 1.65), P("C14", "2")], 0.6)
b.track("VLED", [(vout[0] + 0.25, YU + 1.65), P("C14", "1")], 0.6)
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
# La commande du convertisseur prend la troisième voie : son contact est dans la rangée du
# bas, entre celui des broches CC et le coin du module. Elle a 0,6 mm de chaque côté, pour
# le via par lequel elle quitte le faisceau.
Y_BTN, Y_CC = 21.3 + PLUS, 20.7 + PLUS
Y_BE = Y_CC - 0.6
Y_VBAT_S, Y_VBUS_D, Y_DN, Y_DP, Y_ISET = (y + PLUS - 0.7 for y in (20.2, 19.7, 19.1, 18.6, 18.1))
Y_P1X, Y_P2X, Y_PBUF, Y_CHRG, Y_CE = (y + PLUS - 0.7 for y in (17.6, 17.1, 16.6, 16.1, 15.6))
X_G = 24.5                     # fin du faisceau côté accès, à gauche du connecteur de batterie


def back(net, pts, w=LANE):
    b.track(net, pts, w, layer="B.Cu")


# Colonne de gauche du module : chaque contact sort vers la gauche, descend, puis rejoint
# sa voie. Les verticales s'emboîtent : le contact le plus haut passe le plus à gauche.
# Côté accès, sous le connecteur de batterie, les voies s'écartent (x < X_J2) : celle de la
# mesure de batterie peut alors monter en face avant par un via.
#
# Derrière l'USB-C, les voies remontent côte à côte : depuis l'intérieur de ce nid, seule
# la voie la plus intérieure est accessible. Chacune finit donc là où est son composant.
# Les deux lignes de données montent droit dans leurs résistances série, sous le
# protecteur U1, écartées de 1,9 mm comme ses deux colonnes de pastilles. La lecture des
# broches CC s'arrête plus bas, à côté de ses résistances. La présence de l'USB quitte le
# faisceau par un via, vers son pont de mesure en face avant, près du chargeur.
X_J2, X_J2B = 34.2, 35.0
Y_DP2, Y_DN2, Y_VBUS_D2, Y_VBAT_S2 = (y + PLUS for y in (18.0, 18.5, 19.1, 19.9))
X_U1, Y_U1 = 10.4, 10.55       # protecteur de l'USB, au dos, sous les pastilles de données
Y_R34 = Y_U1 + 3.08            # résistances série R3 et R4, juste sous U1
X_COL = {"USB_DP_R": X_U1 + 0.95, "USB_DN_R": X_U1 - 0.95, "CC_SENSE": 8.9}       # remontée vers l'USB
Y_COL = {"USB_DP_R": Y_R34 + 0.51, "USB_DN_R": Y_R34 + 0.51, "CC_SENSE": 17.0}
X_VBUS_DET = 24.0              # via de la présence de l'USB
col = {}
for k, (pad, net, x, y_end) in enumerate((
        ("16", "VBUS_DET", 104.2, Y_VBUS_D), ("17", "USB_DN_R", 103.7, Y_DN), ("18", "USB_DP_R", 103.2, Y_DP),
        ("19", "ISET", 102.7, Y_ISET), ("20", "PORT_PU", 102.0, 16.0), ("22", "STRAP8", 101.2, 15.2),
        ("23", "BOOT", 100.4, 16.0), ("24", "LED_DATA", 99.6, 14.4))):
    p = P("U6", pad)
    col[net] = (x, y_end)
    back(net, [p, (x, p[1]), (x, y_end)])
for net in ("PORT_PU", "STRAP8", "BOOT", "LED_DATA"):
    b.via(net, *col[net])                      # vers la bande du bas, face avant
Y_ACC = 13.6                                   # l'interruption, en face avant, vers sa traversée
p = P("U6", "15")
back("ACC_INT", [p, (105.3, p[1]), b.via("ACC_INT", 104.9, Y_ACC)])
p = P("U6", "13")
back("IO1", [p, (105.3, p[1]), b.via("IO1", 104.9, 15.2)])
p = P("U6", "12")
back("VBAT_SENSE", [p, (105.2, p[1]), (105.2, Y_VBAT_S), (32.8, Y_VBAT_S), (32.8 - (Y_VBAT_S - Y_VBAT_S2), Y_VBAT_S2),
                    (30.4, Y_VBAT_S2), b.via("VBAT_SENSE", 30.0, Y_VBAT_S2)])
# Chaque voie change de hauteur 0,8 mm plus à gauche que celle du dessus.
for k, (net, y, y2) in enumerate((("USB_DP_R", Y_DP, Y_DP2), ("USB_DN_R", Y_DN, Y_DN2), ("VBUS_DET", Y_VBUS_D, Y_VBUS_D2))):
    xj = X_J2B - 0.8 * k
    if net == "VBUS_DET":
        back(net, [col[net], (xj, y), (xj - (y - y2), y2), (X_VBUS_DET + 0.4, y2), b.via(net, X_VBUS_DET, y2 + 0.1)])
    else:
        x = X_COL[net]
        back(net, [col[net], (xj, y), (xj - (y - y2), y2), (x + 0.4, y2), (x, y2 - 0.4), (x, Y_COL[net])])
X_ISET = 36.3                  # ISET s'arrête à droite du connecteur de batterie, où est Q1
back("ISET", [col["ISET"], (X_ISET, Y_ISET)])
iset = b.via("ISET", X_ISET, Y_ISET - 0.1)   # monte en face avant, vers son transistor
# Rangée du bas. Sous le coin du module, entre le faisceau et la zone de l'antenne, les
# deux faces sont libres depuis que la carte fait 28 mm. Le redémarrage (EN) et le bouton
# (BTN_IO) y descendent au dos, vers leurs composants. En face avant, partant vers la
# gauche avec les autres, EN séparait les signaux du port qui descendent de la colonne
# (IO1, PORT_PU) de celui qui sort ici (IO2) : ils ne se rejoignaient qu'en changeant de
# face, là où le dos est plein. Seuls IO2 et le 3,3 V montent encore en face avant.
Y_EN = 21.75                   # via du redémarrage, vers le bouton interne et sa pastille
p = P("U6", "8")
back("EN", [p, b.via("EN", p[0], Y_EN)])
p = P("U6", "6")
back("BTN_IO", [p, (p[0], 19.0)])
p = P("U6", "5")
io2 = b.via("IO2", p[0], 18.9)
back("IO2", [p, io2])
# Commande du convertisseur : elle reste au dos, dans le faisceau, jusqu'à X_BE. Une piste
# de la face avant, tracée devant le module, enfermerait la donnée des LED et les sorties
# de la colonne de gauche.
X_BE = 74.9
p = P("U6", "10")
back("BOOST_EN", [p, (p[0], Y_BE - 0.4), (p[0] - 0.4, Y_BE), (X_BE, Y_BE)])
b.track("ACC_INT", [(104.9, Y_ACC), (96.6, Y_ACC)], 0.2)
p = P("U6", "9")
x = X_COL["CC_SENSE"]
back("CC_SENSE", [p, (p[0], Y_CC), (x + 0.4, Y_CC), (x, Y_CC - 0.4), (x, Y_COL["CC_SENSE"])])
p = P("U6", "3")
for dx in (-0.45, 0.45):
    back("+3V3", [p, (p[0], 18.0), b.via("+3V3", p[0] + dx, 18.6)], 0.4)
# Le bouton rejoint le faisceau par le bas, depuis ses résistances posées au dos sous le
# module, et va jusqu'au bouton le long du bord, sans changer de face.
sw3 = min(b.pads("SW3", "1"), key=lambda q: -q[1])
back("BTN", [(112.0, Y_BTN), (4.5, Y_BTN), (4.1, Y_BTN - 0.4), (4.1, sw3[1] + 0.8), (sw3[0] + 0.6, sw3[1])])
# Port : trois voies ajoutées par le haut, du bloc du port côté module à la bande du bas
# côté accès. Côté module, chaque voie part du via de son composant : la voie la plus basse
# part du via le plus à droite, pour que les trois s'emboîtent sans se croiser.
port = {"PORT_1X": b.via("PORT_1X", 102.0, 18.35), "PORT_2X": b.via("PORT_2X", 100.8, Y_P2X - 0.5),
        "PORT_BUF_R": b.via("PORT_BUF_R", 97.3, Y_PBUF - 0.25)}
back("PORT_1X", [port["PORT_1X"], (102.0, Y_P1X - 0.4), (101.6, Y_P1X)])
back("PORT_2X", [port["PORT_2X"], (100.3, Y_P2X)])
back("PORT_BUF_R", [port["PORT_BUF_R"], (97.05, Y_PBUF)])
for net, y, x1, x2 in (("PORT_1X", Y_P1X, 101.6, 39.6), ("PORT_2X", Y_P2X, 100.3, 40.8), ("PORT_BUF_R", Y_PBUF, 97.05, 42.0)):
    back(net, [(x1, y), (x2 + 0.4, y), b.via(net, x2, y - 0.4)])
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
#   96,2  interruption de l'accéléromètre (la commande du convertisseur traverse à X_BE) ;
#   98,5  rail des LED, de la barre vers le tampon du port : il oblique sous la bande du
#         bas pour arriver à côté de la broche d'alimentation du tampon.
Y_TRAV = 4.4
vled_port = b.via("VLED", 98.7, 19.84)
back("VLED", [b.via("VLED", 98.5, Y_BUS), (98.5, 15.6), (99.4, 16.5), (99.4, 19.14), vled_port], 0.3)
back("+3V3", [b.via("+3V3", 92.6, 13.9), b.via("+3V3", 92.6, Y_TRAV)], 0.3)
# La commande du convertisseur quitte le faisceau par un via, franchit les autres voies en
# face avant, puis traverse la rangée de LED par le dos.
Y_BE2 = Y_CE - 0.8
b.track("BOOST_EN", [b.via("BOOST_EN", X_BE, Y_BE), (X_BE, Y_BE2)], 0.2)
back("BOOST_EN", [b.via("BOOST_EN", X_BE, Y_BE2), b.via("BOOST_EN", X_BE, Y_TRAV)])
back("ACC_INT", [b.via("ACC_INT", 96.2, Y_ACC), b.via("ACC_INT", 96.2, Y_TRAV)])
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
b.track("BOOST_EN", [(X_BE, Y_TRAV), (X_BE, 5.2), (P("R24", "1")[0] + 0.9, 5.2),
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
# Pastille de la sortie de la chaîne, à côté de sa résistance : entre le rail du port, à
# gauche, et le départ de la barre des LED, à droite.
b.place("TP14", 14.75, 4.5)
b.track("LED_OUT", [P("R30", "2"), (P("R30", "2")[0] + 0.6, P("R30", "2")[1] - 0.6), P("TP14", "1")], SIG)
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
b.track("VSYS", [(X_VSYS2, Y_VSYS_VIA), (X_VSYS2 + 0.8, Y_VSYS_VIA), P("JP2", "1")], 0.6)
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
# Protecteur du port, contre son connecteur, posé et relié par script. Ses deux lignes le
# traversent, et ce qui est entre elles est enfermé : sa masse d'un côté, son condensateur
# de l'autre. Il est tourné pour que la masse regarde la rangée de LED : la dernière LED et
# lui partagent alors la bande du plan qui passe entre eux. PORT_2 entre par le haut ;
# PORT_1 le contourne par le bas et la droite. Dans la poche ainsi fermée : le condensateur,
# son via de masse, et le via par lequel PORT_2 rejoint sa voie au dos.
PORT1_O, PORT2_O = (16.0, 19.4), (12.7, 17.7)      # vias des deux lignes du port, vers leurs voies
b.place("U11", 13.65, 15.2, rot=-90)
u11 = {n: P("U11", n) for n in "123456"}
assert u11["3"][0] < u11["2"][0] < u11["1"][0] and u11["2"][1] < 15.2, "U11 : PORT_2, masse, PORT_1 en haut, de gauche à droite"
assert u11["4"][0] < u11["5"][0] < u11["6"][0] and u11["5"][1] > 15.2, "U11 : PORT_2, condensateur, PORT_1 en bas"
b.place("C41", 13.65, 18.26, rot=V)
assert P("C41", "1")[1] < P("C41", "2")[1], "C41 : masse en bas"
b.track("PORT_ECRET", [u11["5"], P("C41", "1")], 0.2)
b.track("GND", [P("C41", "2"), b.via("GND", 14.5, P("C41", "2")[1])], 0.3)
j31, j32 = P("J3", "1"), P("J3", "2")
b.track("PORT_2", [j32, (11.0, 12.4), (11.55, 12.95), (12.35, 13.75), u11["3"]], 0.2)
b.track("PORT_2", [u11["4"], PORT2_O], 0.2)
Y_SOUS = PORT1_O[1]                                # passage de PORT_1 sous le protecteur
b.track("PORT_1", [j31, (11.3, j31[1]), (11.5, j31[1] + 0.2), (11.5, Y_SOUS - 0.3), (11.8, Y_SOUS), (15.0, Y_SOUS),
                   (15.3, Y_SOUS - 0.3), (15.3, u11["6"][1] + 0.3), (15.0, u11["6"][1]), u11["6"]], 0.2)
# PORT_1 traverse son protecteur, comme PORT_2 : il entre par la broche 6 et repart de la
# broche 1, par la droite, puis redescend jusqu'à son via. Avant, la ligne se séparait 3 mm
# avant le protecteur : une décharge venue du connecteur partait vers l'intérieur de la
# carte sans passer par lui (revue du 18 novembre 2026). Le départ ne passe pas au-dessus
# du protecteur : il y enfermait la masse de la dernière LED et celle du protecteur.
b.track("PORT_1", [u11["6"], u11["1"]], 0.2)
X_P1S = 15.85                  # descente : entre la montée (15,3) et le via de masse de R8 (16,5)
b.track("PORT_1", [u11["1"], (X_P1S - 0.3, u11["1"][1]), (X_P1S, u11["1"][1] + 0.3),
                   (X_P1S, PORT1_O[1] - 0.45), PORT1_O], 0.2)
POSE.append((["TP12"], [(11.9, 13.3, 19.6, BAS2)], False))
b.place("U2", 23.5, 17.3)
assert P("U2", "4")[0] < P("U2", "5")[0] and P("U2", "1")[1] < P("U2", "4")[1]
# Le chargeur est linéaire : à 0,9 A il dissipe plus d'un watt, et sa plage centrale est sa
# seule sortie de chaleur. Six vias dans la plage la relient au plan du dos, libre à cet
# endroit sous le rail de la protection (y = 15,7).
for x in (23.0, 24.0):
    for y in (16.5, 17.4, 18.3):
        b.via("GND", x, y)
# Le condensateur de 1 µF de l'alimentation USB est ici, contre la broche d'entrée du
# chargeur, et non près du connecteur : sans lui, cette broche n'avait aucun découplage à
# moins de 59 mm de piste. Près du connecteur restent l'écrêteur et l'amortisseur (R39, C1).
b.place("C39", 20.5, 20.6, rot=180)
assert P("C39", "2")[0] < P("C39", "1")[0], "C39 : masse à gauche, alimentation à droite"
b.track("VBUS", [P("U2", "4"), (P("C39", "1")[0], P("U2", "4")[1] + 0.2), P("C39", "1")], 0.4)
gnd_via(19.2, 20.6, P("C39", "2"))
# Le pont de température du chargeur (R11, R12) n'est pas ici : il est au dos, à côté de la
# thermistance. R11 relie l'alimentation USB à la broche de température, deux broches qui
# encadrent celle du courant de charge ; posé à gauche du chargeur, il l'enfermait.
# Résistance du courant de charge, contre sa broche, à gauche du chargeur ; au-dessus et
# au-dessous d'elle, les deux résistances qui partent du même point. Sa masse a un via : de
# ce côté du chargeur le dos est un plan.
b.place("R8", 18.2, P("U2", "2")[1], rot=180)
b.place("R42", 19.0, 14.9, rot=VR)
b.place("R9", 19.0, 18.43, rot=V)
assert P("R8", "2")[0] < P("R8", "1")[0] and P("R42", "2")[1] < P("R42", "1")[1] < P("R9", "1")[1] < P("R9", "2")[1]
b.track("PROG", [P("U2", "2"), P("R8", "1")], 0.2)
b.track("PROG", [P("R42", "1"), (P("R42", "1")[0], P("R8", "1")[1]), P("R9", "1")], 0.2)
b.track("GND", [P("R8", "2"), b.via("GND", 16.5, P("R8", "2")[1])], 0.3)
POSE.append((["JP1", "C2", "C40", "D25", "R44", "R41"], [(12.0, 14.6, 39.0, BAS2)], False))
# Transistor du second courant de charge et son rappel, au bout de la voie qui le commande.
# Sous eux, le dos n'est fait que de voies : leur masse a un via juste au nord, entre la
# piste de VBUS de la face avant et la première voie du dos.
b.place("Q1", 34.2, 22.4, rot=180)
b.place("R10", 37.0, 22.3, rot=VR)
g1, s1 = P("Q1", "1"), P("Q1", "2")
assert s1[1] < g1[1] and P("Q1", "3")[0] < g1[0], "Q1 : masse en haut à droite, commande dessous, sortie à gauche"
assert P("R10", "2")[1] < P("R10", "1")[1], "R10 : masse en haut"
b.track("ISET", [g1, iset, P("R10", "1")], 0.2)
b.track("GND", [b.via("GND", 33.7, 21.3), s1, P("R10", "2")], 0.3)
# Pont de mesure de la présence de l'USB, entre l'alimentation du chargeur et son via.
POSE.append((["R5", "R6", "R7"], [(19.0, 20.8, 30.0, BAS2)], False))
# Arrivée des trois liaisons du port : résistances série et pont du tampon.
POSE.append((["JP4", "R31", "R32", "TP1"], [(34.0, 14.6, 53.6, BAS2)], False))
# Pastilles du chargeur : près de lui s'il reste de la place, sinon plus à droite.
POSE.append((["TP17", "TP13"], [(12.0, 14.6, 39.0, BAS2), (39.2, 14.6, 53.6, BAS2)], False))
# Pont de mesure de la batterie, autour du via de sa voie. Sous lui, le dos n'est fait que
# des voies du faisceau : sa masse a un via là où deux d'entre elles s'écartent, à gauche
# du via de la mesure.
vs = (30.0, Y_VBAT_S2)
b.place("R17", vs[0] - 1.15, vs[1], rot=180)
b.place("C4", vs[0] - 1.15, vs[1] - 1.1, rot=180)
b.place("R16", vs[0] + 0.45, vs[1] - 1.3, rot=V)
assert P("R17", "2")[0] < P("R17", "1")[0] and P("C4", "2")[0] < P("C4", "1")[0], "R17, C4 : masse à gauche"
assert P("R16", "1")[1] < P("R16", "2")[1], "R16 : VBAT en haut"
b.track("VBAT_SENSE", [P("C4", "1"), P("R17", "1"), vs], 0.2)
b.track("VBAT_SENSE", [P("R16", "2"), (P("R16", "2")[0], vs[1] - 0.45), vs], 0.2)
b.track("GND", [P("C4", "2"), P("R17", "2"), b.via("GND", vs[0] - 2.45, vs[1])], 0.3)
# Au milieu : boutons internes, pastilles de masse.
POSE.append((["TP16", "TP6", "TP7"], [(54.0, 14.2, 61.8, BAS2)], False))
# Côté module, à gauche du bloc du port (posé par script, plus bas) : transistor de l'arrêt
# de la charge, rappels de l'état de charge et du démarrage, bouton interne du démarrage.
# La bande étroite au-dessus du tampon du port reçoit les rappels, près de leurs vias.
BAS_MODULE = [(78.1, 14.7, 94.6, BAS2), (94.6, 14.7, 100.2, 16.5)]
POSE.append((["Q7", "R47", "R13", "R19", "R20"], BAS_MODULE, False))
POSE.append((["SW2", "TP11"], [(62.0, 14.7, 94.6, BAS2)], False))
# Sous le coin du module. Au dos, à côté des contacts dont ils dépendent : superviseur,
# rappel et condensateur du redémarrage, résistances du bouton. En face avant : bouton
# interne du redémarrage et sa pastille.
POSE.append((["U5", "R18", "C10", "R40", "R21"], [(109.9, 19.3, 116.3, 26.9)], True))
POSE.append((["SW1"], [(106.2, 21.5, 112.6, BAS2)], False))       # le bouton loin de l'antenne
POSE.append((["TP10"], [(112.6, 21.5, 116.3, BAS2)], False))
# Tampon des LED, sous la première LED : sa sortie monte droit dans l'entrée de D1.
b.place("R29", 113.5, 14.05, rot=VR)
X_U9 = 110.85
b.place("U9", X_U9, 16.2)
b.place("C16", 114.0, 16.75, rot=V)
u9a, u9gnd, u9y, u9vcc = (P("U9", n) for n in "2345")
assert u9a[0] < u9vcc[0] and u9vcc[1] < u9y[1], "U9 : entrée à gauche, alimentation en haut à droite"
assert P("R29", "2")[1] < P("R29", "1")[1]
b.track("LED_D0", [P("R29", "2"), (P("R29", "2")[0], P("D1", "1")[1])], SIG)
# Donnée des LED : du via de la colonne du module au tampon, le long du haut de la bande,
# au-dessus des autres vias de la colonne.
xa = u9a[0] - 1.1
b.track("LED_DATA", [col["LED_DATA"], (xa - 0.3, col["LED_DATA"][1]), (xa, col["LED_DATA"][1] + 0.3), (xa, u9a[1] - 0.3),
                     (xa + 0.3, u9a[1]), u9a], 0.2)
b.track("LED_BUF", [P("R29", "1"), (X_U9, P("R29", "1")[1]), (X_U9, u9y[1]), u9y], 0.2)
b.track("VLED", [(X_BUS_FIN, Y_BUS), (X_COULOIR, Y_BUS), (X_COULOIR, u9vcc[1]), u9vcc], 0.3)
b.track("VLED", [(P("C16", "1")[0], u9vcc[1]), P("C16", "1")], 0.3)
# Masse de ce condensateur : il est enfermé entre le rail des LED, la sortie du tampon et
# le 3,3 V, au-dessus du module où aucun via ne tient. Une piste passe sous le tampon
# jusqu'à sa propre broche de masse.
Y_GND_U9 = 17.75
b.track("GND", [P("C16", "2"), (P("C16", "2")[0] - 0.5, Y_GND_U9), (u9gnd[0] + 0.6, Y_GND_U9),
                (u9gnd[0] + 0.2, Y_GND_U9 - 0.4), u9gnd], 0.2)
# Découplage du module, à côté des deux vias de son contact d'alimentation.
b.place("C9", 115.2, 18.6)
b.place("C8", 113.9, 20.3)
assert P("C9", "1")[0] < P("C9", "2")[0] and P("C8", "1")[0] < P("C8", "2")[0]
b.track("+3V3", [P("C35", "1"), (P("C35", "1")[0], Y_33), (X_COULOIR2, Y_33), (X_COULOIR2, 17.3),
                 (P("C9", "1")[0], 18.0), P("C9", "1")], 0.4)
u63 = P("U6", "3")
b.track("+3V3", [P("C9", "1"), (u63[0] + 0.45, 18.6), (u63[0] - 0.45, 18.6), (u63[0] - 0.45, 19.6), P("C8", "1")], 0.4)
gnd_via(115.75, 20.3, P("C8", "2"), 0.4)
b.track("GND", [P("C9", "2"), (115.75, 19.4), (115.75, 20.3)], 0.3)

# ------------------------------------ port universel côté module, face avant
# Les deux signaux du port (IO1, IO2) et la commande de leurs rappels (PORT_PU) sortent du
# coin bas gauche du module ; les trois liaisons vers le connecteur repartent par le
# faisceau du dos. Ce bloc est posé et relié par script. Laissés au poseur, ses huit
# composants s'enfermaient les uns les autres : à toutes les graines, le routeur y laissait
# PORT_PU, IO2 ou IO1.
#
# Autour d'un transistor, source, grille et drain se suivent toujours dans le même sens.
# Le bloc est dessiné pour que chaque signal arrive du bon côté, sans croisement, tout en
# face avant. De haut en bas, par la droite :
#   - IO1 descend du via de la colonne vers R33 et la source de Q8 ;
#   - le 3,3 V arrive une première fois au-dessus d'IO2, pour la grille de Q8 et R35 ;
#   - IO2 passe par la source de Q9 et R34, puis sous le tampon U10, entre ses broches 4
#     et 5, jusqu'à son entrée ;
#   - le 3,3 V arrive une seconde fois au-dessous d'IO2, pour la grille de Q9.
# PORT_PU descend de son via vers R35 et R34, et longe le haut du bloc jusqu'à U10. Les
# deux drains et la sortie du tampon rejoignent le faisceau du dos par un via chacun.
assert PLUS >= 6.0, "le bloc du port, côté module, est dessiné pour une carte de 28 mm"
b.place("R33", 103.9, 16.0)
b.place("Q8", 104.3, 18.35, rot=180)
b.place("Q9", 103.1, 21.9, rot=180)
b.place("R35", 101.3, 19.3, rot=180)
b.place("R34", 99.75, 20.44, rot=V)
b.place("U10", 96.4, 18.7, rot=-90)
b.place("C33", 98.7, 18.75, rot=VR)
b.place("R36", 95.96, 21.65)
g8, s8, d8 = (P("Q8", n) for n in "123")
g9, s9, d9 = (P("Q9", n) for n in "123")
assert d8[0] < s8[0] and s8[1] < g8[1], "Q8 : source en haut à droite, grille dessous, drain à gauche"
assert d9[0] < s9[0] and s9[1] < g9[1], "Q9 : source en haut à droite, grille dessous, drain à gauche"
assert P("R33", "1")[0] < P("R33", "2")[0] and P("R35", "2")[0] < P("R35", "1")[0], "R33 : IO1 à droite ; R35 : 3,3 V à droite"
assert P("R34", "1")[1] < P("R34", "2")[1] and P("C33", "2")[1] < P("C33", "1")[1], "R34 : IO2 en bas ; C33 : masse en haut"
u10 = {n: P("U10", n) for n in "12345"}
assert u10["3"][0] < u10["2"][0] < u10["1"][0] and u10["1"][1] < 18.7, "U10 : masse, entrée, validation en haut, de gauche à droite"
assert u10["4"][0] < u10["5"][0] and u10["5"][1] > 18.7, "U10 : sortie en bas à gauche, alimentation en bas à droite"
assert abs(g8[1] - P("R35", "1")[1]) < 0.01 and abs(s9[1] - P("R34", "2")[1]) < 0.01
io1, pu = (104.9, 15.2), col["PORT_PU"]
b.track("IO1", [io1, (io1[0], s8[1] - 0.34), s8], 0.2)
b.track("IO1", [(io1[0], P("R33", "2")[1]), P("R33", "2")], 0.2)
b.track("PORT_PU", [pu, P("R33", "1")], 0.2)
b.track("PORT_PU", [pu, (101.3, 16.7), (101.3, 17.9), (P("R35", "2")[0], 18.41), P("R35", "2"), (100.2, 19.3),
                    (P("R34", "1")[0], 19.75), P("R34", "1")], 0.2)
b.track("PORT_PU", [(101.3, 16.8), (u10["1"][0], 16.8), u10["1"]], 0.2)
# 3,3 V du haut : il part d'un des deux vias du contact d'alimentation, passe au-dessus du
# via d'IO2, atteint la grille de Q8 et continue sous son boîtier jusqu'à R35.
v33 = (u63[0] - 0.45, 18.6)
b.track("+3V3", [v33, (v33[0] - 0.4, 18.2), (107.1, 18.2), (g8[0] + 0.76, g8[1]), g8, P("R35", "1")], 0.25)
b.track("IO2", [io2, (io2[0], 19.9), (io2[0] - 0.4, 20.3), (s9[0] + 1.41, 20.3), (s9[0] + 0.76, s9[1]), s9,
                P("R34", "2"), (u10["2"][0] + 0.35, s9[1]), (u10["2"][0], s9[1] - 0.35), u10["2"]], 0.2)
# 3,3 V du bas : la liaison qui vient du découplage du module, jusqu'à la grille de Q9.
b.track("+3V3", [P("C8", "1"), (P("C8", "1")[0] - 0.7, 20.9), (106.5, 20.9), (105.6, 21.8), (105.6, 22.4),
                 (g9[0] + 1.11, g9[1]), g9], 0.3)
b.track("VLED", [u10["5"], vled_port, P("C33", "1")], 0.3)
gnd_via(98.7, 17.5, P("C33", "2"))
gnd_via(u10["3"][0], 16.25, u10["3"])
b.track("PORT_BUF", [u10["4"], P("R36", "1")], 0.2)
b.track("PORT_BUF_R", [P("R36", "2"), port["PORT_BUF_R"]], 0.2)
b.track("PORT_1X", [d8, port["PORT_1X"]], 0.25)
b.track("PORT_2X", [d9, port["PORT_2X"]], 0.25)

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
# Les deux autres résistances de la protection, à droite de Q6 : R46 couchée, dans l'axe de
# la grille de Q6 ; R45 debout, entre elle et les trois vias de VBAT. Le pôle positif leur
# arrive par une piste fine le long du haut. Aucun via.
b.place("R46", 34.25, 3.62, rot=180, bottom=True)
b.place("R45", 35.9, 4.45, rot=VR, bottom=True)
r461, r462, r451, r452 = P("R46", "1"), P("R46", "2"), P("R45", "1"), P("R45", "2")
assert r462[0] < r461[0], "R46 : grille de Q6 à gauche, pôle positif à droite"
assert r452[1] < r451[1], "R45 : pôle positif en haut, VBAT en bas"
back("BATP", [(X_BATP, q2d[1]), (X_BATP + 0.5, 2.95), (r461[0], 2.95), r461, (r452[0] - 0.32, r461[1]), r452], 0.2)
back("Q6_G", [P("Q6", "1"), r462])
back("VBAT", [r451, (r451[0], 5.25), (r451[0] - 0.35, Y_VBAT), (X_VBAT + 1.8, Y_VBAT)], 0.25)
# Rappel de la grille de Q2 vers le pôle négatif : debout entre les deux transistors, sur la
# liaison qui va de la grille de Q2 au drain de Q6. La grille reste ainsi au dos, sans via.
# Posée plus à droite, elle obligeait cette liaison à faire le tour du connecteur de
# batterie par six vias, en coupant la masse sous les LED. Le pôle négatif lui arrive de
# sa pastille de test, par la face avant et un via.
b.place("R43", 28.45, 4.1, rot=V, bottom=True)
r431, r432 = P("R43", "1"), P("R43", "2")
assert r431[1] < r432[1], "R43 : grille en haut, pôle négatif en bas"
back("Q2_G", [P("Q2", "1"), r431, (29.45, r431[1]), (29.45 + P("Q6", "3")[1] - r431[1], P("Q6", "3")[1]), P("Q6", "3")])
batn_r43 = b.via("BATN", 27.65, 4.5)           # au bout des pattes de Q2, entre grille et source
back("BATN", [batn_r43, (r432[0] - 0.3, r432[1]), r432])
# VBAT redescend entre les pastilles du connecteur, vers le pont du chargeur en face avant.
X_VBAT2 = 28.6
back("VBAT", [(X_VBAT2, Y_VBAT), (X_VBAT2, 16.4)], 0.8)
for y in (15.6, 16.4):
    b.via("VBAT", X_VBAT2, y)
b.track("VBAT", [(X_VBAT2, 15.6), (X_VBAT2, 16.4)], 0.5)      # les deux vias partagent le courant
# VBUS, l'alimentation USB, est tracée d'un bout à l'autre. Au dos : de l'USB-C, le long
# du bord haut, aux deux vias du partage de charge ; puis elle descend entre la thermistance
# et la batterie jusqu'à un via dans la bande du bas. En face avant : de ce via au
# chargeur, par le dessous de son boîtier. Le chargeur est ainsi alimenté par sa droite,
# et sa gauche reste libre pour la résistance du courant de charge.
X_VBUS_E = 37.3                # à droite des résistances du transistor contre l'inversion
vbus_bas = b.via("VBUS", X_VBUS_E, 20.0)
vbus_bas2 = b.via("VBUS", X_VBUS_E, 19.0)      # second via : le courant de charge (0,9 A) se partage
# En haut, la descente s'écarte de 0,2 mm pour laisser leur place aux trois résistances.
back("VBUS", [(35.6, 1.6), (X_VBUS_E - 0.4, 1.6), (X_VBUS_E + 0.2, 2.2), (X_VBUS_E + 0.2, 7.0), (X_VBUS_E, 7.2), vbus_bas], 0.6)
b.track("VBUS", [vbus_bas, (X_VBUS_E - 0.3, 20.3), (22.5, 20.3), (21.6, 19.4), P("U2", "4")], 0.5)
b.track("VBUS", [vbus_bas2, vbus_bas], 0.5)
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
# De la pastille de test au rappel de la grille de Q2 : par le bord haut, puis entre les
# pastilles de test de VLED et de VBAT.
b.track("BATN", [P("TP18", "1"), (22.75, 2.6), (24.35, 1.0), (26.85, 1.0), (26.85, batn_r43[1] - 0.8),
                 batn_r43], 0.2)
# Protection de la cellule : son condensateur contre ses deux broches, ses deux résistances
# juste dessous. Son alimentation vient de VBAT par un rail fin, au ras de la protection.
# Plus bas, ce rail barrait le dos sous le chargeur : le routeur n'y trouvait plus de
# passage du nord au sud, et faisait le tour par la gauche du chargeur.
b.place("C3", 12.9, 12.1, rot=VR, bottom=True)
assert P("C3", "2")[1] < P("C3", "1")[1], "C3 : pôle négatif en haut"
back("DW_VCC", [P("C3", "1"), P("U3", "5")])
back("BATN", [P("C3", "2"), P("U3", "6")])
Y_RAIL = 15.7
b.place("R15", 15.6, 14.9, bottom=True)
b.place("R14", 17.9, Y_RAIL, rot=180, bottom=True)
assert P("R15", "1")[0] < P("R15", "2")[0] and P("R14", "2")[0] < P("R14", "1")[0], "R15 : masse à droite ; R14 : VBAT à droite"
# La mesure du courant sort sous le boîtier, entre les broches 3 et 4.
back("DW_CS", [P("U3", "2"), (15.9, P("U3", "2")[1]), (15.6, P("U3", "2")[1] + 0.3), (15.6, 14.4), P("R15", "1")])
back("VBAT", [(X_VBAT2, Y_RAIL), P("R14", "1")], 0.25)
back("DW_VCC", [P("R14", "2"), (P("C3", "1")[0], Y_RAIL), P("C3", "1")])
# Les deux lignes du port, du connecteur à leurs résistances série, passent au dos sous le
# chargeur, au lieu de le contourner en face avant sur 27 mm. Elles longent le haut du
# faisceau et remontent vers le connecteur au bout ; la plus basse va le plus loin, des
# deux côtés. À droite, elles passent sous le via de VBUS et finissent près des trois
# liaisons du module.
Y_P1, Y_P2 = 22.0, 22.6
back("PORT_1", [b.via("PORT_1", *PORT1_O), (PORT1_O[0], Y_P1 - 0.4), (PORT1_O[0] + 0.4, Y_P1), (37.5, Y_P1),
                b.via("PORT_1", 37.9, Y_P1 - 0.4)])
back("PORT_2", [b.via("PORT_2", *PORT2_O), (PORT2_O[0], Y_P2 - 0.4), (PORT2_O[0] + 0.4, Y_P2), (38.3, Y_P2),
                b.via("PORT_2", 38.7, Y_P2 - 0.4)])
# La patte de fixation du connecteur de batterie, côté LED, est entourée de pistes : un via
# la relie au plan de la face avant.
back("GND", [(33.0, 7.2), b.via("GND", 33.65, 7.2)], 0.3)
# Thermistance au bord de la zone de la batterie, pas dessous. Le pont de température du
# chargeur est à côté d'elle : R12 en parallèle, R11 posée sur la descente de VBUS. La
# mesure rejoint le chargeur par un via et une piste de la face avant, au-dessus de lui.
b.place("TH1", 36.0, 12.0, rot=VR, bottom=True)
b.place("R12", 34.9, 12.0, rot=VR, bottom=True)
b.place("R11", X_VBUS_E - 0.51, 13.6, rot=180, bottom=True)
assert P("TH1", "2")[1] < P("TH1", "1")[1] and P("R12", "2")[1] < P("R12", "1")[1], "TH1, R12 : mesure en bas, masse en haut"
assert abs(P("R11", "1")[0] - X_VBUS_E) < 0.02 and P("R11", "2")[0] < P("R11", "1")[0], "R11 : VBUS à droite, sur sa descente"
temp = b.via("TEMP", 34.9, 13.5)
back("TEMP", [P("R12", "1"), P("TH1", "1"), P("R11", "2"), temp])
back("TEMP", [P("R12", "1"), temp])
# Leur masse est du côté de la rangée de LED, où la face avant est pleine : une piste la
# mène à un via plus au nord, entre la barre des LED et le partage de charge.
back("GND", [P("TH1", "2"), P("R12", "2"), (P("R12", "2")[0], 7.4), b.via("GND", P("R12", "2")[0], 7.1)], 0.3)
# Elle laisse deux passages. Au-dessus, sous la rangée de LED, une bande du plan de la
# face avant large de 1 mm : c'est le retour de masse des LED de ce côté, où le dos n'est
# pas un plan. Au-dessous, entre elle et les vias de VBAT, la place de deux pistes, celles
# de l'état et de l'arrêt de la charge.
Y_TEMP = 13.8
b.track("TEMP", [temp, (temp[0] - 0.3, Y_TEMP), (21.4 + 15.1 - Y_TEMP, Y_TEMP), (21.4, 15.1), P("U2", "1")], 0.2)


# USB-C, pastilles au pas de 0,5 mm. Chaque signal a deux pastilles, une par sens de
# la fiche, entrelacées avec celles de l'autre : D+ se relie du côté du connecteur, D- du
# côté de la carte.
#
# Le Grove est juste derrière, en face avant : entre les deux connecteurs, presque aucun
# via n'est possible. Le bloc est donc tracé pour s'en passer.
#   - Données : D- entre droit dans le protecteur U1, D+ le contourne par le haut. Elles
#     en ressortent par le bas, dans leurs résistances série, puis dans leurs deux voies.
#   - Entre deux lignes qui traversent un composant, ce qui est au milieu est enfermé.
#     Pour U1, c'est sa broche d'alimentation, en haut, et sa broche de masse, en bas.
#     L'alimentation et son condensateur ont deux vias au nord du Grove, là où la face
#     avant est libre ; la masse descend entre les deux voies jusqu'à un via plus bas.
#   - Broches CC : elles sortent du côté du connecteur et descendent sous sa coque
#     jusqu'à leurs résistances, à gauche de la voie qui les lit.
#   - VBUS : les deux pastilles du haut partent le long du bord haut. Celles du bas
#     descendent jusqu'à un via ; une piste de la face avant, sous le Grove, les relie à
#     celles du haut.
def j1(n):
    (x, y), = set(b.pads("J1", n))
    return x, y


X_IN, X_OUT, X_SORTIE = 6.2, 8.35, 8.95
dp1, dp2, dn1, dn2 = j1("B6"), j1("A6"), j1("A7"), j1("B7")
assert dp1[1] < dn1[1] < dp2[1] < dn2[1], "USB-C : D+ et D- entrelacés, D+ en premier"
back("USB_DP", [dp1, (X_IN, dp1[1]), (X_IN, dp2[1]), dp2])
back("USB_DN", [dn1, (X_OUT, dn1[1]), (X_OUT, dn2[1]), dn2])
b.place("U1", X_U1, Y_U1, rot=90, bottom=True)
u1 = {n: P("U1", n) for n in "123456"}
assert u1["4"][0] < u1["5"][0] < u1["6"][0] and u1["5"][1] < Y_U1, "U1 : D-, alimentation, D+ en haut, de gauche à droite"
assert u1["3"][0] < u1["2"][0] < u1["1"][0] and u1["2"][1] > Y_U1, "U1 : D-, masse, D+ en bas, de gauche à droite"
b.place("R4", u1["3"][0], Y_R34, rot=V, bottom=True)
b.place("R3", u1["1"][0], Y_R34, rot=V, bottom=True)
assert P("R3", "1")[1] < P("R3", "2")[1] and P("R4", "1")[1] < P("R4", "2")[1], "R3, R4 : côté connecteur en haut"
back("USB_DN", [(X_OUT, dp2[1]), (9.45, dp2[1]), (u1["4"][0], dp2[1] + 0.3), u1["4"]])
back("USB_DP", [dp1, (X_SORTIE, dp1[1]), (9.1, dp1[1] - 0.15), (9.1, 5.6), (9.4, 5.3), (u1["6"][0] - 0.3, 5.3),
                (u1["6"][0], 5.6), u1["6"]])
back("USB_DN", [u1["3"], P("R4", "1")])
back("USB_DP", [u1["1"], P("R3", "1")])
# Alimentation de U1 et son condensateur, enfermés entre les deux lignes : deux vias.
b.place("C38", X_U1, 7.45, rot=VR, bottom=True)
assert P("C38", "2")[1] < P("C38", "1")[1], "C38 : masse en haut"
vsys_usb = b.via("VSYS", X_U1 - 0.65, 6.2)
back("VSYS", [u1["5"], P("C38", "1"), (X_U1 - 0.4, P("C38", "1")[1]), (vsys_usb[0], P("C38", "1")[1] - 0.25), vsys_usb], 0.25)
back("GND", [P("C38", "2"), b.via("GND", X_U1 + 0.3, 6.2)], 0.3)
# En face avant, cette alimentation rejoint le partage de charge par le bord haut.
q42 = P("Q4", "2")
b.track("VSYS", [vsys_usb, (vsys_usb[0], 0.9), (vsys_usb[0] + 0.4, 0.5), (q42[0] - 0.94, 0.5), q42], 0.2)
# Masse de U1 : entre les deux résistances puis entre les deux voies, jusqu'à un via.
back("GND", [u1["2"], b.via("GND", X_U1, 16.5)], 0.6)
# Broches CC, sous la coque du connecteur : CC1 à l'intérieur, CC2 à l'extérieur.
back("CC1", [j1("A5"), (5.2, j1("A5")[1]), (4.9, j1("A5")[1] + 0.3), (4.9, 14.0)])
back("CC2", [j1("B5"), (4.7, j1("B5")[1]), (4.4, j1("B5")[1] + 0.3), (4.4, 14.0)])
# VBUS : pastilles du haut vers le bord haut, pastilles du bas vers leur via.
vbus_n, vbus_s = b.via("VBUS", 8.45, 4.2), b.via("VBUS", 7.84, 15.4)
back("VBUS", [j1("A9"), (8.45, j1("A9")[1]), (8.45, 2.6)], 0.5)
back("VBUS", [(8.45, 2.6), (9.45, 1.6), (35.6, 1.6)], 0.8)
back("VBUS", [j1("A4"), (8.35, j1("A4")[1]), (8.35, 13.8), (7.84, 14.31), vbus_s], 0.3)
b.track("VBUS", [vbus_n, (7.84, 4.81), vbus_s], 0.3)
# Au nord, près de l'entrée de VBUS : sa protection, son condensateur, son amortisseur.
POSE.append((["D24", "R39", "C1"], [(12.6, 2.3, 20.8, 10.6)], True))
# Sous l'USB-C, à gauche de la voie qui lit les broches CC : leurs résistances. CC1 arrive
# à droite de CC2 ; chacune a sa résistance vers la masse et sa résistance vers la lecture,
# et la lecture part vers sa voie en passant sous le via de VBUS.
b.place("R37", 6.11, 14.6, bottom=True)
b.place("R1", 5.6, 16.1, rot=V, bottom=True)
b.place("R38", 5.41, 17.6, bottom=True)
b.place("R2", 4.9, 19.1, rot=V, bottom=True)
b.place("C34", 7.9, 17.75, rot=V, bottom=True)
assert P("R37", "1")[0] < P("R37", "2")[0] and P("R38", "1")[0] < P("R38", "2")[0], "R37, R38 : broche CC à gauche"
assert P("R1", "1")[1] < P("R1", "2")[1] and P("R2", "1")[1] < P("R2", "2")[1] and P("C34", "1")[1] < P("C34", "2")[1]
back("CC1", [(4.9, 14.0), (4.9, 14.3), (5.2, 14.6), P("R37", "1"), P("R1", "1")])
back("CC2", [(4.4, 14.0), (4.4, 17.3), (4.7, 17.6), P("R38", "1"), P("R2", "1")])
Y_LEC = Y_COL["CC_SENSE"]
back("CC_SENSE", [P("R37", "2"), (7.05, 15.03), (7.05, Y_LEC), (X_COL["CC_SENSE"], Y_LEC)])
back("CC_SENSE", [P("R38", "2"), (6.45, 17.6), (7.05, Y_LEC)])
# La masse de R1 est enfermée entre CC1, CC2 et leur lecture : un via, sous le Grove.
back("GND", [P("R1", "2"), b.via("GND", 6.35, P("R1", "2")[1])], 0.3)
back("CC_SENSE", [(P("C34", "1")[0], Y_LEC), P("C34", "1")])
# Plus bas, à côté du bouton : sa protection.
POSE.append((["D19", "C11"], [(4.15, 20.2, 8.4, 20.3 + PLUS)], True))

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
poseur = Placer(b, Router(b, forbid=INTERDIT), gap=ECART)
for refs, regions, bottom in POSE:
    refs = [r for r in refs if r not in SANS]
    if refs:
        poseur.auto(refs, regions, bottom)
# Protections USBLC6 (U1 pour l'USB, U11 pour le port) : chaque ligne entre par une pastille
# et ressort par celle d'en face. Les deux liaisons passent droit sous le boîtier, sans se
# croiser ; le routeur n'a plus qu'à amener chaque ligne d'un côté et à repartir de l'autre.
for ref, lignes in (("U1", (("1", "6"), ("3", "4"))), ("U11", (("1", "6"), ("3", "4")))):
    if ref in b.fps:
        face = "B.Cu" if b.fps[ref].IsFlipped() else "F.Cu"
        for a, c in lignes:
            b.track(b.fps[ref].FindPadByNumber(a).GetNetname().lstrip("/"), [P(ref, a), P(ref, c)], 0.2, layer=face)
print("non posés :", sorted(set(b.comps) - set(b.fps)))
print("batterie : x de", round(X_BAT_DEBUT, 2), "à", round(X_BAT_FIN, 2), "; sans cuivre au-delà de x =", X_SANS_CUIVRE)

ROUTAGE = f"{DOSSIER}/{NOM}-routage.json" if ESSAI else "v0/routage.json"
signature = b.signature()
trace = False                  # la carte porte-t-elle son tracé ?
if "--router" in sys.argv:
    trace = True
    r = Router(b, forbid=INTERDIT,
               # le dos, sous la batterie, reste un plan de masse : y passer coûte trois fois plus
               costly=[("B.Cu", X_BAT_DEBUT, 0, X_EVENTAIL, H, COUT_DOS)])
    seuls = [a.split("=")[1].split(",") for a in sys.argv if a.startswith("--reseaux=")]
    # Les alimentations d'abord, tant que la place est libre : ce sont les pistes larges.
    r.route(skip=("GND",), only=seuls[0] if seuls else None, seed=None if GRAINE is None else int(GRAINE),
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
        trace = True

# Plans de masse sur les deux faces. Celui du dos est continu sous la batterie.
EDGE = 0.4
b.zone("GND", "F.Cu", EDGE, EDGE, W - EDGE, H - EDGE)
b.zone("GND", "B.Cu", EDGE, EDGE, W - EDGE, H - EDGE)
# Les pistes découpent les deux plans en morceaux. Une fois la carte tracée, on coud par un
# via chaque morceau isolé au plan principal de l'autre face, là où ils se recouvrent.
# Un morceau sans recouvrement est enfermé entre des pistes : le routeur relie alors une de
# ses pastilles au cuivre de masse principal, comme il route un signal, puis on recoud.
if trace:
    vias = liens = 0
    for tour in range(6):
        n, isoles = b.stitch_zones("GND", quiet=True)
        vias += n
        a_lier = [g for g in isoles if g["pads"] and g["near"]]
        if not a_lier:
            break
        r = Router(b, forbid=INTERDIT)
        faits = sum(1 for g in a_lier if r.tie(g["pads"][0], g["near"]))
        liens += faits
        if not faits:
            break
    n, isoles = b.stitch_zones("GND")
    print(f"plans de masse : {vias + n} via(s) de couture, {liens} liaison(s) tracée(s), {len(isoles)} groupe(s) resté(s) isolé(s)")
    # Le cuivre proposé par la structure et resté sans emploi est retiré.
    if "--sans-ebarbage" not in sys.argv:
        print("ébarbage : %d piste(s) raccourcie(s), %d retirée(s), %d via(s) retiré(s)" % b.trim())

b.save(draft="--brouillon" in sys.argv or bool(SANS))
