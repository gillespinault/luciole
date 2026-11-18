# Cartes électroniques de Luciole²

Les cartes sont décrites par des scripts. Une commande reconstruit le schéma, la carte et les fichiers à déposer chez JLCPCB :

    tools/build.sh essai

Il faut Docker et l'image `kicad/kicad:10.0.8-full`. Le lanceur `tools/kicad` la désigne par son empreinte : la version de KiCad ne change pas tant que ce fichier ne change pas.

La spécification de la carte v0 et la méthode sont dans la collection Luciole² du wiki, pages « Carte Luciole² v0 » et « Conception de la carte v0 ».

## Dossiers

| Dossier | Contenu |
|---------|---------|
| `tools/` | La chaîne d'outils, commune à toutes les cartes |
| `lib/` | Les symboles et empreintes absents de la bibliothèque de KiCad, ou dont le brochage diffère. `build_lib.py` les écrit à partir des cotes des fiches techniques |
| `essai/` | Carte d'essai : trois LED entre deux connecteurs Grove, une pastille de test et un condensateur au dos. Elle a servi à valider la chaîne et la pose chez JLCPCB, et reste le banc de la chaîne |
| `v0/` | Carte v0, en cours. La liste de connexions voulue et le schéma, révision 0.5, concordent : 159 composants, 85 réseaux. Tous les composants sont posés ; la structure du routage est tracée et passe le contrôle des règles. Le routeur sur grille laisse encore entre 23 et 34 liaisons courtes : aucun tracé n'est figé |
| `fiches/` | Fiches techniques des fabricants et pièces de preuve. Gardées en local, non suivies par git ; `fiches/README.md` donne leurs sources |

## Les quatre fichiers d'une carte

Une carte est un dossier qui contient quatre fichiers écrits à la main.

`netlist_voulue.txt` donne les connexions voulues, par numéros de broches lus dans les fiches techniques. Il s'écrit avant le schéma. Une ligne qui commence par un espace continue le réseau de la ligne précédente.

`empreintes_voulues.txt` donne la géométrie voulue de chaque empreinte : le centre, la taille et le numéro de chaque pastille, relevés sur le plan du fabricant. Un boîtier normalisé pris dans la bibliothèque de KiCad s'y déclare `normalisé`, sans cotes.

`circuit.py` décrit le schéma, par noms de broches. Chaque broche doit être reliée à un réseau ou marquée `NC`, sinon la génération s'arrête. Elle s'arrête aussi quand deux composants sont posés si près que les fils de deux réseaux se touchent sur la page. Une empreinte sans pièce à poser (pastille de test, pont de soudure) se déclare avec `assemble=False`, une pièce prévue mais non montée avec `dnp=True`.

`carte.py` pose les composants et trace les pistes, en millimètres depuis le coin haut gauche de la carte. `flow()` range les petits composants d'un bloc dans un rectangle, `netclass()` donne leur largeur aux pistes d'alimentation. Un composant se pose au dos avec `bottom=True`. Son sens se vérifie par une assertion sur la position de ses pastilles, comme le fait la carte d'essai.

Les fichiers `.kicad_sch` et `.kicad_pcb` sont produits par ces scripts. Ils s'ouvrent dans KiCad pour la relecture. Une modification faite à la main dans KiCad est perdue à la construction suivante : elle se reporte dans le script.

## Étapes de la construction

1. Écriture de la bibliothèque du projet.
2. Écriture du schéma.
3. Contrôle électrique du schéma par KiCad.
4. Comparaison, broche par broche, de `netlist_voulue.txt` avec les connexions que KiCad exporte du schéma.
5. Comparaison, pastille par pastille, de `empreintes_voulues.txt` avec les fichiers d'empreintes.
6. Écriture de la carte à partir des connexions exportées.
7. Contrôle des règles de dessin par KiCad, avec la cohérence entre carte et schéma. KiCad remplit lui-même les plans de masse à cette étape. Toute alerte arrête la construction, sauf dérogation écrite dans `<projet>/derogations.txt`, avec sa raison ; `out/drc-compte-rendu.txt` sépare ce qui est ignoré de ce qui reste.
8. Export des fichiers de fabrication et des documents de relecture.

La construction s'arrête à la première étape qui échoue. L'étape 4 est celle qui attrape un symbole au mauvais brochage : le contrôle électrique de KiCad ne le voit pas. L'étape 5 attrape une empreinte mal numérotée ou mal cotée, que le contrôle des règles de dessin ne voit pas non plus dès que la carte est routée par réseau.

La pose d'une empreinte s'arrête aussi dans trois cas. Une pastille numérotée n'a pas de broche dans le schéma : c'est une plage thermique ou un blindage oubliés dans le symbole, ou alors une pastille à déclarer libre avec `free_pads`. Une broche laissée libre correspond à plusieurs pastilles de même numéro : il faut les relier à un réseau. Un symbole a plusieurs unités : la chaîne ne les gère pas, on dessine un symbole à une seule unité dans `lib/build_lib.py`.

Deux constructions de suite donnent les mêmes fichiers, à la date près dans les en-têtes.

Les fichiers KiCad du projet sont supprimés au début de chaque construction, fichier de projet compris. Un réglage fait à la main dans KiCad, comme la désactivation d'un contrôle, ne survit donc pas.

## Routage

Le routage d'une carte se fait en deux temps, tous deux dans `carte.py`.

La structure se trace par script : liaisons longues, alimentations, convertisseur, sorties des boîtiers à pas fin. C'est elle qui décide si la carte est routable. L'en-tête de `v0/carte.py` décrit le plan retenu pour la carte v0.

Les petits composants sont posés par `tools/pose.py` : chacun va à la place libre la plus proche du cuivre que ses pastilles relient, dans l'orientation qui convient. Les ranger par rangées, sans regarder leurs connexions, donnait des blocs où tout devait se croiser.

Les liaisons courtes qui restent, autour de chaque bloc, sont tracées par le routeur sur grille `tools/maille.py`, puis figées dans `<projet>/routage.json` :

    tools/kicad python3 v0/carte.py --router
    tools/kicad python3 v0/carte.py --router --reseaux=EN,BOOT    # quelques réseaux, pour mettre au point un bloc

La construction normale rejoue ce fichier. Sa signature dit pour quelle carte il a été calculé : après un changement de placement ou de structure, la construction s'arrête et demande de relancer le routeur.

Le routeur sur grille applique nos règles d'isolement, sur une grille de 0,05 mm, à 45 degrés, sur deux faces. Quand une liaison ne passe pas, il défait les pistes qu'il a lui-même tracées et qui la barrent, la trace, puis retrace les réseaux défaits. Il ne touche jamais aux pistes tracées par script. Il redonne toujours le même tracé. Il signale les alimentations qu'il a dû tracer plus fin que leur classe. Il ne route pas la masse : les plans la relient, et `Router.stitch()` raccorde par un via les pastilles que le plan de leur face n'atteint pas.

Pour comparer des variantes sans toucher au projet, `v0/carte.py` accepte des options d'essai. Avec l'une d'elles, la carte et son tracé s'écrivent dans `v0/out/`, sous un nom qui dit la variante ; plusieurs essais peuvent tourner en même temps.

    tools/kicad python3 v0/carte.py --router --largeur=28 --graine=7

| Option | Effet |
|--------|-------|
| `--largeur=28` | Largeur de la carte. Elle s'élargit par le bas : la rangée de LED, le module et les connecteurs gardent leur place |
| `--graine=7` | Autre ordre de passage du routeur. Chaque graine donne un autre tracé ; une graine donnée redonne le même |
| `--ecart=0.35` | Écart que le poseur laisse entre deux composants (0,2 mm par défaut) |
| `--dos=1` | Surcoût d'une piste nouvelle au dos, sous la batterie (3 par défaut) |
| `--sans=SW1,SW2` | Ne pose pas ces composants, pour mesurer ce que leur retrait libère sans toucher au schéma |

`--graine` seule n'ouvre pas le mode d'essai : elle sert aussi à tracer la carte du projet avec l'ordre retenu.

### Ce que les essais du 18 novembre 2026 ont appris

- La largeur compte plus que tout le reste. Avec toutes les fonctions, le routeur laisse 26 liaisons à 22 mm, 19 à 24 mm, 15 à 26 mm, 5 à 28 mm et 4 à 30 mm. La carte est passée à 28 mm.
- Retirer les boutons internes ne change rien. Lever le surcoût du dos non plus : les blocs qui coincent sont là où le dos est déjà pris. Un écart du poseur de 0,35 ou 0,5 mm fait moins bien que 0,2 mm.
- Lancer le routeur avec une douzaine de graines dit où chercher. Une liaison qui échoue à un endroit différent selon la graine relève de l'ordre de passage. Un réseau qui échoue à toutes les graines désigne une erreur de structure : une piste tracée par script qui enferme d'autres signaux. La commande du convertisseur, tracée en face avant devant le module, enfermait ainsi la donnée des LED et les sorties de la colonne de gauche ; elle passe maintenant au dos, dans le faisceau.
- Une protection à deux pastilles par ligne (USBLC6) se relie sous son boîtier, par script. Laissé seul, le routeur y croisait les deux lignes.

### Ce que les essais du 17 novembre 2026 sur la carte v0 ont appris

- Deux routeurs libres ont été essayés : Freerouting 2.5.0 et KiCadRoutingTools 0.24.1 (`tools/outils.sh` les installe, `tools/routeur.sh` les lance sur une copie, `tools/gel.py` fige leur tracé). Aucun ne route la carte. Sur deux placements rangés automatiquement, Freerouting laissait entre 61 et 89 liaisons sur 129 et KiCadRoutingTools échouait sur 30 réseaux. Avec la structure tracée par script, Freerouting laissait encore 55 liaisons, dont des liaisons de 1 mm entre pastilles voisines.
- Un routeur ne voit pas la structure de la carte : la barre d'alimentation et la donnée des LED coupent la face avant en deux bandes, et les contacts du module imposent l'ordre des liaisons longues.
- Le placement se pense avec le routage. Ranger les petits composants par rangées, sans regarder leurs connexions, donne des blocs où tout doit se croiser sur une seule face : ni un autre ordre de passage, ni le fait de défaire et retracer n'y changent rien. Chaque réseau, essayé seul, passe pourtant : `Router.alone()` le vérifie, et distingue ainsi une impasse de placement d'un encombrement.
- Freerouting prend les plans de masse pour des obstacles. `routeur.sh` les retire de sa copie et ôte leur réseau aux pastilles de masse.
- KiCadRoutingTools réduit par défaut la taille des vias sous les règles de la carte et l'écrit dans le fichier de projet. `routeur.sh` le lance avec `--escalation off` et remet ensuite le fichier de projet d'origine.

## Banc de fautes

    python3 tools/fautes.py

Le banc applique 27 fautes à des copies du dossier, une par une, et vérifie que la construction s'arrête à l'étape attendue : broche oubliée, symbole mal numéroté, empreinte mal numérotée ou mal cotée, pastille sans broche, piste retirée, court-circuit, même référence LCSC pour deux valeurs, contrôle désactivé dans le fichier de projet. Pour certaines fautes, il cherche aussi le message d'erreur attendu. Il se relance après toute modification de la chaîne. Compter huit minutes.

Il ne couvre pas tout. L'orientation d'une pièce chez JLCPCB ne se vérifie que dans leur aperçu de pose. La géométrie voulue d'une empreinte est écrite par la même main que l'empreinte : elle écarte une faute de frappe ou de numérotation, pas une mauvaise lecture du plan. Une empreinte critique se fait donc aussi relire à l'aveugle.

## Fichiers produits

Dans `essai/out/fab/`, les trois fichiers que JLCPCB demande :

| Fichier | Rôle |
|---------|------|
| `essai-gerbers.zip` | Circuit nu : couches et perçages |
| `essai-bom.csv` | Liste des composants, avec leur référence LCSC |
| `essai-cpl.csv` | Position et orientation de chaque composant |

`essai-jlc.txt` liste les composants dont l'orientation n'a jamais été vérifiée chez JLCPCB.

Dans `essai/out/`, pour la relecture : le schéma en PDF, le tracé des deux faces, deux rendus, un modèle 3D, les rapports des deux contrôles.

## Avant toute commande

Dans l'aperçu de pose de JLCPCB, vérifier l'orientation et le centrage de chaque composant listé dans `essai-jlc.txt`. Une fois vérifiée, la correction s'inscrit dans la table `ROTATION` de `tools/jlc.py`, avec la date. La LED et le connecteur Grove y sont depuis le 17 novembre 2026 ; la capture de l'aperçu est dans `essai/jlcpcb-apercu-2026-11-17.jpg`.

Une pièce posée au dos se vérifie à part : elle n'est déclarée vérifiée que si elle figure dans la table `ROTATION_DOS`. En attendant, la chaîne transforme son angle en 180° moins l'angle de KiCad, convention rapportée par des outils tiers et jamais contrôlée ici, et la liste parmi les pièces à contrôler. Le condensateur C4 de la carte d'essai est dans ce cas.

JLCPCB classe la LED SK6812MINI-B-012 parmi les composants difficiles à traiter. La commande est revue après paiement et des frais d'assemblage avancé peuvent s'ajouter.

## Brochage du connecteur Grove

Le plan du fabricant ne numérote pas les broches. Vu de dessus, ouverture vers soi, on lit de gauche à droite : 4 masse, 3 alimentation, 2 SDA ou donnée d'un ruban LED, 1 SCL. La justification est en tête de l'empreinte, dans `lib/build_lib.py`. Elle repose sur des photos de produits M5Stack : brancher un vrai câble sur la première carte reçue reste la vérification finale.

La bibliothèque de JLCPCB numérote ce connecteur dans l'autre sens. Ne pas s'aligner sur elle.
