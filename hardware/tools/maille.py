"""Routeur sur grille pour les liaisons courtes d'une carte.

    from maille import Router
    r = Router(b, forbid=[("B.Cu", x1, y1, x2, y2)], costly=[("B.Cu", x1, y1, x2, y2, 3)])
    r.route(skip=("GND",))
    r.save("v0/routage.json", signature)

Il part d'une carte dont les composants sont posés et dont la structure est déjà
tracée par script (liaisons longues, alimentations, boîtiers à pas fin). Il relie ce
qui reste, réseau par réseau, par le plus court chemin sur une grille de 0,05 mm, à
45 degrés, sur deux couches.

Pourquoi un routeur maison : sur la carte v0, Freerouting et KiCadRoutingTools
laissaient des dizaines de liaisons, dont des liaisons de 1 mm. Celui-ci est simple,
il applique exactement nos règles, et il redonne toujours le même tracé.

Principe. Pour chaque case de chaque couche, on garde la distance au cuivre du réseau
le plus proche, et la distance au cuivre le plus proche d'un autre réseau. Une piste de
largeur w du réseau N peut passer par le centre d'une case si le cuivre des autres
réseaux est à plus de : isolement + w/2 + marge. La marge couvre l'écart entre une
piste et les centres de cases qu'elle relie ; les formes sont exactes ou majorées.
Quand une liaison ne passe pas, le routeur cherche le chemin qu'elle prendrait sans les
pistes qu'il a lui-même tracées, défait celles qui le barrent, trace la liaison, puis
retrace les réseaux défaits. Il ne touche jamais aux pistes tracées par script. Une
liaison qui ne passe pas même ainsi est signalée : elle se règle par le placement.
Autour d'une pastille pas encore reliée, passer coûte plus cher aux autres réseaux :
cela lui garde une sortie.

Limites voulues : pas de boîtiers à pas fin (leurs sorties se tracent par script),
pas de masse (les plans la relient), pas d'optimisation globale.
"""
import heapq
import json
import math
import random
from array import array
from collections import Counter, deque

import pcbnew

STEP = 0.05                    # pas de la grille, mm
RMAX = 0.62                    # distance au-delà de laquelle un cuivre n'est plus noté
MARGE = 0.036                  # demi-diagonale d'une case : écart piste - centres de cases
BIG = 9.0
HARD = -1                      # « réseau » des obstacles : bord, trous, zones interdites
LAYERS = ("F.Cu", "B.Cu")
ORTH, DIAG = 10, 14            # coût d'un pas ; 200 par millimètre
HALO, HALO_COST = 0.6, 3       # autour d'une pastille pas encore reliée : rayon, surcoût
RIP_COST, RIP_VIA = 25, 6000   # traverser une piste ajoutée par le routeur, qu'il faudra défaire


class Router:
    def __init__(self, b, forbid=(), costly=(), via_cost=500, default_width=0.2):
        """b : pcbkit.Board. forbid : rectangles (couche, x1, y1, x2, y2) interdits au cuivre.
        costly : rectangles (couche, x1, y1, x2, y2, facteur) où un pas coûte plus cher,
        pour garder un plan de masse entier. via_cost : coût d'un via (200 par mm)."""
        self.b = b
        self.clr = b.rules["default_clearance"]
        self.via_r = b.rules["via_diameter"] / 2
        self.via_drill = b.rules["via_drill"]
        self.via_cost = via_cost
        self.w, self.h = b.size
        self.nx, self.ny = int(round(self.w / STEP)) + 1, int(round(self.h / STEP)) + 1
        n = self.nx * self.ny
        self.n1 = [array("h", [0]) * n for _ in LAYERS]
        self.d1 = [array("f", [BIG]) * n for _ in LAYERS]
        self.d2 = [array("f", [BIG]) * n for _ in LAYERS]
        self.novia = bytearray(n)
        self.cost = [None, None]
        self.width = {}
        for nc in b._netclasses:
            for name in nc["nets"]:
                self.width[name.lstrip("/")] = nc["track"]
        self.default_width = default_width
        self.ids, self.names = {}, {}
        self.items = {}            # réseau -> [élément de cuivre]
        self.added = {"pistes": [], "vias": []}
        self.failed = []
        self.halo = [array("h", [0]) * n for _ in LAYERS]
        self.pads = {}             # réseau -> [(couches, rectangle)] pour le surcoût
        self._loading = True
        self._load(forbid)
        self._loading = False
        # État de départ : ce que le routeur ne défait jamais.
        self._base = ([array("h", a) for a in self.n1], [array("f", a) for a in self.d1],
                      [array("f", a) for a in self.d2], bytearray(self.novia))
        self._fixed = {k: list(v) for k, v in self.items.items()}
        for name in self.pads:
            self._halo(name, True)
        for layer, x1, y1, x2, y2, factor in costly:
            L = LAYERS.index(layer)
            if self.cost[L] is None:
                self.cost[L] = bytearray([1]) * n
            for iy in range(self._i(y1, 1), self._i(y2, 0) + 1):
                for ix in range(self._i(x1, 1), self._i(x2, 0) + 1):
                    if 0 <= ix < self.nx and 0 <= iy < self.ny:
                        self.cost[L][iy * self.nx + ix] = factor

    # ------------------------------------------------------------ géométrie

    @staticmethod
    def _i(v, up):
        return int(math.ceil(v / STEP - 1e-9)) if up else int(math.floor(v / STEP + 1e-9))

    def _id(self, name):
        if name not in self.ids:
            self.ids[name] = len(self.ids) + 1
            self.names[self.ids[name]] = name
        return self.ids[name]

    def _note(self, L, i, net, d):
        n1, d1, d2 = self.n1[L], self.d1[L], self.d2[L]
        if n1[i] == net:
            if d < d1[i]:
                d1[i] = d
        elif d < d1[i]:
            d2[i] = d1[i]
            n1[i] = net
            d1[i] = d
        elif d < d2[i]:
            d2[i] = d

    def _rect(self, L, net, x1, y1, x2, y2, adj=0.0):
        """Note un rectangle de cuivre. adj : isolement demandé en plus de l'isolement normal."""
        R = RMAX + adj
        nx = self.nx
        ix1, ix2 = max(0, self._i(x1 - R, 1)), min(nx - 1, self._i(x2 + R, 0))
        iy1, iy2 = max(0, self._i(y1 - R, 1)), min(self.ny - 1, self._i(y2 + R, 0))
        note = self._note
        for iy in range(iy1, iy2 + 1):
            y = iy * STEP
            dy = y1 - y if y < y1 else (y - y2 if y > y2 else 0.0)
            base = iy * nx
            for ix in range(ix1, ix2 + 1):
                x = ix * STEP
                dx = x1 - x if x < x1 else (x - x2 if x > x2 else 0.0)
                d = (math.hypot(dx, dy) if dx and dy else dx + dy) - adj
                if d < RMAX:
                    note(L, base + ix, net, d if d > 0 else 0.0)

    def _seg(self, L, net, ax, ay, bx, by, hw, adj=0.0):
        if abs(ax - bx) < 1e-6 or abs(ay - by) < 1e-6:      # bouts carrés : majorant
            self._rect(L, net, min(ax, bx) - hw, min(ay, by) - hw, max(ax, bx) + hw, max(ay, by) + hw, adj)
            return
        R = RMAX + adj + hw
        nx = self.nx
        ix1, ix2 = max(0, self._i(min(ax, bx) - R, 1)), min(nx - 1, self._i(max(ax, bx) + R, 0))
        iy1, iy2 = max(0, self._i(min(ay, by) - R, 1)), min(self.ny - 1, self._i(max(ay, by) + R, 0))
        vx, vy = bx - ax, by - ay
        vv = vx * vx + vy * vy
        for iy in range(iy1, iy2 + 1):
            y = iy * STEP
            for ix in range(ix1, ix2 + 1):
                x = ix * STEP
                t = ((x - ax) * vx + (y - ay) * vy) / vv
                t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                d = math.hypot(x - ax - t * vx, y - ay - t * vy) - hw - adj
                if d < RMAX:
                    self._note(L, iy * nx + ix, net, d if d > 0 else 0.0)

    def _disc(self, L, net, cx, cy, r, adj=0.0):
        R = RMAX + adj + r
        nx = self.nx
        for iy in range(max(0, self._i(cy - R, 1)), min(self.ny - 1, self._i(cy + R, 0)) + 1):
            for ix in range(max(0, self._i(cx - R, 1)), min(nx - 1, self._i(cx + R, 0)) + 1):
                d = math.hypot(ix * STEP - cx, iy * STEP - cy) - r - adj
                if d < RMAX:
                    self._note(L, iy * nx + ix, net, d if d > 0 else 0.0)

    def _ban_via(self, x1, y1, x2, y2, r):
        """Interdit un via dont le centre serait à moins de r du rectangle."""
        nx = self.nx
        for iy in range(max(0, self._i(y1 - r, 1)), min(self.ny - 1, self._i(y2 + r, 0)) + 1):
            y = iy * STEP
            dy = y1 - y if y < y1 else (y - y2 if y > y2 else 0.0)
            for ix in range(max(0, self._i(x1 - r, 1)), min(nx - 1, self._i(x2 + r, 0)) + 1):
                x = ix * STEP
                dx = x1 - x if x < x1 else (x - x2 if x > x2 else 0.0)
                if dx * dx + dy * dy < r * r:
                    self.novia[iy * nx + ix] = 1

    # ------------------------------------------------- lecture de la carte

    def _load(self, forbid):
        b, mm = self.b, pcbnew.ToMM
        ox, oy = b.ox, b.oy
        edge = b.rules["edge_clearance"] - self.clr
        hole = b.rules["hole_clearance"] - self.clr
        for L in (0, 1):
            self._rect(L, HARD, -5, -5, 0, self.h + 5, edge)
            self._rect(L, HARD, self.w, -5, self.w + 5, self.h + 5, edge)
            self._rect(L, HARD, -5, -5, self.w + 5, 0, edge)
            self._rect(L, HARD, -5, self.h, self.w + 5, self.h + 5, edge)
        for layer, x1, y1, x2, y2 in forbid:
            self._rect(LAYERS.index(layer), HARD, x1, y1, x2, y2)
        for fp in b.board.GetFootprints():
            for pad in fp.Pads():
                box = pad.GetBoundingBox()
                x1, y1 = mm(box.GetLeft()) - ox, mm(box.GetTop()) - oy
                x2, y2 = mm(box.GetRight()) - ox, mm(box.GetBottom()) - oy
                p = pad.GetPosition()
                cx, cy = mm(p.x) - ox, mm(p.y) - oy
                name = pad.GetNetname().lstrip("/")
                drill = mm(pad.GetDrillSize().x)
                attr = pad.GetAttribute()
                if attr == pcbnew.PAD_ATTRIB_NPTH or not name:
                    for L in (0, 1):
                        if attr == pcbnew.PAD_ATTRIB_NPTH:
                            self._disc(L, HARD, cx, cy, drill / 2, hole)
                        elif pad.IsOnLayer(pcbnew.F_Cu if L == 0 else pcbnew.B_Cu):
                            self._rect(L, HARD, x1, y1, x2, y2)
                    self._ban_via(x1, y1, x2, y2, self.via_r + 0.3)
                    continue
                net = self._id(name)
                layers = [L for L in (0, 1) if pad.IsOnLayer(pcbnew.F_Cu if L == 0 else pcbnew.B_Cu)]
                round_pad = pad.GetShape(pcbnew.F_Cu if 0 in layers else pcbnew.B_Cu) == pcbnew.PAD_SHAPE_CIRCLE
                for L in layers:
                    self._rect(L, net, x1, y1, x2, y2)
                # Pas de via dans une pastille ni contre elle, même du même réseau.
                self._ban_via(x1, y1, x2, y2, self.via_r + (0.1 if drill == 0 else 0.5))
                self.items.setdefault(name, []).append(
                    dict(kind="pad", layers=layers, box=(x1, y1, x2, y2), at=(cx, cy), round=round_pad,
                         ref=fp.GetReference() + "." + pad.GetNumber()))
                self.pads.setdefault(name, []).append((layers, (x1, y1, x2, y2)))
        for t in b.board.GetTracks():
            name = t.GetNetname().lstrip("/")
            net = self._id(name) if name else HARD
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                self._note_via(name, net, mm(p.x) - ox, mm(p.y) - oy, mm(t.GetWidth(pcbnew.F_Cu)) / 2)
            else:
                a, e = t.GetStart(), t.GetEnd()
                L = 0 if t.GetLayer() == pcbnew.F_Cu else 1
                self._note_track(name, net, L, mm(a.x) - ox, mm(a.y) - oy, mm(e.x) - ox, mm(e.y) - oy, mm(t.GetWidth()))

    def _note_via(self, name, net, x, y, r):
        for L in (0, 1):
            self._disc(L, net, x, y, r)
        self._ban_via(x, y, x, y, self.via_r + r + 0.2)
        if name:
            self.items.setdefault(name, []).append(dict(kind="via", layers=[0, 1], at=(x, y), r=r, fixe=self._loading))

    def _note_track(self, name, net, L, ax, ay, bx, by, w):
        self._seg(L, net, ax, ay, bx, by, w / 2)
        if name:
            self.items.setdefault(name, []).append(dict(kind="piste", layers=[L], a=(ax, ay), b=(bx, by), hw=w / 2,
                                                        fixe=self._loading))

    def _halo(self, name, on):
        """Pose ou retire le surcoût autour des pastilles d'un réseau."""
        net, nx = self._id(name), self.nx
        for layers, (x1, y1, x2, y2) in self.pads.get(name, ()):
            for iy in range(max(0, self._i(y1 - HALO, 1)), min(self.ny - 1, self._i(y2 + HALO, 0)) + 1):
                for ix in range(max(0, self._i(x1 - HALO, 1)), min(nx - 1, self._i(x2 + HALO, 0)) + 1):
                    i = iy * nx + ix
                    for L in layers:
                        h = self.halo[L]
                        if on:
                            h[i] = net if h[i] in (0, net) else -2
                        elif h[i] == net:
                            h[i] = 0

    def _rebuild(self):
        """Remet la grille dans l'état de départ, puis y note les pistes ajoutées qui restent."""
        n1, d1, d2, novia = self._base
        for L in (0, 1):
            self.n1[L][:] = n1[L]
            self.d1[L][:] = d1[L]
            self.d2[L][:] = d2[L]
        self.novia[:] = novia
        self.items = {k: list(v) for k, v in self._fixed.items()}
        for t in self.added["pistes"]:
            self._note_track(t["net"], self._id(t["net"]), LAYERS.index(t["layer"]), t["a"][0], t["a"][1],
                             t["b"][0], t["b"][1], t["width"])
        for v in self.added["vias"]:
            self._note_via(v["net"], self._id(v["net"]), v["at"][0], v["at"][1], v["diameter"] / 2)

    # ------------------------------------------------------- connexité

    @staticmethod
    def _inside(item, x, y, tol=0.0):
        """Le point est-il dans le cuivre de l'élément ? tol > 0 : avec cette marge en dedans."""
        if item["kind"] == "pad":
            x1, y1, x2, y2 = item["box"]
            if item["round"]:
                return math.hypot(x - (x1 + x2) / 2, y - (y1 + y2) / 2) <= (x2 - x1) / 2 - tol
            return x1 + tol <= x <= x2 - tol and y1 + tol <= y <= y2 - tol
        if item["kind"] == "via":
            return math.hypot(x - item["at"][0], y - item["at"][1]) <= item["r"] - tol
        (ax, ay), (bx, by) = item["a"], item["b"]
        vx, vy = bx - ax, by - ay
        vv = vx * vx + vy * vy
        t = 0.0 if vv == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / vv))
        return math.hypot(x - ax - t * vx, y - ay - t * vy) <= item["hw"] - tol

    def _anchors(self, item):
        if item["kind"] == "piste":
            return [item["a"], item["b"]]
        return [item["at"]]

    def _components(self, name):
        """Groupes d'éléments déjà reliés, comme KiCad les compte : un bout de piste ou
        un centre de via dans le cuivre d'un autre élément de la même couche."""
        items = self.items.get(name, [])
        parent = list(range(len(items)))

        def find(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k

        for i, a in enumerate(items):
            for j in range(i + 1, len(items)):
                c = items[j]
                if not set(a["layers"]) & set(c["layers"]):
                    continue
                if any(self._inside(c, *p, tol=-0.002) for p in self._anchors(a)) or \
                        any(self._inside(a, *p, tol=-0.002) for p in self._anchors(c)):
                    parent[find(i)] = find(j)
        groups = {}
        for k, item in enumerate(items):
            groups.setdefault(find(k), []).append(item)
        return list(groups.values())

    def _cells(self, item):
        """Cases dont le centre est dans le cuivre de l'élément, un peu en dedans."""
        if item["kind"] == "pad":
            x1, y1, x2, y2 = item["box"]
        elif item["kind"] == "via":
            (x, y), r = item["at"], item["r"]
            x1, y1, x2, y2 = x - r, y - r, x + r, y + r
        else:
            (ax, ay), (bx, by), hw = item["a"], item["b"], item["hw"]
            x1, y1, x2, y2 = min(ax, bx) - hw, min(ay, by) - hw, max(ax, bx) + hw, max(ay, by) + hw
        out = []
        for iy in range(max(0, self._i(y1, 1)), min(self.ny - 1, self._i(y2, 0)) + 1):
            for ix in range(max(0, self._i(x1, 1)), min(self.nx - 1, self._i(x2, 0)) + 1):
                if self._inside(item, ix * STEP, iy * STEP, tol=0.03):
                    for L in item["layers"]:
                        out.append((L, iy * self.nx + ix))
        if not out:                                # élément plus fin que la grille : son ancre
            for (x, y) in self._anchors(item):
                for L in item["layers"]:
                    out.append((L, self._i(y + STEP / 2, 0) * self.nx + self._i(x + STEP / 2, 0)))
        return out

    # ------------------------------------------------------------ recherche

    def _search(self, net, sources, targets, w, hint, box=None, limit=700000, rip=False):
        """Plus court chemin des cases `sources` à une case de `targets`. Une case est un
        entier : couche x taille de la grille + indice. hint : point visé (x, y), pour
        chercher d'abord dans sa direction. box : fenêtre (ix1, iy1, ix2, iy2) dont on ne
        sort pas. rip : seules les pistes de départ sont des obstacles ; traverser une piste
        ajoutée par le routeur est permis, mais cher. Rend la liste des cases, ou None."""
        nx, ny = self.nx, self.ny
        n = nx * ny
        r = self.clr + w / 2 + MARGE
        rv = self.clr + self.via_r + 0.005
        novia, via_cost = (self._base[3] if rip else self.novia), self.via_cost
        cur = [(self.n1[L], self.d1[L], self.d2[L]) for L in (0, 1)]
        cur_novia = self.novia
        bx1, by1, bx2, by2 = box if box else (0, 0, nx - 1, ny - 1)
        hx, hy = int(round(hint[0] / STEP)), int(round(hint[1] / STEP))
        INF = 1 << 30
        dist = array("i", [INF]) * (2 * n)
        prev = array("i", [-1]) * (2 * n)
        heap = []
        for key in sources:
            dist[key] = 0
            i = key % n
            dx, dy = abs(i % nx - hx), abs(i // nx - hy)
            heapq.heappush(heap, (ORTH * (dx + dy) - 6 * (dx if dx < dy else dy), 0, key))
        moves = ((1, 0, ORTH), (-1, 0, ORTH), (0, 1, ORTH), (0, -1, ORTH),
                 (1, 1, DIAG), (1, -1, DIAG), (-1, 1, DIAG), (-1, -1, DIAG))
        if rip:
            layers = [(self._base[0][L], self._base[1][L], self._base[2][L], self.cost[L], self.halo[L]) for L in (0, 1)]
        else:
            layers = [(self.n1[L], self.d1[L], self.d2[L], self.cost[L], self.halo[L]) for L in (0, 1)]
        seen = 0
        pop, push = heapq.heappop, heapq.heappush
        while heap:
            f, g, key = pop(heap)
            if dist[key] < g:
                continue
            if g and key in targets:
                path = [key]
                while prev[key] >= 0:
                    key = prev[key]
                    path.append(key)
                return path[::-1]
            seen += 1
            if seen > limit:
                return None
            L, i = divmod(key, n)
            n1, d1, d2, cl, hal = layers[L]
            ix, iy = i % nx, i // nx
            off = L * n
            for dx, dy, c in moves:
                jx, jy = ix + dx, iy + dy
                if jx < bx1 or jx > bx2 or jy < by1 or jy > by2:
                    continue
                j = jy * nx + jx
                if (d2[j] if n1[j] == net else d1[j]) < r:
                    continue
                if dx and dy:                       # pas en diagonale entre deux coins occupés
                    k1, k2 = iy * nx + jx, jy * nx + ix
                    if (d2[k1] if n1[k1] == net else d1[k1]) < r or (d2[k2] if n1[k2] == net else d1[k2]) < r:
                        continue
                if cl is not None:
                    c = c * cl[j]
                if hal is not None and hal[j] and hal[j] != net:
                    c = c * HALO_COST
                if rip:
                    q1, q2, q3 = cur[L]
                    if (q3[j] if q1[j] == net else q2[j]) < r:
                        c = c * RIP_COST
                ng = g + c
                nk = off + j
                if ng < dist[nk]:
                    dist[nk] = ng
                    prev[nk] = key
                    ax, ay = jx - hx, jy - hy
                    if ax < 0:
                        ax = -ax
                    if ay < 0:
                        ay = -ay
                    push(heap, (ng + ORTH * (ax + ay) - 6 * (ax if ax < ay else ay), ng, nk))
            if not novia[i]:
                a, c, e = layers[0][:3]
                if (e[i] if a[i] == net else c[i]) >= rv:
                    a, c, e = layers[1][:3]
                    if (e[i] if a[i] == net else c[i]) >= rv:
                        ng = g + via_cost
                        if rip and (cur_novia[i] or any((q3[i] if q1[i] == net else q2[i]) < rv for q1, q2, q3 in cur)):
                            ng += RIP_VIA
                        nk = (1 - L) * n + i
                        if ng < dist[nk]:
                            dist[nk] = ng
                            prev[nk] = key
                            ax, ay = ix - hx, iy - hy
                            if ax < 0:
                                ax = -ax
                            if ay < 0:
                                ay = -ay
                            push(heap, (ng + ORTH * (ax + ay) - 6 * (ax if ax < ay else ay), ng, nk))
        return None

    # --------------------------------------------------------------- tracé

    def _clear(self, L, net, r, a, c):
        """Peut-on aller de la case a à la case c, sur la couche L, par un tronçon à 45
        degrés suivi d'un tronçon droit ? Rend le coin, ou None."""
        nx = self.nx
        n1, d1, d2 = self.n1[L], self.d1[L], self.d2[L]
        ax, ay, cx, cy = a % nx, a // nx, c % nx, c // nx
        sx, sy = (cx > ax) - (cx < ax), (cy > ay) - (cy < ay)
        diag = min(abs(cx - ax), abs(cy - ay))
        for first in (True, False):                # oblique d'abord, puis droit d'abord
            x, y, ok = ax, ay, True
            steps = [(sx, sy)] * diag + [(sx if abs(cx - ax) > diag else 0, sy if abs(cy - ay) > diag else 0)] * \
                (max(abs(cx - ax), abs(cy - ay)) - diag)
            if not first:
                steps = steps[diag:] + steps[:diag]
            corner = None
            for k, (dx, dy) in enumerate(steps):
                if k and steps[k - 1] != (dx, dy):
                    corner = y * nx + x
                jx, jy = x + dx, y + dy
                j = jy * nx + jx
                if (d2[j] if n1[j] == net else d1[j]) < r:
                    ok = False
                    break
                if dx and dy:
                    k1, k2 = y * nx + jx, jy * nx + x
                    if (d2[k1] if n1[k1] == net else d1[k1]) < r or (d2[k2] if n1[k2] == net else d1[k2]) < r:
                        ok = False
                        break
                x, y = jx, jy
            if ok:
                return corner if corner is not None else a
        return None

    def _smooth(self, L, net, r, cells):
        """Remplace le chemin case par case par le moins de tronçons possible."""
        out, k = [cells[0]], 0
        while k < len(cells) - 1:
            for m in range(len(cells) - 1, k, -1):
                corner = self._clear(L, net, r, cells[k], cells[m]) if m > k + 1 else cells[k]
                if corner is not None:
                    if corner != cells[k]:
                        out.append(corner)
                    out.append(cells[m])
                    k = m
                    break
        return out

    def _emit(self, name, path, w):
        nx = self.nx
        n = nx * self.ny
        net = self._id(name)
        path = [divmod(key, n) for key in path]
        runs, cur = [], [path[0]]
        for a, c in zip(path, path[1:]):
            if a[0] != c[0]:
                runs.append(cur)
                x, y = round((a[1] % nx) * STEP, 4), round((a[1] // nx) * STEP, 4)
                self.added["vias"].append(dict(net=name, at=[x, y], diameter=2 * self.via_r, drill=self.via_drill))
                self._note_via(name, net, x, y, self.via_r)
                cur = [c]
            else:
                cur.append(c)
        runs.append(cur)
        for run in runs:
            if len(run) < 2:
                continue
            L = run[0][0]
            cells = self._smooth(L, net, self.clr + w / 2 + MARGE, [i for _, i in run])
            pts = [(round((i % nx) * STEP, 4), round((i // nx) * STEP, 4)) for i in cells]
            for a, c in zip(pts, pts[1:]):
                self.added["pistes"].append(dict(net=name, layer=LAYERS[L], a=list(a), b=list(c), width=w))
                self._note_track(name, net, L, a[0], a[1], c[0], c[1], w)

    def apply(self):
        """Écrit sur la carte les pistes et les vias trouvés."""
        for t in self.added["pistes"]:
            self.b.track(t["net"], [tuple(t["a"]), tuple(t["b"])], t["width"], layer=t["layer"])
        for v in self.added["vias"]:
            self.b.via(v["net"], v["at"][0], v["at"][1], diameter=v["diameter"], drill=v["drill"])

    def _hint(self, group, others):
        """Point visé : l'ancre des autres groupes la plus proche du groupe."""
        mine = [p for item in group for p in self._anchors(item)]
        best = None
        for g in others:
            for item in g:
                pts = self._anchors(item)
                if item["kind"] == "piste":        # une piste longue : un point par millimètre
                    (ax, ay), (bx, by) = item["a"], item["b"]
                    k = int(math.hypot(bx - ax, by - ay))
                    pts = pts + [(ax + (bx - ax) * m / (k + 1), ay + (by - ay) * m / (k + 1)) for m in range(1, k + 1)]
                for p in pts:
                    for q in mine:
                        d = math.hypot(p[0] - q[0], p[1] - q[1])
                        if best is None or (d, p, q) < best:
                            best = (d, p, q)
        return best

    def _key(self, group):
        """Repère d'un groupe : ses éléments fixes, qui ne changent pas quand on défait."""
        return min(id(i) for i in group if i.get("fixe", True))

    def _ends(self, name, group, others):
        n = self.nx * self.ny
        targets = set()
        for g in others:
            for item in g:
                for L, i in self._cells(item):
                    targets.add(L * n + i)
        sources = set(L * n + i for item in group for L, i in self._cells(item))
        d, hint, start = self._hint(group, others)
        return sources, targets, hint, start

    def route_net(self, name):
        """Relie les groupes du réseau, du plus petit vers n'importe quel autre. Rend les
        groupes qu'il n'a pas su relier."""
        w0 = self.width.get(name, self.default_width)
        widths = [w0] + [w for w in (0.3, 0.15) if w < w0]       # en dernier recours, 0,15 mm
        net = self._id(name)
        stuck = set()
        while True:
            groups = self._components(name)
            free = [g for g in groups if self._key(g) not in stuck]
            if len(groups) < 2 or not free:
                break
            free.sort(key=lambda g: (len(g), sorted(str(self._anchors(i)) for i in g)))
            group = free[0]
            others = [g for g in groups if g is not group]
            sources, targets, hint, start = self._ends(name, group, others)
            # D'abord dans une fenêtre autour du groupe et du point visé, puis partout.
            m = 6.0
            box = (max(0, self._i(min(hint[0], start[0]) - m, 1)), max(0, self._i(min(hint[1], start[1]) - m, 1)),
                   min(self.nx - 1, self._i(max(hint[0], start[0]) + m, 0)), min(self.ny - 1, self._i(max(hint[1], start[1]) + m, 0)))
            path = None
            for w in widths:
                path = self._search(net, sources, targets, w, hint, box)
                if path:
                    break
            if not path:
                w = widths[0]
                path = self._search(net, sources, targets, w, hint)
            if path:
                self._emit(name, path, w)
            else:
                stuck.add(self._key(group))
        groups = self._components(name)
        return [g for g in groups if self._key(g) in stuck] if len(groups) > 1 else []

    def _unroute(self, names):
        names = set(names)
        self.added["pistes"] = [t for t in self.added["pistes"] if t["net"] not in names]
        self.added["vias"] = [v for v in self.added["vias"] if v["net"] not in names]
        self._rebuild()
        for name in names:
            self._halo(name, True)

    def _blockers(self, name, path, w):
        """Réseaux dont une piste ajoutée par le routeur barre ce chemin."""
        nx = self.nx
        n = nx * self.ny
        net = self._id(name)
        r = self.clr + w / 2 + MARGE
        rv = self.clr + self.via_r + 0.005
        out = set()
        cells = [divmod(key, n) for key in path]
        vias = set(a[1] for a, c in zip(cells, cells[1:]) if a[0] != c[0])
        for L, i in cells:
            n1, d1, d2 = self.n1[L][i], self.d1[L][i], self.d2[L][i]
            if (d2 if n1 == net else d1) < r:
                out.add(None)                      # on cherchera lesquels par la géométrie
        if None in out or vias:
            out.discard(None)
            pts = [(L, (i % nx) * STEP, (i // nx) * STEP, i in vias) for L, i in cells]
            for t in self.added["pistes"]:
                if t["net"] == name:
                    continue
                Lt = LAYERS.index(t["layer"])
                (ax, ay), (bx, by), hw = t["a"], t["b"], t["width"] / 2
                vx, vy = bx - ax, by - ay
                vv = vx * vx + vy * vy or 1e-12
                for L, x, y, is_via in pts:
                    if L != Lt and not is_via:
                        continue
                    k = ((x - ax) * vx + (y - ay) * vy) / vv
                    k = 0.0 if k < 0 else (1.0 if k > 1 else k)
                    if math.hypot(x - ax - k * vx, y - ay - k * vy) - hw < (rv if is_via else r) + 0.01:
                        out.add(t["net"])
                        break
            for v in self.added["vias"]:
                if v["net"] == name:
                    continue
                vr = v["diameter"] / 2
                for L, x, y, is_via in pts:
                    d = math.hypot(x - v["at"][0], y - v["at"][1])
                    if d - vr < (rv if is_via else r) + 0.01 or (is_via and d < 2 * self.via_r + 0.25):
                        out.add(v["net"])
                        break
        return out

    def _rip_for(self, name, group, rips, max_rips):
        """Défait ce qui barre la liaison du groupe, puis la trace. Rend les réseaux
        défaits, ou None si la liaison ne passe pas même sans les pistes ajoutées."""
        groups = self._components(name)
        key = self._key(group)
        group = next(g for g in groups if self._key(g) == key)
        others = [g for g in groups if g is not group]
        sources, targets, hint, start = self._ends(name, group, others)
        w0 = self.width.get(name, self.default_width)
        net = self._id(name)
        for w in [w0] + [x for x in (0.3, 0.15) if x < w0]:
            path = self._search(net, sources, targets, w, hint, rip=True, limit=1500000)
            if path:
                break
        if not path:
            return None
        ripped = set()
        for _ in range(4):
            blockers = self._blockers(name, path, w)
            if not blockers:
                self._emit(name, path, w)
                return ripped
            if any(rips[m] >= max_rips for m in blockers):
                break
            for m in blockers:
                rips[m] += 1
            ripped |= blockers
            self._unroute(blockers)
        if ripped:                                 # défait pour rien : on le dit, ils seront retracés
            return ripped
        return None

    def route(self, skip=(), order=(), only=None, max_rips=6, seed=None):
        """Route tous les réseaux, sauf ceux de `skip`. `order` : réseaux à router d'abord ;
        les autres suivent, du plus court au plus long. Rend le nombre de liaisons non faites.

        seed : graine d'un tirage qui bouscule cet ordre (longueur comptée de 60 à 140 %).
        Le résultat dépend de l'ordre de passage ; plusieurs graines donnent plusieurs
        tracés, dont on garde le meilleur. Une graine donnée redonne le même ordre."""
        names = [k for k in self.items if k not in skip and not k.startswith("unconnected-")
                 and (only is None or k in only)]

        def span(k):
            pts = [p for item in self.items[k] for p in self._anchors(item)]
            return (max(p[0] for p in pts) - min(p[0] for p in pts) + max(p[1] for p in pts) - min(p[1] for p in pts), k)

        first = [k for k in order if k in names]
        if seed is None:
            rest = sorted(names, key=span)
        else:
            rnd = random.Random(seed)
            rest = [k for _, k in sorted((span(k)[0] * rnd.uniform(0.6, 1.4), k) for k in sorted(names))]
        queue = deque(first + [x for x in rest if x not in first])
        rips, undone, stuck_nets = Counter(), 0, {}
        while queue:
            name = queue.popleft()
            stuck = self.route_net(name)
            tries = 0
            while stuck and tries < 8:
                tries += 1
                ripped = self._rip_for(name, stuck[0], rips, max_rips)
                if ripped is None:
                    break
                undone += len(ripped)
                for m in sorted(ripped):               # retracés aussitôt, tant que la place est libre
                    stuck_nets.pop(m, None)
                    if m in queue:
                        queue.remove(m)
                    queue.appendleft(m)
                stuck = self.route_net(name)
            if stuck:
                stuck_nets[name] = len(stuck)
            else:
                stuck_nets.pop(name, None)
                self._halo(name, False)
        self.failed = []
        for name in sorted(stuck_nets):
            desc = []
            for g in self._components(name):
                pts = [p for i in g for p in self._anchors(i)]
                refs = [i["ref"] for i in g if "ref" in i]
                desc.append(f"{' '.join(refs[:4]) or 'pistes'} en x {min(p[0] for p in pts):.1f}-{max(p[0] for p in pts):.1f}"
                            f" y {min(p[1] for p in pts):.1f}-{max(p[1] for p in pts):.1f}")
            self.failed.append((name, desc))
        total = sum(len(self._components(k)) - 1 for k in names)
        print(f"routeur : {len(self.added['pistes'])} pistes, {len(self.added['vias'])} vias, "
              f"{undone} réseau(x) défait(s) puis retracé(s), {total} liaison(s) non faite(s)")
        self.apply()
        # Réseaux tracés plus fin que leur classe : à regarder à la revue du tracé.
        thin = {}
        for t in self.added["pistes"]:
            if t["width"] < self.width.get(t["net"], self.default_width) - 1e-6:
                a, c = t["a"], t["b"]
                k = (t["net"], t["width"])
                thin[k] = thin.get(k, 0.0) + math.hypot(c[0] - a[0], c[1] - a[1])
        for (name, w), length in sorted(thin.items()):
            print(f"  plus fin que sa classe : {name}, {w} mm sur {length:.1f} mm "
                  f"(classe à {self.width.get(name, self.default_width)} mm)")
        return total

    def alone(self, skip=()):
        """Essaie chaque réseau seul, sur la carte de départ. Un réseau qui échoue ainsi
        est une impasse du placement ou des pistes tracées par script : aucun ordre de
        passage ne le sauvera. Rend la liste (réseau, groupes isolés)."""
        out = []
        for name in sorted(self.items):
            if name in skip or name.startswith("unconnected-"):
                continue
            self.added = {"pistes": [], "vias": []}
            self._rebuild()
            stuck = self.route_net(name)
            if stuck:
                desc = []
                for g in self._components(name):
                    pts = [p for i in g for p in self._anchors(i)]
                    refs = [i["ref"] for i in g if "ref" in i]
                    desc.append(f"{' '.join(refs[:4]) or 'pistes'} en x {min(p[0] for p in pts):.1f}-{max(p[0] for p in pts):.1f}"
                                f" y {min(p[1] for p in pts):.1f}-{max(p[1] for p in pts):.1f}")
                out.append((name, desc))
        self.added = {"pistes": [], "vias": []}
        self._rebuild()
        return out

    def stitch(self, refs, name="GND", w=0.3, reach=4.0):
        """Relie des pastilles de masse au plan de l'autre face. Pour chaque pastille
        (« C9.2 »), cherche la case la plus proche où un via tient sur les deux faces, y
        pose un via et le relie par une piste. À utiliser pour les pastilles que le plan
        de leur propre face n'atteint pas. Rend les pastilles qu'on n'a pas su relier."""
        net = self._id(name)
        nx = self.nx
        n = nx * self.ny
        rv = self.clr + self.via_r + 0.005
        r = self.clr + w / 2 + MARGE
        by_ref = {i["ref"]: i for i in self.items.get(name, []) if "ref" in i}
        missing = []
        for ref in refs:
            item = by_ref.get(ref)
            if item is None:
                raise KeyError(f"{ref} n'est pas une pastille de {name}")
            sources = set(L * n + i for L, i in self._cells(item))
            layers = [(self.n1[L], self.d1[L], self.d2[L]) for L in (0, 1)]
            dist, prev, heap, goal = {}, {}, [], None
            for key in sources:
                dist[key] = 0
                heapq.heappush(heap, (0, key))
            limit = int(reach / STEP) * ORTH
            while heap:
                g, key = heapq.heappop(heap)
                if dist[key] < g:
                    continue
                L, i = divmod(key, n)
                if g and not self.novia[i] and all((e[i] if a[i] == net else c[i]) >= rv for a, c, e in layers):
                    goal = key
                    break
                if g > limit:
                    break
                n1, d1, d2 = layers[L]
                ix, iy = i % nx, i // nx
                for dx, dy, c in ((1, 0, ORTH), (-1, 0, ORTH), (0, 1, ORTH), (0, -1, ORTH),
                                  (1, 1, DIAG), (1, -1, DIAG), (-1, 1, DIAG), (-1, -1, DIAG)):
                    jx, jy = ix + dx, iy + dy
                    if not (0 <= jx < nx and 0 <= jy < self.ny):
                        continue
                    j = jy * nx + jx
                    if (d2[j] if n1[j] == net else d1[j]) < r:
                        continue
                    if dx and dy:
                        k1, k2 = iy * nx + jx, jy * nx + ix
                        if (d2[k1] if n1[k1] == net else d1[k1]) < r or (d2[k2] if n1[k2] == net else d1[k2]) < r:
                            continue
                    nk = L * n + j
                    if g + c < dist.get(nk, 1 << 30):
                        dist[nk] = g + c
                        prev[nk] = key
                        heapq.heappush(heap, (g + c, nk))
            if goal is None:
                missing.append(ref)
                continue
            path = [goal]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            path = path[::-1]
            L, i = divmod(goal, n)
            # Le chemin, puis le via au bout : _emit pose un via à chaque changement de couche.
            before = (len(self.added["pistes"]), len(self.added["vias"]))
            self._emit(name, path + [(1 - L) * n + i], w)
            for t in self.added["pistes"][before[0]:]:
                self.b.track(t["net"], [tuple(t["a"]), tuple(t["b"])], t["width"], layer=t["layer"])
            for v in self.added["vias"][before[1]:]:
                self.b.via(v["net"], v["at"][0], v["at"][1], diameter=v["diameter"], drill=v["drill"])
        return missing

    def save(self, path, signature):
        with open(path, "w", encoding="utf-8") as f:
            f.write('{\n "signature": ' + json.dumps(signature) + ',\n "pistes": [\n')
            f.write(",\n".join("  " + json.dumps(t, ensure_ascii=False) for t in self.added["pistes"]))
            f.write('\n ],\n "vias": [\n')
            f.write(",\n".join("  " + json.dumps(v, ensure_ascii=False) for v in self.added["vias"]))
            f.write("\n ]\n}\n")
