"""Lecture de la liste de connexions (netlist) que KiCad exporte d'un schéma."""
import sexp

FLAGS = ("exclude_from_bom", "exclude_from_pos_files", "dnp")


def read_netlist(path):
    """Rend ({réseau: [(ref, broche)]}, {ref: {value, footprint, uuid, fields, flags}}).

    Les noms de réseaux sont ceux de KiCad, tels quels : « /DIN » pour une étiquette
    locale, « GND » pour un symbole d'alimentation, « unconnected-(...) » pour une
    broche laissée libre.
    """
    root = sexp.load(path)
    nets = {}
    for net in sexp.find_all(sexp.find(root, "nets"), "net"):
        name = str(sexp.find(net, "name")[1])
        nets[name] = [(str(sexp.find(nd, "ref")[1]), str(sexp.find(nd, "pin")[1]))
                      for nd in sexp.find_all(net, "node")]
    comps = {}
    for c in sexp.find_all(sexp.find(root, "components"), "comp"):
        ref = str(sexp.find(c, "ref")[1])
        fields = {}
        node = sexp.find(c, "fields")
        for fld in (sexp.find_all(node, "field") if node else []):
            fields[str(sexp.find(fld, "name")[1])] = str(fld[-1]) if not isinstance(fld[-1], list) else ""
        fp = sexp.find(c, "footprint")
        tst = sexp.find(c, "tstamps")
        # KiCad signale par une propriété sans valeur un composant hors nomenclature,
        # hors fichier de pose, ou non monté.
        flags = {str(sexp.find(pr, "name")[1]) for pr in sexp.find_all(c, "property")} & set(FLAGS)
        comps[ref] = dict(value=str(sexp.find(c, "value")[1]), footprint=str(fp[1]) if fp else "",
                          uuid=str(tst[1]) if tst else "", fields=fields, flags=flags)
    return nets, comps


def assembled(comp):
    """Vrai si une pièce doit être posée sur cette empreinte."""
    return not comp["flags"] & {"exclude_from_bom", "dnp"}


def logical(nets):
    """Sépare les réseaux nommés des broches libres, et retire le « / » des étiquettes locales."""
    named, free = {}, set()
    for name, nodes in nets.items():
        if name.startswith("unconnected-"):
            free |= set(nodes)
        else:
            named[name.lstrip("/")] = set(nodes)
    return named, free
