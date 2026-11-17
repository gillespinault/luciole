"""Compare la liste de connexions voulue à celle que KiCad exporte du schéma.

    python3 tools/netcheck.py essai/netlist_voulue.txt essai/out/essai.net

Code de sortie 0 si les deux listes sont identiques broche par broche, 1 sinon.
"""
import sys

from netlist import logical, read_netlist


def read_wanted(path):
    nets, nc = {}, set()
    name = None
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            text = raw.split("#", 1)[0]
            line = text.split()
            if not line:
                continue
            # Une ligne qui commence par un espace continue le réseau de la ligne précédente.
            if text[0] in " \t":
                if name is None:
                    sys.exit(f"{path}:{n} : ligne de suite sans réseau au-dessus")
                tokens = line
            else:
                name, tokens = line[0], line[1:]
                if name != "NC" and name in nets:
                    sys.exit(f"{path}:{n} : réseau {name} défini deux fois")
                if name != "NC":
                    nets[name] = set()
            for tok in tokens:
                ref, _, pin = tok.partition(".")
                if not pin:
                    sys.exit(f"{path}:{n} : « {tok} » n'est pas de la forme REPÈRE.BROCHE")
                target = nc if name == "NC" else nets[name]
                if (ref, pin) in target:
                    sys.exit(f"{path}:{n} : {tok} figure deux fois dans {name}")
                target.add((ref, pin))
    return nets, nc


def fmt(nodes):
    return " ".join(f"{r}.{p}" for r, p in sorted(nodes))


def main(wanted_path, kicad_path):
    want, want_nc = read_wanted(wanted_path)
    got, got_nc = logical(read_netlist(kicad_path)[0])
    errors = []

    all_want = set().union(*want.values()) if want else set()
    for a, b in ((x, y) for i, x in enumerate(want) for y in list(want)[i + 1:]):
        dup = want[a] & want[b]
        if dup:
            errors.append(f"liste voulue : {fmt(dup)} figure dans {a} et dans {b}")
    if all_want & want_nc:
        errors.append(f"liste voulue : {fmt(all_want & want_nc)} à la fois reliée et NC")

    by_nodes = {frozenset(v): k for k, v in got.items()}
    for name, nodes in want.items():
        if frozenset(nodes) in by_nodes:
            other = by_nodes[frozenset(nodes)]
            if other != name:
                errors.append(f"réseau {name} : mêmes broches, mais KiCad le nomme {other}")
            continue
        if name in got:
            miss, extra = nodes - got[name], got[name] - nodes
            if miss:
                errors.append(f"réseau {name} : broches absentes du schéma : {fmt(miss)}")
            if extra:
                errors.append(f"réseau {name} : broches en trop dans le schéma : {fmt(extra)}")
        else:
            errors.append(f"réseau {name} : absent du schéma (voulu : {fmt(nodes)})")
    for name, nodes in got.items():
        if name not in want and frozenset(nodes) not in {frozenset(v) for v in want.values()}:
            errors.append(f"réseau {name} : présent dans le schéma, absent de la liste voulue ({fmt(nodes)})")
    if want_nc != got_nc:
        if want_nc - got_nc:
            errors.append(f"broches voulues libres mais reliées : {fmt(want_nc - got_nc)}")
        if got_nc - want_nc:
            errors.append(f"broches libres dans le schéma, non prévues : {fmt(got_nc - want_nc)}")

    npins = sum(len(v) for v in want.values())
    if errors:
        print(f"ÉCART entre {wanted_path} et {kicad_path} :")
        for e in errors:
            print("  -", e)
        return 1
    print(f"Connexions conformes : {len(want)} réseaux, {npins} broches reliées, {len(want_nc)} broches libres.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
