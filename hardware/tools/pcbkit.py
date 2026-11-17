"""Construit une carte KiCad par script, à partir de la netlist exportée du schéma.

S'exécute dans l'image KiCad (module pcbnew). Toutes les cotes sont en
millimètres, mesurées depuis le coin haut gauche de la carte, X vers la droite,
Y vers le bas. La carte part de la netlist que KiCad a exportée du schéma, pas
de la description du circuit : le schéma reste la seule source des connexions.
"""
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

    def _pt(self, x, y):
        return pcbnew.VECTOR2I(MM(self.ox + x), MM(self.oy + y))

    def _net(self, name):
        for cand in (name, "/" + name):
            if cand in self.net:
                return self.net[cand]
        raise KeyError(f"réseau inconnu du schéma : {name}")

    # --------------------------------------------------------- composants

    def place(self, ref, x, y, rot=0.0, bottom=False, silk_ref=False):
        """Pose l'empreinte du composant `ref`, centre en (x, y), tournée de `rot` degrés
        (sens trigonométrique à l'écran). bottom=True la pose au dos.

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
        self.board.Add(fp)
        fp.SetPosition(self._pt(x, y))
        if bottom:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(rot)

        wanted = {pin for (r, pin) in self.pad_net if r == ref}
        seen = set()
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue
            if (ref, num) in self.pad_net:
                pad.SetNet(self.net[self.pad_net[(ref, num)]])
                seen.add(num)
            else:
                self.warnings.append(f"{ref} : pastille {num} sans broche dans le schéma")
        if wanted - seen:
            raise ValueError(f"{ref} : broches du schéma sans pastille sur {fpname} : {sorted(wanted - seen)}")
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
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(MM(0.25))
        z.SetThermalReliefSpokeWidth(MM(0.3))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetAssignedPriority(priority)
        z.SetZoneName(f"{net}_{layer}")
        self.board.Add(z)
        return z

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

    def save(self):
        missing = sorted(set(self.comps) - set(self.fps))
        if missing:
            raise ValueError(f"composants du schéma non posés : {missing}")
        self.board.BuildConnectivity()
        pcbnew.ZONE_FILLER(self.board).Fill(self.board.Zones())
        pcbnew.SaveBoard(self.path, self.board)
        for w in self.warnings:
            print("alerte :", w)
        print(f"écrit {self.path} : {len(self.fps)} composants, "
              f"{len(self.board.GetTracks())} pistes et vias, {len(self.board.Zones())} plans")
