"""Donne un volume simple aux pièces d'une carte qui n'ont pas de modèle 3D.

    tools/kicad python3 tools/volumes.py v0/v0.kicad_pcb v0/out/apercu

L'image KiCad n'a qu'une partie des modèles 3D, et nos empreintes dessinées à la main n'en
ont aucun : sans rien faire, l'export 3D sort une carte sans LED, sans module radio et
sans connecteurs. Pour chaque pièce sans modèle dont la valeur figure dans la table
VOLUMES, ce script écrit un pavé à l'emprise de son contour de fabrication (couche Fab),
de la hauteur donnée par la table. Les pavés vont dans <dossier>/volumes.step, et une
copie de la carte, <dossier>/<nom>-apercu.kicad_pcb, les porte par une empreinte sans
pastille ni texte visible, ajoutée au coin de la carte. Le projet lui-même n'est pas touché.

Repère du fichier STEP : celui d'un modèle KiCad posé à ce coin, face avant.
x vers la droite, y vers le haut de la feuille, z = 0 sur le dessus de la carte.
"""
import os, re, sys

import pcbnew

# valeur de la pièce -> hauteur (mm), couleur, nom. « ~ » : hauteur approximative, non
# relevée dans une fiche ; à vérifier avant de dessiner un boîtier au plus près.
VOLUMES = {
    "SK6812MINI-B-012": (1.1, (0.93, 0.93, 0.88), "LED"),                      # fiche OPSCO : 3,7 x 3,5 x 1,1
    "ESP32-C6-MINI-1":  (2.4, (0.74, 0.75, 0.78), "module radio"),             # fiche Espressif : 13,2 x 16,6 x 2,4
    "TYPE-C-31-M-12":   (3.2, (0.72, 0.73, 0.75), "USB-C"),
    "A2001WR-S-2P":     (5.0, (0.93, 0.91, 0.84), "connecteur de batterie ~"),
    "Grove":            (5.0, (0.93, 0.91, 0.84), "Grove ~"),
    "1uH FXL0420":      (2.0, (0.24, 0.24, 0.26), "bobine"),
    "TP4056-42-ESOP8":  (1.5, (0.10, 0.10, 0.11), "chargeur"),
    "SKRTLAE010":       (1.6, (0.70, 0.71, 0.73), "bouton de bord ~"),
}
MODELES = os.environ.get("KICAD10_3DMODEL_DIR", "/usr/share/kicad/3dmodels")

class Step:
    def __init__(self): self.lines = []; self.n = 0
    def e(self, text):
        self.n += 1; self.lines.append(f"#{self.n} = {text};"); return f"#{self.n}"

def f(v): return ("%.6f" % v).rstrip("0").rstrip(".") + ("." if "." not in ("%.6f" % v).rstrip("0").rstrip(".") else "")

def pave(s, nom, x0, y0, z0, x1, y1, z1):
    X, Y, Z = (x0, x1), (y0, y1), (z0, z1)
    pt = {}; vx = {}
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                pt[i, j, k] = s.e(f"CARTESIAN_POINT('',({f(X[i])},{f(Y[j])},{f(Z[k])}))")
                vx[i, j, k] = s.e(f"VERTEX_POINT('',{pt[i, j, k]})")
    dirs = [s.e("DIRECTION('',(1.,0.,0.))"), s.e("DIRECTION('',(0.,1.,0.))"), s.e("DIRECTION('',(0.,0.,1.))")]
    ndirs = [s.e("DIRECTION('',(-1.,0.,0.))"), s.e("DIRECTION('',(0.,-1.,0.))"), s.e("DIRECTION('',(0.,0.,-1.))")]
    edge = {}
    for axe in range(3):
        for a in (0, 1):
            for b in (0, 1):
                lo = [a, b]; lo.insert(axe, 0); hi = [a, b]; hi.insert(axe, 1); lo, hi = tuple(lo), tuple(hi)
                vec = s.e(f"VECTOR('',{dirs[axe]},1.)")
                line = s.e(f"LINE('',{pt[lo]},{vec})")
                edge[lo, hi] = s.e(f"EDGE_CURVE('',{vx[lo]},{vx[hi]},{line},.T.)")
    faces = []
    boucles = [  # sommets dans le sens direct vu de l'extérieur, normale, direction de référence
        ([(0,0,1),(1,0,1),(1,1,1),(0,1,1)], dirs[2], dirs[0]),
        ([(0,0,0),(0,1,0),(1,1,0),(1,0,0)], ndirs[2], dirs[0]),
        ([(1,0,0),(1,1,0),(1,1,1),(1,0,1)], dirs[0], dirs[1]),
        ([(0,0,0),(0,0,1),(0,1,1),(0,1,0)], ndirs[0], dirs[1]),
        ([(0,1,0),(0,1,1),(1,1,1),(1,1,0)], dirs[1], dirs[2]),
        ([(0,0,0),(1,0,0),(1,0,1),(0,0,1)], ndirs[1], dirs[2]),
    ]
    for sommets, normale, ref in boucles:
        oes = []
        for q in range(4):
            a, b = sommets[q], sommets[(q + 1) % 4]
            if (a, b) in edge: oes.append(s.e(f"ORIENTED_EDGE('',*,*,{edge[a, b]},.T.)"))
            else: oes.append(s.e(f"ORIENTED_EDGE('',*,*,{edge[b, a]},.F.)"))
        loop = s.e(f"EDGE_LOOP('',({','.join(oes)}))")
        bound = s.e(f"FACE_OUTER_BOUND('',{loop},.T.)")
        ax = s.e(f"AXIS2_PLACEMENT_3D('',{pt[sommets[0]]},{normale},{ref})")
        plane = s.e(f"PLANE('',{ax})")
        faces.append(s.e(f"ADVANCED_FACE('',({bound}),{plane},.T.)"))
    shell = s.e(f"CLOSED_SHELL('',({','.join(faces)}))")
    return s.e(f"MANIFOLD_SOLID_BREP('{nom}',{shell})")

def a_un_modele(f):
    for m in f.Models():
        chemin = re.sub(r"\$\{KICAD\d*_3DMODEL_DIR\}", MODELES, m.m_Filename)
        base = os.path.splitext(chemin)[0]
        if any(os.path.exists(base + ext) for ext in (".step", ".stp", ".STEP", ".STP")): return True
    return False

def contour(f):
    """Étendue du contour de fabrication de l'empreinte, en millimètres de la feuille."""
    couche = pcbnew.B_Fab if f.IsFlipped() else pcbnew.F_Fab
    x0 = y0 = 1e9; x1 = y1 = -1e9
    for g in f.GraphicalItems():
        if g.GetLayer() != couche or g.GetClass() != "PCB_SHAPE": continue
        e = g.GetBoundingBox()
        x0 = min(x0, pcbnew.ToMM(e.GetLeft())); y0 = min(y0, pcbnew.ToMM(e.GetTop()))
        x1 = max(x1, pcbnew.ToMM(e.GetRight())); y1 = max(y1, pcbnew.ToMM(e.GetBottom()))
    return None if x0 > x1 else (x0, y0, x1, y1)

def main():
    carte, dossier = sys.argv[1], sys.argv[2]
    b = pcbnew.LoadBoard(carte)
    epaisseur = pcbnew.ToMM(b.GetDesignSettings().GetBoardThickness())
    bord = b.GetBoardEdgesBoundingBox()
    ox, oy = pcbnew.ToMM(bord.GetLeft()), pcbnew.ToMM(bord.GetTop())      # coin de la carte : origine des volumes
    s = Step()
    app = s.e("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
    s.e(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,{app})")
    pctx = s.e(f"PRODUCT_CONTEXT('',{app},'mechanical')")
    prod = s.e(f"PRODUCT('volumes','volumes','',({pctx}))")
    s.e(f"PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,({prod}))")
    pdf = s.e(f"PRODUCT_DEFINITION_FORMATION('','',{prod})")
    pdc = s.e(f"PRODUCT_DEFINITION_CONTEXT('part definition',{app},'design')")
    pd = s.e(f"PRODUCT_DEFINITION('design','',{pdf},{pdc})")
    pds = s.e(f"PRODUCT_DEFINITION_SHAPE('','',{pd})")
    mm = s.e("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
    rad = s.e("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
    sr = s.e("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
    unc = s.e(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),{mm},'distance_accuracy_value','confusion accuracy')")
    ctx = s.e(f"( GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({unc})) GLOBAL_UNIT_ASSIGNED_CONTEXT(({mm},{rad},{sr})) REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY') )")
    o = s.e("CARTESIAN_POINT('',(0.,0.,0.))"); dz = s.e("DIRECTION('',(0.,0.,1.))"); dx = s.e("DIRECTION('',(1.,0.,0.))")
    ax0 = s.e(f"AXIS2_PLACEMENT_3D('',{o},{dz},{dx})")
    solides, styles, oublies = [], [], []
    for fp in sorted(b.GetFootprints(), key=lambda fp: fp.GetReference()):
        ref, val = fp.GetReference(), fp.GetValue()
        if a_un_modele(fp): continue
        c = contour(fp)
        if val not in VOLUMES or c is None:
            if not fp.GetReference().rstrip("0123456789") in ("TP", "JP"): oublies.append(f"{ref} ({val})")
            continue
        h, coul, nom = VOLUMES[val]
        x0, y0, x1, y1 = c
        z0, z1 = (-epaisseur - h, -epaisseur) if fp.IsFlipped() else (0.0, h)
        brep = pave(s, ref, x0 - ox, oy - y1, z0, x1 - ox, oy - y0, z1)
        col = s.e(f"COLOUR_RGB('',{f(coul[0])},{f(coul[1])},{f(coul[2])})")
        fasc = s.e(f"FILL_AREA_STYLE_COLOUR('',{col})")
        fas = s.e(f"FILL_AREA_STYLE('',({fasc}))")
        ssfa = s.e(f"SURFACE_STYLE_FILL_AREA({fas})")
        sss = s.e(f"SURFACE_SIDE_STYLE('',({ssfa}))")
        ssu = s.e(f"SURFACE_STYLE_USAGE(.BOTH.,{sss})")
        psa = s.e(f"PRESENTATION_STYLE_ASSIGNMENT(({ssu}))")
        styles.append(s.e(f"STYLED_ITEM('color',({psa}),{brep})"))
        solides.append(brep)
        print(f"  {ref:5} {nom:26} {x1 - x0:5.1f} x {y1 - y0:5.1f} x {h:3.1f} mm, {'dos' if fp.IsFlipped() else 'avant'}")
    if not solides:
        print("aucune pièce sans modèle"); return
    rep = s.e(f"ADVANCED_BREP_SHAPE_REPRESENTATION('',({ax0},{','.join(solides)}),{ctx})")
    s.e(f"SHAPE_DEFINITION_REPRESENTATION({pds},{rep})")
    s.e(f"MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION('',({','.join(styles)}),{ctx})")
    os.makedirs(dossier, exist_ok=True)
    step = os.path.abspath(os.path.join(dossier, "volumes.step"))
    with open(step, "w", encoding="ascii") as out:
        out.write("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('volumes simples des pieces sans modele'),'2;1');\n"
                  "FILE_NAME('volumes.step','',(''),(''),'','','');\n"
                  "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\nENDSEC;\nDATA;\n")
        out.write("\n".join(s.lines)); out.write("\nENDSEC;\nEND-ISO-10303-21;\n")
    porte = pcbnew.FOOTPRINT(b)
    porte.SetReference("VOLUMES"); porte.SetValue("volumes simples")
    porte.SetPosition(pcbnew.VECTOR2I(bord.GetLeft(), bord.GetTop()))
    porte.Reference().SetVisible(False); porte.Value().SetVisible(False)
    porte.SetAttributes(pcbnew.FP_SMD | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    m = pcbnew.FP_3DMODEL(); m.m_Filename = step
    porte.Models().push_back(m)
    b.Add(porte)
    nom = os.path.splitext(os.path.basename(carte))[0]
    pcbnew.SaveBoard(os.path.join(dossier, nom + "-apercu.kicad_pcb"), b)
    print(len(solides), "volumes écrits dans", step)
    if oublies: print("sans modèle ni volume (à ajouter à la table VOLUMES) :", ", ".join(oublies))

main()
