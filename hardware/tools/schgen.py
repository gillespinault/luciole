"""Écrit un schéma KiCad à partir d'une description de circuit.

Chaque composant est posé à un endroit choisi. Chaque broche reçoit un court
fil, terminé par une étiquette de réseau ou par un symbole d'alimentation.
Deux broches sont reliées quand elles portent le même nom de réseau : le
schéma se lit bloc par bloc, sans fil à suivre d'un bout à l'autre de la page.

Une broche oubliée arrête la génération : toute broche doit être reliée à un
réseau ou marquée NC, volontairement.
"""
import copy
import json
import os

import sexp
from libgen import uid
from sexp import Q

SCH_VERSION = "20260306"
STUB = 2.54                    # longueur du fil posé sur chaque broche
NC = object()                  # broche laissée libre, volontairement

# Sens du fil selon l'angle de la broche dans le symbole (repère de la page, Y vers le bas).
OUTWARD = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}
# Angle et calage de l'étiquette pour que le texte parte du fil vers l'extérieur.
LABEL = {(-1, 0): (180, "right bottom"), (1, 0): (0, "left bottom"),
         (0, -1): (90, "left bottom"), (0, 1): (270, "right bottom")}


def _font(size=1.27):
    return ["font", ["size", size, size]]


def _f(x):
    return round(float(x), 4)


class Pin:
    def __init__(self, tree):
        self.etype = tree[1]
        at = sexp.find(tree, "at")
        self.x, self.y, self.angle = _f(at[1]), _f(at[2]), int(float(at[3]))
        self.name = str(sexp.find(tree, "name")[1])
        self.number = str(sexp.find(tree, "number")[1])


class Schematic:
    def __init__(self, project, title, rev, date, libs, power=(), paper="A4", company="Luciole²"):
        """libs : {surnom: chemin du .kicad_sym}. power : réseaux portés par un symbole
        d'alimentation de la bibliothèque `power` (GND, +3V3...), les autres par étiquette."""
        self.project = project
        self.title, self.rev, self.date, self.company, self.paper = title, rev, date, company, paper
        self.libs = dict(libs)
        self.power = set(power)
        self.root_uuid = uid(project, "root")
        self._lib_trees = {}
        self._lib_symbols = {}      # lib_id -> arbre aplati, tel qu'il sera recopié dans le schéma
        self._pins = {}             # lib_id -> [Pin]
        self.items = []
        self.refs = set()
        self.nets = {}              # réseau -> [(ref, numéro de broche)]
        self._npwr = 0
        self._seen_stub = set()

    # ------------------------------------------------------ bibliothèques

    def _symbol(self, lib_id):
        if lib_id in self._lib_symbols:
            return self._lib_symbols[lib_id]
        nick, name = lib_id.split(":", 1)
        if nick not in self._lib_trees:
            if nick not in self.libs:
                raise KeyError(f"bibliothèque de symboles inconnue : {nick}")
            self._lib_trees[nick] = sexp.load(self.libs[nick])
        tree = self._flatten(self._lib_trees[nick], name)
        tree[1] = Q(lib_id)
        self._lib_symbols[lib_id] = tree
        pins = []
        for unit in sexp.find_all(tree, "symbol"):
            u, style = str(unit[1]).rsplit("_", 2)[1:]
            if u in ("0", "1") and style in ("0", "1"):
                pins += [Pin(p) for p in sexp.find_all(unit, "pin")]
        self._pins[lib_id] = pins
        return tree

    @staticmethod
    def _flatten(lib, name):
        """Rend une copie du symbole, héritage (`extends`) résolu."""
        sym = next((s for s in sexp.find_all(lib, "symbol") if s[1] == name), None)
        if sym is None:
            raise KeyError(f"symbole introuvable : {name}")
        sym = copy.deepcopy(sym)
        ext = sexp.find(sym, "extends")
        if ext is None:
            return sym
        parent = Schematic._flatten(lib, str(ext[1]))
        pname = str(parent[1])
        own = {str(p[1]): p for p in sexp.find_all(sym, "property")}
        out = []
        for c in parent:
            if isinstance(c, list) and c[0] == "property":
                out.append(own.pop(str(c[1]), c))
            elif isinstance(c, list) and c[0] == "symbol":
                c[1] = Q(name + str(c[1])[len(pname):])
                out.append(c)
            else:
                out.append(c)
        tail = [c for c in out if isinstance(c, list) and c[0] in ("symbol", "embedded_fonts")]
        body = [c for c in out if not (isinstance(c, list) and c[0] in ("symbol", "embedded_fonts"))]
        res = body + list(own.values()) + tail
        res[1] = Q(name)
        return res

    # ----------------------------------------------------------- éléments

    def note(self, text, x, y, size=2.0):
        """Texte libre, pour titrer un bloc."""
        self.items.append(["text", Q(text), ["exclude_from_sim", "no"], ["at", x, y, 0],
                           ["effects", _font(size), ["justify", "left", "bottom"]],
                           ["uuid", uid(self.project, "text", text, x, y)]])

    def part(self, ref, lib_id, x, y, pins, value=None, footprint=None, lcsc="", fields=None):
        """Pose un composant. pins : {nom ou numéro de broche: réseau, ou NC}."""
        if ref in self.refs:
            raise ValueError(f"repère en double : {ref}")
        self.refs.add(ref)
        lib = self._symbol(lib_id)
        libpins = self._pins[lib_id]

        assigned = {}                                   # numéro de broche -> réseau
        for key, net in pins.items():
            hits = [p for p in libpins if p.number == str(key)] or [p for p in libpins if p.name == str(key)]
            if not hits:
                raise KeyError(f"{ref} ({lib_id}) : pas de broche « {key} »")
            for p in hits:
                if p.number in assigned:
                    raise ValueError(f"{ref} : broche {p.number} affectée deux fois")
                assigned[p.number] = net
        missing = [f"{p.number} ({p.name})" for p in libpins if p.number not in assigned]
        if missing:
            raise ValueError(f"{ref} ({lib_id}) : broches sans réseau ni NC : {', '.join(missing)}")

        libprops = {str(p[1]): p for p in sexp.find_all(lib, "property")}
        values = {"Reference": ref,
                  "Value": value if value is not None else str(libprops["Value"][2]),
                  "Footprint": footprint if footprint is not None else str(libprops["Footprint"][2]),
                  "Datasheet": str(libprops.get("Datasheet", [0, 0, ""])[2]),
                  "Description": str(libprops.get("Description", [0, 0, ""])[2]),
                  "LCSC": lcsc or str(libprops.get("LCSC", [0, 0, ""])[2])}
        values.update(fields or {})
        self._instance(ref, lib_id, x, y, 0, values, [p.number for p in libpins])

        for p in libpins:
            net = assigned[p.number]
            tip = (_f(x + p.x), _f(y - p.y))
            if net is NC:
                self.items.append(["no_connect", ["at", tip[0], tip[1]],
                                   ["uuid", uid(self.project, "nc", ref, p.number)]])
                continue
            self.nets.setdefault(net, []).append((ref, p.number))
            self._stub(ref, p, tip, net)

    def flag(self, net, x, y):
        """Drapeau PWR_FLAG : dit au contrôle électrique qu'un réseau est bien alimenté
        (par un connecteur, par exemple)."""
        self._npwr += 1
        ref = f"#FLG{self._npwr:02d}"
        lib_id = "power:PWR_FLAG"
        self._symbol(lib_id)
        self._instance(ref, lib_id, x, y, 0, {"Reference": ref, "Value": "PWR_FLAG"}, ["1"], hide_ref=True)
        pin = self._pins[lib_id][0]
        pin_down = copy.copy(pin)
        pin_down.angle = 90                              # le fil part vers le bas, sous le drapeau
        self._stub(ref, pin_down, (_f(x), _f(y)), net)

    # ------------------------------------------------------------ détails

    def _stub(self, ref, pin, tip, net):
        dx, dy = OUTWARD[pin.angle]
        end = (_f(tip[0] + dx * STUB), _f(tip[1] + dy * STUB))
        key = (tip, end, net)
        if key in self._seen_stub:                       # broches empilées au même endroit
            return
        self._seen_stub.add(key)
        self.items.append(["wire", ["pts", ["xy", tip[0], tip[1]], ["xy", end[0], end[1]]],
                           ["stroke", ["width", 0], ["type", "default"]],
                           ["uuid", uid(self.project, "wire", ref, pin.number)]])
        if net in self.power:
            self._power(net, end, (dx, dy))
        else:
            angle, justify = LABEL[(dx, dy)]
            self.items.append(["label", Q(net), ["at", end[0], end[1], angle],
                               ["effects", _font(), ["justify"] + justify.split()],
                               ["uuid", uid(self.project, "label", ref, pin.number)]])

    def _power(self, net, at, outward):
        lib_id = f"power:{net}"
        self._symbol(lib_id)
        self._npwr += 1
        ref = f"#PWR{self._npwr:02d}"
        points_down = net.upper().startswith(("GND", "VSS", "EARTH"))
        # Le symbole pend sous le fil (masse) ou se dresse au-dessus (tension). On ne le
        # retourne que si le fil arrive par le côté où il se dessine.
        rot = 180 if outward == ((0, -1) if points_down else (0, 1)) else 0
        self._instance(ref, lib_id, at[0], at[1], rot, {"Reference": ref, "Value": net}, ["1"], hide_ref=True)

    def _instance(self, ref, lib_id, x, y, rot, values, pin_numbers, hide_ref=False):
        lib = self._lib_symbols[lib_id]
        libprops = {str(p[1]): p for p in sexp.find_all(lib, "property")}
        sign = -1 if rot == 180 else 1

        def flag(tag, default):
            node = sexp.find(lib, tag)
            return [tag, node[1] if node else default]

        inst = ["symbol", ["lib_id", Q(lib_id)], ["at", _f(x), _f(y), rot], ["unit", 1], ["body_style", 1],
                flag("exclude_from_sim", "no"), flag("in_bom", "yes"), flag("on_board", "yes"),
                flag("in_pos_files", "yes"), ["dnp", "no"], ["uuid", uid(self.project, "sym", ref)]]
        for name, value in values.items():
            lp = libprops.get(name)
            if lp is not None:
                at = sexp.find(lp, "at")
                px, py = _f(at[1]), _f(at[2])
                angle = int(float(at[3])) if len(at) > 3 else 0
                eff = copy.deepcopy(sexp.find(lp, "effects"))
                hidden = sexp.find(lp, "hide") is not None
            else:
                px, py, angle, eff, hidden = 0.0, 0.0, 0, ["effects", _font()], True
            if name == "Reference" and hide_ref:
                hidden = True
            prop = ["property", Q(name), Q(value), ["at", _f(x + sign * px), _f(y - sign * py), angle]]
            if hidden:
                prop.append(["hide", "yes"])
            prop += [["show_name", "no"], ["do_not_autoplace", "no"], eff]
            inst.append(prop)
        for n in pin_numbers:
            inst.append(["pin", Q(n), ["uuid", uid(self.project, "pin", ref, n)]])
        inst.append(["instances", ["project", Q(self.project),
                                   ["path", Q(f"/{self.root_uuid}"), ["reference", Q(ref)], ["unit", 1]]]])
        self.items.append(inst)

    # ----------------------------------------------------------- écriture

    def tree(self):
        order = {"text": 0, "wire": 1, "label": 2, "no_connect": 3, "symbol": 4}
        items = sorted(self.items, key=lambda it: order[it[0]])
        return ["kicad_sch", ["version", SCH_VERSION], ["generator", Q("luciole_schgen")],
                ["generator_version", Q("10.0")], ["uuid", self.root_uuid], ["paper", Q(self.paper)],
                ["title_block", ["title", Q(self.title)], ["date", Q(self.date)], ["rev", Q(self.rev)],
                 ["company", Q(self.company)]],
                ["lib_symbols"] + [self._lib_symbols[k] for k in sorted(self._lib_symbols)]] + items + [
                ["sheet_instances", ["path", Q("/"), ["page", Q("1")]]],
                ["embedded_fonts", "no"]]

    def write(self, directory, project_libs=()):
        """Écrit le schéma et les tables de bibliothèques du projet.
        project_libs : [(surnom, symboles relatifs au projet, empreintes relatives au projet)]."""
        os.makedirs(directory, exist_ok=True)
        sexp.save(os.path.join(directory, f"{self.project}.kicad_sch"), self.tree())
        sym = ["sym_lib_table", ["version", 7]]
        fpt = ["fp_lib_table", ["version", 7]]
        for nick, sympath, fppath in project_libs:
            sym.append(["lib", ["name", Q(nick)], ["type", Q("KiCad")],
                        ["uri", Q("${KIPRJMOD}/" + sympath)], ["options", Q("")], ["descr", Q("")]])
            fpt.append(["lib", ["name", Q(nick)], ["type", Q("KiCad")],
                        ["uri", Q("${KIPRJMOD}/" + fppath)], ["options", Q("")], ["descr", Q("")]])
        sexp.save(os.path.join(directory, "sym-lib-table"), sym)
        sexp.save(os.path.join(directory, "fp-lib-table"), fpt)
        pro = os.path.join(directory, f"{self.project}.kicad_pro")
        if not os.path.exists(pro):
            with open(pro, "w", encoding="utf-8") as f:
                json.dump({"meta": {"filename": f"{self.project}.kicad_pro", "version": 3}}, f, indent=2)
                f.write("\n")

    def netlist(self):
        """Liste de connexions décrite, {réseau: {(ref, broche)}}, sans les symboles d'alimentation."""
        return {net: {(r, p) for r, p in nodes if not r.startswith("#")}
                for net, nodes in self.nets.items()}


def stock(*nicks):
    """Chemins des bibliothèques officielles de l'image KiCad."""
    return {n: f"/usr/share/kicad/symbols/{n}.kicad_sym" for n in nicks}
