#!/usr/bin/env python3
"""Banc d'essai du firmware sur l'ordinateur : le vrai main.c, une copie par luciole.

    python3 simulation/essai.py              tous les essais, une ligne de bilan chacun
    python3 simulation/essai.py vote ligne   quelques essais
    python3 simulation/essai.py -v vote      avec le journal des lucioles

Le banc compile sim.c (qui inclut main.c) avec un faux ESP-IDF, charge la
bibliothèque une fois par luciole, fait avancer le temps par pas de 10 ms et
porte les trames de l'une à l'autre. Radio : chaque trame est perdue avec une
probabilité donnée ; deux trames entendues dans le même pas de 10 ms par une
luciole y sont perdues toutes les deux (plus sévère que la réalité, où une
trame dure 3 à 10 ms) ; une luciole qui émet n'entend rien pendant ce pas.
« voisinage » dit qui entend qui : toute la pièce, ou une ligne où chacune
n'entend que ses voisines.

Ce que le banc ne dit pas : la vraie radio (portée, brouillage du Wi-Fi), les
pilotes d'ESP-IDF, l'USB, le courant du ruban.
"""
import ctypes
import os
import random
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
ENTETES = """freertos/FreeRTOS.h freertos/task.h freertos/queue.h esp_log.h esp_timer.h esp_random.h esp_wifi.h
esp_now.h esp_event.h esp_netif.h esp_mac.h nvs_flash.h nvs.h esp_system.h driver/gpio.h driver/usb_serial_jtag.h
driver/usb_serial_jtag_vfs.h led_strip.h""".split()
LEDS_MAX, CASES = 144, 22
PAS = 10_000                                # µs
TYPES = {0: "balises", 2: "ondes", 4: "votes"}


class Etat(ctypes.Structure):
    _fields_ = [(n, ctypes.c_int) for n in
                "together near playing leds scene scene_set arg epoch seed known master expired age_s mine n".split()] + \
               [("counts", ctypes.c_int * CASES), ("team", ctypes.c_int), ("table", ctypes.c_int), ("crowd", ctypes.c_int),
                ("px", (ctypes.c_uint8 * 3) * LEDS_MAX)]


def compile_(tmp):
    inc = os.path.join(tmp, "inc")
    for h in ENTETES:
        os.makedirs(os.path.join(inc, os.path.dirname(h)), exist_ok=True)
        with open(os.path.join(inc, h), "w") as f:
            f.write('#include "faux_idf.h"\n')
    with open(os.path.join(inc, "sdkconfig.h"), "w") as f:
        f.write("#define CONFIG_IDF_TARGET_ESP32C6 1\n")
    so = os.path.join(tmp, "luciole.so")
    subprocess.run(["gcc", "-std=gnu17", "-O1", "-g", "-shared", "-fPIC", "-Wall", "-Wextra", "-Wshadow",
                    "-Wno-unused-parameter", "-Wno-unused-function", "-I", inc, "-I", ICI,
                    os.path.join(ICI, "sim.c"), "-lm", "-o", so], check=True)
    return so


class Luciole:
    copies = 0

    def __init__(self, monde, mac, graine):
        self.mac = bytes(mac)
        self.nom = "%02x%02x" % (mac[4], mac[5])
        # Une copie du fichier par luciole : chargée sous un autre nom, elle a ses propres variables.
        # Le numéro ne resserre jamais : recopier sur un fichier déjà chargé corromprait la luciole qui s'en sert.
        Luciole.copies += 1
        chemin = os.path.join(monde.tmp, "l%d.so" % Luciole.copies)
        shutil.copy(monde.so, chemin)
        self.lib = ctypes.CDLL(chemin)
        self.lib.sim_step.argtypes = [ctypes.c_int64]
        self.lib.sim_boot.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_int64, ctypes.c_int]
        self.lib.sim_rx.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int64]
        self.lib.sim_console.argtypes = [ctypes.c_char_p]
        self.tampon = ctypes.create_string_buffer(65536)
        self.allumee = True
        self.lib.sim_boot(self.mac, graine, monde.t, int(monde.bavard))
        self.sortie()

    def cmd(self, ligne):
        self.lib.sim_console(ligne.encode())

    def sortie(self):
        self.lib.sim_out(self.tampon, len(self.tampon))
        return self.tampon.value.decode("utf-8", "replace")

    def etat(self):
        e = Etat()
        self.lib.sim_get(ctypes.byref(e))
        return e


class Monde:
    """voisinage(i, j) -> vrai si i entend j. pertes : probabilité qu'une trame se perde."""

    def __init__(self, so, tmp, n, pertes=0.0, voisinage=None, collisions=True, graine=1, bavard=False):
        self.so, self.tmp, self.bavard = so, tmp, bavard
        self.rnd = random.Random(graine)
        self.t = 1_000_000
        self.pertes, self.voisinage, self.collisions = pertes, voisinage, collisions
        self.l = []
        self.trames = {}                    # type -> [nombre, octets]
        for _ in range(n):
            self.ajoute()

    def ajoute(self, mac=None):
        mac = mac or bytes([0x02, 0, self.rnd.randrange(256), self.rnd.randrange(256), self.rnd.randrange(256), self.rnd.randrange(256)])
        self.l.append(Luciole(self, mac, self.rnd.randrange(1 << 30)))
        return self.l[-1]

    def pas(self):
        self.t += PAS
        emises = []
        buf = ctypes.create_string_buffer(256)
        for i, a in enumerate(self.l):
            if not a.allumee:
                continue
            a.lib.sim_step(self.t)
            while True:
                n = a.lib.sim_tx(buf)
                if not n:
                    break
                emises.append((i, buf.raw[:n]))
                c = self.trames.setdefault(buf.raw[3], [0, 0])
                c[0] += 1
                c[1] += n
            if self.bavard:
                s = a.sortie()
                if s.strip():
                    print("\n".join("  [%s %7.2f] %s" % (a.nom, self.t / 1e6, x) for x in s.splitlines() if x.strip()))
        if not emises:
            return
        parle = {i for i, _ in emises}
        for j, b in enumerate(self.l):
            if not b.allumee or j in parle:
                continue
            recues = [(i, d) for i, d in emises if (self.voisinage is None or self.voisinage(j, i))]
            if self.collisions and len(recues) > 1:
                continue
            for i, d in recues:
                if self.rnd.random() >= self.pertes:
                    b.lib.sim_rx(self.l[i].mac, -60, d, len(d), self.t + 3000)

    def tourne(self, secondes, jusqua=None, chaque=None):
        """Avance de `secondes`, ou jusqu'à ce que jusqua() soit vrai. Rend le temps écoulé, ou None si jamais vrai."""
        debut = self.t
        fin = self.t + int(secondes * 1e6)
        while self.t < fin:
            self.pas()
            if chaque:
                chaque()
            if jusqua and (self.t - debut) % 100_000 == 0 and jusqua():
                return (self.t - debut) / 1e6
        return None if jusqua else secondes

    def vivantes(self):
        return [a for a in self.l if a.allumee]

    def occupation(self, secondes):
        """Part du temps d'antenne : 250 kbit/s, 43 octets d'en-têtes et 1 ms de préambule par trame (hypothèses de l'étude)."""
        return {TYPES.get(k, str(k)): (c[0] / secondes, 100 * c[0] * (1e-3 + (c[1] / c[0] + 43) * 8 / 250e3) / secondes)
                for k, c in sorted(self.trames.items()) if c[0]}


# ---------------------------------------------------------------- essais
def en_ligne(portee):
    return lambda i, j: abs(i - j) <= portee


def decompte_vrai(m, cases):
    c = [0] * cases
    for a in m.vivantes():
        c[a.etat().mine] += 1
    return c


def tous_d_accord(m, cases, qui=None):
    vrai = decompte_vrai(m, cases)
    return all(list(a.etat().counts[:cases]) == vrai for a in (qui or m.vivantes()))


def essai_ensemble(F):
    """Deux lucioles côte à côte qui perdent des balises : ne plus retomber « seule »."""
    out = []
    for n, pertes, minutes in ((2, 0.20, 60), (2, 0.30, 60), (5, 0.20, 20)):
        m = F(n, pertes=pertes, collisions=False)
        m.tourne(20)
        avant = [a.etat().together for a in m.l]
        chutes = [0]

        def compte():
            if m.t % 100_000:
                return
            for k, a in enumerate(m.l):
                e = a.etat().together
                if avant[k] and not e:
                    chutes[0] += 1
                avant[k] = e
        m.tourne(minutes * 60, chaque=compte)
        out.append(("%d lucioles, %d %% de balises perdues, %d min : retours à « seule »" % (n, pertes * 100, minutes), chutes[0] == 0, str(chutes[0])))
    # Une voisine qui s'éteint : l'arc-en-ciel revient, après une dizaine de secondes.
    m = F(2, pertes=0.05, collisions=False)
    m.tourne(20)
    m.l[1].allumee = False
    d = m.tourne(30, jusqua=lambda: not m.l[0].etat().together)
    out.append(("la voisine s'éteint : « seule » après", d is not None and 8 <= d <= 14, "%s s" % d))
    return out


def essai_onde(F):
    m = F(5, pertes=0.10)
    m.tourne(15)
    m.l[0].cmd("clic")
    d = m.tourne(2, jusqua=lambda: all(a.etat().playing for a in m.l))
    fin = m.tourne(8, jusqua=lambda: not any(a.etat().playing for a in m.l))
    m.tourne(0.3)
    ambre = all(p[0] >= p[1] > p[2] or (p[0] == p[1] == p[2] == 0) or p[2] == 0 for a in m.l for p in [tuple(a.etat().px[4])])
    return [("onde : jouée par toutes après", d is not None and d <= 0.6, "%s s" % d),
            ("onde : toutes revenues à l'ambre après", fin is not None and 4.5 <= (d or 0) + fin <= 5.5 and ambre, "%.1f s" % ((d or 0) + (fin or 99)))]


def essai_equipes(F):
    out = []
    for n, k in ((15, 3), (20, 4), (20, 5), (13, 3)):
        m = F(n, pertes=0.10)
        m.tourne(12)
        m.l[0].cmd("scene equipes %d" % k)
        d = m.tourne(10, jusqua=lambda: all(a.etat().scene == 1 and a.etat().epoch == m.l[0].etat().epoch for a in m.l))
        tailles = [0] * k
        for a in m.l:
            tailles[a.etat().team] += 1
        out.append(("%d lucioles en %d équipes : adoptée après" % (n, k), d is not None and d <= 1.5, "%s s" % d))
        out.append(("%d lucioles en %d équipes : effectifs" % (n, k), max(tailles) - min(tailles) <= (1 if n % k else 0), "/".join(map(str, tailles))))
    # Une retardataire, puis le retour à la normale.
    tard = m.ajoute()
    d = m.tourne(10, jusqua=lambda: tard.etat().scene == 1)
    out.append(("une luciole allumée après coup prend la scène après", d is not None and d <= 2, "%s s" % d))
    m.l[0].cmd("scene normale")
    d = m.tourne(10, jusqua=lambda: all(a.etat().scene == 0 for a in m.l))
    out.append(("retour à la normale après", d is not None and d <= 1.5, "%s s" % d))
    return out


def vote(F, n, scene, cases, pertes, voisinage=None, duree_clics=8, titre=""):
    m = F(n, pertes=pertes, voisinage=voisinage)
    m.tourne(12)
    m.trames.clear()
    t0 = m.t
    m.l[0].cmd("scene " + scene)
    d_scene = m.tourne(30, jusqua=lambda: all(a.etat().scene >= 2 and a.etat().epoch == m.l[0].etat().epoch for a in m.l))
    clics = sorted((m.t + m.rnd.randrange(int(duree_clics * 1e6)), i) for i in range(n) for _ in range(m.rnd.choice([0, 1, 1, 2, 3, 5] if cases > 3 else [0, 1, 1, 2, 3])))

    def clique():
        while clics and clics[0][0] <= m.t:
            m.l[clics.pop(0)[1]].cmd("clic")
    m.tourne(duree_clics + 0.05, chaque=clique)
    d_maitre = m.tourne(120, jusqua=lambda: tous_d_accord(m, cases, [m.l[0]]))
    d_tous = 0 if tous_d_accord(m, cases) else m.tourne(120, jusqua=lambda: tous_d_accord(m, cases))
    occ = m.occupation((m.t - t0) / 1e6)
    vrai = decompte_vrai(m, cases)
    detail = "décompte %s" % vrai + " | canal : " + ", ".join("%s %.0f/s %.1f %%" % (k, v[0], v[1]) for k, v in occ.items())
    return m, [("%s : scène adoptée par toutes après" % titre, d_scene is not None, "%s s" % d_scene),
               ("%s : décompte exact chez le maître, après le dernier appui" % titre, d_maitre is not None, "%s s" % d_maitre),
               ("%s : décompte exact chez toutes, ensuite" % titre, d_tous is not None, "%s s" % d_tous),
               ("%s : charge" % titre, True, detail)]


def essai_vote(F):
    m, out = vote(F, 20, "vote", 3, 0.20, titre="vote, 20 dans une pièce, 20 % de pertes")
    # Une luciole redémarre : le groupe lui rend son vote.
    k = next(i for i, a in enumerate(m.l) if i and a.etat().mine)
    avant = m.l[k].etat().mine
    mac = m.l[k].mac
    m.l[k].allumee = False
    m.tourne(1)
    m.l[k] = Luciole(m, mac, 12345)
    d = m.tourne(20, jusqua=lambda: m.l[k].etat().scene == 2 and m.l[k].etat().mine == avant and tous_d_accord(m, 3))
    out.append(("une luciole redémarre : elle retrouve son vote, décompte intact, après", d is not None and d <= 5, "%s s" % d))
    return out


def essai_jauge(F):
    return vote(F, 20, "jauge", 12, 0.20, titre="jauge, 20 dans une pièce, 20 % de pertes")[1]


def essai_ligne(F):
    """De proche en proche : 12 lucioles en ligne, chacune n'entend que deux voisines de chaque côté."""
    return vote(F, 12, "vote", 3, 0.10, voisinage=en_ligne(2), titre="vote, 12 en ligne (6 sauts), 10 % de pertes")[1]


def essai_salle(F):
    return vote(F, 60, "jauge", 12, 0.10, titre="jauge, 60 dans une pièce, 10 % de pertes")[1]


def essai_maitre(F):
    """Le maître s'éteint : la scène s'efface seule au bout de dix minutes."""
    m = F(5, pertes=0.10)
    m.tourne(12)
    m.l[0].cmd("scene vote")
    m.tourne(5)
    for a in m.l[1:3]:
        a.cmd("clic")
    m.tourne(60)
    ages = [a.etat().age_s for a in m.l[1:]]
    tient = all(a.etat().scene == 2 for a in m.l[1:]) and max(ages) <= 8
    m.l[0].allumee = False
    d = m.tourne(700, jusqua=lambda: all(a.etat().scene == 0 for a in m.l[1:]))
    return [("maître présent : la scène tient, âge entendu faible", tient, "âges %s s" % ages),
            ("maître éteint : toutes redevenues normales après", d is not None and 595 <= d <= 625, "%s s" % d)]


ESSAIS = {"ensemble": essai_ensemble, "onde": essai_onde, "equipes": essai_equipes, "vote": essai_vote,
          "jauge": essai_jauge, "ligne": essai_ligne, "salle": essai_salle, "maitre": essai_maitre}


def main():
    args = [a for a in sys.argv[1:] if a != "-v"]
    bavard = "-v" in sys.argv
    tmp = tempfile.mkdtemp(prefix="luciole-sim-")
    try:
        so = compile_(tmp)
        echecs = 0
        for nom in (args or ESSAIS):
            def F(n, **kw):
                return Monde(so, tmp, n, bavard=bavard, **kw)
            for titre, ok, detail in ESSAIS[nom](F):
                echecs += not ok
                print("%-6s %-9s %s : %s" % ("ok" if ok else "ÉCHEC", nom, titre, detail), flush=True)
        print("\n%s" % ("tout passe" if not echecs else "%d échec(s)" % echecs))
        return 1 if echecs else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
