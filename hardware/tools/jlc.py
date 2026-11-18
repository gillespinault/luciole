"""Prépare les fichiers d'assemblage au format JLCPCB.

    python3 tools/jlc.py <netlist KiCad> <fichier de pose KiCad .csv> <dossier des Gerber> <dossier de sortie> <nom>

Écrit dans le dossier de sortie :
    <nom>-bom.csv       nomenclature : Comment, Designator, Footprint, LCSC Part #
    <nom>-cpl.csv       pose : Designator, Mid X, Mid Y, Layer, Rotation
    <nom>-gerbers.zip   Gerber et perçages, archive reproductible
    <nom>-jlc.txt       compte rendu : ce qui reste à contrôler dans l'aperçu de JLCPCB
"""
import csv
import os
import re
import sys
import zipfile

from netlist import assembled, read_netlist

# Correction de rotation, en degrés, ajoutée à l'angle KiCad pour obtenir celui de JLCPCB.
# JLCPCB oriente une pièce d'après sa position dans la bande, KiCad d'après le dessin de
# l'empreinte : les deux ne coïncident pas toujours. Une entrée n'entre dans cette table
# qu'après contrôle dans l'aperçu de pose de JLCPCB, avec la date du contrôle.
#
# Les contrôles de cette table valent pour une pose sur la face du dessus, et pour elle
# seule. Une pièce posée au dos a sa propre table, ROTATION_DOS, plus bas.
#
# La correction dépend de la pièce commandée, pas seulement du boîtier : JLCPCB dessine une
# empreinte par référence, et deux pièces de même boîtier n'y sont pas tournées pareil.
# Le 18 novembre 2026, sur la carte v0, deux SOT-23-5 demandaient l'un un demi-tour, l'autre
# un quart de tour. Une entrée porte donc un motif sur l'empreinte et un motif sur la valeur.
V0 = "aperçu JLCPCB du 18 novembre 2026, carte v0 : "
ROTATION = [
    # (motif sur le nom d'empreinte, motif sur la valeur, correction, justification)
    (r"^[CR]_0402_1005Metric$", r"", 0, "boîtier à deux bornes, convention commune"),
    (r"^[CR]_0603_1608Metric$", r"", 0, "boîtier à deux bornes, convention commune"),
    (r"^C_0805_2012Metric$", r"", 0, "boîtier à deux bornes, convention commune"),
    (r"^Fuse_1206_3216Metric$", r"", 0, "boîtier à deux bornes sans polarité"),
    (r"^LED_OPSCO_SK6812MINI-B-012_3\.7x3\.5mm$", r"", 0,
     "aperçu JLCPCB du 17 novembre 2026, carte d'essai : repère de broche 1 sur DIN, marque VDD sur la pastille VDD"),
    (r"^Grove_HY2\.0-4P_Megastar_ZX-HY2\.0-4PWT_Horizontal$", r"", 0,
     "aperçu JLCPCB du 17 novembre 2026, carte d'essai : ouverture du bon côté, queues sur les pastilles ; "
     "leur modèle 3D place les pattes de fixation à l'arrière, leur empreinte les place à l'avant comme la nôtre"),
    (r"^D_SOD-123F$", r"^DSK24$", 0, V0 + "barre de la cathode sur la pastille 1 ; la pièce est un SOD-123FL, ses pattes tombent sur les pastilles"),
    (r"^D_SOD-323$", r"^1N4148WS$", 0, V0 + "barre de la cathode sur la pastille 1"),
    (r"^L_cjiang_FXL0420$", r"", 0, V0 + "bornes sur les pastilles, pièce sans polarité"),
    (r"^SW_SPST_TS-1088-xR020$", r"", 0, V0 + "bornes sur les pastilles, pièce symétrique"),
    (r"^SOT-23$", r"^(AO3400A|DMP1045U|BSS138)$", 180, V0 + "sans correction, les deux pattes étaient du côté de la pastille seule"),
    (r"^SOT-563$", r"^TPS61023DRL$", 180, V0 + "sans correction, le repère de broche 1 était à l'opposé de la pastille 1"),
    (r"^SOT-23-5$", r"^SN74LV1T34DBV$", 180, V0 + "sans correction, les trois pattes étaient du côté des deux pastilles"),
    (r"^SOT-23-5$", r"^SN74LV1T125DBV$", 270, V0 + "sans correction, la pièce était en travers des pastilles (pièce TECH PUBLIC)"),
    (r"^TSOT-23-5$", r"^RT9080-33GJ5$", 270, V0 + "sans correction, la pièce était en travers des pastilles"),
    (r"^SOT-23-6$", r"^USBLC6-2SC6$", 270, V0 + "sans correction, la pièce était en travers des pastilles"),
    (r"^SOIC-8-1EP_3\.9x4\.9mm_P1\.27mm_EP2\.41x3\.3mm$", r"^TP4056", 270, V0 + "sans correction, la pièce était en travers des pastilles"),
    (r"^LGA-12_2x2mm_P0\.5mm$", r"^LIS2DH12$", 270, V0 + "sans correction, le repère de broche 1 était un quart de tour avant la pastille 1"),
]


# Face du dessous. KiCad donne l'angle d'une pièce du dos vu de dessus, à travers la
# carte. Des outils tiers (kicad-jlcpcb-tools, JLCKicadTools) le transforment en
# 180° − angle pour JLCPCB. Cette convention n'a jamais été contrôlée ici : la chaîne
# l'applique, mais ne déclare vérifiée une pièce du dos que si elle figure dans cette
# table, après contrôle dans l'aperçu de pose de JLCPCB, face du dessous, avec la date.
# Une vérification faite sur le dessus ne vaut pas pour le dos (constat C3 de la revue
# du 17 novembre 2026).
ROTATION_DOS = [
    # (motif sur le nom d'empreinte, motif sur la valeur, correction, justification)
    (r"^[CR]_0402_1005Metric$", r"", 0, V0 + "pièces à deux bornes sur leurs pastilles, au dos"),
    (r"^[CR]_0603_1608Metric$", r"", 0, V0 + "pièces à deux bornes sur leurs pastilles, au dos"),
    (r"^ESP32-C6-MINI-1$", r"", 0, V0 + "antenne vers le bout de la carte, repère de broche 1 sur la pastille 1"),
    (r"^USB_C_Receptacle_HRO_TYPE-C-31-M-12$", r"", 0, V0 + "ouverture vers le bord de la carte, contacts sur les pastilles"),
    (r"^JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2\.00mm_Horizontal$", r"^A2001WR-S-2P$", 0,
     V0 + "ouverture vers la batterie, queues sur les pastilles ; leur modèle 3D place les pattes de fixation à l'arrière"),
    (r"^SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010$", r"", 0, V0 + "poussoir vers le bord de la carte"),
    (r"^D_SOD-523$", r"^PESD5Z5\.0$", 0, V0 + "cathode sur la pastille 1"),
    (r"^SOT-23$", r"^(DMP1045U|AO3401A|TLV803EA30DBZ)$", 180, V0 + "sans correction, les deux pattes étaient du côté de la pastille seule"),
    (r"^SOT-23-6$", r"^FS8205A$", 180, V0 + "sans correction, le repère de broche 1 était à l'opposé de la pastille 1"),
    (r"^SOT-23-6$", r"^(USBLC6-2SC6|DW01A)$", 270, V0 + "sans correction, la pièce était en travers des pastilles"),
]


def rotation_for(footprint, bottom=False, value=""):
    for pattern, valpat, delta, _why in (ROTATION_DOS if bottom else ROTATION):
        if re.search(pattern, footprint) and re.search(valpat, value):
            return delta
    return None


def write_bom(comps, path):
    """Rend (lignes, repères sans référence, références LCSC portées par deux lignes)."""
    groups = {}
    for ref, c in comps.items():
        if not assembled(c):
            continue
        key = (c["fields"].get("LCSC", ""), c["value"], c["footprint"].split(":")[-1])
        groups.setdefault(key, []).append(ref)
    missing = []
    # Une référence LCSC désigne une seule pièce. Deux lignes pour la même référence
    # veulent dire qu'une valeur ou une empreinte est fausse quelque part : JLCPCB
    # poserait la même pièce aux deux endroits (constat C4).
    by_lcsc = {}
    for (lcsc, value, fp), refs in groups.items():
        if lcsc:
            by_lcsc.setdefault(lcsc, []).append(f"{value} en {fp} ({', '.join(sorted(refs))})")
    clashes = {k: v for k, v in by_lcsc.items() if len(v) > 1}

    def order(ref):
        m = re.match(r"([A-Za-z#]+)(\d+)", ref)
        return (m.group(1), int(m.group(2))) if m else (ref, 0)

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (lcsc, value, fp), refs in sorted(groups.items(), key=lambda kv: order(sorted(kv[1], key=order)[0])):
            refs = sorted(refs, key=order)
            w.writerow([value, ",".join(refs), fp, lcsc])
            if not lcsc:
                missing += refs
    return groups, missing, clashes


def write_cpl(pos_csv, path):
    """Rend (lignes, {(empreinte, face): repères} dont l'orientation n'est pas vérifiée)."""
    rows, unverified = [], {}
    with open(pos_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bottom = r["Side"].lower() not in ("top", "front")
            delta = rotation_for(r["Package"], bottom, r.get("Val", ""))
            if delta is None:
                unverified.setdefault((r["Package"], "dos" if bottom else "dessus"), []).append(r["Ref"])
                delta = 0
            rot = float(r["Rot"])
            if bottom:
                rot = 180 - rot
            rot = (rot + delta) % 360
            rows.append([r["Ref"], f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm",
                         "Bottom" if bottom else "Top", f"{rot:g}"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(rows)
    return rows, unverified


def write_zip(gerber_dir, path):
    """Archive à dates fixes : deux générations identiques donnent le même fichier."""
    names = sorted(n for n in os.listdir(gerber_dir) if not n.endswith(".gbrjob"))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            info = zipfile.ZipInfo(n, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(gerber_dir, n), "rb") as f:
                z.writestr(info, f.read())
    return names


def main(netlist, pos_csv, gerber_dir, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    _, everything = read_netlist(netlist)
    comps = {ref: c for ref, c in everything.items() if assembled(c)}
    bare = sorted(set(everything) - set(comps))
    groups, missing, clashes = write_bom(everything, os.path.join(out_dir, f"{name}-bom.csv"))
    rows, unverified = write_cpl(pos_csv, os.path.join(out_dir, f"{name}-cpl.csv"))
    files = write_zip(gerber_dir, os.path.join(out_dir, f"{name}-gerbers.zip"))

    placed = {r[0] for r in rows}
    lines = [f"Fichiers JLCPCB pour « {name} »", "",
             f"Nomenclature : {len(groups)} lignes, {len(comps)} composants."
             + (f" Sans pièce à poser : {', '.join(bare)}." if bare else ""),
             f"Pose : {len(rows)} composants ({sum(r[3] == 'Top' for r in rows)} dessus, "
             f"{sum(r[3] == 'Bottom' for r in rows)} dessous).",
             f"Gerber et perçages : {len(files)} fichiers ({', '.join(files)}).", ""]
    problems = 0
    if missing:
        problems += 1
        lines.append(f"MANQUE : pas de référence LCSC pour {', '.join(missing)}.")
    for lcsc, uses in sorted(clashes.items()):
        problems += 1
        lines.append(f"CONFLIT : la référence {lcsc} sert à deux pièces différentes : {' ; '.join(uses)}.")
    if set(comps) - placed:
        problems += 1
        lines.append(f"MANQUE : dans la nomenclature mais pas dans la pose : {', '.join(sorted(set(comps) - placed))}.")
    if placed - set(comps):
        problems += 1
        lines.append(f"MANQUE : dans la pose mais pas dans la nomenclature : {', '.join(sorted(placed - set(comps)))}.")
    if unverified:
        lines.append("À CONTRÔLER dans l'aperçu de pose de JLCPCB (orientation et centrage jamais vérifiés) :")
        for (fp, side), refs in sorted(unverified.items()):
            lines.append(f"  - {fp}, {side} : {', '.join(refs)}")
        if any(side == "dos" for _fp, side in unverified):
            lines.append("Au dos, l'angle est transformé en 180° − angle KiCad. Cette convention vient d'outils "
                         "tiers et n'a pas été contrôlée chez JLCPCB.")
    else:
        lines.append("Toutes les orientations viennent de la table des corrections vérifiées.")
    report = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, f"{name}-jlc.txt"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report, end="")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
