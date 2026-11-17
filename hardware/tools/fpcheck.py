"""Compare la géométrie voulue des empreintes à celle des fichiers d'empreintes.

    python3 tools/fpcheck.py <projet>/empreintes_voulues.txt <netlist KiCad> [surnom=dossier.pretty ...]

Le fichier des empreintes voulues s'écrit à la main, d'après les plans des
fabricants, comme la liste de connexions voulue : il dit où est chaque pastille
et quel numéro elle porte, sans passer par le code qui dessine l'empreinte.
Sans lui, une empreinte mal numérotée passe tous les contrôles dès que la
carte est routée par réseau (constat 9 de la revue du 17 novembre 2026).

Format : une section par empreinte utilisée par la carte.

    [bibliothèque:empreinte]
    numéro  x  y  largeur  hauteur        une ligne par pastille
    trou    x  y  diamètre                un perçage sans cuivre (ergot de centrage)

    [bibliothèque:empreinte] normalisé    boîtier normalisé, pris tel quel dans KiCad

    [bibliothèque:empreinte] plages       les lignes sont les plages du boîtier (pattes,
                                          bornes), pas des pastilles : chaque plage doit
                                          tomber dans la pastille de même numéro

Cotes en millimètres dans le repère de l'empreinte non tournée, vue de dessus,
X vers la droite, Y vers le bas. Largeur selon X, hauteur selon Y.

Toute empreinte utilisée par la carte doit avoir sa section, et toute section
doit servir. Code de sortie 0 si tout concorde à 0,01 mm près (0,03 mm pour les
plages d'un boîtier), 1 sinon.
"""
import os
import sys

import sexp
from netlist import read_netlist

TOL = 0.01
TOL_PLAGE = 0.03               # une plage de boîtier peut dépasser sa pastille de cette marge
STOCK = "/usr/share/kicad/footprints"


def read_wanted(path):
    """Rend ({empreinte: lignes, ou None si normalisé}, {empreinte: "plages"})."""
    wanted, modes, cur = {}, {}, None
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("["):
                name, _, rest = line[1:].partition("]")
                if name in wanted:
                    sys.exit(f"{path}:{n} : empreinte {name} décrite deux fois")
                rest = rest.strip()
                if rest not in ("", "normalisé", "plages"):
                    sys.exit(f"{path}:{n} : après le nom, seuls « normalisé » et « plages » sont admis")
                cur = wanted[name] = None if rest == "normalisé" else []
                if rest == "plages":
                    modes[name] = "plages"
                continue
            if cur is None:
                sys.exit(f"{path}:{n} : cote hors d'une section, ou dans une section « normalisé »")
            tok = line.split()
            try:
                if tok[0] == "trou":
                    if len(tok) != 4:
                        raise ValueError
                    cur.append(("trou", float(tok[1]), float(tok[2]), float(tok[3]), float(tok[3])))
                else:
                    if len(tok) != 5:
                        raise ValueError
                    cur.append((tok[0],) + tuple(float(t) for t in tok[1:]))
            except ValueError:
                sys.exit(f"{path}:{n} : attendu « numéro x y largeur hauteur » ou « trou x y diamètre »")
    return wanted, modes


def read_footprint(path):
    """Pastilles du fichier .kicad_mod : [(numéro ou « trou », x, y, largeur, hauteur)].
    Les ouvertures de pâte sans numéro ne sont pas des pastilles et sont ignorées."""
    out = []
    for pad in sexp.find_all(sexp.load(path), "pad"):
        number, kind = str(pad[1]), str(pad[2])
        at, size = sexp.find(pad, "at"), sexp.find(pad, "size")
        x, y = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0.0
        w, h = float(size[1]), float(size[2])
        if round(rot) % 180 == 90:
            w, h = h, w
        elif round(rot) % 180 != 0:
            sys.exit(f"{path} : pastille {number} tournée de {rot}°, cas non géré")
        if kind == "np_thru_hole":
            drill = sexp.find(pad, "drill")
            d = float(drill[1]) if not isinstance(drill[1], str) or drill[1] != "oval" else float(drill[2])
            out.append(("trou", x, y, d, d))
        elif number:
            out.append((number, x, y, w, h))
    return out


def fmt(p):
    return f"{p[0]} en ({p[1]:g}, {p[2]:g}), {p[3]:g} × {p[4]:g}"


def compare(name, want, got):
    errors, left = [], list(got)
    for w in want:
        same = [g for g in left if g[0] == w[0]]
        hit = next((g for g in same if all(abs(a - b) <= TOL for a, b in zip(w[1:], g[1:]))), None)
        if hit is not None:
            left.remove(hit)
            continue
        here = next((g for g in left if all(abs(a - b) <= TOL for a, b in zip(w[1:3], g[1:3]))), None)
        if here is not None:
            left.remove(here)
            what = "porte le numéro" if here[0] != w[0] else "mesure"
            errors.append(f"{name} : voulu {fmt(w)} ; l'empreinte a {fmt(here)} ({what} autre chose)")
        else:
            errors.append(f"{name} : voulu {fmt(w)} ; rien à cet endroit dans l'empreinte")
    errors += [f"{name} : l'empreinte a {fmt(g)}, absent de la géométrie voulue" for g in left]
    return errors


def compare_lands(name, lands, got):
    """Mode « plages » : chaque plage du boîtier doit tomber dans une pastille de même
    numéro, et chaque pastille doit recevoir au moins une plage."""
    def inside(land, pad):
        return all(abs(land[1 + k] - pad[1 + k]) + land[3 + k] / 2 <= pad[3 + k] / 2 + TOL_PLAGE for k in (0, 1))
    errors, served = [], set()
    for land in lands:
        hits = [i for i, pad in enumerate(got) if pad[0] == land[0] and inside(land, pad)]
        if hits:
            served.add(hits[0])
            continue
        here = next((pad for pad in got if inside(land, pad)), None)
        if here is not None:
            errors.append(f"{name} : la plage {fmt(land)} tombe dans la pastille {here[0]}, pas {land[0]}")
        else:
            errors.append(f"{name} : la plage {fmt(land)} ne tombe dans aucune pastille {land[0]}")
    errors += [f"{name} : la pastille {fmt(pad)} ne reçoit aucune plage du boîtier"
               for i, pad in enumerate(got) if i not in served]
    return errors


def main(wanted_path, netlist_path, *libs):
    fp_libs = dict(a.split("=", 1) for a in libs)
    wanted, modes = read_wanted(wanted_path)
    _, comps = read_netlist(netlist_path)
    used = {}
    for ref, c in comps.items():
        used.setdefault(c["footprint"], []).append(ref)

    errors, checked, trusted = [], 0, 0
    for name in sorted(used):
        if name not in wanted:
            errors.append(f"{name} ({', '.join(sorted(used[name]))}) : pas de section dans {wanted_path}")
            continue
        if wanted[name] is None:
            trusted += 1
            continue
        lib, _, fp = name.partition(":")
        path = os.path.join(fp_libs.get(lib, os.path.join(STOCK, lib + ".pretty")), fp + ".kicad_mod")
        if not os.path.exists(path):
            errors.append(f"{name} : fichier d'empreinte introuvable ({path})")
            continue
        if modes.get(name) == "plages":
            errors += compare_lands(name, wanted[name], read_footprint(path))
        else:
            errors += compare(name, wanted[name], read_footprint(path))
        checked += 1
    for name in sorted(set(wanted) - set(used)):
        errors.append(f"{name} : décrite dans {wanted_path}, mais aucun composant ne l'utilise")

    if errors:
        print(f"ÉCART entre {wanted_path} et les empreintes :")
        for e in errors:
            print("  -", e)
        return 1
    print(f"Empreintes conformes : {checked} comparées pastille par pastille, {trusted} boîtiers normalisés.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
