# Consigne de relecture : routage de la carte Luciole² v0

Vous relisez le routage d'une carte électronique que vous n'avez pas dessinée. Le but : trouver ce qui empêcherait la carte de fonctionner, de se fabriquer ou de durer, avant d'en commander cinq exemplaires pour des mesures.

Le schéma a déjà été relu trois fois (révision 0.5) : ce n'est pas le sujet. Signalez tout de même une erreur de schéma si le routage vous la fait voir.

## La carte

Barre lumineuse de vélo, 122 × 28 mm, deux couches, assemblée sur les deux faces chez JLCPCB.

- Face avant : une rangée de 15 LED adressables (SK6812 mini, D1 à D15, D1 à droite), leur barre d'alimentation VLED, le convertisseur élévateur TPS61023 (U8) qui fait VLED à 4,5 V ou 5,0 V, le chargeur linéaire TP4056 (U2), le régulateur 3,3 V RT9080 (U4), un accéléromètre LIS2DH12 (U7), un connecteur Grove (J3) à l'extrémité gauche.
- Dos : le module radio ESP32-C6-MINI-1 (U6) à l'extrémité droite, antenne au bord de la carte ; l'USB-C (J1) et un bouton (SW3) à l'extrémité gauche, dos à dos avec le Grove ; le connecteur de batterie (J2) et les protections de la cellule (DW01A U3, FS8205A Q3, deux MOSFET P contre l'inversion Q2 et Q6). Une cellule Li-ion est plaquée sur le dos, entre x = 37,8 et x = 104,8 mm : aucun composant n'y est posé.
- Courants à tenir : jusqu'à 1,0 A sur VLED ; charge jusqu'à 0,9 A ; 1,15 A tirés de l'USB quand la carte éclaire et charge à la fois ; 2 A en pointe côté batterie.
- Signaux rapides : USB 2.0 pleine vitesse (12 Mbit/s) entre J1 et U6 ; donnée des LED à 800 kHz ; I2C de l'accéléromètre ; radio à 2,4 GHz dans le module.

## Pièces

Toutes dans ce dossier ou à côté. Dépôt : `https://github.com/gillespinault/luciole`, branche `carte-v0`, dossier `hardware/`.

| Fichier | Contenu |
|---|---|
| `v0/revue/routage.md` | La carte en clair : règles, composants (repère, valeur, face, position), et pour chaque réseau ses pastilles, ses pistes mises bout à bout avec leur largeur, ses vias |
| `v0/revue/avant-1.png` à `avant-3.png` | Cuivre de la face avant, de gauche à droite, avec le nom du réseau sur chaque pastille. Pistes en rouge, vias en vert, plan de masse en vert pâle |
| `v0/revue/dos-1.png` à `dos-3.png` | Cuivre du dos, vu par transparence, dans le même repère. Pistes en bleu, plan de masse en jaune pâle |
| `v0/revue/rendu-avant.png`, `rendu-dos.png` | Rendus de la carte |
| `v0/netlist_voulue.txt` | Les connexions voulues, par numéros de broches |
| `v0/circuit.py` | Le schéma décrit en code : valeurs et références des composants |
| `v0/carte.py` | Le placement et les pistes tracées par script, avec leurs commentaires |
| `v0/v0.kicad_pcb` | Le fichier KiCad complet, si vous savez le lire |

Cotes en millimètres depuis le coin haut gauche, face avant vue de dessus ; x vers la droite, y vers le bas.

## Ce qui est déjà contrôlé

Le contrôle des règles de KiCad passe : isolements, largeurs minimales, perçages, bord de carte, aucune liaison manquante, carte conforme au schéma. Inutile de le refaire. Ce contrôle ne dit rien de ce qui suit.

## Ce qu'il faut parcourir

Pour chaque point, partez des pistes et des positions du dossier, pas de ce que la carte devrait être.

1. Chemins de courant. Suivez chaque alimentation de sa source à ses charges : VBUS de l'USB-C au chargeur et au partage de charge ; la batterie de J2 à travers ses protections jusqu'à VBAT, puis VSYS ; l'entrée et la sortie du convertisseur ; VLED le long des 15 LED ; le 3,3 V. Largeur de chaque tronçon contre son courant, nombre de vias en série, chute de tension, goulets.
2. Convertisseur TPS61023. Boucle à courant haché (sortie, condensateurs de sortie, masse), nœud SW, bobine, pont de mesure et sa broche FB, retour de masse. Comparez à la disposition recommandée par sa fiche technique.
3. Masse. Les deux plans sont découpés par les pistes. Pour chaque fonction, par où revient le courant ? Cherchez les pastilles de masse reliées par un seul lien fin, les retours qui font un détour, les morceaux de plan reliés par un seul via, le retour de masse des LED à chaque bout de la rangée.
4. USB. Trajet de D+ et D- du connecteur au module : longueur, écart entre les deux lignes, vias, ce qu'elles longent, plan de référence. Place de la protection U1 et des résistances série. Broches CC et leurs résistances. Blindage du connecteur.
5. LED. Donnée d'une LED à la suivante, tampon U9 et résistance série, condensateur de chaque LED, distribution de VLED et de la masse sur toute la longueur.
6. Radio. Cuivre, composants et pistes près de l'antenne et sous le module ; masse du module ; ce qui pourrait désaccorder l'antenne ou la brouiller. Comparez aux recommandations d'Espressif pour ce module.
7. Chargeur et thermique. Plage thermique du TP4056, cuivre et vias qui évacuent sa chaleur à 0,9 A ; échauffement des protections et du convertisseur.
8. Connecteurs et décharges électrostatiques. Ordre connecteur, protection, reste du circuit sur l'USB et sur le Grove ; longueur des pistes avant la protection.
9. Fabrication et assemblage chez JLCPCB. Vias près des pastilles ou sous des composants, pistes sous les connecteurs et sous la coque de l'USB-C, pastilles de test accessibles, composants trop près d'un bord ou l'un de l'autre pour la pose, cuivre mince ou pointu.
10. Batterie. Pistes et vias sous la cellule, place de la thermistance, risque de court-circuit contre la poche.
11. Tout tracé qui vous paraît anormal : détour long, vias nombreux sur un même signal, piste d'alimentation fine, signal sensible longeant un signal bruyant.

## Forme du rapport

Des constats numérotés. Pour chacun :

- la gravité : bloquant (la carte ne marchera pas ou sera dangereuse), à corriger (elle marchera mal ou vieillira mal), à discuter ;
- l'endroit : repères, réseau, cotes ;
- ce que vous avez lu dans les pièces qui le montre, avec les chiffres ;
- la correction que vous proposez.

Puis la liste de ce que vous n'avez pas pu vérifier, et pourquoi.

Un constat sans repère ni chiffre ne sert pas. Ne corrigez rien vous-même.
