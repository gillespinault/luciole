"""Fabrique des symboles et des empreintes KiCad à partir de cotes.

Sert aux pièces absentes de la bibliothèque officielle, ou dont le brochage
diffère. Chaque empreinte doit citer la fiche technique dont viennent ses cotes.
"""
import uuid

from sexp import Q

NS = uuid.UUID("6c756369-6f6c-6532-0000-000000000000")  # espace de noms « luciole2 »
SYM_VERSION = "20251024"
FP_VERSION = "20260206"
GRID = 2.54


def uid(*key):
    """Identifiant stable : la même clé redonne toujours le même identifiant."""
    return Q(str(uuid.uuid5(NS, "/".join(str(k) for k in key))))


def _font(size=1.27, thickness=None):
    f = ["font", ["size", size, size]]
    if thickness:
        f.append(["thickness", thickness])
    return f


# ---------------------------------------------------------------- symboles

def _sym_prop(name, value, x, y, hide=False, justify=None):
    p = ["property", Q(name), Q(value), ["at", x, y, 0]]
    if hide:
        p.append(["hide", "yes"])
    p += [["show_name", "no"], ["do_not_autoplace", "no"]]
    eff = ["effects", _font()]
    if justify:
        eff.append(["justify"] + justify.split())
    p.append(eff)
    return p


def box_symbol(name, ref, footprint, datasheet, descr, lcsc="",
               left=(), right=(), top=(), bottom=(), min_half_width=5.08):
    """Symbole rectangulaire. Chaque broche est (numéro, nom, type électrique).

    Types : input, output, bidirectional, passive, power_in, power_out,
    open_collector, no_connect, unspecified.
    """
    rows = max(len(left), len(right), 1)
    cols = max(len(top), len(bottom), 1)
    y0 = GRID * ((rows - 1) // 2)                 # ordonnée de la première broche latérale
    room = GRID if (top or bottom) else 0         # place pour les noms des broches du haut et du bas
    y_top = y0 + GRID + room
    y_bot = y0 - GRID * (rows - 1) - GRID - room
    longest = max([len(p[1]) for p in list(left) + list(right)] or [0])
    half_w = max(min_half_width, GRID * (cols // 2 + 1), GRID * round((longest * 1.1 + 2.0) / GRID + 0.5))
    x0 = -GRID * ((cols - 1) // 2)

    pins = []

    def pin(p, x, y, angle):
        number, pname, etype = p
        pins.append(["pin", etype, "line", ["at", x, y, angle], ["length", GRID],
                     ["name", Q(pname), ["effects", _font()]],
                     ["number", Q(number), ["effects", _font()]]])

    for i, p in enumerate(left):
        pin(p, -(half_w + GRID), y0 - GRID * i, 0)
    for i, p in enumerate(right):
        pin(p, half_w + GRID, y0 - GRID * i, 180)
    for i, p in enumerate(top):
        pin(p, x0 + GRID * i, y_top + GRID, 270)
    for i, p in enumerate(bottom):
        pin(p, x0 + GRID * i, y_bot - GRID, 90)

    body = ["rectangle", ["start", -half_w, y_top], ["end", half_w, y_bot],
            ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]]

    return ["symbol", Q(name),
            ["pin_names", ["offset", 0.508]],
            ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            ["in_pos_files", "yes"], ["duplicate_pin_numbers_are_jumpers", "no"],
            _sym_prop("Reference", ref, -half_w, y_top + 1.27, justify="left bottom"),
            # La valeur se range à droite des broches du bas pour ne pas les recouvrir.
            _sym_prop("Value", name, x0 + GRID * len(bottom) - 1.27 if bottom else -half_w,
                      y_bot - 1.27, justify="left top"),
            _sym_prop("Footprint", footprint, 0, 0, hide=True),
            _sym_prop("Datasheet", datasheet, 0, 0, hide=True),
            _sym_prop("Description", descr, 0, 0, hide=True),
            _sym_prop("LCSC", lcsc, 0, 0, hide=True),
            ["symbol", Q(f"{name}_0_1"), body],
            ["symbol", Q(f"{name}_1_1")] + pins,
            ["embedded_fonts", "no"]]


def symbol_lib(symbols):
    return ["kicad_symbol_lib", ["version", SYM_VERSION], ["generator", Q("luciole_libgen")],
            ["generator_version", Q("10.0")]] + list(symbols)


# --------------------------------------------------------------- empreintes

class Footprint:
    def __init__(self, name, descr, tags, smd=True):
        self.name = name
        self.descr = descr
        self.tags = tags
        self.smd = smd
        self.items = []
        self._n = 0

    def _uid(self, kind):
        self._n += 1
        return uid("fp", self.name, kind, self._n)

    def pad(self, number, x, y, w, h, shape="rect"):
        """Pastille de surface, centre (x, y), largeur w sur X, hauteur h sur Y."""
        p = ["pad", Q(str(number)), "smd", shape, ["at", x, y], ["size", w, h],
             ["layers", Q("F.Cu"), Q("F.Mask"), Q("F.Paste")]]
        if shape == "roundrect":
            p.append(["roundrect_rratio", 0.15])
        p.append(["uuid", self._uid("pad")])
        self.items.append(p)

    def line(self, x1, y1, x2, y2, layer, width):
        self.items.append(["fp_line", ["start", x1, y1], ["end", x2, y2],
                           ["stroke", ["width", width], ["type", "solid"]],
                           ["layer", Q(layer)], ["uuid", self._uid("line")]])

    def polyline(self, pts, layer, width, close=True):
        seq = list(pts) + ([pts[0]] if close else [])
        for (x1, y1), (x2, y2) in zip(seq, seq[1:]):
            self.line(x1, y1, x2, y2, layer, width)

    def rect(self, x1, y1, x2, y2, layer, width):
        self.polyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], layer, width)

    def dot(self, x, y, r, layer):
        self.items.append(["fp_circle", ["center", x, y], ["end", x + r, y],
                           ["stroke", ["width", 0.1], ["type", "solid"]], ["fill", "yes"],
                           ["layer", Q(layer)], ["uuid", self._uid("circle")]])

    def fab(self, pts):
        self.polyline(pts, "F.Fab", 0.1)

    def silk(self, x1, y1, x2, y2):
        self.line(x1, y1, x2, y2, "F.SilkS", 0.12)

    def courtyard(self, x1, y1, x2, y2):
        self.rect(x1, y1, x2, y2, "F.CrtYd", 0.05)

    def tree(self, ref_y, val_y):
        def prop(pname, value, y, layer, hide=False, size=1.0):
            p = ["property", Q(pname), Q(value), ["at", 0, y, 0]]
            if hide:
                p.append(["unlocked", "yes"])
            p.append(["layer", Q(layer)])
            if hide:
                p.append(["hide", "yes"])
            p += [["uuid", self._uid("prop")], ["effects", _font(size, 0.15)]]
            return p

        return ["footprint", Q(self.name), ["version", FP_VERSION], ["generator", Q("luciole_libgen")],
                ["generator_version", Q("10.0")], ["layer", Q("F.Cu")],
                ["descr", Q(self.descr)], ["tags", Q(self.tags)],
                prop("Reference", "REF**", ref_y, "F.SilkS"),
                prop("Value", self.name, val_y, "F.Fab"),
                prop("Datasheet", "", 0, "F.Fab", hide=True, size=1.27),
                prop("Description", "", 0, "F.Fab", hide=True, size=1.27),
                ["attr", "smd" if self.smd else "through_hole"],
                ["duplicate_pad_numbers_are_jumpers", "no"]] + self.items + [["embedded_fonts", "no"]]
