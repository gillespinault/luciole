"""Vote décentralisé par propagation : lois d'échelle, calculées avant toute simulation.

    python3 sim/vote/modele.py

Le modèle compte du temps d'antenne. Une trame occupe le canal autour de son émettrice
pendant sa durée ; la part du temps qu'on s'autorise à occuper est G. Tout le reste en découle.

Une « entrée » est le vote d'une luciole tel qu'il voyage : ticket, version, valeur.
Un « domaine » est ce qu'une luciole entend : les n lucioles à portée.
"""
import math

# --- Radio (firmware 7.2 : ESP-NOW longue portée à 250 kbit/s, trames de 250 octets au plus) ---
DEBIT = 250e3            # bit/s ; 500e3 est l'autre débit du mode longue portée
PREAMBULE = 1.0e-3       # s, supposé : à mesurer à l'analyseur
ENVELOPPE = 43           # octets d'en-têtes 802.11 et ESP-NOW autour de la charge utile
CHARGE_MAX = 250         # octets utiles par trame
EN_TETE_VOTE = 10        # octets : type, session, émettrice, nombre d'entrées
ENTREE = 4               # octets : ticket sur 24 bits, version et valeur sur 4 bits chacune


def duree(octets, debit=DEBIT):
    """Durée d'antenne d'une trame de charge utile donnée, en secondes."""
    return PREAMBULE + 8 * (octets + ENVELOPPE) / debit


def par_trame():
    return (CHARGE_MAX - EN_TETE_VOTE) // ENTREE


# --- Protocole ---
G_VOTE = 0.12            # part du temps d'antenne accordée au vote, dans chaque domaine
CRENEAU = 0.5            # s : les relais partent au début de créneaux communs, calés sur l'horloge du battement
RELAYEUSES = 6           # lucioles qui relaient par créneau et par domaine, tirées au sort (probabilité 6/n)
# Deux constantes viennent de la simulation de cette règle (sim/vote/simulation.py), pas du calcul :
ANNONCES = 1.3           # annonces par entrée : une, répétée si la luciole n'entend pas son vote relayé
COPIES = {False: 2.5, True: 8.0}   # copies relayées audibles par entrée : salle, cortège


def rafraichissement(N, n, k, cortege, debit=DEBIT):
    """Temps pour que tous les votes comptés aient voyagé une fois, en secondes.

    N lucioles, n à portée, panel de k. E = min(N, k) entrées voyagent.
    Dans un domaine : ses propres annonces, puis le relais de toutes les entrées par paquets.
    """
    E = min(N, k)
    annonces = E * (n / N) * ANNONCES * duree(EN_TETE_VOTE + ENTREE, debit)
    relais = COPIES[cortege] * E * duree(CHARGE_MAX, debit) / par_trame()
    return (annonces + relais) / G_VOTE, annonces, relais


def latence(sauts):
    """Temps pour qu'un vote isolé atteigne le maître : un créneau par saut, plus celui de l'annonce."""
    return (sauts + 1) * CRENEAU


def marge(N, k, p=0.5):
    """Marge d'erreur à 95 % sur une part p, en points. Nulle si toute la foule est dans le panel."""
    if k >= N:
        return 0.0
    return 196 * math.sqrt(p * (1 - p) / k * (N - k) / (N - 1))


def debit_entrees(cortege, debit=DEBIT):
    """Entrées par seconde qu'une coupe du réseau laisse passer, trames pleines."""
    return G_VOTE / (COPIES[cortege] * duree(CHARGE_MAX, debit) / par_trame())


SCENES = [
    # nom, N, n à portée, sauts, cortège ?
    ("Dîner", 20, 20, 1, False),
    ("Salle de séminaire", 300, 300, 1, False),
    ("Course relais, boucle de 2 km", 500, 100, 6, True),
    ("Cortège de 2 km", 1000, 250, 8, True),
    ("Cortège de 2 km", 5000, 1250, 8, True),
    ("Stade, tous à portée", 20000, 20000, 1, False),
    ("Stade, tous à portée", 50000, 50000, 1, False),
]


def main():
    b = par_trame()
    print(f"Trame courte (une entrée) : {1e3 * duree(EN_TETE_VOTE + ENTREE):.2f} ms. Trame pleine ({b} entrées) : "
          f"{1e3 * duree(CHARGE_MAX):.2f} ms, soit {1e3 * duree(CHARGE_MAX) / b:.3f} ms par entrée.")
    for copies, nom in ((False, "salle"), (True, "cortège")):
        print(f"Débit d'une coupe, {nom} : {debit_entrees(copies):.0f} entrées/s à 250 kbit/s, "
              f"{debit_entrees(copies, 500e3):.0f} à 500 kbit/s.")
    print()
    print("Temps pour que tous les votes comptés aient voyagé une fois, propagation comprise. Marge d'erreur à 95 % sur une part de 50 %.")
    print(f"{'scène':32} {'N':>6} {'n':>6} | {'exact : temps':>13} | {'k=256':>7} {'marge':>6} | {'k=1024':>7} {'marge':>6} | {'un vote isolé':>13}")
    for nom, N, n, sauts, copies in SCENES:
        exact = rafraichissement(N, n, N, copies)[0] + latence(sauts)
        ligne = f"{nom:32} {N:>6} {n:>6} | {exact:>11.1f} s |"
        for k in (256, 1024):
            t = rafraichissement(N, n, k, copies)[0] + latence(sauts)
            ligne += f" {t:>5.1f} s {marge(N, k):>4.1f} pt |"
        print(ligne + f" {latence(sauts):>11.1f} s")
    print()
    print("Détail du temps d'antenne par domaine, vote exact (s) : annonces + relais")
    for nom, N, n, sauts, copies in SCENES:
        t, a, r = rafraichissement(N, n, N, copies)
        print(f"  {nom:32} N={N:<6} annonces {a:8.2f}  relais {r:8.2f}  -> {t:8.1f} s")
    print()
    print("Précision contre vitesse, foule très grande, cortège : k = 1/(4 sigma²), temps = k / débit")
    for sigma in (0.05, 0.03, 0.02, 0.01, 0.005):
        k = 1 / (4 * sigma ** 2)
        print(f"  écart-type {100 * sigma:>4.1f} pt : panel de {k:>6.0f}, rafraîchi en {k / debit_entrees(True):>6.1f} s (relais seuls)")
    print()
    print("Pour comparaison, par domaine et par mise à jour complète :")
    N, n, D = 5000, 1250, 8
    t_court = duree(EN_TETE_VOTE + ENTREE)
    print(f"  cortège N={N}, n={n}, {D} sauts")
    print(f"  inondation d'un message par vote      : {16 * N * t_court / G_VOTE:8.0f} s")
    print(f"  arbre vers le maître (une trame chacun): {n * t_court / G_VOTE:8.0f} s, mais un vote à 8 sauts arrive avec une probabilité {0.8 ** D:.2f} si un lien perd 20 %")
    tours = D * D * math.log(100)
    print(f"  moyenne par commérage (~{tours:.0f} tours)   : {n * tours * t_court / G_VOTE:8.0f} s")
    for m in (64, 128):
        octets = 2 * m * 5 // 8
        trames = 2 * m * (1 + math.log(max(1, n / (2 * m)))) + COPIES[True] * D
        print(f"  deux croquis de {m} registres ({octets} octets) : {trames * duree(octets) / G_VOTE:8.0f} s par époque, "
              f"écart-type {100 * 0.354 * 1.04 / math.sqrt(m):.1f} pt quel que soit N")
    t, _, _ = rafraichissement(N, n, 256, True)
    print(f"  panel de 256                           : {t:8.0f} s, écart-type {marge(N, 256) / 1.96:.1f} pt, puis seuls les changements voyagent")


if __name__ == "__main__":
    main()
