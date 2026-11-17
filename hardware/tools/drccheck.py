"""Lit le rapport du contrôle des règles de dessin et applique les dérogations du projet.

    python3 tools/drccheck.py <rapport.json> [<projet>/derogations.txt]

Le rapport vient de `kicad-cli pcb drc --format json --severity-all`. Toute alerte,
erreur ou simple avertissement, arrête la construction, sauf si une dérogation écrite
la couvre. Le compte rendu sépare ce qui est ignoré, avec sa raison, de ce qui reste.

Une dérogation par ligne, quatre champs séparés par « | » :

    type de l'alerte | texte du premier élément | texte du second élément | raison

Les deux textes sont cherchés dans la description que KiCad donne des éléments en
cause (« NPTH pad of J1 », « Footprint J3 »...). Un champ vide accepte tout. La raison
est obligatoire. Une dérogation qui ne sert à rien est une erreur : elle date d'un
dessin qui a changé.

Les liaisons manquantes et les écarts entre carte et schéma n'ont pas de dérogation.
Code de sortie 0 si rien ne reste, 1 sinon.
"""
import json
import os
import sys


def read_waivers(path):
    out = []
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 4 or not parts[0] or not parts[3]:
                sys.exit(f"{path}:{n} : attendu « type | élément | élément | raison », raison obligatoire")
            out.append(dict(type=parts[0], a=parts[1], b=parts[2], why=parts[3], line=n, hits=0))
    return out


def covers(w, v):
    if w["type"] != v.get("type"):
        return False
    texts = [it.get("description", "") for it in v.get("items", [])]
    for needle in (w["a"], w["b"]):
        if needle and not any(needle in t for t in texts):
            return False
    return True


def describe(v):
    items = " ; ".join(it.get("description", "?") for it in v.get("items", []))
    return f"[{v.get('type')}] {v.get('description', '')} : {items}"


def main(report_path, waiver_path=None):
    with open(report_path, encoding="utf-8") as f:
        rep = json.load(f)
    waivers = read_waivers(waiver_path)
    left, waived = [], []
    for v in rep.get("violations", []):
        w = next((w for w in waivers if covers(w, v)), None)
        if w is None:
            left.append(v)
        else:
            w["hits"] += 1
            waived.append((v, w))
    unconnected = rep.get("unconnected_items", [])
    parity = rep.get("schematic_parity", [])
    stale = [w for w in waivers if not w["hits"]]

    print(f"Alertes : {len(rep.get('violations', []))}, dont {len(waived)} ignorées par dérogation. "
          f"Liaisons manquantes : {len(unconnected)}. Écarts avec le schéma : {len(parity)}.")
    for w in waivers:
        if w["hits"]:
            print(f"  ignoré ({w['hits']}) : {w['type']}, {w['a'] or '*'} / {w['b'] or '*'}. Raison : {w['why']}")
    for v in left:
        print("  RESTE :", describe(v))
    for v in unconnected:
        print("  LIAISON MANQUANTE :", " ; ".join(it.get("description", "?") for it in v.get("items", [])))
    for v in parity:
        print("  ÉCART AVEC LE SCHÉMA :", describe(v))
    for w in stale:
        print(f"  DÉROGATION SANS OBJET, ligne {w['line']} : {w['type']}, {w['a'] or '*'} / {w['b'] or '*'}")
    return 1 if (left or unconnected or parity or stale) else 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
