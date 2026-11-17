"""Carte Luciole² v0 : schéma.

    tools/kicad python3 v0/circuit.py

Écrit v0/v0.kicad_sch. Le schéma est décrit par noms de broches ; la liste de
connexions voulue (netlist_voulue.txt) l'est par numéros, d'après les fiches.
La construction compare les deux.

La table des broches, l'arbre d'alimentation et les raisons des choix sont dans
le wiki, page « Conception de la carte v0 ». Deux masses : GND est la masse de
la carte, BATN le pôle négatif de la batterie, en amont de la protection.

Révision 0.3 du 17 novembre 2026, après la relecture du schéma contre les
fiches et la contre-relecture des corrections : voir la page « Revue
indépendante » du wiki.
"""
from schgen import NC, Schematic, stock

G = 2.54                       # pas de la grille du schéma

R0402 = "Resistor_SMD:R_0402_1005Metric"
RES = {  # valeur -> référence LCSC (résistances 0402 à 1 %)
    "22R": "C25092", "220R": "C25091", "100R": "C25076", "470R": "C25117", "1k": "C11702",
    "1k5": "C25867", "2k2": "C25879", "4k7": "C25900", "5k1": "C25905", "5k6": "C25908",
    "10k": "C25744", "51k": "C25794", "100k": "C25741", "200k": "C25764", "330k": "C25778",
    "470k": "C25790", "1M": "C26083",
}
CAP = {  # valeur -> (référence LCSC, empreinte)
    "470pF": ("C1537", "Capacitor_SMD:C_0402_1005Metric"),
    "100nF": ("C1525", "Capacitor_SMD:C_0402_1005Metric"),
    "1uF": ("C52923", "Capacitor_SMD:C_0402_1005Metric"),
    "10uF": ("C19702", "Capacitor_SMD:C_0603_1608Metric"),
    "22uF": ("C45783", "Capacitor_SMD:C_0805_2012Metric"),
}
LED = dict(lib_id="luciole:SK6812MINI-B-012", lcsc="C5183448")
NFET = dict(lib_id="Transistor_FET:AO3400A", value="AO3400A", lcsc="C20917")
# Le symbole AO3401A de KiCad a le brochage du DMP1045U : 1 grille, 2 source, 3 drain.
PFET = dict(lib_id="Transistor_FET:AO3401A", value="DMP1045U", lcsc="C177033")
PFET_12V = dict(lib_id="Transistor_FET:AO3401A", value="AO3401A", lcsc="C15127")
SCHOTTKY = dict(lib_id="Device:D_Schottky", value="DSK24", lcsc="C22466352", footprint="Diode_SMD:D_SOD-123F")
TVS = dict(lib_id="Device:D_Zener", value="PESD5Z5.0", lcsc="C132368", footprint="Diode_SMD:D_SOD-523")
BAT54C = dict(lib_id="Diode:BAT54C", value="BAT54C", lcsc="C37704")
USBLC6 = dict(lib_id="Power_Protection:USBLC6-2SC6", lcsc="C7519")
BUTTON = dict(lib_id="Switch:SW_Push", value="TS-1088", lcsc="C720477",
              footprint="Button_Switch_SMD:SW_SPST_TS-1088-xR020")
TESTPOINT = dict(lib_id="Connector:TestPoint", assemble=False)
JUMPER = dict(lib_id="Jumper:SolderJumper_2_Bridged", value="pont fermé", assemble=False,
              footprint="Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm")

# Décalage vertical de chaque rangée de blocs sur la page, en pas de grille.
ROW2, ROW3, ROW4 = 6, 10, 18


def build():
    s = Schematic("v0", "Luciole² : carte v0", rev="0.3", date="2026-11-17", paper="A1",
                  libs={**stock("Device", "power", "Connector", "Connector_Generic_MountingPin", "RF_Module",
                                "Battery_Management", "Power_Protection", "Logic_LevelTranslator",
                                "Transistor_FET", "Diode", "Switch", "Jumper"),
                        "luciole": "lib/luciole.kicad_sym"},
                  power={"GND", "+3V3"})

    def R(ref, value, a, b, x, y):
        s.part(ref, x=x * G, y=y * G, lib_id="Device:R", value=value, lcsc=RES[value], footprint=R0402,
               pins={"1": a, "2": b})

    def C(ref, value, a, b, x, y, dnp=False):
        lcsc, footprint = CAP[value]
        s.part(ref, x=x * G, y=y * G, lib_id="Device:C", value=value, lcsc=lcsc, footprint=footprint,
               pins={"1": a, "2": b}, dnp=dnp)

    def TP(ref, net, x, y, diameter="1.5"):
        s.part(ref, x=x * G, y=y * G, value=net, footprint=f"TestPoint:TestPoint_Pad_D{diameter}mm",
               pins={"1": net}, **TESTPOINT)

    def JP(ref, a, b, x, y):
        s.part(ref, x=x * G, y=y * G, pins={"A": a, "B": b}, **JUMPER)

    # ------------------------------------------------------------------ USB
    s.note("USB-C : charge et flashage. CC_SENSE : courant annoncé par la source", 8 * G, 8 * G)
    s.part("J1", x=16 * G, y=34 * G, lib_id="Connector:USB_C_Receptacle_USB2.0_16P", value="TYPE-C-31-M-12",
           lcsc="C165948", footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
           pins={"VBUS": "VBUS", "GND": "GND", "SHIELD": "GND", "CC1": "CC1", "CC2": "CC2",
                 "D+": "USB_DP", "D-": "USB_DN", "SBU1": NC, "SBU2": NC})
    R("R1", "5k1", "CC1", "GND", 34, 18)
    R("R2", "5k1", "CC2", "GND", 42, 18)
    # Rail d'écrêtage de U1 sur le nœud système et non sur VBUS : relié à VBUS, le rappel
    # de D+ de la puce réalimenterait VBUS par la diode de U1, câble débranché. Le nœud
    # système est toujours au-dessus du 3,3 V, qui en dérive, et il existe côté connecteur.
    s.part("U1", x=40 * G, y=36 * G, **USBLC6,
           pins={"I/O1": "USB_DP", "I/O2": "USB_DN", "VBUS": "VSYS", "GND": "GND"})
    R("R3", "22R", "USB_DP", "USB_DP_R", 56, 18)
    R("R4", "22R", "USB_DN", "USB_DN_R", 64, 18)
    # Entrée : 1 µF direct, et 10 µF derrière 1 Ω pour amortir la surtension au branchement
    # (fiche du TP4056, « CC bypass capacitor »).
    s.part("R39", x=30 * G, y=52 * G, lib_id="Device:R", value="1R", lcsc="C22936",
           footprint="Resistor_SMD:R_0603_1608Metric", pins={"1": "VBUS", "2": "VBUS_AMORTI"})
    C("C1", "10uF", "VBUS_AMORTI", "GND", 38, 52)
    C("C39", "1uF", "VBUS", "GND", 46, 52)
    # Présence de l'USB : pont sur VBUS, lu par GPIO7 à travers 100 kΩ. Le pont décharge
    # aussi VBUS au débranchement et absorbe la fuite de D16.
    R("R5", "1k", "VBUS", "VBUS_SENSE", 54, 52)
    R("R6", "1k5", "VBUS_SENSE", "GND", 62, 52)
    R("R7", "100k", "VBUS_SENSE", "VBUS_DET", 70, 52)
    # Courant annoncé par la source : moyenne des deux broches CC, lue par GPIO4.
    R("R37", "200k", "CC1", "CC_SENSE", 30, 62)
    R("R38", "200k", "CC2", "CC_SENSE", 38, 62)
    C("C34", "100nF", "CC_SENSE", "GND", 46, 62)
    s.part("D24", x=54 * G, y=62 * G, **TVS, pins={"K": "VBUS", "A": "GND"})
    C("C38", "100nF", "VSYS", "GND", 62, 62)

    # ------------------------------------------------------------- chargeur
    s.note("Chargeur : 500 mA, 1 A si ISET est à 1. Arrêté si CHG_INH est à 0. Charge de 2 à 46 °C", 76 * G, 8 * G)
    s.part("U2", x=92 * G, y=30 * G, lib_id="Battery_Management:TP4056-42-ESOP8", lcsc="C16581",
           footprint="Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.3mm",
           pins={"V_{CC}": "VBUS", "CE": "CE", "BAT": "VCHG", "PROG": "PROG", "TEMP": "TEMP",
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
    JP("JP1", "VCHG", "VBAT", 112, 56)
    # Charge permise par défaut : CE est tiré à VBUS. Q7, grille au 3,3 V, est monté en
    # adaptateur de niveau : GPIO21 à 0 tire CE à 0 et arrête la charge ; en l'air, à 1 ou
    # sans 3,3 V, Q7 est bloqué et la broche ne voit jamais le 5 V de CE.
    # R44 de 330 kΩ et non 1 MΩ : la fuite de Q7 et l'entrée de CE, que la fiche ne chiffre
    # pas, ne doivent pas pouvoir arrêter la charge. R47 limite le courant quand la broche
    # vide C40. Le firmware tire GPIO21 à 0 ou la relâche, il ne la pousse jamais à 1.
    R("R44", "330k", "VBUS", "CE", 124, 56)
    C("C40", "100nF", "CE", "GND", 132, 56)
    s.part("Q7", x=140 * G, y=(118 + ROW2) * G, **NFET, pins={"D": "CE", "G": "+3V3", "S": "Q7_S"})
    R("R47", "10k", "CHG_INH", "Q7_S", 152, 118 + ROW2)
    R("R41", "100k", "+3V3", "STDBY", 146, 56)
    R("R42", "10k", "PROG", "PROG_TP", 154, 56)

    # ------------------------------------------------ batterie et protection
    s.note("Batterie : inversion (Q2, Q6), protection de cellule (U3, Q3). BATN = pôle négatif", 160 * G, 8 * G)
    s.part("J2", x=166 * G, y=24 * G, lib_id="Connector_Generic_MountingPin:Conn_01x02_MountingPin",
           value="A2001WR-S-2P", lcsc="C225233",
           footprint="Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",
           pins={"Pin_1": "BATP", "Pin_2": "BATN", "MountPin": "GND"})
    # Q2 est rendu passant par R43 quand la batterie est à l'endroit. Batterie inversée,
    # BATP passe sous VBAT : Q6 conduit et relie la grille de Q2 à sa source. Q2 reste
    # bloqué même si le chargeur et la protection de cellule ramènent BATN vers la masse.
    s.part("Q2", x=182 * G, y=22 * G, **PFET, pins={"D": "BATP", "S": "VBAT", "G": "Q2_G"})
    s.part("Q6", x=182 * G, y=38 * G, **PFET_12V, pins={"S": "VBAT", "G": "Q6_G", "D": "Q2_G"})
    R("R43", "10k", "Q2_G", "BATN", 191, 42)
    # R45 : sans batterie, BATP suit VBAT et Q6 reste bloqué. Sans elle, USB branché le
    # premier, Q6 tiendrait Q2 bloqué et une batterie branchée ensuite resterait isolée.
    # R46 protège la grille de Q6, qui donne sur une broche du connecteur.
    R("R45", "1M", "VBAT", "BATP", 174, 40)
    R("R46", "100k", "BATP", "Q6_G", 166, 40)
    s.part("U3", x=202 * G, y=24 * G, lib_id="Battery_Management:DW01A", lcsc="C351410",
           pins={"VCC": "DW_VCC", "GND": "BATN", "OD": "DW_OD", "OC": "DW_OC", "CS": "DW_CS", "TD": NC})
    R("R14", "100R", "VBAT", "DW_VCC", 216, 16)
    C("C3", "100nF", "DW_VCC", "BATN", 224, 16)
    R("R15", "1k", "DW_CS", "GND", 216, 32)
    s.part("Q3", x=206 * G, y=48 * G, lib_id="luciole:FS8205A",
           pins={"S1": "BATN", "G1": "DW_OD", "D12": "PROT_D", "S2": "GND", "G2": "DW_OC"})
    R("R16", "470k", "VBAT", "VBAT_SENSE", 164, 56)
    R("R17", "470k", "VBAT_SENSE", "GND", 172, 56)
    C("C4", "100nF", "VBAT_SENSE", "GND", 180, 56)

    # ------------------------------------------- partage de charge et 3,3 V
    y = ROW2
    s.note("Partage de charge : VSYS vient de l'USB (D16), sinon de la batterie (Q4, et D22 pendant la bascule)",
           8 * G, (64 + y) * G)
    s.part("D16", x=14 * G, y=(74 + y) * G, **SCHOTTKY, pins={"A": "VBUS", "K": "VSYS"})
    s.part("D22", x=24 * G, y=(74 + y) * G, **SCHOTTKY, pins={"A": "VBAT", "K": "VSYS"})
    s.part("Q4", x=36 * G, y=(74 + y) * G, **PFET, pins={"S": "VSYS", "D": "VBAT", "G": "VBUS"})
    C("C5", "10uF", "VSYS", "GND", 48, 74 + y)
    JP("JP2", "VSYS", "V3IN", 16, 90 + y)
    C("C6", "10uF", "V3IN", "GND", 26, 90 + y)
    s.part("U4", x=40 * G, y=(90 + y) * G, lib_id="luciole:RT9080-33GJ5",
           pins={"VIN": "V3IN", "EN": "V3IN", "VOUT": "+3V3", "NC": NC, "GND": "GND"})
    C("C7", "10uF", "+3V3", "GND", 56, 90 + y)
    s.part("U5", x=70 * G, y=(90 + y) * G, lib_id="luciole:TLV803EA30DBZ",
           pins={"VDD": "+3V3", "GND": "GND", "~{RESET}": "EN"})
    C("C35", "100nF", "+3V3", "GND", 82, 90 + y)

    # ----------------------------------------------------------------- module
    s.note("Module radio. Rappels et commandes : voir la table des broches du wiki", 92 * G, (64 + y) * G)
    s.part("U6", x=120 * G, y=(96 + y) * G, lib_id="RF_Module:ESP32-C6-MINI-1", lcsc="C5736265",
           pins={"3V3": "+3V3", "GND": "GND", "EN": "EN", "NC": NC,
                 "IO0": "VBAT_SENSE", "IO1": "IO1", "IO2": "IO2", "IO3": "BTN_IO", "IO4": "CC_SENSE",
                 "IO5": "BOOST_EN", "IO6": "ACC_INT", "IO7": "VBUS_DET", "IO8": "STRAP8", "IO9": "BOOT",
                 "IO12": "USB_DN_R", "IO13": "USB_DP_R", "IO14": "ISET", "IO15": "PORT_PU",
                 "IO18": "LED_DATA", "IO19": "CHRG", "IO20": "VSEL", "IO21": "CHG_INH",
                 "IO22": "ACC_SDA", "IO23": "ACC_SCL", "RXD0": "RXD0", "TXD0": "TXD0"})
    C("C8", "10uF", "+3V3", "GND", 96, 76 + y)
    C("C9", "100nF", "+3V3", "GND", 104, 76 + y)
    # 100 kΩ et 100 nF : même constante de temps que les 10 kΩ et 1 µF d'Espressif, mais
    # dix fois moins de courant quand le superviseur tient EN à la masse, batterie vide.
    R("R18", "100k", "+3V3", "EN", 148, 76 + y)
    C("C10", "100nF", "EN", "GND", 156, 76 + y)
    s.part("SW1", x=166 * G, y=(76 + y) * G, **BUTTON, pins={"1": "EN", "2": "GND"})
    R("R19", "10k", "+3V3", "BOOT", 148, 92 + y)
    s.part("SW2", x=166 * G, y=(92 + y) * G, **BUTTON, pins={"1": "BOOT", "2": "GND"})
    R("R20", "10k", "+3V3", "STRAP8", 148, 106 + y)

    # -------------------------------------------------- bouton, accéléromètre
    s.note("Bouton utilisateur et accéléromètre", 180 * G, (64 + y) * G)
    s.part("SW3", x=188 * G, y=(76 + y) * G, lib_id="luciole:SKRTLAE010", pins={"1": "BTN", "2": "GND", "MP": "GND"})
    R("R21", "100k", "+3V3", "BTN", 202, 76 + y)
    s.part("D19", x=210 * G, y=(76 + y) * G, **TVS, pins={"K": "BTN", "A": "GND"})
    C("C11", "100nF", "BTN", "GND", 218, 76 + y)
    R("R40", "1k", "BTN", "BTN_IO", 226, 76 + y)
    # Adresse et sélection au 3,3 V : à la masse, elles fuiraient dans un rappel interne.
    s.part("U7", x=194 * G, y=(100 + y) * G, lib_id="luciole:LIS2DH12",
           pins={"VDD": "+3V3", "VDD_IO": "+3V3", "GND": "GND", "RES": "GND", "CS": "+3V3", "SA0": "+3V3",
                 "SCL": "ACC_SCL", "SDA": "ACC_SDA", "INT1": "ACC_INT", "INT2": NC})
    R("R22", "10k", "+3V3", "ACC_SDA", 212, 96 + y)
    R("R23", "10k", "+3V3", "ACC_SCL", 220, 96 + y)
    C("C12", "100nF", "+3V3", "GND", 212, 110 + y)
    C("C36", "10uF", "+3V3", "GND", 220, 110 + y)

    # -------------------------------------------- convertisseur et rail des LED
    y = ROW3
    s.note("Rail des LED : 4,45 V, ou 5,04 V si VSEL est à 1. Coupé tant que BOOST_EN est à 0", 8 * G, (112 + y) * G)
    JP("JP3", "VSYS", "VBIN", 14, 124 + y)
    C("C13", "10uF", "VBIN", "GND", 24, 124 + y)
    s.part("L1", x=34 * G, y=(124 + y) * G, lib_id="Device:L", value="1uH FXL0420", lcsc="C167203",
           footprint="luciole:L_cjiang_FXL0420", pins={"1": "VBIN", "2": "SW"})
    s.part("U8", x=48 * G, y=(124 + y) * G, lib_id="luciole:TPS61023DRL",
           pins={"VIN": "VBIN", "SW": "SW", "EN": "BOOST_EN", "VOUT": "VLED", "FB": "FB", "GND": "GND"})
    R("R24", "100k", "BOOST_EN", "GND", 14, 140 + y)
    R("R25", "330k", "VLED", "FB", 64, 120 + y)
    R("R26", "51k", "FB", "GND", 64, 134 + y)
    R("R27", "330k", "FB", "FB_X", 72, 134 + y)
    s.part("Q5", x=82 * G, y=(136 + y) * G, **NFET, pins={"D": "FB_X", "G": "VSEL", "S": "GND"})
    # VSEL est sur GPIO20, qui a un rappel interne au 3,3 V pendant le reset : 1 MΩ ne le
    # contre pas (5,04 V choisi, convertisseur arrêté, sans effet) et ne fuit que 3 µA.
    R("R28", "1M", "VSEL", "GND", 94, 134 + y)
    C("C14", "22uF", "VLED", "GND", 74, 120 + y)
    C("C15", "22uF", "VLED", "GND", 82, 120 + y)
    # Emplacement non monté : TI demande ce condensateur quand la sortie dépasse 40 µF
    # effectifs, ce qu'un ruban externe peut apporter.
    C("C37", "470pF", "VLED", "FB", 90, 120 + y, dnp=True)

    # ---------------------------------------------------------- chaîne de LED
    s.note("15 LED, tampon de niveau alimenté par le rail", 104 * G, (112 + y) * G)
    s.part("U9", x=112 * G, y=(124 + y) * G, lib_id="Logic_LevelTranslator:SN74LV1T34DBV", lcsc="C100024",
           pins={"VCC": "VLED", "GND": "GND", "A": "LED_DATA", "Y": "LED_BUF", "NC": NC})
    C("C16", "100nF", "VLED", "GND", 126, 118 + y)
    R("R29", "470R", "LED_BUF", "LED_D0", 126, 132 + y)
    for i in range(15):
        col, row = i % 8, i // 8
        lx, ly = 134 + 12 * col, 124 + y + 22 * row
        s.part(f"D{i + 1}", x=lx * G, y=ly * G, **LED,
               pins={"DIN": f"LED_D{i}", "DOUT": f"LED_D{i + 1}", "VDD": "VLED", "GND": "GND"})
        C(f"C{17 + i}", "100nF", "VLED", "GND", lx + 6, ly)
    R("R30", "470R", "LED_D15", "LED_OUT", 218, 146 + y)

    # ------------------------------------------------------------- port Grove
    y = ROW4
    s.note("Port Grove : ruban LED ou I2C. PORT_PU à 1 : rappels alimentés, tampon U10 inactif. "
           "PORT_PU à 0 : tampon actif vers la broche 2, par JP4", 8 * G, (148 + y) * G)
    s.part("J3", x=14 * G, y=(158 + y) * G, lib_id="Connector_Generic_MountingPin:Conn_01x04_MountingPin",
           value="Grove", lcsc="C7429571", footprint="luciole:Grove_HY2.0-4P_Megastar_ZX-HY2.0-4PWT_Horizontal",
           pins={"1": "PORT_1", "2": "PORT_2", "3": "VPORT", "4": "GND", "MP": "GND"})
    s.part("F1", x=26 * G, y=(156 + y) * G, lib_id="Device:Polyfuse", value="0,75 A", lcsc="C269118",
           footprint="Fuse:Fuse_1206_3216Metric", pins={"1": "VLED", "2": "VPORT"})
    C("C32", "100nF", "VPORT", "GND", 34, 156 + y)
    # Protection à faible capacité (3 pF par ligne). Son rail d'écrêtage reste isolé, sur
    # son propre condensateur : relié au rail du port, un niveau haut sur une ligne
    # réalimenterait le rail des LED quand il est coupé.
    s.part("U11", x=48 * G, y=(158 + y) * G, **USBLC6,
           pins={"I/O1": "PORT_1", "I/O2": "PORT_2", "VBUS": "PORT_ECRET", "GND": "GND"})
    C("C41", "100nF", "PORT_ECRET", "GND", 56, 168 + y)
    R("R31", "470R", "IO1", "PORT_1", 64, 156 + y)
    R("R32", "470R", "IO2", "PORT_2", 72, 156 + y)
    R("R33", "4k7", "PORT_PU", "PORT_1", 80, 156 + y)
    R("R34", "4k7", "PORT_PU", "PORT_2", 88, 156 + y)
    # Limitation au 3,3 V : un accessoire peut tirer les lignes vers sa propre alimentation.
    s.part("D20", x=98 * G, y=(156 + y) * G, **BAT54C, pins={"1": "IO1", "2": "IO2", "3": "+3V3"})
    s.part("D21", x=110 * G, y=(156 + y) * G, **BAT54C, pins={"1": "PORT_PU", "2": "PORT_PU", "3": "+3V3"})
    s.part("U10", x=126 * G, y=(158 + y) * G, lib_id="luciole:SN74LV1T125DBV",
           pins={"VCC": "VLED", "GND": "GND", "A": "IO2", "~{OE}": "PORT_PU", "Y": "PORT_BUF"})
    C("C33", "100nF", "VLED", "GND", 140, 156 + y)
    R("R36", "220R", "PORT_BUF", "PORT_BUF_R", 148, 156 + y)
    # /OE de U10 ne doit pas flotter : 1 MΩ au 3,3 V le tient à 1, tampon inactif.
    R("R35", "1M", "+3V3", "PORT_PU", 166, 156 + y)
    JP("JP4", "PORT_BUF_R", "PORT_2", 158, 156 + y)

    # ------------------------------------------------------ pastilles de test
    s.note("Pastilles de test du premier lot. TP15 et TP16 : injection sur le rail des LED", 8 * G, 186 * G)
    pads = [("TP1", "VBUS"), ("TP2", "VBAT"), ("TP3", "VSYS"), ("TP4", "+3V3"), ("TP5", "VLED"),
            ("TP6", "GND"), ("TP7", "GND"), ("TP8", "TXD0"), ("TP9", "RXD0"), ("TP10", "EN"),
            ("TP11", "BOOT"), ("TP12", "CC_SENSE"), ("TP13", "STDBY"), ("TP14", "LED_OUT"),
            ("TP17", "PROG_TP"), ("TP18", "BATN")]
    for i, (ref, net) in enumerate(pads):
        TP(ref, net, 12 + 10 * i, 194)
    TP("TP15", "VLED", 176, 194, diameter="2.0")
    TP("TP16", "GND", 186, 194, diameter="2.0")

    # Réseaux alimentés par un connecteur ou à travers un composant passif : le contrôle
    # électrique a besoin de le savoir.
    for i, net in enumerate(("VBUS", "V3IN", "VBIN", "DW_VCC", "BATN", "GND")):
        s.flag(net, (12 + 10 * i) * G, 208 * G)
    return s


if __name__ == "__main__":
    build().write("v0", project_libs=[("luciole", "../lib/luciole.kicad_sym", "../lib/luciole.pretty")])
    print("écrit v0/v0.kicad_sch")
