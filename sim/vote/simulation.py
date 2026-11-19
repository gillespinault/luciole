"""Vérifie par simulation les lois de sim/vote/modele.py. Elle vient après le calcul, pas à sa place.

    python3 sim/vote/simulation.py [--rapide]

Trois vérifications :
  1. la diffusion des entrées du panel avec des relais par créneaux, la règle retenue ;
  2. la même diffusion avec une minuterie par luciole, comme l'onde du firmware 7 : la règle écartée ;
  3. l'élection du panel par seuils doublés.

Collisions : deux trames qui se chevauchent chez une réceptrice y sont perdues toutes les deux.
« ALOHA pur » : personne n'écoute avant d'émettre, le cas le plus sévère. « Avec écoute » : une
luciole qui entend une trame attend sa fin, comme le fait le Wi-Fi. Les émettrices cachées, hors
de portée l'une de l'autre, se brouillent dans les deux cas.

Deux géométries : la salle, où tout le monde s'entend, et le cortège, une ligne de L mètres avec
une portée de R mètres. Ce sont les deux extrêmes du modèle.

Python pur, sans dépendance. Ce que sait une luciole est un entier dont le bit e vaut 1 si elle
connaît l'entrée e.
"""
import bisect
import heapq
import random
import sys

import modele as M

ANNONCE, RELAIS, FIN, CRENEAU, ACCUSE = range(5)


def diffusion(N, k, geometrie, L=2000.0, R=250.0, graine=1, ecoute=False, creneaux=True):
    rng = random.Random(graine)
    if geometrie == "ligne":
        x = sorted(rng.uniform(0, L) for _ in range(N))
        lo = [bisect.bisect_left(x, xi - R) for xi in x]
        hi = [bisect.bisect_right(x, xi + R) for xi in x]
    else:
        lo, hi = [0] * N, [N] * N
    n = sum(h - l for l, h in zip(lo, hi)) / N
    E = min(N, k)
    b = M.par_trame()
    T_plan = M.rafraichissement(N, n, k, geometrie == "ligne")[0]
    S = M.CRENEAU
    J = 0.6 * S                                             # fenêtre de tirage au début du créneau
    W = min(1.5, max(0.15, b * T_plan / E))                 # règle écartée : fenêtre de la minuterie

    membres = rng.sample(range(N), E)                       # l'entrée e appartient à la luciole membres[e]
    mien = [0] * N
    connu = [0] * N
    for e, i in enumerate(membres):
        connu[i] = mien[i] = 1 << e
    frais, attente, c0, c1 = [0] * N, [0] * N, [0] * N, [0] * N
    minuterie = [False] * N
    accuse = [False] * E
    rx_fin, rx_trame, rx_bon = [0.0] * N, [-1] * N, [False] * N
    maitre, milieu = 0, N // 2

    file, trames, compteur = [], {}, 0

    def pousser(t, genre, a=0, e=0):
        nonlocal compteur
        compteur += 1
        heapq.heappush(file, (t, compteur, genre, a, e))

    for e in range(E):
        pousser(rng.uniform(0, T_plan), ANNONCE, membres[e], e)
        if not creneaux:
            pousser(rng.uniform(0, T_plan), ANNONCE, membres[e], e)      # deux annonces, sans accusé
    if creneaux:
        pousser(S, CRENEAU)
    s = dict(annonces=0, relais=0, entrees_relayees=0, antenne_milieu=0.0, copies_milieu=0, livrees=0, tentees=0)
    t99_maitre = t99_tous = None
    seuil99 = 0.99 * E
    fin = T_plan * 2 + 20
    prochain_controle = 0.0

    def emettre(t, i, masque, nombre, relais):
        nonlocal compteur
        d = M.duree(M.EN_TETE_VOTE + M.ENTREE * nombre)
        compteur += 1
        f = compteur
        for j in range(lo[i], hi[i]):
            if rx_fin[j] > t:
                rx_bon[j] = False                           # chevauchement : les deux trames sont perdues ici
            else:
                rx_bon[j], rx_trame[j] = True, f
            if rx_fin[j] < t + d:
                rx_fin[j] = t + d
        rx_bon[i], rx_trame[i] = False, -1                  # une émettrice n'entend rien
        trames[f] = (i, masque)
        heapq.heappush(file, (t + d, compteur, FIN, f, 0))
        s["relais" if relais else "annonces"] += 1
        if relais:
            s["entrees_relayees"] += nombre
        if lo[i] <= milieu < hi[i]:
            s["antenne_milieu"] += d
            if relais:
                s["copies_milieu"] += nombre

    def paquet(a):
        masque, reste, nombre = 0, attente[a], 0
        while reste and nombre < b:                         # les b premières entrées en attente
            bit = reste & -reste
            masque |= bit
            reste ^= bit
            nombre += 1
        attente[a] = reste
        return masque, nombre

    while file:
        t, _, genre, a, e = heapq.heappop(file)
        if t > fin:
            break
        if genre == ANNONCE:
            if ecoute and rx_fin[a] > t:
                pousser(rx_fin[a] + rng.uniform(0, 0.02), ANNONCE, a, e)
                continue
            emettre(t, a, 1 << e, 1, False)
            if creneaux:                                    # accusé implicite : entendre son vote relayé
                pousser((int(t / S) + 2) * S + 0.001, ACCUSE, a, e)
        elif genre == ACCUSE:
            if not accuse[e]:
                pousser(t + rng.uniform(0, S), ANNONCE, a, e)
        elif genre == CRENEAU:
            pousser(t + S, CRENEAU)
            for j in range(N):
                if frais[j]:                                # appris au créneau précédent : à relayer maintenant
                    attente[j] |= frais[j]
                    c0[j] &= ~frais[j]
                    frais[j] = 0
                if attente[j] and rng.random() < M.RELAYEUSES / (hi[j] - lo[j]):
                    pousser(t + rng.uniform(0, J), RELAIS, j, int(t / S))
        elif genre == RELAIS:
            minuterie[a] = False
            if not attente[a]:
                continue
            if ecoute and rx_fin[a] > t:
                if not creneaux or rx_fin[a] < (e + 1) * S:
                    minuterie[a] = True
                    pousser(rx_fin[a] + rng.uniform(0, 0.02), RELAIS, a, e)
                continue
            masque, nombre = paquet(a)
            emettre(t, a, masque, nombre, True)
            if attente[a] and not creneaux:
                minuterie[a] = True
                pousser(t + max(0.2, rng.uniform(0.3 * W, W)), RELAIS, a, 0)
        else:                                               # fin d'une trame : qui l'a reçue entière ?
            i, masque = trames.pop(a)
            s["tentees"] += hi[i] - lo[i] - 1
            for j in range(lo[i], hi[i]):
                if rx_trame[j] != a or not rx_bon[j]:
                    continue
                s["livrees"] += 1
                neuf = masque & ~connu[j]
                connu[j] |= masque
                if mien[j] & masque:
                    accuse[mien[j].bit_length() - 1] = True
                if creneaux:
                    frais[j] |= neuf
                    vu = masque & attente[j]
                    second = vu & c0[j]                     # deuxième copie entendue depuis qu'elle attend : on se tait
                    c0[j] = (c0[j] | vu) & ~second
                    attente[j] &= ~second
                else:
                    deja = masque & ~neuf
                    n0 = (c0[j] & ~masque) | neuf | (deja & (~c0[j] | c1[j]))
                    n1 = (c1[j] & ~masque) | (deja & (c0[j] | c1[j]))
                    c0[j], c1[j] = n0, n1
                    attente[j] = (attente[j] | neuf) & ~(deja & n0 & n1)   # troisième copie : on se tait
                    if neuf and not minuterie[j]:
                        minuterie[j] = True
                        pousser(t + rng.uniform(0.3 * W, W), RELAIS, j, 0)
            if t99_maitre is None and bin(connu[maitre]).count("1") >= seuil99:
                t99_maitre = t
            if t99_tous is None and t >= prochain_controle:
                prochain_controle = t + 0.25
                if sum(1 for c in connu if bin(c).count("1") >= seuil99) >= 0.99 * N:
                    t99_tous = t
    recu = sum(bin(c).count("1") for c in connu) / (N * E)
    return dict(N=N, k=k, E=E, n=n, T_plan=T_plan, t99_maitre=t99_maitre, t99_tous=t99_tous, recu=recu,
                charge=s["antenne_milieu"] / T_plan, copies=s["copies_milieu"] / E, par_entree=s["annonces"] / E,
                par_trame=s["entrees_relayees"] / max(1, s["relais"]), perte=1 - s["livrees"] / max(1, s["tentees"]), **s)


def election(N, n, k, graine=1):
    """Seuils doublés : au tour r, annoncent les tickets sous seuil x 2^r, tant qu'on connaît moins de k tickets."""
    rng = random.Random(graine)
    tickets = sorted(rng.random() for _ in range(N))
    seuil = min(1.0, k / (32 * n))                          # chaque luciole part de ce qu'elle entend : n voisines
    tours = 0
    while True:
        tours += 1
        candidats = bisect.bisect_left(tickets, seuil)
        if candidats >= min(k, N):
            return candidats, tours
        seuil *= 2


def f(x):
    return "    —  " if x is None else f"{x:5.1f} s"


def tableau(cas, creneaux):
    print(f"{'géométrie':9} {'N':>5} {'k':>5} {'n':>5} | {'plan':>7} | {'maître 99 %':>11} {'tous 99 %':>9} | {'reçu':>6} {'charge':>6} "
          f"{'annonces':>8} {'copies':>6} {'par trame':>9} {'perte':>6}")
    for geo, N, k in cas:
        for ecoute in (False, True):
            r = diffusion(N, k, geo, ecoute=ecoute, creneaux=creneaux)
            print(f"{geo:9} {N:>5} {k:>5} {r['n']:>5.0f} | {f(r['T_plan'])} | {f(r['t99_maitre']):>11} {f(r['t99_tous']):>9} | "
                  f"{100 * r['recu']:>5.1f}% {100 * r['charge']:>5.1f}% {r['par_entree']:>8.2f} {r['copies']:>6.1f} {r['par_trame']:>9.1f} "
                  f"{100 * r['perte']:>5.1f}%" + ("  avec écoute" if ecoute else "  ALOHA pur"), flush=True)


def main():
    cas = [("salle", 20, 1024), ("salle", 300, 1024), ("ligne", 500, 1024), ("ligne", 1000, 1024),
           ("salle", 2000, 256), ("ligne", 5000, 256), ("ligne", 5000, 1024)]
    if "--rapide" in sys.argv:
        cas = cas[:4]
    print("« plan » est le temps donné par le modèle ; la simulation étale les annonces dessus.")
    print("« annonces » : par entrée. « copies » : copies relayées audibles au milieu, par entrée. « par trame » : entrées par trame de relais.")
    print("\n1. Relais par créneaux, la règle retenue")
    tableau(cas, True)
    print("\n2. Une minuterie par luciole, la règle écartée")
    tableau(cas[:4], False)
    print("\n3. Élection du panel par seuils doublés, k = 256 : annonces et tours (200 tirages)")
    for N, n in ((20, 20), (300, 300), (1000, 250), (5000, 1250), (50000, 50000), (50000, 2000)):
        res = [election(N, n, 256, g) for g in range(200)]
        print(f"  N={N:>6}, n={n:>6} : {sum(r[0] for r in res) / 200:6.0f} annonces en moyenne, {max(r[0] for r in res)} au plus, "
              f"{sum(r[1] for r in res) / 200:.1f} tours")


if __name__ == "__main__":
    main()
