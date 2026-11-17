"""Carte Luciole² v0 : schéma.

    tools/kicad python3 v0/circuit.py

Écrit v0/v0.kicad_sch. Le schéma est décrit par noms de broches ; la liste de
connexions voulue (netlist_voulue.txt) l'est par numéros, d'après les fiches.
La construction compare les deux.

La table des broches, l'arbre d'alimentation et les raisons des choix sont dans
le wiki, page « Conception de la carte v0 ». Deux masses : GND est la masse de
la carte, BATN le pôle négatif de la batterie, en amont de la protection.
"""
from schgen import NC, Schematic, stock

G = 2.54                       # pas de la grille du schéma

R0402 = "Resistor_SMD:R_0402_1005Metric"
RES = {  # valeur -> référence LCSC (résistances 0402 à 1 %)
    "22R": "C25092", "100R": "C25076", "470R": "C25117", "1k": "C11702", "2k2": "C25879",
    "3k3": "C25890", "4k7": "C25900", "5k1": "C25905", "5k6": "C25908", "10k": "C25744",
    "51k": "C25794", "100k": "C25741", "200k": "C25764", "330k": "C25778", "470k": "C25790",
}
CAP = {  # valeur -> (référence LCSC, empreinte)
    "100nF": ("C1525", "Capacitor_SMD:C_0402_1005Metric"),
    "1uF": ("C52923", "Capacitor_SMD:C_0402_1005Metric"),
    "10uF": ("C19702", "Capacitor_SMD:C_0603_1608Metric"),
    "22uF": ("C45783", "Capacitor_SMD:C_0805_2012Metric"),
}
LED = dict(lib_id="luciole:SK6812MINI-B-012", lcsc="C5183448")
NFET = dict(lib_id="Transistor_FET:AO3400A", value="AO3400A", lcsc="C20917")
# Le symbole AO3401A de KiCad a le brochage du DMP1045U : 1 grille, 2 source, 3 drain.
PFET = dict(lib_id="Transistor_FET:AO3401A", value="DMP1045U", lcsc="C177033")
TVS = dict(lib_id="Device:D_Zener", value="PESD5Z5.0", lcsc="C132368", footprint="Diode_SMD:D_SOD-523")
BAT54C = dict(lib_id="Diode:BAT54C", value="BAT54C", lcsc="C37704")
BUTTON = dict(lib_id="Switch:SW_Push", value="TS-1088", lcsc="C720477",
              footprint="Button_Switch_SMD:SW_SPST_TS-1088-xR020")
TESTPOINT = dict(lib_id="Connector:TestPoint", assemble=False)
JUMPER = dict(lib_id="Jumper:SolderJumper_2_Bridged", value="pont fermé", assemble=False,
              footprint="Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm")


def build():
    s = Schematic("v0", "Luciole² : carte v0", rev="0.1", date="2026-11-17", paper="A2",
                  libs={**stock("Device", "power", "Connector", "Connector_Generic_MountingPin", "RF_Module",
                                "Battery_Management", "Power_Protection", "Logic_LevelTranslator",
                                "Transistor_FET", "Diode", "Switch", "Jumper"),
                        "luciole": "lib/luciole.kicad_sym"},
                  power={"GND", "+3V3"})

    def R(ref, value, a, b, x, y):
        s.part(ref, x=x * G, y=y * G, lib_id="Device:R", value=value, lcsc=RES[value], footprint=R0402,
               pins={"1": a, "2": b})

    def C(ref, value, a, b, x, y):
        lcsc, footprint = CAP[value]
        s.part(ref, x=x * G, y=y * G, lib_id="Device:C", value=value, lcsc=lcsc, footprint=footprint,
               pins={"1": a, "2": b})

    def TP(ref, net, x, y, diameter="1.5"):
        s.part(ref, x=x * G, y=y * G, value=net, footprint=f"TestPoint:TestPoint_Pad_D{diameter}mm",
               pins={"1": net}, **TESTPOINT)

    def JP(ref, a, b, x, y):
        s.part(ref, x=x * G, y=y * G, pins={"A": a, "B": b}, **JUMPER)

    # ------------------------------------------------------------------ USB
    s.note("USB-C : charge et flashage", 8, 8 * G)
    s.part("J1", x=16 * G, y=34 * G, lib_id="Connector:USB_C_Receptacle_USB2.0_16P", value="TYPE-C-31-M-12",
           lcsc="C165948", footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
           pins={"VBUS": "VBUS", "GND": "GND", "SHIELD": "GND", "CC1": "CC1", "CC2": "CC2",
                 "D+": "USB_DP", "D-": "USB_DN", "SBU1": NC, "SBU2": NC})
    R("R1", "5k1", "CC1", "GND", 34, 18)
    R("R2", "5k1", "CC2", "GND", 42, 18)
    s.part("U1", x=40 * G, y=36 * G, lib_id="Power_Protection:USBLC6-2SC6", lcsc="C7519",
           pins={"I/O1": "USB_DP", "I/O2": "USB_DN", "VBUS": "VBUS", "GND": "GND"})
    R("R3", "22R", "USB_DP", "USB_DP_R", 56, 18)
    R("R4", "22R", "USB_DN", "USB_DN_R", 64, 18)
    C("C1", "10uF", "VBUS", "GND", 34, 52)
    # Présence de l'USB : pont sur VBUS, lu par GPIO7 à travers 100 kΩ.
    R("R5", "3k3", "VBUS", "VBUS_SENSE", 46, 52)
    R("R6", "5k1", "VBUS_SENSE", "GND", 54, 52)
    R("R7", "100k", "VBUS_SENSE", "VBUS_DET", 62, 52)

    # ------------------------------------------------------------- chargeur
    s.note("Chargeur : 500 mA, 1 A si ISET est à 1. Charge permise de 2 à 46 °C environ", 76 * G, 8 * G)
    s.part("U2", x=92 * G, y=30 * G, lib_id="Battery_Management:TP4056-42-ESOP8", lcsc="C16581",
           footprint="Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.3mm",
           pins={"V_{CC}": "VBUS", "CE": "VBUS", "BAT": "VCHG", "PROG": "PROG", "TEMP": "TEMP",
                 "~{CHRG}": "CHRG", "~{STDBY}": "STDBY", "GND": "GND", "EPAD": "GND"})
    R("R8", "2k2", "PROG", "GND", 112, 18)
    R("R9", "2k2", "PROG", "PROG_X", 120, 18)
    s.part("Q1", x=130 * G, y=20 * G, **NFET, pins={"D": "PROG_X", "G": "ISET", "S": "GND"})
    R("R10", "100k", "ISET", "GND", 142, 18)
    R("R11", "5k6", "VBUS", "TEMP", 112, 40)
    R("R12", "200k", "TEMP", "GND", 120, 40)
    s.part("TH1", x=128 * G, y=40 * G, lib_id="Device:Thermistor_NTC", value="10k B3380", lcsc="C77131",
           footprint=R0402, pins={"1": "TEMP", "2": "GND"})
    C("C2", "10uF", "VCHG", "GND", 138, 40)
    R("R13", "100k", "+3V3", "CHRG", 148, 40)
    JP("JP1", "VCHG", "VBAT", 112, 54)

    # ------------------------------------------------ batterie et protection
    s.note("Batterie : inversion (Q2), protection de cellule (U3, Q3). BATN = pôle négatif", 160 * G, 8 * G)
    s.part("J2", x=166 * G, y=24 * G, lib_id="Connector_Generic_MountingPin:Conn_01x02_MountingPin",
           value="A2001WR-S-2P", lcsc="C225233",
           footprint="Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",
           pins={"Pin_1": "BATP", "Pin_2": "BATN", "MountPin": "GND"})
    # Grille au pôle négatif du connecteur, et non à la masse : batterie inversée, le
    # transistor reste bloqué même quand le chargeur est alimenté.
    s.part("Q2", x=182 * G, y=22 * G, **PFET, pins={"D": "BATP", "S": "VBAT", "G": "BATN"})
    s.part("U3", x=200 * G, y=24 * G, lib_id="Battery_Management:DW01A", lcsc="C351410",
           pins={"VCC": "DW_VCC", "GND": "BATN", "OD": "DW_OD", "OC": "DW_OC", "CS": "DW_CS", "TD": NC})
    R("R14", "100R", "VBAT", "DW_VCC", 214, 16)
    C("C3", "100nF", "DW_VCC", "BATN", 222, 16)
    R("R15", "1k", "DW_CS", "GND", 214, 32)
    s.part("Q3", x=200 * G, y=44 * G, lib_id="luciole:FS8205A",
           pins={"S1": "BATN", "G1": "DW_OD", "D12": "PROT_D", "S2": "GND", "G2": "DW_OC"})
    R("R16", "470k", "VBAT", "VBAT_SENSE", 168, 44)
    R("R17", "470k", "VBAT_SENSE", "GND", 176, 44)
    C("C4", "100nF", "VBAT_SENSE", "GND", 184, 44)

    # ------------------------------------------- partage de charge et 3,3 V
    s.note("Partage de charge : VSYS vient de l'USB (D16), sinon de la batterie (Q4)", 8 * G, 64 * G)
    s.part("D16", x=16 * G, y=74 * G, lib_id="Device:D_Schottky", value="DSK24", lcsc="C22466352",
           footprint="Diode_SMD:D_SOD-123F", pins={"A": "VBUS", "K": "VSYS"})
    s.part("Q4", x=30 * G, y=74 * G, **PFET, pins={"S": "VSYS", "D": "VBAT", "G": "VBUS"})
    C("C5", "10uF", "VSYS", "GND", 42, 74)
    JP("JP2", "VSYS", "V3IN", 16, 90)
    C("C6", "10uF", "V3IN", "GND", 26, 90)
    s.part("U4", x=40 * G, y=90 * G, lib_id="luciole:RT9080-33GJ5",
           pins={"VIN": "V3IN", "EN": "V3IN", "VOUT": "+3V3", "NC": NC, "GND": "GND"})
    C("C7", "10uF", "+3V3", "GND", 56, 90)
    s.part("U5", x=70 * G, y=90 * G, lib_id="luciole:TLV803EA30DBZ",
           pins={"VDD": "+3V3", "GND": "GND", "~{RESET}": "EN"})

    # ----------------------------------------------------------------- module
    s.note("Module radio. Rappels et commandes : voir la table des broches du wiki", 92 * G, 64 * G)
    s.part("U6", x=120 * G, y=96 * G, lib_id="RF_Module:ESP32-C6-MINI-1", lcsc="C5736265",
           pins={"3V3": "+3V3", "GND": "GND", "EN": "EN", "NC": NC,
                 "IO0": "VBAT_SENSE", "IO1": "IO1", "IO2": "IO2", "IO3": "BTN", "IO4": "PORT_PU",
                 "IO5": "BOOST_EN", "IO6": "ACC_INT", "IO7": "VBUS_DET", "IO8": "STRAP8", "IO9": "BOOT",
                 "IO12": "USB_DN_R", "IO13": "USB_DP_R", "IO14": "ISET", "IO15": "VSEL",
                 "IO18": "LED_DATA", "IO19": "CHRG", "IO20": "IO20", "IO21": "PORT_OE",
                 "IO22": "ACC_SDA", "IO23": "ACC_SCL", "RXD0": "RXD0", "TXD0": "TXD0"})
    C("C8", "10uF", "+3V3", "GND", 96, 76)
    C("C9", "100nF", "+3V3", "GND", 104, 76)
    R("R18", "10k", "+3V3", "EN", 148, 76)
    C("C10", "1uF", "EN", "GND", 156, 76)
    s.part("SW1", x=166 * G, y=76 * G, **BUTTON, pins={"1": "EN", "2": "GND"})
    R("R19", "10k", "+3V3", "BOOT", 148, 92)
    s.part("SW2", x=166 * G, y=92 * G, **BUTTON, pins={"1": "BOOT", "2": "GND"})
    R("R20", "10k", "+3V3", "STRAP8", 148, 106)

    # -------------------------------------------------- bouton, accéléromètre
    s.note("Bouton utilisateur et accéléromètre", 180 * G, 64 * G)
    s.part("SW3", x=188 * G, y=76 * G, lib_id="luciole:SKRTLAE010", pins={"1": "BTN", "2": "GND", "MP": "GND"})
    R("R21", "100k", "+3V3", "BTN", 202, 76)
    s.part("D19", x=210 * G, y=76 * G, **TVS, pins={"K": "BTN", "A": "GND"})
    C("C11", "100nF", "BTN", "GND", 218, 76)
    # Adresse et sélection au 3,3 V : à la masse, elles fuiraient dans un rappel interne.
    s.part("U7", x=194 * G, y=100 * G, lib_id="luciole:LIS2DH12",
           pins={"VDD": "+3V3", "VDD_IO": "+3V3", "GND": "GND", "RES": "GND", "CS": "+3V3", "SA0": "+3V3",
                 "SCL": "ACC_SCL", "SDA": "ACC_SDA", "INT1": "ACC_INT", "INT2": NC})
    R("R22", "10k", "+3V3", "ACC_SDA", 212, 96)
    R("R23", "10k", "+3V3", "ACC_SCL", 220, 96)
    C("C12", "100nF", "+3V3", "GND", 212, 110)

    # -------------------------------------------- convertisseur et rail des LED
    s.note("Rail des LED : 4,45 V, ou 5,04 V si VSEL est à 1. Coupé tant que BOOST_EN est à 0", 8 * G, 112 * G)
    JP("JP3", "VSYS", "VBIN", 14, 124)
    C("C13", "10uF", "VBIN", "GND", 24, 124)
    s.part("L1", x=34 * G, y=124 * G, lib_id="Device:L", value="1uH FXL0420", lcsc="C167203",
           footprint="luciole:L_cjiang_FXL0420", pins={"1": "VBIN", "2": "SW"})
    s.part("U8", x=48 * G, y=124 * G, lib_id="luciole:TPS61023DRL",
           pins={"VIN": "VBIN", "SW": "SW", "EN": "BOOST_EN", "VOUT": "VLED", "FB": "FB", "GND": "GND"})
    R("R24", "100k", "BOOST_EN", "GND", 14, 140)
    R("R25", "330k", "VLED", "FB", 64, 120)
    R("R26", "51k", "FB", "GND", 64, 134)
    R("R27", "330k", "FB", "FB_X", 72, 134)
    s.part("Q5", x=82 * G, y=136 * G, **NFET, pins={"D": "FB_X", "G": "VSEL", "S": "GND"})
    R("R28", "100k", "VSEL", "GND", 94, 134)
    C("C14", "22uF", "VLED", "GND", 74, 120)
    C("C15", "22uF", "VLED", "GND", 82, 120)

    # ---------------------------------------------------------- chaîne de LED
    s.note("15 LED, tampon de niveau alimenté par le rail", 104 * G, 112 * G)
    s.part("U9", x=112 * G, y=124 * G, lib_id="Logic_LevelTranslator:SN74LV1T34DBV", lcsc="C100024",
           pins={"VCC": "VLED", "GND": "GND", "A": "LED_DATA", "Y": "LED_BUF", "NC": NC})
    C("C16", "100nF", "VLED", "GND", 126, 118)
    R("R29", "470R", "LED_BUF", "LED_D0", 126, 132)
    for i in range(15):
        col, row = i % 8, i // 8
        x, y = 134 + 12 * col, 124 + 22 * row
        s.part(f"D{i + 1}", x=x * G, y=y * G, **LED,
               pins={"DIN": f"LED_D{i}", "DOUT": f"LED_D{i + 1}", "VDD": "VLED", "GND": "GND"})
        C(f"C{17 + i}", "100nF", "VLED", "GND", x + 6, y)
    R("R30", "470R", "LED_D15", "LED_OUT", 218, 146)

    # ------------------------------------------------------------- port Grove
    s.note("Port Grove : ruban LED ou I2C. Tampon U10 à l'essai, relié par JP4", 8 * G, 148 * G)
    s.part("J3", x=14 * G, y=158 * G, lib_id="Connector_Generic_MountingPin:Conn_01x04_MountingPin",
           value="Grove", lcsc="C7429571", footprint="luciole:Grove_HY2.0-4P_Megastar_ZX-HY2.0-4PWT_Horizontal",
           pins={"1": "PORT_1", "2": "PORT_2", "3": "VPORT", "4": "GND", "MP": "GND"})
    s.part("F1", x=26 * G, y=156 * G, lib_id="Device:Polyfuse", value="0,75 A", lcsc="C269118",
           footprint="Fuse:Fuse_1206_3216Metric", pins={"1": "VLED", "2": "VPORT"})
    C("C32", "100nF", "VPORT", "GND", 34, 156)
    s.part("D17", x=42 * G, y=156 * G, **TVS, pins={"K": "PORT_1", "A": "GND"})
    s.part("D18", x=50 * G, y=156 * G, **TVS, pins={"K": "PORT_2", "A": "GND"})
    R("R31", "470R", "IO1", "PORT_1", 58, 156)
    R("R32", "470R", "IO2", "PORT_2", 66, 156)
    R("R33", "4k7", "PORT_PU", "PORT_1", 74, 156)
    R("R34", "4k7", "PORT_PU", "PORT_2", 82, 156)
    # Limitation au 3,3 V : un accessoire peut tirer les lignes vers sa propre alimentation.
    s.part("D20", x=92 * G, y=156 * G, **BAT54C, pins={"1": "IO1", "2": "IO2", "3": "+3V3"})
    s.part("D21", x=104 * G, y=156 * G, **BAT54C, pins={"1": "PORT_PU", "2": "PORT_PU", "3": "+3V3"})
    s.part("U10", x=116 * G, y=160 * G, lib_id="luciole:SN74LV1T125DBV",
           pins={"VCC": "VLED", "GND": "GND", "A": "IO2", "~{OE}": "PORT_OE", "Y": "PORT_BUF"})
    C("C33", "100nF", "VLED", "GND", 128, 160)
    R("R35", "100k", "+3V3", "PORT_OE", 136, 160)
    R("R36", "470R", "PORT_BUF", "PORT_BUF_R", 144, 160)
    JP("JP4", "PORT_BUF_R", "PORT_2", 154, 160)

    # ------------------------------------------------------ pastilles de test
    s.note("Pastilles de test du premier lot. TP15 et TP16 : injection sur le rail des LED", 170 * G, 30 * G)
    pads = [("TP1", "VBUS"), ("TP2", "VBAT"), ("TP3", "VSYS"), ("TP4", "+3V3"), ("TP5", "VLED"),
            ("TP6", "GND"), ("TP7", "GND"), ("TP8", "TXD0"), ("TP9", "RXD0"), ("TP10", "EN"),
            ("TP11", "BOOT"), ("TP12", "IO20"), ("TP13", "STDBY"), ("TP14", "LED_OUT")]
    for i, (ref, net) in enumerate(pads):
        TP(ref, net, 172 + 8 * (i % 7), 54 + 6 * (i // 7))
    TP("TP15", "VLED", 172, 36, diameter="2.0")
    TP("TP16", "GND", 180, 36, diameter="2.0")

    # Réseaux alimentés par un connecteur ou à travers un composant passif : le contrôle
    # électrique a besoin de le savoir.
    for i, net in enumerate(("VBUS", "V3IN", "VBIN", "DW_VCC", "BATN", "GND")):
        s.flag(net, (190 + 6 * i) * G, 36 * G)
    return s


if __name__ == "__main__":
    build().write("v0", project_libs=[("luciole", "../lib/luciole.kicad_sym", "../lib/luciole.pretty")])
    print("écrit v0/v0.kicad_sch")
