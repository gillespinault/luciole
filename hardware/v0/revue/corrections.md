# Consigne de contre-relecture : corrections du 18 novembre 2026

Le routage de la carte Luciole² v0 a été relu une première fois (consigne dans `consigne.md`). Huit corrections ont été faites. Vous vérifiez ces corrections, et rien d'autre : chacune est-elle faite comme elle est décrite, et a-t-elle créé un défaut qui n'existait pas ?

Note du 18 novembre 2026 au soir : cette consigne décrit la carte au moment de la contre-relecture. Depuis, la correction T1 a été retouchée : cinq vias au lieu de six, placés entre les dépôts de pâte de la plage du chargeur. La raison est dans `hardware/README.md`, section « Ce que les retours d'expérience ont appris ».

Les pièces de ce dossier décrivent la carte corrigée : `routage.md` (règles, composants, réseaux avec leurs pastilles, leurs pistes et leurs vias), les six images du cuivre et les deux rendus. `../carte.py` porte le placement et les pistes tracées par script. Cotes en millimètres depuis le coin haut gauche, face avant vue de dessus ; le dos est donné dans le même repère.

Le contrôle des règles de KiCad passe sur la carte corrigée : isolements, aucune liaison manquante, carte conforme au schéma. Inutile de le refaire.

## Les huit corrections

| N° | Avant | Après | Où regarder |
|---|---|---|---|
| T1 | Aucun via sous la plage centrale du chargeur U2 | Six vias de masse dans la plage, en (23,0 ou 24,0 ; 16,5, 17,4 ou 18,3) | Réseau GND, U2.9, plan du dos sous U2 |
| T2 | R43 à (36,5 ; 5,25) au dos ; Q2_G : 36 mm et 6 vias | R43 à (28,45 ; 4,1) au dos, entre Q2 et Q6 ; Q2_G au dos seulement. BATN arrive par la face avant depuis TP18 et le via (27,65 ; 4,5) | Réseaux Q2_G et BATN, composants Q2, Q6, R43, TP18, TP5, TP2 |
| T3 | R45 et R46 posés par le poseur ; Q6_G : 4,4 mm et 2 vias | R46 à (34,25 ; 3,62), R45 à (35,9 ; 4,45), au dos ; Q6_G, BATP et VBAT reliés au dos sans via | Réseaux Q6_G, BATP, VBAT |
| T4 | C39 (1 µF sur VBUS) près du connecteur USB, au dos | C39 en face avant à (20,5 ; 20,6), contre U2.4, avec un via de masse en (19,2 ; 20,6) | Réseau VBUS, U2.4, C39, composants voisins |
| T5 | Un via VBUS en (37,3 ; 20,0) entre le dos et la face avant | Deux vias, en (37,3 ; 19,0) et (37,3 ; 20,0), reliés sur les deux faces | Réseau VBUS |
| T6 | PORT_1 se séparait en (15,1 ; 19,4) : une branche vers U11.6, l'autre vers le via (16,0 ; 19,4) | PORT_1 arrive sur U11.6, relie U11.6 à U11.1 sous le boîtier, repart de U11.1 par la droite et descend en x = 15,85 jusqu'au via (16,0 ; 19,4) | Réseau PORT_1, U11, C41, plan de masse autour de U11.2 et de D15.4 |
| T7 | Pistes de 0,24 mm de U8.4 et U8.6 vers C14 | Les mêmes, doublées d'une piste de 0,6 mm entre le condensateur et le point situé 1,65 mm sous l'axe de U8 | Réseaux GND et VLED près de U8 et C14 |
| T8 | Masse de U1.2 : piste de 0,3 mm jusqu'au via (10,4 ; 16,5) | La même, en 0,6 mm | Réseau GND, U1, R3, R4, voies USB_DP_R et USB_DN_R |

Le routeur a retracé les liaisons courtes après ces changements : d'autres réseaux ont pu changer de chemin.

## Ce qu'il faut chercher

1. Chaque correction est-elle bien là, aux cotes annoncées ?
2. Crée-t-elle un défaut : isolement faible avec un voisin, masse enfermée ou reliée par un lien étroit, via sous une pastille ou trop près d'elle, composant trop près d'un autre pour la pose, piste d'alimentation amincie, boucle allongée ?
3. T4 : le déplacement de C39 laisse-t-il l'entrée USB sans ce qu'il lui faut (écrêteur D24, amortisseur R39 et C1) ?
4. T6 : la ligne traverse-t-elle bien le protecteur, sans autre dérivation avant lui ?
5. T1 : les six vias gênent-ils la soudure de la plage ou un tracé du dos ?
6. Les réseaux retracés par le routeur ont-ils un tracé pire qu'avant (détour, vias, passage sous un composant sensible) ?

## Forme du rapport

Une ligne par correction : faite ou non, défaut créé ou non, avec les cotes et les chiffres lus dans les pièces. Puis les défauts nouveaux, numérotés, avec leur gravité (bloquant, à corriger, à discuter) et la correction proposée. Ne corrigez rien vous-même.
