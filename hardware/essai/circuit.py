"""Carte d'essai Luciole² : un tronçon de trois LED entre deux connecteurs Grove.

    tools/kicad python3 essai/circuit.py

Écrit essai/essai.kicad_sch. Cette carte valide la chaîne d'outils sur un
morceau réel de la carte v0 : la LED et son empreinte, le pas de 7 mm, le
connecteur Grove. Elle n'est pas destinée à être commandée.
"""
from schgen import NC, Schematic, stock

G = 2.54                       # pas de la grille du schéma

LED = dict(lib_id="luciole:SK6812MINI-B-012", lcsc="C5183448")
CAP = dict(lib_id="Device:C", value="100nF", lcsc="C1525",
           footprint="Capacitor_SMD:C_0402_1005Metric")
RES = dict(lib_id="Device:R", value="470R", lcsc="C25117",
           footprint="Resistor_SMD:R_0402_1005Metric")
GROVE = dict(lib_id="Connector_Generic_MountingPin:Conn_01x04_MountingPin", value="Grove", lcsc="C7429571",
             footprint="luciole:Grove_HY2.0-4P_Megastar_ZX-HY2.0-4PWT_Horizontal")


def build():
    s = Schematic("essai", "Luciole² : tronçon d'essai, 3 LED", rev="0.1", date="2026-11-17",
                  libs={**stock("Device", "power", "Connector_Generic_MountingPin"),
                        "luciole": "lib/luciole.kicad_sym"},
                  power={"GND"})
    y = 32 * G

    s.note("Entrée Grove", 8 * G, 22 * G)
    # Brochage Grove de M5Stack : 4 masse, 3 alimentation, 2 donnée du ruban, 1 libre.
    s.part("J1", x=12 * G, y=y, **GROVE,
           pins={"1": NC, "2": "DIN", "3": "VLED", "4": "GND", "MP": "GND"})
    s.part("R1", x=24 * G, y=y, **RES, pins={"1": "DIN", "2": "LED_D0"})

    s.note("Chaîne de LED, un condensateur par LED", 34 * G, 22 * G)
    for i in range(3):
        x = (38 + 20 * i) * G
        s.part(f"D{i + 1}", x=x, y=y, **LED,
               pins={"DIN": f"LED_D{i}", "DOUT": f"LED_D{i + 1}", "VDD": "VLED", "GND": "GND"})
        s.part(f"C{i + 1}", x=x + 10 * G, y=y, **CAP, pins={"1": "VLED", "2": "GND"})

    s.note("Sortie Grove", 94 * G, 22 * G)
    s.part("R2", x=96 * G, y=y, **RES, pins={"1": "LED_D3", "2": "DOUT"})
    s.part("J2", x=108 * G, y=y, **GROVE,
           pins={"1": NC, "2": "DOUT", "3": "VLED", "4": "GND", "MP": "GND"})

    s.note("L'alimentation arrive par un connecteur", 8 * G, 52 * G)
    s.flag("VLED", 12 * G, 58 * G)
    s.flag("GND", 20 * G, 58 * G)
    return s


if __name__ == "__main__":
    build().write("essai", project_libs=[("luciole", "../lib/luciole.kicad_sym", "../lib/luciole.pretty")])
    print("écrit essai/essai.kicad_sch")
