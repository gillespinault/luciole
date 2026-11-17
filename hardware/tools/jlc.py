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

from netlist import read_netlist

# Correction de rotation, en degrés, ajoutée à l'angle KiCad pour obtenir celui de JLCPCB.
# JLCPCB oriente une pièce d'après sa position dans la bande, KiCad d'après le dessin de
# l'empreinte : les deux ne coïncident pas toujours. Une entrée n'entre dans cette table
# qu'après contrôle dans l'aperçu de pose de JLCPCB, avec la date du contrôle.
#
# Les contrôles ci-dessous valent pour une pose sur la face du dessus. JLCPCB traite
# autrement les angles de la face du dessous : à recontrôler le jour où une de ces
# pièces passe au dos.
ROTATION = [
    # (motif sur le nom d'empreinte, correction, justification)
    (r"^[CR]_0402_1005Metric$", 0, "boîtier à deux bornes, convention commune"),
    (r"^[CR]_0603_1608Metric$", 0, "boîtier à deux bornes, convention commune"),
    (r"^LED_OPSCO_SK6812MINI-B-012_3\.7x3\.5mm$", 0,
     "aperçu JLCPCB du 17 novembre 2026, carte d'essai : repère de broche 1 sur DIN, marque VDD sur la pastille VDD"),
    (r"^Grove_HY2\.0-4P_Megastar_ZX-HY2\.0-4PWT_Horizontal$", 0,
     "aperçu JLCPCB du 17 novembre 2026, carte d'essai : ouverture du bon côté, queues sur les pastilles ; "
     "leur modèle 3D place les pattes de fixation à l'arrière, leur empreinte les place à l'avant comme la nôtre"),
]


def rotation_for(footprint):
    for pattern, delta, _why in ROTATION:
        if re.search(pattern, footprint):
            return delta
    return None


def write_bom(comps, path):
    groups = {}
    for ref, c in comps.items():
        key = (c["fields"].get("LCSC", ""), c["value"], c["footprint"].split(":")[-1])
        groups.setdefault(key, []).append(ref)
    missing = []

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
    return groups, missing


def write_cpl(pos_csv, path):
    rows, unverified = [], {}
    with open(pos_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            delta = rotation_for(r["Package"])
            if delta is None:
                unverified.setdefault(r["Package"], []).append(r["Ref"])
                delta = 0
            rot = (float(r["Rot"]) + delta) % 360
            rows.append([r["Ref"], f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm",
                         "Top" if r["Side"].lower() in ("top", "front") else "Bottom", f"{rot:g}"])
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
    _, comps = read_netlist(netlist)
    groups, missing = write_bom(comps, os.path.join(out_dir, f"{name}-bom.csv"))
    rows, unverified = write_cpl(pos_csv, os.path.join(out_dir, f"{name}-cpl.csv"))
    files = write_zip(gerber_dir, os.path.join(out_dir, f"{name}-gerbers.zip"))

    placed = {r[0] for r in rows}
    lines = [f"Fichiers JLCPCB pour « {name} »", "",
             f"Nomenclature : {len(groups)} lignes, {len(comps)} composants.",
             f"Pose : {len(rows)} composants ({sum(r[3] == 'Top' for r in rows)} dessus, "
             f"{sum(r[3] == 'Bottom' for r in rows)} dessous).",
             f"Gerber et perçages : {len(files)} fichiers ({', '.join(files)}).", ""]
    problems = 0
    if missing:
        problems += 1
        lines.append(f"MANQUE : pas de référence LCSC pour {', '.join(missing)}.")
    if set(comps) - placed:
        problems += 1
        lines.append(f"MANQUE : dans la nomenclature mais pas dans la pose : {', '.join(sorted(set(comps) - placed))}.")
    if placed - set(comps):
        problems += 1
        lines.append(f"MANQUE : dans la pose mais pas dans la nomenclature : {', '.join(sorted(placed - set(comps)))}.")
    if unverified:
        lines.append("À CONTRÔLER dans l'aperçu de pose de JLCPCB (orientation et centrage jamais vérifiés) :")
        for fp, refs in sorted(unverified.items()):
            lines.append(f"  - {fp} : {', '.join(refs)}")
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
