"""Pose des petits composants au plus près de ce qu'ils relient.

    from pose import Placer
    p = Placer(b, Router(b))
    p.auto(["R18", "C10", "U5"], [(98.5, 15.6, 105.4, 21.3)])

Ranger des composants par rangées, sans regarder leurs connexions, donne des blocs où
tout doit se croiser. Ici, chaque composant va à la place libre où la somme des
distances entre ses pastilles et le cuivre déjà posé de leurs réseaux est la plus
petite, dans l'orientation qui convient. On pose d'abord ceux dont le plus de
pastilles ont déjà un réseau posé ; les autres suivent, attirés par les premiers.

Ce qui est vérifié avant de retenir une place : la zone de garde tient dans la région
et ne recouvre aucune autre ; les pastilles sont à l'isolement du cuivre des autres
réseaux (grille du routeur, tools/maille.py) ; aucune pastille ne couvre un via.

La masse n'attire pas : les plans la relient partout.
"""
import math

import pcbnew

from maille import STEP, LAYERS


class Placer:
    def __init__(self, b, router, gap=0.2, reach=5.0, step=0.25, skip_nets=("GND",)):
        """gap : écart laissé entre deux zones de garde, pour qu'une piste passe.
        reach : rayon de recherche autour du cuivre visé. step : pas des positions."""
        self.b, self.r = b, router
        self.gap, self.reach, self.step = gap, reach, step
        self.skip = set(skip_nets)
        self.yards = {False: [], True: []}
        for ref, fp in b.fps.items():
            self.yards[bool(fp.IsFlipped())].append(b.courtyard(ref))
        self.vias = []
        for t in b.board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                self.vias.append((pcbnew.ToMM(q.x) - b.ox, pcbnew.ToMM(q.y) - b.oy))
        self._shape = {}

    # ------------------------------------------------------------ géométrie

    def _shapes(self, ref, bottom):
        """Pour chaque orientation : zone de garde et pastilles, relatives à l'origine."""
        fp = self.b.fps[ref]
        out = {}
        for rot in (0, 90, 180, 270):
            fp.SetOrientationDegrees(rot)
            p = fp.GetPosition()
            ox, oy = pcbnew.ToMM(p.x) - self.b.ox, pcbnew.ToMM(p.y) - self.b.oy
            cx1, cy1, cx2, cy2 = self.b.courtyard(ref)
            pads = []
            for pad in fp.Pads():
                box = pad.GetBoundingBox()
                pads.append((pad.GetNetname().lstrip("/"),
                             pcbnew.ToMM(box.GetLeft()) - self.b.ox - ox, pcbnew.ToMM(box.GetTop()) - self.b.oy - oy,
                             pcbnew.ToMM(box.GetRight()) - self.b.ox - ox, pcbnew.ToMM(box.GetBottom()) - self.b.oy - oy))
            out[rot] = ((cx1 - ox, cy1 - oy, cx2 - ox, cy2 - oy), pads)
        return out

    def _terminals(self, name, L):
        """Points de cuivre déjà posés du réseau : (x, y, surcoût si autre face)."""
        pts = []
        for item in self.r.items.get(name, ()):
            other = 0.0 if L in item["layers"] else 2.0
            if item["kind"] == "piste":
                (ax, ay), (bx, by) = item["a"], item["b"]
                k = int(math.hypot(bx - ax, by - ay) / 0.5)
                pts += [(ax + (bx - ax) * m / (k + 1), ay + (by - ay) * m / (k + 1), other) for m in range(k + 2)]
            else:
                pts.append((item["at"][0], item["at"][1], other))
        return pts

    def _legal(self, yard, pads, regions, bottom, L):
        why = self._why = getattr(self, "_why", {})
        x1, y1, x2, y2 = yard
        if not any(rx1 <= x1 and ry1 <= y1 and x2 <= rx2 and y2 <= ry2 for rx1, ry1, rx2, ry2 in regions):
            why["hors région"] = why.get("hors région", 0) + 1
            return False
        g = self.gap
        for ax1, ay1, ax2, ay2 in self.yards[bottom]:
            if x1 - g < ax2 and ax1 < x2 + g and y1 - g < ay2 and ay1 < y2 + g:
                why["zone de garde"] = why.get("zone de garde", 0) + 1
                return False
        r, nx = self.r, self.r.nx
        n1, d1, d2 = r.n1[L], r.d1[L], r.d2[L]
        clr = r.clr + 0.03
        for name, px1, py1, px2, py2 in pads:
            net = r.ids.get(name, 0)
            for vx, vy in self.vias:               # pas de via sous une pastille ni contre elle
                dx = px1 - vx if vx < px1 else (vx - px2 if vx > px2 else 0.0)
                dy = py1 - vy if vy < py1 else (vy - py2 if vy > py2 else 0.0)
                if dx * dx + dy * dy < (r.via_r + 0.15) ** 2:
                    why["via"] = why.get("via", 0) + 1
                    return False
            for fx in (0.0, 0.5, 1.0):
                for fy in (0.0, 0.5, 1.0):
                    x, y = px1 + (px2 - px1) * fx, py1 + (py2 - py1) * fy
                    ix, iy = int(round(x / STEP)), int(round(y / STEP))
                    if not (0 <= ix < nx and 0 <= iy < r.ny):
                        return False
                    i = iy * nx + ix
                    if (d2[i] if n1[i] == net else d1[i]) < clr:
                        why["cuivre"] = why.get("cuivre", 0) + 1
                        return False
        return True

    # ----------------------------------------------------------------- pose

    def _best(self, ref, regions, bottom):
        """Meilleure place : (coût, x, y, orientation, zone de garde, pastilles), ou None.
        On cherche d'abord près du cuivre visé, puis dans toute la région."""
        L = 1 if bottom else 0
        shapes = self._shape.setdefault(ref, self._shapes(ref, bottom))
        nets = [name for name, *_ in shapes[0][1]]
        terms = {name: self._terminals(name, L) for name in set(nets)
                 if name and name not in self.skip and not name.startswith("unconnected-")}
        terms = {k: v for k, v in terms.items() if v}
        s = self.step
        near, everywhere = set(), set()
        for rx1, ry1, rx2, ry2 in regions:
            for iy in range(int((ry2 - ry1) / s) + 1):
                for ix in range(int((rx2 - rx1) / s) + 1):
                    everywhere.add((round(rx1 + ix * s, 3), round(ry1 + iy * s, 3)))
        if terms:
            pts = [t for v in terms.values() for t in v]
            for x, y in everywhere:
                if any(abs(x - tx) <= self.reach and abs(y - ty) <= self.reach for tx, ty, _ in pts):
                    near.add((x, y))
        for cands in ((near, everywhere - near) if near else (everywhere,)):
            scored = []
            for x, y in cands:
                for rot, (yard, pads) in shapes.items():
                    cost = 0.0
                    for name, px1, py1, px2, py2 in pads:
                        pts = terms.get(name)
                        if not pts:
                            continue
                        cx, cy = x + (px1 + px2) / 2, y + (py1 + py2) / 2
                        cost += min(math.hypot(cx - tx, cy - ty) + extra for tx, ty, extra in pts)
                    scored.append((round(cost, 3), y, x, rot))
            scored.sort()
            for cost, y, x, rot in scored:
                yard, pads = shapes[rot]
                ayard = (x + yard[0], y + yard[1], x + yard[2], y + yard[3])
                apads = [(name, x + a, y + c, x + e, y + f) for name, a, c, e, f in pads]
                if self._legal(ayard, apads, regions, bottom, L):
                    return cost, x, y, rot, ayard, apads
        return None

    def auto(self, refs, regions, bottom=False):
        """Pose les composants `refs` dans les rectangles `regions` (x1, y1, x2, y2)."""
        b, r = self.b, self.r
        L = 1 if bottom else 0
        rx1, ry1, rx2, ry2 = regions[0]
        for ref in refs:                           # posés d'abord hors carte, pour lire leur forme
            b.place(ref, -20.0, -20.0, bottom=bottom)
        todo = list(refs)
        while todo:
            def anchored(ref):
                fp = b.fps[ref]
                nets = set(pad.GetNetname().lstrip("/") for pad in fp.Pads())
                return sum(1 for k in nets if k and k not in self.skip and r.items.get(k))
            todo.sort(key=lambda ref: (-anchored(ref), refs.index(ref)))
            ref = todo.pop(0)
            self._why = {}
            best = self._best(ref, regions, bottom)
            if best is None:
                why = getattr(self, "_why", {})
                raise ValueError(f"{ref} : aucune place libre dans {regions} ; refus : {why}")
            cost, x, y, rot, yard, pads = best
            fp = b.fps[ref]
            fp.SetOrientationDegrees(rot)
            b.move(ref, x, y)
            self.yards[bottom].append(yard)
            for name, px1, py1, px2, py2 in pads:
                if not name:
                    continue
                net = r._id(name)
                r._rect(L, net, px1, py1, px2, py2)
                r.items.setdefault(name, []).append(
                    dict(kind="pad", layers=[L], box=(px1, py1, px2, py2), at=((px1 + px2) / 2, (py1 + py2) / 2),
                         round=False, ref=ref))
