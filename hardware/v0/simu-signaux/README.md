# Simulation des signaux de la carte v0

Les modèles téléchargés chez les fabricants ne sont pas dans le dépôt : ils restent en local, comme les fiches techniques. Avant de relancer les simulations sur une copie neuve, les télécharger aux adresses du tableau des modèles, plus bas, et les poser dans `modeles/`. Les journaux bruts de ngspice ne sont pas suivis non plus : `lancer.sh` les refait.

Ce dossier simule avec ngspice les circuits de signal de la carte v0, révision 0.5, avant toute commande : port Grove, donnée des LED, reset, bouton, pont de retour du convertisseur. Chaque cas compare ce que le schéma veut, d'après les commentaires de `circuit.py`, à ce que le calcul donne. Simulations du 18 novembre 2026, ngspice 44.2.

Rien ici n'est mesuré sur une carte. Les circuits intégrés sont des modèles écrits d'après leurs fiches ; la section « Modèles » dit ce qui vient d'une fiche et ce qui est une hypothèse.

## Relancer

Depuis `hardware/` :

    v0/simu-signaux/lancer.sh                  # tout, 3 minutes environ
    v0/simu-signaux/lancer.sh a2_ruban.cir     # un seul cas
    tools/kicad ngspice -b v0/simu-signaux/a2_ruban.cir   # le même, journal complet à l'écran

`lancer.sh` garde le journal de ngspice dans `sorties/` et n'affiche que les lignes de résultat.

## Lire les résultats

Chaque ligne utile commence par `RESULTAT`. La première ligne d'un bloc nomme les colonnes, les suivantes donnent les valeurs, séparées par des points-virgules, en volts, ampères, secondes. L'en-tête de chaque fichier `.cir` dit quelles limites regarder.

Une valeur `-1` veut dire qu'un niveau n'est jamais atteint : la ligne ne monte pas assez haut dans le temps simulé. `lancer.sh` compte ces cas dans une ligne `note`.

Une ligne `ALERTE` veut dire que ngspice n'a pas mené un calcul au bout. Le résultat de ce cas ne vaut alors rien. Deux pièges ont été rencontrés et sont réglés dans les fichiers : le point de repos du rail d'écrêtage de U11, que ngspice remplaçait par un régime transitoire trop court (options en tête de `port_grove.inc`), et un pas de calcul trop grand sur la première trame du ruban (pas borné à 1 ns dans `a2_ruban.cir`).

Presque tous les blocs se terminent par une « variation » : une valeur change, et le résultat doit bouger dans le sens prévu. C'est ce qui montre qu'un cas conforme l'est pour la bonne raison.

## Fichiers

| Fichier | Circuit |
|---------|---------|
| `port_grove.inc` | Le port Grove recopié de `circuit.py` : Q8, Q9, R31 à R36, U10, JP4, U11, C41. Commun aux cas A1 à A4 |
| `a1_i2c_niveaux.cir` | A1, I2C : niveaux bas et haut des deux côtés, accessoire à rappels vers 3,3 V, vers 5 V, sans rappel |
| `a1_i2c_fronts.cir` | A1, I2C : fronts montants avec 100 et 400 pF de câble, à 100 et 400 kHz |
| `a2_ruban.cir` | A2, ruban de LED sur la broche 2 : niveaux, fronts, courants, première trame |
| `a3_rail_coupe.cir` | A3, rail des LED coupé : courant renvoyé vers le rail dans chaque état de PORT_PU, IO1 et IO2 |
| `a4_carte_eteinte.cir` | A4, carte éteinte et accessoire alimenté |
| `b_donnee_led.cir` | B, donnée des LED : GPIO18, U9, R29, D1, puis D1 vers D2 |
| `c_reset.cir` | C, mise sous tension et reset : R18, C10, U5, SW1, GPIO8, GPIO9 |
| `d_bouton.cir` | D, bouton SW3 : R21, C11, D19, R40 |
| `e_pont_retour.cir` | E, pont de retour : R25, R26, R27, Q5, C37 |
| `modeles/modeles.lib` | Tous les modèles, avec l'origine de chaque chiffre |
| `modeles/bss138_onsemi.lib` | Le modèle BSS138 d'onsemi tel que téléchargé (fins de ligne converties) |
| `modeles/bss138_onsemi_thermique.lib` | Son premier sous-circuit, extrait sans retouche, le seul que ngspice lit tel quel |
| `modeles/essai_bss138.cir` | Seuil et résistance du modèle BSS138, à comparer à la fiche de la copie R+O |
| `sorties/` | Journaux de la dernière exécution |

## Résultats

| Cas | Attendu | Simulé | Verdict |
|-----|---------|--------|---------|
| A1, niveaux bas | Bas reconnu des deux côtés | Côté accessoire 0,02 à 0,28 V quand la puce tire (limite 0,99 V). Côté puce 0,23 à 0,36 V quand l'accessoire tire, 0,53 V s'il ne descend qu'à 0,4 V (limite 0,825 V ; 0,74 V si le 3,3 V est à -10 %) | Conforme |
| A1, niveaux hauts | Haut reconnu des deux côtés | Puce 3,30 V. Accessoire 3,30 V ou 4,99 V avec ses rappels. Sans rappel côté accessoire : 2,8 à 2,9 V | Conforme si l'accessoire a ses rappels ou travaille en 3,3 V ; trop bas pour un accessoire en 5 V sans rappel (il lui faut 3,5 V) |
| A1, broche de la puce | Jamais plus de 3,3 V, 3,6 V au plus d'après la fiche | 3,30 V au repos, 3,41 V en pointe quand la ligne monte à 5 V | Conforme |
| A1, fronts à 100 kHz | Montée de 1 µs au plus | Côté accessoire : 0,5 à 0,7 µs avec 100 pF et des rappels, 1,2 à 1,8 µs avec 400 pF ; sans rappel, 1,3 µs (100 pF) et 2,9 µs (400 pF). Côté puce : 0,3 à 1,6 µs. Le niveau haut est toujours atteint dans la demi-période | Conforme jusqu'à 100 pF avec rappels ; hors norme au-delà, mais fonctionnel |
| A1, fronts à 400 kHz | Montée de 0,3 µs au plus | Jamais sous 0,3 µs. Niveau atteint en 0,6 à 0,9 µs avec 100 pF et rappels ; jamais atteint avec 400 pF ou sans rappel | Non conforme |
| A2, ruban, régime établi | Haut au-dessus de 0,65 × le rail ; pas de conflit entre U10 et la broche | Haut 4,48 V (seuil 2,93 V) et 4,98 V (seuil 3,25 V). Montée 0,12 µs, descente 0,04 µs. Bit 0 vu 0,30 µs, bit 1 vu 0,68 µs. Aucun courant au repos entre U10, Q9 et la broche. IO2 monte à 3,40 V au plus | Conforme jusqu'à 200 pF de câble |
| A2, première trame | Même signal | C41 vide : les 38 à 67 premiers bits restent sous le seuil | Non conforme |
| A3, rail coupé | Aucun courant renvoyé vers le rail ; R35 tient PORT_PU à 1 | 3 à 4 µA dans les états sûrs. 0,5 mA si PORT_PU reste à 1, 4,2 mA si IO2 reste à 1 : le courant passe par la sortie de U10. Broches en l'air, PORT_PU tombe à 0,5 V | Non conforme |
| A4, carte éteinte | Aucun courant n'entre par les lignes | Broche 1 : 0,6 µA. Broche 2 : 0,9 mA par des rappels de 4,7 kΩ, 16 mA par une sortie franche, vers le rail des LED par U10 | Conforme sur la broche 1, non conforme sur la broche 2 |
| B, donnée des LED | Haut au-dessus de 0,65 × le rail à l'entrée de D1 | Haut égal au rail. Fronts de 21 ns. Bit 0 vu 0,31 µs, bit 1 vu 0,69 µs. Seuil de U9 garanti par les fiches avec 0,27 V de marge | Conforme |
| C, reset | EN sous 0,825 V au moins 50 µs après le 3,3 V à 2,8 V ; GPIO9 à 1 | Marge de 133 à 278 ms, que le 3,3 V monte en 1 ou en 50 ms. Sans U5 et avec une montée de 50 ms, EN serait en avance de 21 ms. GPIO8 et GPIO9 à 3,30 V au relâchement | Conforme |
| D, bouton | Haut au repos, bas à l'appui, rebonds filtrés | 3,29 V au repos, 0 V à l'appui, 0,16 V au plus pendant des rebonds de 0,5 ms. Retour au niveau haut en 14 ms | Conforme |
| E, tension du rail | 4,45 V et 5,04 V | 4,45 V (4,27 à 4,64) et 5,04 V (4,83 à 5,25 ; 5,30 à faible charge) | Conforme |
| E, zéro de C37 | 1 kHz | 1,03 kHz, pôle à 7,7 ou 8,7 kHz | Conforme |

## Constats

### 1. U10 renvoie du courant dans le rail des LED quand il est coupé (à corriger)

La sortie de U10 a une diode vers son alimentation. La fiche TI la dessine (figure 8-2). La fiche de la copie TECH PUBLIC annonce une « Power Down Protection » sans rien chiffrer pour la sortie : c'est la première mesure à faire sur une carte, 3,3 V sur la broche 2 du port, rail coupé, courant dans R36. JP4 étant fermé, tout niveau haut sur la broche 2 du port passe par R36 et cette diode vers le rail des LED éteint.

Rail coupé et tenu à 0 V : 0,51 mA quand PORT_PU est à 1 et IO2 en l'air (le repos de l'I2C), 4,2 mA quand IO2 est à 1, 3,3 µA quand tout est en l'air. Si le rail n'est chargé que par son pont de 381 kΩ, il monte à 2,3 V. La réalité est entre les deux : la fiche des LED ne dit pas ce qu'elles consomment sous 3,7 V. Carte éteinte, un accessoire alimenté injecte 0,9 mA par des rappels de 4,7 kΩ, 16 mA par une sortie franche (le maximum de la diode est 20 mA).

Vérifié de deux façons : JP4 coupé, le courant tombe à quelques pA ; R36 multipliée par 100, il est divisé par 6, comme le veut le calcul avec R34 en série.

Sans changer la carte : tant que le convertisseur est arrêté, le firmware tient PORT_PU à 0 ou en l'air, et IO1, IO2 à 0 ou en l'air. Le courant de veille dû au port est alors de 3 à 4 µA, dont 3,3 µA dans R35. Cela ne règle pas le cas de la carte éteinte.

Correction proposée : une diode en série avec R36, anode du côté de U10. Simulée avec une 1N4148WS, déjà dans la nomenclature : courant renvoyé de 2,5 nA dans tous les états, 0,6 µA carte éteinte. Le niveau bas du ruban reste fait par Q9. Le niveau haut perd la chute de la diode : 3,95 V sous 4,5 V et 4,45 V sous 5,0 V à la fin d'un bit 0, avec 100 pF. Autre voie : un tampon dont la sortie s'isole hors tension, à deux alimentations (SN74LVC1T45).

### 2. C41 avale le début de la première trame du ruban (à corriger)

Le rail d'écrêtage de U11 est isolé sur C41, 100 nF. Quand la broche 2 monte, la diode de U11 charge C41 à travers R36 : la ligne ne peut pas dépasser la tension de C41 de plus de 0,8 V. C41 vide, il faut environ 20 µs de niveau haut cumulé pour atteindre le seuil d'une LED : 38 à 41 bits si la trame alterne les 0 et les 1, 62 à 67 bits si elle ne contient que des 0. Le ruban affiche donc une première trame fausse. Ensuite C41 reste chargé. La fuite de U11 le ramène sous le niveau utile en une seconde au pire (150 nA), une quinzaine en typique (10 nA) : calcul à la main. Le défaut revient après une pause plus longue.

C41 est vide à la mise en route : rail coupé et broches en l'air, il n'est qu'à 0,2 V (cas A3).

Correction proposée : ne pas monter C41. La diode d'écrêtage interne de U11 protège toujours les lignes. Simulé : le seuil est atteint 0,04 µs après le début du premier bit. Avec 1 nF le premier bit est encore rogné (seuil atteint après 0,23 à 0,26 µs, pour un bit 0 de 0,32 µs). Une diode du rail des LED vers C41 marche aussi.

Sans changer la carte : le firmware pousse IO1 à 1 pendant l'usage du ruban, ce qui précharge C41 à 2,8 V par Q8 et la broche 1. Simulé : premier bit valable. Coût : 0,7 mA dans R33.

### 3. R35 ne tient pas /OE de U10 à 1 (à corriger par le firmware, réglé par la correction 1)

Rail coupé, la diode de U10 tire PORT_PU à 0,5 V à travers R34. Quand le rail revient et que le firmware n'a pas encore commandé PORT_PU, U10 se trouve actif avec IO2 à 0 : il tire la broche 2 à 0, ce qui tient IO2 puis PORT_PU à 0 par Q9 et R34. L'état se verrouille (PORT_PU à 19 mV, 300 ms après). Un accessoire I2C voit alors sa ligne de données tenue à 0 par 220 Ω. Pousser PORT_PU à 1 en sort tout de suite.

Règle pour le firmware : commander PORT_PU avant BOOST_EN. Avec la diode du constat 1, le verrouillage disparaît et R35 tient PORT_PU à 3,05 V.

### 4. I2C : 100 kHz seulement, et des accessoires qui ont leurs rappels (à discuter)

Chaque BSS138 ajoute à la ligne une centaine de pF d'après le modèle d'onsemi (capacités grille-source et grille-drain, la grille étant au 3,3 V). Avec les rappels de 4,7 kΩ, la norme I2C n'est tenue à 100 kHz que jusqu'à 100 pF de câble environ et avec un accessoire qui a ses rappels. Elle ne l'est jamais à 400 kHz. Le bus marche pourtant à 100 kHz dans tous les cas simulés : le niveau haut est atteint en 3,8 µs au pire (4,1 µs avec des transistors à seuil haut) pour une demi-période de 5 µs.

Baisser R33 et R34 à 2,2 kΩ divise les temps par 1,4 à 2, mais le niveau bas côté puce monte à 0,66 V dans le pire cas, pour une limite de 0,825 V (0,74 V à -10 %).

Sans rappel côté accessoire, le niveau haut de la ligne plafonne à 2,8 ou 2,9 V : il passe par la diode de Q8 ou Q9. C'est assez pour un accessoire en 3,3 V, pas pour un accessoire en 5 V sans rappel.

Le seuil haut de la copie R+O (1,6 V) change les temps côté accessoire de moins de 10 %. Sa résistance, que la fiche ne donne qu'à 4,5 V et 10 V, reste sous 6 Ω dans le pire cas extrapolé : sans effet à côté des 220 Ω de R31 et R32.

### 5. Ruban : 200 pF de câble au plus (à discuter)

Avec 400 pF, un bit 0 émis 0,32 µs n'est vu que 0,24 µs au-dessus du seuil ; la LED demande 0,25 µs. Avec 200 pF, 0,28 µs. Avec la diode du constat 1 et 200 pF : 0,26 µs, et un bit 1 émis 0,70 µs est vu 0,64 à 0,65 µs pour 0,65 demandé. Le firmware peut allonger les bits de 0,05 µs.

### 6. C11 se décharge dans le contact de SW3 (à discuter)

À l'appui, les 100 nF de C11 se vident dans le contact : 5,9 A en pointe avec un contact de 0,5 Ω, au-dessus de 50 mA pendant 0,25 µs. La fiche de SW3 donne 50 mA au plus. Placer C11 du côté de la broche, derrière R40, ramène la pointe à 38 mA sans changer le filtrage (rebonds à 0,16 V, retour en 14 ms). C10 et SW1 ont le même montage, non mesuré ici.

## Vérifié dans les fiches, sans simulation

Seuil de U9 et de U10. Les fiches garantissent le niveau haut à partir de 2,03 V sous 4,5 à 5,0 V et de 2,11 V sous 5,5 V. La puce sort au moins 0,8 fois son alimentation, soit 2,376 V sous 3,3 V - 10 %. Marge : 0,27 V au moins.

Superviseur U5. Son seuil est 3,08 V (± 2 %, soit 3,14 V au plus), avec 1,5 % d'hystérésis au plus. Le régulateur donne 3,3 V ± 2 %, soit 3,23 V au moins. Il reste 92 mV avant un reset et 45 mV pour en sortir, dans le pire cas des deux pièces.

Tampons en I2C. Une entrée de U9 ou U10 tenue à 3,3 V, rail à 5 V, fait consommer au tampon jusqu'à 1,35 mA de plus à 25 °C (fiche, « ΔICC »). En I2C, rail allumé, U10 a ses deux entrées dans ce cas.

Sortie de U10 en l'air à plus de 4,6 V. La fiche TECH PUBLIC limite à 4,6 V la tension sur la sortie inactive. La ligne 2 y est à 5 V avec un accessoire à rappels vers 5 V. La fiche TI récente n'a plus cette limite.

## Modèles

| Pièce | Modèle | Origine |
|-------|--------|---------|
| BSS138 (Q8, Q9) | `BSS138P` | Sous-circuit « BSS138/FAI » d'onsemi, téléchargé de onsemi.com (`bss138.lib`), recopié avec ses coefficients à 27 °C. Typique : seuil 1,32 V, 1,16 Ω à 4,5 V, proche de la copie R+O (1,2 V, 1,2 Ω). Pire cas réglé sur la fiche R+O : 1,60 V et 2,95 Ω à 4,5 V ; le modèle donne alors 3,7 Ω à 3,3 V |
| AO3400A (Q5) | `AO3400A` | Écrit d'après la fiche AOS. Aucun modèle du fabricant trouvé |
| Broches de l'ESP32-C6 | `ESPPIN` | Fiche de la puce v1.6, tableau 5-4 : seuils, 2 pF, 50 nA, rappel de 45 kΩ. Hypothèses : sortie de 35 Ω, diodes de protection vers le 3,3 V et la masse |
| SN74LV1T34, SN74LV1T125 (U9, U10) | `LV1T` | Fiches TI SCLS743A et SCLS745D. Sortie dimensionnée sur les limites à 25 °C sous 4,5 V. Hypothèses : seuil typique de 0,25 × l'alimentation + 0,2 V ; comportement sous 1,6 V d'alimentation |
| USBLC6-2SC6 (U11) | `USBLC6` | Fiche ST rév. 5. Hypothèses : chute des diodes 0,86 V à 10 mA (la fiche donne 1,1 V au plus), capacité de la diode d'écrêtage 30 pF |
| TLV803EA30 (U5) | `TLV803` | Fiche TI : 3,08 V, 200 ms, sortie non définie sous 0,7 V |
| SK6812MINI-B-012 | `LEDDIN` | Fiche OPSCO : seuils seulement. Hypothèses : 15 pF, sortie logique de 100 Ω |
| PESD5Z5.0 (D19) | `PESD5Z5` | Fiche Nexperia : 89 pF, 50 nA |
| TPS61023 | Source idéale | Remplacé par ce qu'il fait en régime établi : FB égale à la référence, 580 à 610 mV (fiche TI) |

Le modèle d'onsemi contient des résistances de 10 MΩ entre grille et drain. Elles font apparaître 0,2 à 0,5 µA par transistor vers le 3,3 V quand une ligne est à 5 V, et 0,7 µA dans le courant de veille du cas A3. La fiche borne la fuite réelle de grille à 0,1 µA.

Capacités de piste : 3 pF par nœud, hypothèse.

## Ce qui n'est pas simulé

- Les décharges électrostatiques sur le port et le bouton.
- Le convertisseur lui-même : démarrage, stabilité, ondulation. Seul son pont de retour l'est.
- La consommation des LED sous 3,7 V. Les cas A3 et A4 l'encadrent par deux hypothèses.
- La sortie de donnée d'une LED : la fiche n'en dit rien, le passage de D1 à D2 repose sur une hypothèse.
- Les lignes longues : un câble est une capacité, sans réflexions.
- La température : tout est à 27 °C, sauf les limites des fiches prises sur toute la plage.
- L'USB, la charge, la protection de batterie, l'accéléromètre : hors du périmètre.
