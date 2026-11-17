"""Bibliothèque du projet : symboles et empreintes propres à Luciole².

    tools/kicad python3 lib/build_lib.py

Réécrit lib/luciole.kicad_sym et lib/luciole.pretty/. Toutes les cotes sont en
millimètres, origine au centre de la pièce, X vers la droite, Y vers le bas,
vue de dessus (convention des empreintes KiCad).
"""
import os

import sexp
from libgen import Footprint, box_symbol, symbol_lib

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# LED SK6812MINI-B-012, OPSCO, LCSC C5183448
# Fiche B/1 du 2025-09-01 : pages 4 (boîtier 3,7 × 3,5 × 1,1) et 5 (brochage,
# pastilles conseillées).
#
# Ne pas remplacer par le SK6812MINI de KiCad : la numérotation diffère
# (KiCad : 1 DOUT, 2 VSS, 3 DIN, 4 VDD ; ici : 1 DIN, 2 VDD, 3 DOUT, 4 GND)
# et les quatre pastilles ont des tailles différentes.
#
# Pastilles conseillées, vue de dessus, coin biseauté (broche 1) en bas à droite :
#
#        1,5    0,6      2,2
#      +------+     +-----------+
#      |3 DOUT| 1,3 |  2 VDD    | 1,2
#      +------+     +-----------+
#        0,5 d'écart vertical des deux côtés
#      +-----------+     +------+
#      |  4 GND    | 0,8 |1 DIN | 0,9
#      +-----------+     +------+
#          2,4      0,6    1,3
#
# Emprise des pastilles : 4,3 × 2,6, centrée sur le boîtier.
# --------------------------------------------------------------------------
LED_FP = "LED_OPSCO_SK6812MINI-B-012_3.7x3.5mm"
LED_DS = "https://datasheet.lcsc.com/datasheet/pdf/548befcadb2d78c7835f9363d2f11b5b.pdf"


def led_footprint():
    fp = Footprint(LED_FP,
                   "LED RGB adressable OPSCO SK6812MINI-B-012, 3,7 x 3,5 x 1,1 mm, 12 mA par couleur, "
                   "1 DIN 2 VDD 3 DOUT 4 GND, pastilles de la fiche B/1 page 5, LCSC C5183448",
                   "LED RGB SK6812 3535 OPSCO")
    left, right, top, bottom = -2.15, 2.15, -1.30, 1.30

    def pad(number, x1, x2, y1, y2):
        fp.pad(number, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)

    pad(3, left, left + 1.5, top, top + 1.3)             # DOUT, en haut à gauche
    pad(2, right - 2.2, right, top, top + 1.2)           # VDD, en haut à droite
    pad(4, left, left + 2.4, bottom - 0.8, bottom)       # GND, en bas à gauche
    pad(1, right - 1.3, right, bottom - 0.9, bottom)     # DIN, en bas à droite

    # Boîtier 3,7 × 3,5, coin biseauté côté broche 1.
    fp.fab([(-1.85, -1.75), (1.85, -1.75), (1.85, 1.15), (1.25, 1.75), (-1.85, 1.75)])
    # Sérigraphie au-dessus et au-dessous seulement : les pastilles dépassent sur les côtés.
    fp.silk(-1.85, -1.95, 1.85, -1.95)
    fp.silk(-1.85, 1.95, 1.25, 1.95)
    fp.dot(2.55, 1.75, 0.15, "F.SilkS")                  # repère de la broche 1
    fp.courtyard(-2.40, -2.00, 2.40, 2.00)               # pastilles et boîtier, plus 0,25
    return fp.tree(ref_y=-2.9, val_y=3.0)


LED_SYM = box_symbol(
    "SK6812MINI-B-012", "D", f"luciole:{LED_FP}", LED_DS,
    "LED RGB adressable 3535, 12 mA par couleur, VDD 3,7 à 5,5 V", lcsc="C5183448",
    left=[("1", "DIN", "input")], right=[("3", "DOUT", "output")],
    top=[("2", "VDD", "power_in")], bottom=[("4", "GND", "power_in")])


# --------------------------------------------------------------------------
# Connecteur Grove HY2.0-4P couché, montage en surface
# Megastar ZX-HY2.0-4PWT, LCSC C7429571. Plan « HY2.0 卧贴 4P » :
# A = 6,0 (entraxe des broches extrêmes), B = 12,0 (largeur), profondeur 9,2
# (10,5 avec les queues), hauteur 5,2.
#
# Implantation du plan, vue de dessus, queues en haut, ouverture en bas :
#   4 pastilles de 1,5 × 3,0 au pas de 2,0 ;
#   2 pattes de fixation de 1,5 × 3,4, bord extérieur à 2,2 de la dernière
#   pastille, haut des pattes à 4,5 sous le bas des pastilles.
#
# Origine : centre de l'emprise de toutes les pastilles. L'ouverture regarde +Y.
#
# Numérotation Grove, commune à Seeed et à M5Stack : 4 = masse, 3 = alimentation,
# 2 = SDA ou donnée d'un ruban LED, 1 = SCL (libre sur un ruban).
# Schéma du NanoC6 (Sch_M5NanoC6_v0.0.1) : J1 HY-2.0, 1 = GPIO1, 2 = GPIO2, 3 = +5V, 4 = GND.
# Le ruban SK6812 de M5Stack porte sa donnée sur G2, donc sur la broche 2.
# Les couleurs ne sont pas normalisées : Seeed met le fil jaune en 1, M5Stack en 2.
#
# Position des broches, vue de dessus, ouverture vers soi :
#
#        queues
#     4    3    2    1
#    GND  VCC  SDA  SCL        la masse est à GAUCHE
#       ouverture
#
# Le plan du fabricant ne numérote pas les broches. Cette position est établie
# par deux produits M5Stack, vérifiés le 17 novembre 2026 sur leurs photos :
#   - adaptateur « Grove to 4PIN » (A099) : au dos, sous le connecteur, la
#     sérigraphie lit signal, signal, 5V, GND ; la pastille carrée, à droite
#     dans les deux vues, montre que gauche et droite sont conservées ; vu de
#     dessus, ouverture vers le haut, la masse est donc à droite ;
#   - NanoC6 : l'étiquette du dessous lit G, 5V, G2, G1, la légende côté bouton
#     lit G1, G2, 5V, G, et le connecteur est monté côté bouton.
# Ne pas renuméroter sans refaire cette vérification.
# --------------------------------------------------------------------------
GROVE_FP = "Grove_HY2.0-4P_Megastar_ZX-HY2.0-4PWT_Horizontal"
GROVE_DS = "https://datasheet.lcsc.com/datasheet/pdf/e46d54a94fecda2645bf71cedac5ff20.pdf"


def grove_footprint():
    fp = Footprint(GROVE_FP,
                   "Connecteur Grove HY2.0 4 broches couché CMS, Megastar ZX-HY2.0-4PWT, pas 2 mm, "
                   "12 x 10,5 x 5,2 mm, ouverture vers +Y, LCSC C7429571. "
                   "Vue de dessus, ouverture vers soi : 4 GND, 3 VCC, 2 SDA, 1 SCL de gauche à droite",
                   "Grove HY2.0 connecteur CMS")
    # Cotes du plan, mesurées depuis le centre de la rangée de pastilles, puis décalées de
    # OY pour amener l'origine au centre de l'emprise de toutes les pastilles. C'est le
    # point que JLCPCB attend dans le fichier de pose (à contrôler dans leur aperçu).
    OY = (-1.5 + 9.4) / 2                                # 3,95
    for k in range(4):                                   # de gauche à droite : 4, 3, 2, 1
        fp.pad(4 - k, -3.0 + 2.0 * k, 0.0 - OY, 1.5, 3.0)
    mp_x = 3.75 + 2.2 - 0.75                             # 5,20 : centre des pattes
    mp_y = 1.5 + 4.5 + 1.7                               # 7,70
    fp.pad("MP", -mp_x, mp_y - OY, 1.5, 3.4)
    fp.pad("MP", mp_x, mp_y - OY, 1.5, 3.4)

    back, step, front = -0.10 - OY, 1.30 - OY, 9.10 - OY     # fond des oreilles, fond du corps, face d'ouverture
    fp.fab([(-6.0, back), (-4.95, back), (-4.95, step), (4.95, step), (4.95, back),
            (6.0, back), (6.0, front), (-6.0, front)])
    fp.silk(-6.15, back - 0.1, -6.15, 5.6 - OY)
    fp.silk(6.15, back - 0.1, 6.15, 5.6 - OY)
    fp.dot(4.4, -1.9 - OY, 0.2, "F.SilkS")               # repère de la broche 1, à côté d'elle
    fp.courtyard(-6.25, -1.75 - OY, 6.25, 9.65 - OY)     # pastilles et boîtier, plus 0,25
    return fp.tree(ref_y=-0.5, val_y=1.5)


def main():
    sexp.save(os.path.join(HERE, "luciole.kicad_sym"), symbol_lib([LED_SYM]))
    pretty = os.path.join(HERE, "luciole.pretty")
    os.makedirs(pretty, exist_ok=True)
    for name, tree in ((LED_FP, led_footprint()), (GROVE_FP, grove_footprint())):
        sexp.save(os.path.join(pretty, name + ".kicad_mod"), tree)
        print("écrit", name)


if __name__ == "__main__":
    main()
