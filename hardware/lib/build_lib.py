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


# --------------------------------------------------------------------------
# Symboles des circuits de la carte v0 absents de la bibliothèque de KiCad.
# Les numéros de broches viennent des fiches de hardware/fiches/. Les empreintes
# sont celles de KiCad pour le boîtier normalisé.
# --------------------------------------------------------------------------

# Convertisseur élévateur TI TPS61023DRLR, LCSC C919459. Fiche SLVSF14B, page 3,
# boîtier DRL (SOT-563) : 1 FB, 2 EN, 3 VIN, 4 GND, 5 SW, 6 VOUT.
TPS61023_SYM = box_symbol(
    "TPS61023DRL", "U", "Package_TO_SOT_SMD:SOT-563", "https://www.ti.com/lit/ds/symlink/tps61023.pdf",
    "Convertisseur élévateur synchrone, entrée 0,5 à 5,5 V, sortie 2,2 à 5,5 V, coupure de la sortie à l'arrêt",
    lcsc="C919459",
    left=[("3", "VIN", "power_in"), ("2", "EN", "input"), ("5", "SW", "passive")],
    right=[("6", "VOUT", "power_out"), ("1", "FB", "input")],
    bottom=[("4", "GND", "power_in")])

# Régulateur 3,3 V Richtek RT9080-33GJ5, LCSC C841192. Fiche DS9080-05, page 2,
# boîtier TSOT-23-5 : 1 VIN, 2 GND, 3 EN, 4 NC, 5 VOUT.
RT9080_SYM = box_symbol(
    "RT9080-33GJ5", "U", "Package_TO_SOT_SMD:TSOT-23-5",
    "https://datasheet.lcsc.com/datasheet/pdf/2701e0c3a2b84b9965f7a61f2c14e970.pdf",
    "Régulateur linéaire 3,3 V, 600 mA, 2 µA au repos, entrée 1,2 à 5,5 V", lcsc="C841192",
    left=[("1", "VIN", "power_in"), ("3", "EN", "input")],
    right=[("5", "VOUT", "power_out"), ("4", "NC", "no_connect")],
    bottom=[("2", "GND", "power_in")])

# Accéléromètre ST LIS2DH12TR, LCSC C110926. Fiche, table 2, boîtier LGA-12 2 × 2 mm :
# 1 SCL, 2 CS, 3 SA0, 4 SDA, 5 Res (à la masse), 6 à 8 GND, 9 Vdd, 10 Vdd_IO, 11 INT2, 12 INT1.
LIS2DH12_SYM = box_symbol(
    "LIS2DH12", "U", "Package_LGA:LGA-12_2x2mm_P0.5mm",
    "https://datasheet.lcsc.com/datasheet/pdf/80fd3cb5c04ce9b30e9bec7b53c4a455.pdf",
    "Accéléromètre 3 axes, I2C ou SPI, 1,71 à 3,6 V, 2 µA à 1 Hz", lcsc="C110926",
    left=[("1", "SCL", "input"), ("4", "SDA", "bidirectional"), ("2", "CS", "input"), ("3", "SA0", "input")],
    right=[("12", "INT1", "output"), ("11", "INT2", "output"), ("5", "RES", "passive")],
    top=[("9", "VDD", "power_in"), ("10", "VDD_IO", "power_in")],
    bottom=[("6", "GND", "power_in"), ("7", "GND", "power_in"), ("8", "GND", "power_in")])

# Double transistor N à drains communs FS8205A (Tech Public), LCSC C2830320, pour la
# protection de la cellule. Fiche page 1, boîtier SOT-23-6 : 1 S1, 2 D1/D2, 3 S2,
# 4 G2, 5 D1/D2, 6 G1. Symbole à une seule unité : la chaîne ne gère pas les autres.
FS8205A_SYM = box_symbol(
    "FS8205A", "Q", "Package_TO_SOT_SMD:SOT-23-6",
    "https://datasheet.lcsc.com/datasheet/pdf/c060cb7baa8cc2b2d2a0ed3afa443ef8.pdf",
    "Deux transistors N à drains communs, 20 V, 6 A, 25 mΩ à 2,5 V", lcsc="C2830320",
    left=[("1", "S1", "passive"), ("6", "G1", "input")],
    right=[("3", "S2", "passive"), ("4", "G2", "input")],
    top=[("2", "D12", "passive"), ("5", "D12", "passive")])

# Superviseur de tension TI TLV803EA30DBZR, LCSC C5218924 : tient sa sortie à la masse
# sous 3,08 V, sortie à drain ouvert. Fiche, figure 6-1, boîtier DBZ (SOT-23), brochage
# sans suffixe : 1 GND, 2 RESET, 3 VDD. Les références à suffixe R ou V ont un autre
# brochage : ne pas en changer sans relire la fiche.
TLV803E_SYM = box_symbol(
    "TLV803EA30DBZ", "U", "Package_TO_SOT_SMD:SOT-23",
    "https://datasheet.lcsc.com/datasheet/pdf/075232f81476471fb0145392049399fa.pdf",
    "Superviseur de tension 3,08 V, sortie à drain ouvert active à 0, 0,25 µA", lcsc="C5218924",
    right=[("2", "~{RESET}", "open_collector")],
    top=[("3", "VDD", "power_in")], bottom=[("1", "GND", "power_in")])

# Tampon à trois états SN74LV1T125DBVR-TP (Tech Public), LCSC C51886115. Fiche page 1,
# SOT-23-5 : 1 /OE, 2 A, 3 GND, 4 Y, 5 VCC. Sortie en haute impédance quand /OE est à 1.
LV1T125_SYM = box_symbol(
    "SN74LV1T125DBV", "U", "Package_TO_SOT_SMD:SOT-23-5",
    "https://datasheet.lcsc.com/datasheet/pdf/d61badc48b1e3ef9b419e747e22ee65f.pdf",
    "Tampon à trois états, 1,6 à 5,5 V, seuil d'entrée bas, sortie au niveau de VCC", lcsc="C51886115",
    left=[("2", "A", "input"), ("1", "~{OE}", "input")],
    right=[("4", "Y", "tri_state")],
    top=[("5", "VCC", "power_in")], bottom=[("3", "GND", "power_in")])

# Bouton à poussée latérale Alps SKRTLAE010, LCSC C110293. L'empreinte de KiCad porte
# deux pastilles 1, une pastille 2 et deux pattes de fixation MP.
SKRTLAE010_SYM = box_symbol(
    "SKRTLAE010", "SW", "Button_Switch_SMD:SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010",
    "https://datasheet.lcsc.com/datasheet/pdf/776a4001117146b9aca9bcb4d41038c0.pdf",
    "Bouton poussoir à poussée latérale, 100 000 cycles", lcsc="C110293",
    left=[("1", "1", "passive")], right=[("2", "2", "passive")], bottom=[("MP", "MP", "passive")])

SYMBOLS = [LED_SYM, TPS61023_SYM, RT9080_SYM, LIS2DH12_SYM, FS8205A_SYM, TLV803E_SYM, LV1T125_SYM,
           SKRTLAE010_SYM]


# --------------------------------------------------------------------------
# Inductance moulée cjiang FXL0420 (4,4 × 4,2 × 2,0 mm), LCSC C167203 pour 1 µH.
# Catalogue FXL page 5, « Recommend Land Pattern » : a = 2,2 entre les pastilles,
# b = 5,2 d'un bord extérieur à l'autre, c = 2,5 de hauteur. Soit deux pastilles de
# 1,5 × 2,5, centres à ±1,85.
# --------------------------------------------------------------------------
FXL0420_FP = "L_cjiang_FXL0420"


def fxl0420_footprint():
    fp = Footprint(FXL0420_FP,
                   "Inductance moulée cjiang FXL0420, 4,4 x 4,2 x 2,0 mm, pastilles du catalogue FXL page 5",
                   "inductance moulée 4020")
    fp.pad(1, -1.85, 0.0, 1.5, 2.5)
    fp.pad(2, 1.85, 0.0, 1.5, 2.5)
    fp.fab([(-2.2, -2.1), (2.2, -2.1), (2.2, 2.1), (-2.2, 2.1)])
    fp.silk(-1.0, -2.3, 1.0, -2.3)
    fp.silk(-1.0, 2.3, 1.0, 2.3)
    fp.courtyard(-2.85, -2.45, 2.85, 2.45)
    return fp.tree(ref_y=-3.3, val_y=3.3)


def main():
    sexp.save(os.path.join(HERE, "luciole.kicad_sym"), symbol_lib(SYMBOLS))
    pretty = os.path.join(HERE, "luciole.pretty")
    os.makedirs(pretty, exist_ok=True)
    for name, tree in ((LED_FP, led_footprint()), (GROVE_FP, grove_footprint()),
                       (FXL0420_FP, fxl0420_footprint())):
        sexp.save(os.path.join(pretty, name + ".kicad_mod"), tree)
        print("écrit", name)


if __name__ == "__main__":
    main()
