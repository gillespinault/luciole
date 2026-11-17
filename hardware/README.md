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
| `essai/` | Carte d'essai : trois LED entre deux connecteurs Grove. Elle a servi à valider la chaîne et la pose chez JLCPCB |
| `fiches/` | Fiches techniques des fabricants et pièces de preuve. Gardées en local, non suivies par git ; `fiches/README.md` donne leurs sources |

## Les trois fichiers d'une carte

Une carte est un dossier qui contient trois fichiers écrits à la main.

`netlist_voulue.txt` donne les connexions voulues, par numéros de broches lus dans les fiches techniques. Il s'écrit avant le schéma.

`circuit.py` décrit le schéma, par noms de broches. Chaque broche doit être reliée à un réseau ou marquée `NC`, sinon la génération s'arrête.

`carte.py` pose les composants et trace les pistes, en millimètres depuis le coin haut gauche de la carte.

Les fichiers `.kicad_sch` et `.kicad_pcb` sont produits par ces scripts. Ils s'ouvrent dans KiCad pour la relecture. Une modification faite à la main dans KiCad est perdue à la construction suivante : elle se reporte dans le script.

## Étapes de la construction

1. Écriture de la bibliothèque du projet.
2. Écriture du schéma.
3. Contrôle électrique du schéma par KiCad.
4. Comparaison, broche par broche, de `netlist_voulue.txt` avec les connexions que KiCad exporte du schéma.
5. Écriture de la carte à partir de ces connexions exportées.
6. Contrôle des règles de dessin par KiCad, avec la cohérence entre carte et schéma.
7. Export des fichiers de fabrication et des documents de relecture.

La construction s'arrête à la première étape qui échoue. L'étape 4 est celle qui attrape un symbole au mauvais brochage : le contrôle électrique de KiCad ne le voit pas.

Deux constructions de suite donnent les mêmes fichiers, à la date près dans les en-têtes.

Les fichiers KiCad du projet sont supprimés au début de chaque construction, fichier de projet compris. Un réglage fait à la main dans KiCad, comme la désactivation d'un contrôle, ne survit donc pas.

## Banc de fautes

    python3 tools/fautes.py

Le banc applique 17 fautes à des copies du dossier, une par une, et vérifie que la construction s'arrête à l'étape attendue : broche oubliée, symbole mal numéroté, piste retirée, court-circuit, contrôle désactivé dans le fichier de projet. Il se relance après toute modification de la chaîne. Compter cinq minutes.

Il ne couvre pas tout. La numérotation des pastilles d'une empreinte n'est comparée à aucune référence : une empreinte fausse passe si la carte est routée par réseau. Les autres limites connues de la chaîne (composants au dos, symboles à plusieurs unités, points de test) sont listées dans la page « Revue indépendante du 17 novembre 2026 » du wiki.

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

JLCPCB classe la LED SK6812MINI-B-012 parmi les composants difficiles à traiter. La commande est revue après paiement et des frais d'assemblage avancé peuvent s'ajouter.

## Brochage du connecteur Grove

Le plan du fabricant ne numérote pas les broches. Vu de dessus, ouverture vers soi, on lit de gauche à droite : 4 masse, 3 alimentation, 2 SDA ou donnée d'un ruban LED, 1 SCL. La justification est en tête de l'empreinte, dans `lib/build_lib.py`. Elle repose sur des photos de produits M5Stack : brancher un vrai câble sur la première carte reçue reste la vérification finale.

La bibliothèque de JLCPCB numérote ce connecteur dans l'autre sens. Ne pas s'aligner sur elle.
