"""Construit une carte KiCad par script, à partir de la netlist exportée du schéma.

S'exécute dans l'image KiCad (module pcbnew). Toutes les cotes sont en
millimètres, mesurées depuis le coin haut gauche de la carte, X vers la droite,
Y vers le bas. La carte part de la netlist que KiCad a exportée du schéma, pas
de la description du circuit : le schéma reste la seule source des connexions.
"""
import hashlib
import json
import os

import pcbnew

from netlist import read_netlist

MM = pcbnew.FromMM
STOCK_FOOTPRINTS = "/usr/share/kicad/footprints"

# Règles de dessin pour un circuit deux couches chez JLCPCB. Valeurs prudentes,
# plus larges que les minima annoncés par le fabricant ; à confronter à leur
# page de capacités avant la carte v0.
RULES_JLC_2L = dict(
    clearance=0.15,            # isolement minimal cuivre à cuivre
    track=0.15,                # largeur minimale de piste
    via_diameter=0.6, via_drill=0.3, annular=0.13,
    hole_clearance=0.25, hole_to_hole=0.5,
    edge_clearance=0.3,        # cuivre au bord de carte
    silk_height=0.8, silk_thickness=0.15,
    default_clearance=0.2, default_track=0.25,
)


LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS,
          "F.Fab": pcbnew.F_Fab, "B.Fab": pcbnew.B_Fab, "Edge.Cuts": pcbnew.Edge_Cuts,
          "Dwgs.User": pcbnew.Dwgs_User, "Cmts.User": pcbnew.Cmts_User}


def layer_id(name):
    """Couche par son nom interne. BOARD.GetLayerID attend le nom affiché (« F.Silkscreen »)
    et rend une couche indéfinie sans erreur pour un nom interne : on ne s'en sert pas."""
    if name not in LAYERS:
        raise KeyError(f"couche inconnue : {name}")
    return LAYERS[name]


class Board:
    def __init__(self, directory, name, netlist, fp_libs, origin=(100.0, 100.0), rules=RULES_JLC_2L,
                 title="", rev="", date=""):
        """fp_libs : {surnom: dossier .pretty} pour les bibliothèques du projet."""
        self.name = name
        self.path = os.path.join(directory, f"{name}.kicad_pcb")
        self.ox, self.oy = origin
        self.fp_libs = dict(fp_libs)
        if os.path.exists(self.path):
            os.remove(self.path)                      # on repart toujours d'une carte vide
        pcbnew.KIID.SeedGenerator(1)                  # identifiants reproductibles d'une génération à l'autre
        self.board = pcbnew.NewBoard(self.path)
        self.nets_raw, self.comps = read_netlist(netlist)
        self.net = {}                                 # nom KiCad -> NETINFO_ITEM
        self.pad_net = {}                             # (ref, broche) -> nom KiCad
        for netname, nodes in self.nets_raw.items():
            item = pcbnew.NETINFO_ITEM(self.board, netname)
            self.board.Add(item)
            self.net[netname] = item
            for node in nodes:
                self.pad_net[node] = netname
        self.fps = {}
        self.warnings = []
        self._netclasses = []
        self._rules(rules)
        tb = self.board.GetTitleBlock()
        tb.SetTitle(title)
        tb.SetRevision(rev)
        tb.SetDate(date)
        tb.SetCompany("Luciole²")

    # ----------------------------------------------------------- réglages

    def _rules(self, r):
        ds = self.board.GetDesignSettings()
        ds.m_MinClearance = MM(r["clearance"])
        ds.m_TrackMinWidth = MM(r["track"])
        ds.m_ViasMinSize = MM(r["via_diameter"])
        ds.m_MinThroughDrill = MM(r["via_drill"])
        ds.m_ViasMinAnnularWidth = MM(r["annular"])
        ds.m_HoleClearance = MM(r["hole_clearance"])
        ds.m_HoleToHoleMin = MM(r["hole_to_hole"])
        ds.m_CopperEdgeClearance = MM(r["edge_clearance"])
        ds.m_MinSilkTextHeight = MM(r["silk_height"])
        ds.m_MinSilkTextThickness = MM(r["silk_thickness"])
        nc = ds.m_NetSettings.GetDefaultNetclass()
        nc.SetClearance(MM(r["default_clearance"]))
        nc.SetTrackWidth(MM(r["default_track"]))
        nc.SetViaDiameter(MM(r["via_diameter"]))
        nc.SetViaDrill(MM(r["via_drill"]))
        self.rules = r

    def netclass(self, name, nets, track, clearance=None):
        """Classe de réseaux : largeur de piste (et isolement) pour les réseaux cités.
        Un routeur automatique lit ces largeurs ; le contrôle des règles aussi. Les classes
        sont écrites dans le fichier de projet à l'enregistrement : l'interface de script de
        KiCad 10 accepte d'en créer une, mais ne l'enregistre pas."""
        self._netclasses.append(dict(name=name, nets=[self._net(n).GetNetname() for n in nets], track=track,
                                     clearance=clearance if clearance is not None else self.rules["default_clearance"]))

    def _write_netclasses(self):
        pro = os.path.splitext(self.path)[0] + ".kicad_pro"
        with open(pro, encoding="utf-8") as f:
            data = json.load(f)
        ns = data.setdefault("net_settings", {})
        base = next(c for c in ns["classes"] if c["name"] == "Default")
        ns["classes"] = [base]
        ns["netclass_patterns"] = []
        for k, nc in enumerate(self._netclasses):
            ns["classes"].append({**base, "name": nc["name"], "track_width": nc["track"],
                                  "clearance": nc["clearance"], "priority": k})
            ns["netclass_patterns"] += [{"netclass": nc["name"], "pattern": net} for net in nc["nets"]]
        with open(pro, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def _pt(self, x, y):
        return pcbnew.VECTOR2I(MM(self.ox + x), MM(self.oy + y))

    def _net(self, name):
        for cand in (name, "/" + name):
            if cand in self.net:
                return self.net[cand]
        raise KeyError(f"réseau inconnu du schéma : {name}")

    # --------------------------------------------------------- composants

    def place(self, ref, x, y, rot=0.0, bottom=False, silk_ref=False, free_pads=()):
        """Pose l'empreinte du composant `ref`, centre en (x, y), tournée de `rot` degrés
        (sens trigonométrique à l'écran). bottom=True la pose au dos.

        Au dos, à rot=0, l'empreinte est retournée autour de son axe horizontal : vue de
        dessus, à travers la carte, sa gauche reste à gauche et son haut passe en bas.
        `rot` la tourne ensuite, toujours mesuré vu de dessus. C'est la convention de
        KiCad pour une empreinte au dos d'orientation nulle (relevé sur la carte d'essai ;
        la revue du 17 novembre 2026 avait noté, constat C8, que le code laissait croire
        l'inverse). Le sens d'un connecteur ou d'un boîtier polarisé posé au dos ne se
        déduit pas de tête : le vérifier par une assertion sur la position de ses pastilles.

        free_pads : numéros des pastilles de l'empreinte qui n'ont volontairement aucune
        broche dans le schéma. Sans cette dérogation, une telle pastille est une erreur :
        c'est le cas d'une plage thermique ou d'un blindage oubliés dans le symbole
        (constat C2 de la revue du 17 novembre 2026).

        Le repère (R1, D3...) va sur la couche de documentation, pas en sérigraphie :
        la pose automatique n'en a pas besoin et la carte est trop étroite pour les
        loger sans chevauchement. silk_ref=True le laisse en sérigraphie."""
        if ref in self.fps:
            raise ValueError(f"{ref} posé deux fois")
        comp = self.comps[ref]
        lib, _, fpname = comp["footprint"].partition(":")
        libdir = self.fp_libs.get(lib, os.path.join(STOCK_FOOTPRINTS, lib + ".pretty"))
        fp = pcbnew.FootprintLoad(libdir, fpname)
        if fp is None:
            raise KeyError(f"{ref} : empreinte introuvable {comp['footprint']}")
        fp.SetFPID(pcbnew.LIB_ID(lib, fpname))
        fp.SetReference(ref)
        fp.SetValue(comp["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + comp["uuid"]))
        fp.SetSheetname("/")
        fp.SetSheetfile(f"{self.name}.kicad_sch")
        # Tous les champs du schéma sont recopiés, invisibles : le contrôle de cohérence
        # entre carte et schéma les compare un à un.
        for key, value in comp["fields"].items():
            if key in ("Footprint", "Value", "Reference"):
                continue
            fp.SetField(key, value)
            fp.GetField(key).SetVisible(False)
        if not silk_ref:
            fp.Reference().SetLayer(pcbnew.F_Fab)
        # Hors nomenclature, hors pose, non monté : la carte reprend ce que dit le schéma,
        # et non ce que dit l'empreinte de la bibliothèque. Le contrôle de cohérence
        # compare les deux.
        fp.SetExcludedFromBOM("exclude_from_bom" in comp["flags"])
        fp.SetExcludedFromPosFiles("exclude_from_pos_files" in comp["flags"])
        fp.SetDNP("dnp" in comp["flags"])
        self.board.Add(fp)
        fp.SetPosition(self._pt(x, y))
        if bottom:
            # Le sens du retournement importe peu ici : l'orientation est imposée juste
            # après, et KiCad ramène alors l'empreinte à son retournement de base.
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        fp.SetOrientationDegrees(rot)

        wanted = {pin for (r, pin) in self.pad_net if r == ref}
        free = {str(n) for n in free_pads}
        seen, orphan, count = set(), set(), {}
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue
            count[num] = count.get(num, 0) + 1
            if (ref, num) in self.pad_net:
                pad.SetNet(self.net[self.pad_net[(ref, num)]])
                seen.add(num)
            else:
                orphan.add(num)
        if wanted - seen:
            raise ValueError(f"{ref} : broches du schéma sans pastille sur {fpname} : {sorted(wanted - seen)}")
        if orphan - free:
            raise ValueError(f"{ref} : pastilles {sorted(orphan - free)} de {fpname} sans broche dans le schéma. "
                             f"Ajouter la broche au symbole, ou déclarer la pastille libre avec free_pads.")
        if free - orphan:
            raise ValueError(f"{ref} : free_pads cite {sorted(free - orphan)}, qui ne sont pas des pastilles "
                             f"sans broche de {fpname}")
        # Une broche laissée libre dans le schéma donne un réseau « unconnected-... ». Si
        # l'empreinte a plusieurs pastilles de ce numéro, KiCad leur donne ce même réseau
        # et exige ensuite de les relier entre elles (constat C6). On le dit ici, clairement.
        shared = sorted(n for n in seen if count[n] > 1 and self.pad_net[(ref, n)].startswith("unconnected-"))
        if shared:
            raise ValueError(f"{ref} : la broche {', '.join(shared)} est libre dans le schéma, mais {fpname} a "
                             f"plusieurs pastilles de ce numéro. Les relier à un réseau (la masse pour un "
                             f"blindage ou des pattes de fixation).")
        self.fps[ref] = fp
        return fp

    def pads(self, ref, number):
        """Centres (x, y) de toutes les pastilles portant ce numéro."""
        out = []
        for pad in self.fps[ref].Pads():
            if pad.GetNumber() == str(number):
                p = pad.GetPosition()
                out.append((round(pcbnew.ToMM(p.x) - self.ox, 4), round(pcbnew.ToMM(p.y) - self.oy, 4)))
        if not out:
            raise KeyError(f"{ref} : pas de pastille {number}")
        return out

    def pad(self, ref, number):
        """Centre (x, y) de la pastille ; erreur s'il y en a plusieurs."""
        found = self.pads(ref, number)
        if len(found) != 1:
            raise ValueError(f"{ref} : {len(found)} pastilles {number}, utiliser pads()")
        return found[0]

    # --------------------------------------------------------------- cuivre

    def track(self, net, points, width, layer="F.Cu"):
        """Piste passant par les points donnés."""
        lid = layer_id(layer)
        n = self._net(net)
        for a, b in zip(points, points[1:]):
            if a == b:
                continue
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(self._pt(*a))
            t.SetEnd(self._pt(*b))
            t.SetWidth(MM(width))
            t.SetLayer(lid)
            t.SetNet(n)
            self.board.Add(t)

    def via(self, net, x, y, diameter=None, drill=None):
        v = pcbnew.PCB_VIA(self.board)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(self._pt(x, y))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(pcbnew.F_Cu, MM(diameter or self.rules["via_diameter"]))
        v.SetDrill(MM(drill or self.rules["via_drill"]))
        v.SetNet(self._net(net))
        self.board.Add(v)
        return (x, y)

    def signature(self):
        """Empreinte de la carte telle qu'elle est : composants posés, pistes et vias.
        Sert à vérifier qu'un tracé figé a bien été calculé pour cette carte-là."""
        rows = []
        for ref, fp in sorted(self.fps.items()):
            p = fp.GetPosition()
            rows.append(f"{ref} {p.x} {p.y} {fp.GetOrientationDegrees():.1f} {int(fp.IsFlipped())}")
        for t in self.board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                rows.append(f"via {t.GetNetname()} {q.x} {q.y} {t.GetWidth(pcbnew.F_Cu)}")
            else:
                a, e = sorted(((t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)))
                rows.append(f"piste {t.GetNetname()} {t.GetLayer()} {a} {e} {t.GetWidth()}")
        return hashlib.sha1("\n".join(sorted(rows)).encode()).hexdigest()[:16]

    def replay(self, path):
        """Rejoue un tracé figé par tools/gel.py : les pistes et les vias qu'un routeur
        automatique avait ajoutés. Un réseau disparu du schéma arrête la construction."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for t in data["pistes"]:
            self.track(t["net"].lstrip("/"), [tuple(t["a"]), tuple(t["b"])], t["width"], layer=t["layer"])
        for v in data["vias"]:
            self.via(v["net"].lstrip("/"), v["at"][0], v["at"][1], diameter=v["diameter"], drill=v["drill"])
        return len(data["pistes"]), len(data["vias"])

    def zone(self, net, layer, x1, y1, x2, y2, clearance=0.25, min_width=0.2, priority=0):
        """Plan de cuivre rectangulaire relié au réseau `net`. Le dessiner en retrait du
        bord de carte : le contrôle compare aussi le contour du plan au bord."""
        z = pcbnew.ZONE(self.board)
        z.SetLayer(layer_id(layer))
        z.SetNet(self._net(net))
        outline = z.Outline()
        outline.NewOutline()
        for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
            p = self._pt(x, y)
            outline.Append(p.x, p.y)
        z.SetLocalClearance(MM(clearance))
        z.SetMinThickness(MM(min_width))
        # Pastilles de surface reliées en plein au plan, freins thermiques pour les seules
        # pattes traversantes : la carte est soudée au four, et un frein thermique dont un
        # voisin coupe les branches laisse une pastille mal reliée.
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
        z.SetThermalReliefGap(MM(0.25))
        z.SetThermalReliefSpokeWidth(MM(0.3))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetAssignedPriority(priority)
        z.SetZoneName(f"{net}_{layer}")
        self.board.Add(z)
        return z

    def keepout(self, x1, y1, x2, y2, layers=("F.Cu", "B.Cu"), name="interdit"):
        """Zone interdite au cuivre : ni piste, ni via, ni plan. Sert sous l'antenne du
        module, où Espressif demande une carte sans cuivre sur toutes les couches."""
        z = pcbnew.ZONE(self.board)
        z.SetIsRuleArea(True)
        ls = pcbnew.LSET()
        for layer in layers:
            ls.AddLayer(layer_id(layer))
        z.SetLayerSet(ls)
        outline = z.Outline()
        outline.NewOutline()
        for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
            p = self._pt(x, y)
            outline.Append(p.x, p.y)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetZoneName(name)
        self.board.Add(z)
        return z

    def extent(self, ref):
        """Rectangle englobant des pastilles de `ref` : (x1, y1, x2, y2). Pour vérifier un
        placement par assertion, sans supposer le sens de l'empreinte."""
        xs, ys = [], []
        for pad in self.fps[ref].Pads():
            box = pad.GetBoundingBox()
            xs += [pcbnew.ToMM(box.GetLeft()) - self.ox, pcbnew.ToMM(box.GetRight()) - self.ox]
            ys += [pcbnew.ToMM(box.GetTop()) - self.oy, pcbnew.ToMM(box.GetBottom()) - self.oy]
        return (round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3))

    def courtyard(self, ref):
        """Rectangle d'encombrement (x1, y1, x2, y2) de `ref` : sa zone de garde, pastilles
        comprises. Sert à ranger des composants côte à côte sans qu'ils se chevauchent."""
        fp = self.fps[ref]
        fp.BuildCourtyardCaches()
        box = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
        x1, y1 = pcbnew.ToMM(box.GetLeft()) - self.ox, pcbnew.ToMM(box.GetTop()) - self.oy
        x2, y2 = pcbnew.ToMM(box.GetRight()) - self.ox, pcbnew.ToMM(box.GetBottom()) - self.oy
        for bx1, by1, bx2, by2 in (self.extent(ref),):
            x1, y1, x2, y2 = min(x1, bx1), min(y1, by1), max(x2, bx2), max(y2, by2)
        return (round(x1, 3), round(y1, 3), round(x2, 3), round(y2, 3))

    def move(self, ref, x, y):
        """Déplace un composant déjà posé : son origine va en (x, y)."""
        self.fps[ref].SetPosition(self._pt(x, y))

    def flow(self, refs, x1, y1, x2, y2, bottom=False, gap=0.25, rot=None):
        """Range des composants dans le rectangle donné, de gauche à droite puis de haut en
        bas, zone de garde contre zone de garde. `rot` : {repère: angle}. Sert au premier
        placement des petits composants d'un bloc ; les pièces dont la position compte se
        posent une à une avec place(). Erreur si le rectangle est trop petit. Rend le coin
        bas droit de ce qui a été rangé."""
        rot = rot or {}
        cx, cy, row_h, right = x1, y1, 0.0, x1
        for ref in refs:
            self.place(ref, 0.0, 0.0, rot=rot.get(ref, 0.0), bottom=bottom)
            bx1, by1, bx2, by2 = self.courtyard(ref)
            w, h = bx2 - bx1, by2 - by1
            if cx + w > x2 + 1e-6 and cx > x1:
                cx, cy, row_h = x1, cy + row_h + gap, 0.0
            if cx + w > x2 + 1e-6 or cy + h > y2 + 1e-6:
                raise ValueError(f"{ref} ne tient pas dans le rectangle ({x1}, {y1}) - ({x2}, {y2})")
            self.move(ref, cx - bx1, cy - by1)
            cx, row_h = cx + w + gap, max(row_h, h)
            right = max(right, cx - gap)
        return (round(right, 3), round(cy + row_h, 3))

    def boxes(self, ref, number):
        """Rectangles (x1, y1, x2, y2) des pastilles de `ref` portant ce numéro."""
        out = []
        for pad in self.fps[ref].Pads():
            if pad.GetNumber() == str(number):
                box = pad.GetBoundingBox()
                out.append((round(pcbnew.ToMM(box.GetLeft()) - self.ox, 3), round(pcbnew.ToMM(box.GetTop()) - self.oy, 3),
                            round(pcbnew.ToMM(box.GetRight()) - self.ox, 3), round(pcbnew.ToMM(box.GetBottom()) - self.oy, 3)))
        if not out:
            raise KeyError(f"{ref} : pas de pastille {number}")
        return out

    # ------------------------------------------------------ contour, textes

    def outline(self, x1, y1, x2, y2):
        """Contour rectangulaire de la carte."""
        s = pcbnew.PCB_SHAPE(self.board)
        s.SetShape(pcbnew.SHAPE_T_RECT)
        s.SetStart(self._pt(x1, y1))
        s.SetEnd(self._pt(x2, y2))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        self.board.Add(s)
        self.size = (x2 - x1, y2 - y1)

    def text(self, string, x, y, size=1.0, layer="F.SilkS", rot=0.0):
        t = pcbnew.PCB_TEXT(self.board)
        t.SetText(string)
        t.SetPosition(self._pt(x, y))
        t.SetLayer(layer_id(layer))
        t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
        t.SetTextThickness(MM(max(0.15, size * 0.15)))
        t.SetTextAngleDegrees(rot)
        if layer.startswith("B."):
            t.SetMirrored(True)
        self.board.Add(t)

    # ------------------------------------------------------------ écriture

    def save(self, draft=False):
        """draft=True : écrit une carte incomplète, pour regarder un placement en cours.
        La construction normale n'y recourt pas : elle exige tous les composants."""
        missing = sorted(set(self.comps) - set(self.fps))
        if missing and not draft:
            raise ValueError(f"composants du schéma non posés : {missing}")
        if missing:
            print(f"brouillon : {len(missing)} composants non posés")
        self.board.BuildConnectivity()
        pcbnew.ZONE_FILLER(self.board).Fill(self.board.Zones())
        pcbnew.SaveBoard(self.path, self.board)
        if self._netclasses:
            self._write_netclasses()
        for w in self.warnings:
            print("alerte :", w)
        print(f"écrit {self.path} : {len(self.fps)} composants, "
              f"{len(self.board.GetTracks())} pistes et vias, {len(self.board.Zones())} plans")
