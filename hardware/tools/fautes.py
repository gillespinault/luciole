#!/usr/bin/env python3
"""Banc de fautes injectées : vérifie que la construction s'arrête quand elle le doit.

    python3 tools/fautes.py            toutes les fautes
    python3 tools/fautes.py nom ...    seulement celles-là

Pour chaque faute, le dossier hardware/ est copié dans un dossier temporaire,
une modification précise y est appliquée, puis `tools/build.sh essai` est
lancé. Le banc compare l'étape où la construction s'arrête à l'étape attendue.

Une faute marquée « non détectée » est une lacune connue de la chaîne : elle
est listée pour qu'on ne l'oublie pas, et le banc signale le jour où elle se
met à être détectée.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OK = "aucune"                   # la construction va au bout

# (nom, description, [(fichier, texte à remplacer, texte de remplacement)], étape attendue)
FAUTES = [
    ("temoin", "aucune modification : la construction doit réussir", [], OK),

    ("broche_oubliee", "une broche du schéma n'est reliée à rien et n'est pas marquée NC",
     [("essai/circuit.py", '"2": "DIN", "3": "VLED", "4": "GND", "MP": "GND"', '"2": "DIN", "3": "VLED", "4": "GND"')],
     "Schéma"),

    # Les noms sont incohérents : KiCad 10 le voit lui-même (broche GND hors d'une masse).
    ("alimentation_inversee", "VDD et GND échangés sur les LED dans le schéma",
     [("essai/circuit.py", '"VDD": "VLED", "GND": "GND"', '"VDD": "GND", "GND": "VLED"')],
     "Contrôle électrique"),

    # Les noms sont justes, les numéros faux : c'est le cas du symbole SK6812MINI de KiCad
    # employé pour une LED au brochage différent. Le contrôle électrique ne voit rien,
    # seule la liste de connexions écrite à la main l'arrête.
    ("symbole_mal_numerote", "le symbole de la LED porte VDD en 4 et GND en 2 au lieu de 2 et 4",
     [("lib/build_lib.py", 'top=[("2", "VDD", "power_in")], bottom=[("4", "GND", "power_in")]',
       'top=[("4", "VDD", "power_in")], bottom=[("2", "GND", "power_in")]')],
     "Connexions"),

    ("donnee_sur_mauvaise_broche", "la sortie de données part sur la broche 1 du Grove au lieu de la 2",
     [("essai/circuit.py", 'pins={"1": NC, "2": "DOUT",', 'pins={"1": "DOUT", "2": NC,')],
     "Connexions"),

    ("liste_voulue_differente", "la liste de connexions voulue ne dit plus la même chose que le schéma",
     [("essai/netlist_voulue.txt", "LED_D1  D1.3 D2.1", "LED_D1  D1.3 D3.1"),
      ("essai/netlist_voulue.txt", "LED_D2  D2.3 D3.1", "LED_D2  D2.3 D2.1")],
     "Connexions"),

    ("empreinte_sans_pastille", "l'empreinte du Grove perd une pastille",
     [("lib/build_lib.py", "for k in range(4):                                   # de gauche", "for k in range(3):                                   # de gauche")],
     "Carte"),

    ("grove_en_miroir", "la numérotation du Grove est inversée (l'erreur du 17 novembre)",
     [("lib/build_lib.py", "fp.pad(4 - k, -3.0 + 2.0 * k", "fp.pad(k + 1, -3.0 + 2.0 * k")],
     "Carte"),

    ("led_din_dout_echanges", "DIN et DOUT échangés dans l'empreinte de la LED",
     [("lib/build_lib.py", "pad(3, left, left + 1.5, top, top + 1.3)", "pad(1, left, left + 1.5, top, top + 1.3)"),
      ("lib/build_lib.py", "pad(1, right - 1.3, right, bottom - 0.9, bottom)", "pad(3, right - 1.3, right, bottom - 0.9, bottom)")],
     "Carte"),

    ("drapeau_alimentation_retire", "le réseau d'alimentation n'est plus déclaré comme alimenté",
     [("essai/circuit.py", '    s.flag("VLED", 12 * G, 58 * G)\n', "")],
     "Contrôle électrique"),

    # Trouvé par la revue du 17 novembre 2026 : un contrôle désactivé à la main dans KiCad
    # restait désactivé à chaque construction, parce que le fichier de projet n'était pas
    # régénéré. La construction doit maintenant repartir d'un fichier neuf et s'arrêter.
    ("controle_desactive", "une piste manque ET le contrôle des liaisons est désactivé dans le fichier de projet",
     [("essai/carte.py", 'b.track("DOUT", [r2b, (r2b[0], j2d[1]), j2d], SIG)', "pass"),
      ("essai/essai.kicad_pro", '"unconnected_items": "error"', '"unconnected_items": "ignore"')],
     "Contrôle des règles de dessin"),

    ("piste_retiree", "une piste manque : la sortie de données n'atteint plus le connecteur",
     [("essai/carte.py", 'b.track("DOUT", [r2b, (r2b[0], j2d[1]), j2d], SIG)', "pass")],
     "Contrôle des règles de dessin"),

    ("court_circuit", "une piste d'alimentation traverse une liaison de données",
     [("essai/carte.py", 'b.zone("GND", "F.Cu"', 'b.track("VLED", [(20.0, 6.0), (20.0, 16.5)], PWR)\nb.zone("GND", "F.Cu"')],
     "Contrôle des règles de dessin"),

    ("trop_pres_du_bord", "un connecteur dépasse du bord de la carte",
     [("essai/carte.py", "JX = 5.85 ", "JX = 5.30 ")],
     "Contrôle des règles de dessin"),

    ("composants_trop_proches", "un condensateur chevauche une LED",
     [("essai/carte.py", 'x - 0.6, YC + 2.6)', 'x - 0.6, YC + 1.9)')],
     "Contrôle des règles de dessin"),

    ("sans_reference_lcsc", "un composant n'a pas de référence LCSC",
     [("essai/circuit.py", 'value="470R", lcsc="C25117"', 'value="470R", lcsc=""')],
     "Fichiers de fabrication"),

    # Arrêt obtenu par chance, pas par construction. La numérotation d'une empreinte n'est
    # comparée à aucune référence extérieure. Ici la faute est vue parce que le routage de
    # la carte d'essai est écrit en coordonnées : les pistes tombent sur les mauvaises
    # pastilles. Sur une carte routée par réseau (routeur automatique), elle passerait.
    ("led_vdd_gnd_echanges", "VDD et GND échangés dans l'empreinte de la LED",
     [("lib/build_lib.py", "pad(2, right - 2.2, right, top, top + 1.2)", "pad(4, right - 2.2, right, top, top + 1.2)"),
      ("lib/build_lib.py", "pad(4, left, left + 2.4, bottom - 0.8, bottom)", "pad(2, left, left + 2.4, bottom - 0.8, bottom)")],
     "Contrôle des règles de dessin"),
]


def run(nom, edits):
    """Applique la faute à une copie et rend (étape d'arrêt, fin de la sortie)."""
    tmp = tempfile.mkdtemp(prefix=f"luciole-faute-{nom}-")
    work = os.path.join(tmp, "hardware")
    try:
        shutil.copytree(HW, work, ignore=shutil.ignore_patterns("out", "__pycache__", "*.kicad_prl"))
        for rel, old, new in edits:
            path = os.path.join(work, rel)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if text.count(old) != 1:
                return "FAUTE INAPPLICABLE", f"« {old} » trouvé {text.count(old)} fois dans {rel}"
            with open(path, "w", encoding="utf-8") as f:
                f.write(text.replace(old, new))
        p = subprocess.run([os.path.join(work, "tools", "build.sh"), "essai"],
                           capture_output=True, text=True, timeout=600)
        out = p.stdout + p.stderr
        steps = [line[3:].strip() for line in out.splitlines() if line.startswith("== ")]
        if p.returncode == 0:
            return OK, ""
        last = steps[-1] if steps else "avant la première étape"
        tail = "\n".join(line for line in out.splitlines()[-12:] if line.strip())
        return last, tail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(names):
    wanted = [f for f in FAUTES if not names or f[0] in names]
    bad = 0
    for nom, descr, edits, attendu in wanted:
        etape, detail = run(nom, edits)
        conforme = etape.startswith(attendu) if attendu != OK else etape == OK
        if attendu == OK and nom != "temoin":
            verdict = "LACUNE CONFIRMÉE" if conforme else "LACUNE COMBLÉE ? À RECLASSER"
        else:
            verdict = "conforme" if conforme else "ÉCART"
        bad += 0 if conforme else 1
        print(f"{verdict:<18} {nom:<28} arrêt : {etape:<48} attendu : {attendu}")
        print(f"{'':<18} {descr}")
        if not conforme or (attendu != OK and "-v" in sys.argv):
            for line in detail.splitlines():
                print(f"{'':<20}| {line}")
        sys.stdout.flush()
    print(f"\n{len(wanted)} fautes essayées, {bad} écart(s).")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main([a for a in sys.argv[1:] if not a.startswith("-")]))
