# Simulations ngspice de l'alimentation de la carte v0

Les modèles téléchargés chez les fabricants ne sont pas dans le dépôt : ils restent en local, comme les fiches techniques. Avant de relancer les simulations sur une copie neuve, les télécharger aux adresses du tableau des modèles, plus bas, et les poser dans `modeles/`. Les journaux bruts de ngspice ne sont pas suivis non plus : `lancer.sh` les refait.

## État : révision 0.6 du schéma (18 novembre 2026)

Les simulations décrites plus bas ont été écrites sur la révision 0.5. Elles y ont trouvé le défaut du cas A5 (cellule inversée branchée à chaud). La révision 0.6 du schéma applique la correction, et `commun.inc` porte maintenant ses valeurs :

- `cg2 = 22n` : le condensateur C42 entre la grille de Q2 et BATN ;
- `r46 = 10k` ;
- Q2 est un AO3401A (30 V) au lieu d'un DMP1045U (12 V) ;
- `r5 = 470`, `r6 = 1k` : le pont de VBUS.

Résultats relancés sur ces valeurs, de −10 à 60 °C :

- A5d, cellule inversée branchée sous USB : VBAT ne descend pas sous +0,81 V (avant : −3,3 V), aucune tension négative, 7,2 à 8,4 V aux bornes de Q2 pour 30 V admis.
- A5e, échange de batterie : VBAT reste au-dessus de 1,8 V.
- A5a, A5b, A5c, A1 à A4 : inchangés dans leur verdict. Q2 perd 87 à 111 mV sous 2 A.
- B4 : la lecture de VBUS_DET reste sûre jusqu'à 0,5 mA de fuite de D16 (avant : 0,2 mA).
- B3 : inchangé, le creux au retrait de l'USB ne dépend pas de ces valeurs.

Le fichier `a5_corrections.cir` part des valeurs de `commun.inc` : sa ligne « schema tel quel » décrit donc la révision 0.6, et ses variantes s'y ajoutent. Les valeurs de la révision 0.5 sont dans l'historique du dépôt.

`lancer.sh` affiche « ATTENTION » pour `b_partage` et `c_chargeur`. ngspice y cherche le point de repos par sa méthode de secours (« Transient op ») et y parvient : chaque recherche commencée se termine par « Transient op finished successfully » dans le journal. Les tableaux sont valables. L'alerte reste utile : un calcul réellement échoué n'aurait pas cette ligne de fin.

Ces fichiers simulent les circuits à transistors de l'alimentation de la carte v0, révision 0.5, avant toute mise sous tension : la protection contre l'inversion de la batterie (Q2, Q6), le partage entre USB et batterie (D16, D22, Q4) et la commande du chargeur (Q1, Q7). Les valeurs et les connexions viennent de `v0/circuit.py` et de `v0/netlist_voulue.txt`.

Résultats du 18 novembre 2026, ngspice 44.2 de l'image Docker du projet.

## Relancer

Depuis `hardware/` :

```
v0/simu/lancer.sh               # tout, une minute environ
v0/simu/lancer.sh b_partage     # un seul fichier
tools/kicad ngspice -b v0/simu/b_partage.cir    # à la main, sortie brute
```

`lancer.sh` écrit les tableaux dans `resultats/X.txt` et la sortie complète de ngspice dans `resultats/journaux/X.log`. Il affiche « ATTENTION » quand un calcul n'a pas convergé ou qu'une commande a échoué. Un tableau signalé ainsi n'est pas un résultat.

Après une modification du schéma, reporter la valeur dans `commun.inc`, relancer, puis comparer `resultats/` avec la version précédente.

## Fichiers

| Fichier | Contenu |
|---|---|
| `commun.inc` | L'étage d'alimentation, inclus par tous les cas. Les nœuds portent les noms des réseaux du schéma. L'en-tête liste ce qu'un cas peut changer. |
| `modeles/` | Les modèles des pièces, voir plus bas. |
| `00_modeles.cir` | Chaque modèle contre sa fiche : seuil, résistance à l'état passant, diode de corps, fuite. |
| `a_inversion.cir` | Cas A1 à A4, au repos, à −10, 25 et 60 °C, puis contre-épreuves. |
| `a5_branchement.cir` | Cas A5 : branchement de la batterie à chaud, dans le temps (A5a à A5i). |
| `a5_corrections.cir` | Le cas A5d repris en changeant une chose à la fois, puis la correction proposée. Rien de ce fichier n'est dans le schéma. |
| `b_partage.cir` | Cas B1, B2 et B4, au repos, puis contre-épreuves. |
| `b3_debranchement.cir` | Cas B3 : retrait de l'USB sous charge, dans le temps. |
| `c_chargeur.cir` | Cas C1 à C4 : réseau de CE, courants de charge, CHRG et STDBY, pont de température. |
| `lancer.sh` | Relance tout et range les résultats. |

Chaque fichier `.cir` explique ses colonnes dans son en-tête.

## Ce qu'il faut lire

Les valeurs entre parenthèses sont celles obtenues le 18 novembre 2026, à 25 °C sauf mention.

`00_modeles.txt` : à lire en premier. Chaque ligne rappelle la valeur de la fiche. Si un modèle change, tout le reste est à relire.

`a_inversion.txt`
- A1 : `chuteQ2` et `chuteQ3` à 2 A (56 à 66 mV et 82 à 96 mV). `VGS_Q6` doit rester positif : Q6 bloqué.
- A2 : `Icell` en microampères (4,2 µA, le courant de R45).
- A3 : `VDS_Q2` et `VGS_Q6` contre 12 V (−8,4 V ; −9,8 V au pire, dans les contre-épreuves). `VGS_Q2` doit valoir 0.
- A4 : le connecteur porte VBAT (4,2 V ; 5,0 V à 60 °C, voir le constat 3).

`a5_branchement.txt`
- A5d et A5e : `VBATmin` ne devrait pas passer sous −0,3 V et `tQ2` devrait rester sous 1 µs. Ce n'est pas le cas (constat 1).
- A5b et A5g : `VGS6min` doit rester au-dessus de −0,5 V (−0,18 V au pire) et la charge doit finir à 0,407 A.
- A5f : temps mis par R45 pour débloquer Q2 après le retrait d'une cellule inversée (6,5 ms).
- A5i : tension de cellule sous laquelle Q2 reste bloqué s'il l'était déjà (constat 4).

`a5_corrections.txt` : la ligne « schema tel quel » doit redonner A5d. Les lignes suivantes montrent que le résultat suit R43, puis ce que donnent les corrections.

`b_partage.txt`
- B1 : `chute totale` de la cellule à VSYS (195 à 226 mV à 2 A).
- B2 : `I_Q4` doit valoir 0 (0 µA ; −0,9 µA à 60 °C). `Icell` avec le chargeur arrêté montre la fuite de D22.
- B4 : colonne `lecture` de VBUS_DET et `chuteQ4`.

`b3_debranchement.txt` : `creux` et `tD22` (300 mV pendant 5 ms à 0,5 A), `3V3min` contre 3,0 V.

`c_chargeur.txt` : CE à 0,21 V quand GPIO21 est à 0 ; 407 et 907 mA ; seuils du pont à 2,5 et 46,3 °C.

Sous USB, avec une cellule sous 3,4 V environ, le circuit a deux états stables (constat 4). Un calcul de point de repos peut tomber sur l'un ou l'autre, ou sur l'équilibre instable entre les deux. Les cas concernés sont donc simulés dans le temps, en partant d'un état sans ambiguïté. Dans B2, si `Icell` vaut 0 pour une cellule à 3,0 V, le calcul est tombé sur l'autre état : le cas A5g fait foi.

## Constats

1. À corriger avant commande. Une cellule à l'envers branchée pendant que Q2 conduit n'est pas arrêtée à temps. Q2 conduit quand la carte est sous USB (A5d), ou quand les condensateurs sont encore chargés après le retrait d'une bonne batterie (A5e). Le commentaire de R46 attend un blocage en moins d'une microseconde, avant que VBAT passe sous la masse. La simulation donne 16 à 35 µs de conduction, 7 à 60 A en pointe selon la résistance de la cellule, et VBAT tiré entre −1,3 et −4,0 V pendant 40 µs environ (−3,3 V pour 0,1 Ω). La broche BAT du TP4056 est limitée à −0,3 V. Cause : pendant le transitoire, la grille de Q2 suit sa source à travers sa propre capacité, et R43 (10 kΩ) met 14 µs à la ramener vers BATN. Q6 ne voit que la chute dans Q2 : 0,5 V sur sa grille pour une cellule de 0,1 Ω, sous son seuil. Contre-épreuve : la durée suit R43 (3 µs à 1 kΩ, 147 µs à 100 kΩ). Sans USB et condensateurs vides, la protection tient (A5c : 4,2 µA).
   Correction essayée : 22 nF entre la grille de Q2 et BATN, en parallèle de R43, et R46 à 10 kΩ. VBAT ne descend plus sous +0,3 V, les autres cas tiennent. Il reste une pointe de tension sur Q2 quand le chemin de la cellule fait 0,03 Ω, ou 0,1 Ω avec des fils longs (200 nH) : −12,5 à −20 V pour une limite de 12 V. À 0,1 Ω et 50 nH, la pointe reste à −8,4 V. Un transistor de 20 ou 30 V à la place de Q2 lève ce reste.

2. À discuter. Au retrait de l'USB, VSYS passe par D22 pendant 3 à 6 ms, 200 à 350 mV sous son niveau final, parce que VBUS se vide lentement (11 µF dans 2,15 kΩ) et que Q4 attend. Avec un régulateur à 0,15 V de chute, le 3,3 V passe sous 3,0 V, seuil du superviseur U5, dès que la cellule est sous 3,6 V environ à 0,5 A : la puce redémarre au débranchement alors que la batterie suffirait. La durée suit R5 + R6 et C1 (1,3 ms avec 200 Ω + 300 Ω), le creux non.

3. À discuter. Fuite inverse des diodes DSK24.
   - D16, USB absent : VBUS remonte de 2,15 V par mA de fuite. À 0,2 mA tout va bien (VBUS_DET à 0,26 V). À 1 mA VBUS_DET est à 1,29 V, niveau indéfini. À 2 mA Q4 se bloque, D22 porte le courant (315 mV de chute) et VBUS_DET atteint 2,1 à 2,4 V. Le modèle typique donne 0,15 mA à 60 °C et 0,8 mA à 85 °C ; au maximum de la fiche, 1,1 mA dès 45 °C. Cette fuite est aussi prise à la batterie en veille : 8 µA à 25 °C, 145 µA à 60 °C.
   - D22, USB présent : sa fuite entre dans la cellule, chargeur arrêté ou charge finie. Typique : rien à 25 °C, 35 µA à 45 °C, 136 µA à 60 °C. Maximum de la fiche : 0,19 mA à 25 °C, 1,1 mA à 45 °C. Seule la protection de cellule arrête cette charge, à 4,3 V. Sans cellule, VBAT monte à VSYS (5,0 V à 60 °C).

4. À discuter. Sous USB, si Q2 se trouve bloqué alors que la cellule est à l'endroit et sous 3,3 à 3,5 V, Q6 le garde bloqué : la cellule ne charge pas tant que l'USB reste branché (A5i). Aucune séquence simulée n'y mène : branchement de la cellule sous USB (A5b), branchement de l'USB (A5g), retrait d'une cellule inversée (A5f).

5. À discuter. À 2 A, la chute dans Q3 atteint 78 à 103 mV avec le modèle typique. La protection DW01A coupe à 150 mV (130 mV au pire). Avec la résistance maximale de la fiche (31,5 mΩ au lieu de 25) et 10 % de plus à chaud, le calcul donne 130 à 140 mV.

6. À discuter. Pont de température : seuil froid à 2,5 °C, mais −0,8 °C si le seuil du TP4056 est à 82 % au lieu de 80 %. Seuil chaud à 46,3 °C (48,9 °C à 43 %). Thermistance coupée : charge arrêtée. Thermistance en court-circuit : la fiche dit que TEMP à la masse désactive la surveillance, la puce chargerait à toute température.

## Modèles

| Pièce | Fichier | Origine | Contre la fiche, à 25 °C |
|---|---|---|---|
| DMP1045U (Q2, Q4) | `DMP1045U.spice.txt` | Diodes Inc., lien de la page produit : `https://www.diodes.com/spice/download/3691/DMP1045U+.spice.txt` | Seuil 0,74 V (fiche 0,3 / 0,55 / 1,0). 35,6 mΩ à 2,5 V (31 typ, 45 max), 26,7 mΩ à 4,5 V (26 typ). Le claquage à 12 V et les diodes de protection de grille n'y sont pas. |
| AO3401A (Q6) | `AO3401A.mod` | Alpha & Omega : `https://www.aosmd.com/sites/default/files/res/spice_models/AO3401A.mod` | Seuil 0,80 V (0,5 / 0,9 / 1,3). 72 mΩ à 2,5 V (60 typ, 85 max). |
| AO3400A (Q1, Q7) | `AO3400.mod` | Alpha & Omega, modèle de l'AO3400. AOS ne publie pas de modèle de l'AO3400A. | Seuil 1,08 V (1,05 typ). 43 mΩ à 2,5 V (24 typ, 48 max). Sans effet ici : ces transistors commutent des kilo-ohms. |
| DSK24 (D16, D22) | `luciole.lib` | Écrit à la main d'après la fiche Hongjiacheng. | 0,35 V à 1 A, 8 µA sous 4 V, 2,1 mA à 100 °C. Variante `DSK24_MAX` : 0,55 V à 2 A, 0,2 mA. |
| FS8205A (Q3) | `luciole.lib` | Écrit à la main d'après la fiche Tech Public. | 25,2 mΩ à 2,5 V, 19,5 mΩ à 4,5 V. |
| 1N4148WS (D25), PESD5Z5.0 (D24) | `luciole.lib` | Écrits à la main. | 0,58 V à 1 mA pour D25. |
| TP4056 (U2), DW01A (U3) | `luciole.lib` | Modèles de comportement, décrits dans le fichier. | |

Les trois fichiers des fabricants sont recopiés sans changement. `luciole.lib` contient aussi deux copies à seuil réglable (`DMP1045U_SEUIL`, `AO3401A_SEUIL`), pour essayer les extrêmes des fiches ; `00_modeles.cir` vérifie qu'elles redonnent les valeurs d'origine.

## Hypothèses

- La cellule est une source de tension derrière une résistance et 50 nH. La résistance vaut 0,1 Ω par défaut (cellule, protection du pack, fils, contacts) et 1 mΩ dans `b_partage.cir`. Une cellule à l'envers est une source négative.
- La protection de cellule est forcée : Q3 passant, ou Q3 ouvert (diodes de corps seules). Les délais du DW01A (0,4 à 110 ms) ne sont pas simulés.
- Le chargeur est une source de 4,2 V limitée en courant, qui n'absorbe rien. Son seuil de CE (1,4 V) est supposé. La fin de charge au dixième du courant n'est pas simulée.
- Deux diodes parasites sont supposées, les fiches n'en disent rien : de la masse vers la broche BAT du TP4056 (0,5 Ω), et de la masse vers l'alimentation du DW01A. La première fixe jusqu'où VBAT descend dans le constat 1 (−4,1 V sans elle, −2,1 V à 0,1 Ω). La durée de conduction n'en dépend pas.
- Les charges sur VSYS et VBAT sont des courants constants.
- Les condensateurs ont leur valeur marquée ; `kc=0.5` les réduit de moitié (essayé dans A5 et B3).
- Température : les modèles des transistors sous-estiment la hausse de résistance à chaud. Ils donnent +5 % à 60 °C ; la fiche du DMP1045U donne +10 %.
- La thermistance garde 25 °C quand la température de simulation change, pour que le chargeur reste en marche. Sur la carte, la charge s'arrête à −10 et à 60 °C.

## Ce qui n'est pas simulé

- La tenue du TP4056 à une tension négative sur BAT, et la tenue de Q2 à une pointe au-delà de 12 V.
- La stabilité de la boucle de courant du TP4056 avec R9 et Q1 sur PROG.
- La tolérance du courant de charge. La formule donne 407 et 907 mA ; la fiche annonce ±15 %, et son tableau donne 400 mA à 3 kΩ et 580 mA à 2 kΩ, soit vers 440 mA pour 2,7 kΩ.
- Le régulateur 3,3 V, le convertisseur des LED et la puce : seuls leurs courants sont représentés.
- Les rebonds du contact de batterie et l'inductance des pistes.

## Pièges de ngspice

- Un nœud nommé `gnd` dans un sous-circuit est la masse générale. Les broches de masse des modèles de comportement s'appellent `vss`.
- Dans une source `B`, `{1-auto}*V(x)` est mal développé. Écrire `(1-{auto})*V(x)`.
- `itl1=1000` laisse passer de faux points de repos (un nœud interne à −73 MV). Garder la valeur par défaut.
- Le repli « Transient op » de ngspice ne donne pas un point de repos fiable ici. `lancer.sh` le signale.
- `alterparam` doit être suivi de `reset`, qui annule les `alter` déjà faits.
