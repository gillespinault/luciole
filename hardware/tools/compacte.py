"""Compacte un modèle 3D (GLB) exporté par KiCad pour l'afficher dans un navigateur.

    python3 tools/compacte.py v0/out/apercu/complet.glb v0/out/apercu/carte.glb

KiCad écrit un morceau par face : près de 17 000 pour la carte v0, trop pour un téléphone.
Ce script en fait un seul maillage par matière, en millimètres, centré sur la carte,
Y vers le haut. Il rend aussi les matières lisibles sans décor (aucune n'est laissée
métallique par défaut) et la sérigraphie opaque, sinon le vernis la recouvre.
"""
import array, json, struct, sys

def main():
    data = open(sys.argv[1], "rb").read()
    jlen = struct.unpack_from("<I", data, 12)[0]
    j = json.loads(data[20:20 + jlen])
    bin0 = 20 + jlen + 8
    FMT = {5126: "f", 5123: "H", 5125: "I", 5121: "B"}; NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}

    def acc(i):
        a = j["accessors"][i]; bv = j["bufferViews"][a["bufferView"]]
        fmt = FMT[a["componentType"]]; nc = NC[a["type"]]; size = struct.calcsize(fmt) * nc
        off = bin0 + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride") or size
        arr = array.array(fmt)
        if stride == size: arr.frombytes(data[off:off + a["count"] * size])
        else:
            for k in range(a["count"]): arr.frombytes(data[off + k * stride:off + k * stride + size])
        return arr

    def rot(q):
        x, y, z, w = q
        return (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
                2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
                2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y))

    def mul(A, B): return tuple(sum(A[3 * r + k] * B[3 * k + c] for k in range(3)) for r in range(3) for c in range(3))
    def app(A, v): return tuple(A[3 * r] * v[0] + A[3 * r + 1] * v[1] + A[3 * r + 2] * v[2] for r in range(3))

    mats = j["materials"]
    def cle(mi):
        p = mats[mi].get("pbrMetallicRoughness", {})
        c = [round(v, 3) for v in p.get("baseColorFactor", [1, 1, 1, 1])]
        return (tuple(c), mats[mi].get("alphaMode", "OPAQUE"), p.get("metallicFactor"), p.get("roughnessFactor"))

    groupes = {}      # clé de matière -> (positions, normales, indices)
    suivi = {}        # étendue par nom de nœud de premier niveau, pour contrôle
    def visite(ni, R, t, nom):
        nd = j["nodes"][ni]
        Rn = rot(nd["rotation"]) if "rotation" in nd else (1, 0, 0, 0, 1, 0, 0, 0, 1)
        tn = nd.get("translation", (0, 0, 0))
        R2 = mul(R, Rn); t2 = tuple(a + b for a, b in zip(app(R, tn), t))
        nom = nom or nd.get("name")
        if "mesh" in nd:
            for pr in j["meshes"][nd["mesh"]]["primitives"]:
                P = acc(pr["attributes"]["POSITION"]); N = acc(pr["attributes"]["NORMAL"]); I = acc(pr["indices"])
                gp, gn, gi = groupes.setdefault(cle(pr["material"]), (array.array("f"), array.array("f"), array.array("I")))
                base = len(gp) // 3
                r00, r01, r02, r10, r11, r12, r20, r21, r22 = R2; tx, ty, tz = t2
                e = suivi.setdefault(nom, [1e9, 1e9, 1e9, -1e9, -1e9, -1e9])
                for k in range(0, len(P), 3):
                    x, y, z = P[k], P[k + 1], P[k + 2]
                    X = (r00 * x + r01 * y + r02 * z + tx) * 1000.0
                    Y = (r10 * x + r11 * y + r12 * z + ty) * 1000.0
                    Z = (r20 * x + r21 * y + r22 * z + tz) * 1000.0
                    gp.extend((X, Y, Z))
                    if X < e[0]: e[0] = X
                    if Y < e[1]: e[1] = Y
                    if Z < e[2]: e[2] = Z
                    if X > e[3]: e[3] = X
                    if Y > e[4]: e[4] = Y
                    if Z > e[5]: e[5] = Z
                    x, y, z = N[k], N[k + 1], N[k + 2]
                    gn.extend((r00 * x + r01 * y + r02 * z, r10 * x + r11 * y + r12 * z, r20 * x + r21 * y + r22 * z))
                gi.extend(base + v for v in I)
        for c in nd.get("children", []): visite(c, R2, t2, nom if ni != racine else None)

    racine = j["scenes"][j.get("scene", 0)]["nodes"][0]
    sys.setrecursionlimit(10000)
    visite(racine, (1, 0, 0, 0, 1, 0, 0, 0, 1), (0, 0, 0), None)

    # Centrage sur le milieu de l'étendue, en x et en z.
    cx = (min(e[0] for e in suivi.values()) + max(e[3] for e in suivi.values())) / 2
    cz = (min(e[2] for e in suivi.values()) + max(e[5] for e in suivi.values())) / 2
    for gp, _, _ in groupes.values():
        for k in range(0, len(gp), 3):
            gp[k] -= cx; gp[k + 2] -= cz
    for e in suivi.values():
        e[0] -= cx; e[3] -= cx; e[2] -= cz; e[5] -= cz

    out = {"asset": {"version": "2.0", "generator": "compacte.py, d'après KiCad"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0, "name": "carte"}], "meshes": [{"primitives": []}], "materials": [], "accessors": [], "bufferViews": [], "buffers": []}
    blob = bytearray()
    def vue(arr, cible):
        off = len(blob); b = arr.tobytes(); blob.extend(b)
        while len(blob) % 4: blob.append(0)
        out["bufferViews"].append({"buffer": 0, "byteOffset": off, "byteLength": len(b), "target": cible})
        return len(out["bufferViews"]) - 1
    tri = 0
    for (coul, alpha, metal, rug), (gp, gn, gi) in sorted(groupes.items(), key=lambda kv: kv[0][1] == "BLEND"):
        mn = [min(gp[k::3]) for k in range(3)]; mx = [max(gp[k::3]) for k in range(3)]
        out["accessors"].append({"bufferView": vue(gp, 34962), "componentType": 5126, "count": len(gp) // 3, "type": "VEC3", "min": mn, "max": mx})
        out["accessors"].append({"bufferView": vue(gn, 34962), "componentType": 5126, "count": len(gn) // 3, "type": "VEC3"})
        out["accessors"].append({"bufferView": vue(gi, 34963), "componentType": 5125, "count": len(gi), "type": "SCALAR"})
        n = len(out["accessors"])
        blanc = alpha == "BLEND" and coul[0] > 0.9      # sérigraphie : rendue opaque, sinon le vernis la recouvre
        m = {"pbrMetallicRoughness": {"baseColorFactor": [coul[0], coul[1], coul[2], 1.0 if (blanc or alpha != "BLEND") else coul[3]],
                                      "metallicFactor": 0.35 if metal == 1.0 else 0.05, "roughnessFactor": 0.45 if metal == 1.0 else (rug or 0.7)},
             "doubleSided": True}
        if alpha == "BLEND" and not blanc: m["alphaMode"] = "BLEND"
        out["materials"].append(m)
        out["meshes"][0]["primitives"].append({"attributes": {"POSITION": n - 3, "NORMAL": n - 2}, "indices": n - 1, "material": len(out["materials"]) - 1})
        tri += len(gi) // 3
    out["buffers"].append({"byteLength": len(blob)})
    js = json.dumps(out, separators=(",", ":")).encode()
    while len(js) % 4: js += b" "
    with open(sys.argv[2], "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack("<I4s", len(js), b"JSON")); f.write(js)
        f.write(struct.pack("<I4s", len(blob), b"BIN\0")); f.write(blob)
    tout = [min(e[k] for e in suivi.values()) for k in range(3)] + [max(e[k] for e in suivi.values()) for k in range(3, 6)]
    print("matières :", len(out["materials"]), "; triangles :", tri, "; sommets :", sum(len(g[0]) // 3 for g in groupes.values()), "; taille :", round((len(js) + len(blob)) / 1e6, 2), "Mo")
    print("étendue totale (mm) :", [round(v, 2) for v in tout])

main()
