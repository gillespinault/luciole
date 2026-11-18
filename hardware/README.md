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
| `v0/` | Carte v0, 122 × 28 mm, deux couches. La liste de connexions voulue et le schéma, révision 0.6, concordent : 160 composants, 85 réseaux. La carte est tracée en entier depuis le 18 novembre 2026 : `tools/build.sh v0` va au bout, sans liaison manquante ni alerte hors dérogations. Le tracé est figé dans `v0/routage.json`. Deux modèles l'ont relu le 18 novembre : huit corrections sont faites et contre-relues (dossier dans `v0/revue/`). Le brochage des 27 pièces autres que résistances et condensateurs a été relevé à l'aveugle dans les fiches des pièces commandées, et l'orientation de chaque pièce contrôlée dans l'aperçu de pose de JLCPCB. Le schéma a été comparé aux montages de référence et simulé, puis la carte confrontée aux retours d'expérience d'autres concepteurs. Rien n'est commandé |
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

Les fichiers KiCad du projet sont supprimés au début de chaque construction, fichier de projet compris. Un réglage fait à la main dans KiCad, comme la désactivation d'un contrôle, ne survit donc pas. Les verrous (`~projet.kicad_pro.lck`) sont supprimés aussi : un verrou resté d'une session interrompue fait croire à KiCad que le projet est ouvert ailleurs, il n'écrit alors plus le fichier de projet et la carte échoue à l'écriture des classes de réseaux.

## Routage

Le routage d'une carte se fait en deux temps, tous deux dans `carte.py`.

La structure se trace par script : liaisons longues, alimentations, convertisseur, sorties des boîtiers à pas fin. C'est elle qui décide si la carte est routable. L'en-tête de `v0/carte.py` décrit le plan retenu pour la carte v0.

Les petits composants sont posés par `tools/pose.py` : chacun va à la place libre la plus proche du cuivre que ses pastilles relient, dans l'orientation qui convient. Les ranger par rangées, sans regarder leurs connexions, donnait des blocs où tout devait se croiser.

Les liaisons courtes qui restent, autour de chaque bloc, sont tracées par le routeur sur grille `tools/maille.py`, puis figées dans `<projet>/routage.json` :

    tools/kicad python3 v0/carte.py --router
    tools/kicad python3 v0/carte.py --router --reseaux=EN,BOOT    # quelques réseaux, pour mettre au point un bloc

La construction normale rejoue ce fichier. Sa signature dit pour quelle carte il a été calculé : après un changement de placement ou de structure, la construction s'arrête et demande de relancer le routeur.

Le routeur sur grille applique nos règles d'isolement, sur une grille de 0,05 mm, à 45 degrés, sur deux faces. Quand une liaison ne passe pas, il défait les pistes qu'il a lui-même tracées et qui la barrent, la trace, puis retrace les réseaux défaits. Il ne touche jamais aux pistes tracées par script. Il redonne toujours le même tracé. Il signale les alimentations qu'il a dû tracer plus fin que leur classe. Une pastille ni rectangulaire ni ronde (pont de soudure, pastille aux coins arrondis) est prise avec son contour exact : une piste arrêtée dans un coin de son rectangle englobant n'y est pas reliée, pour KiCad.

Une fois la carte tracée, `carte.py` fait deux finitions, à chaque construction.

La masse d'abord. Sur deux couches, chaque piste coupe un plan, et les deux plans finissent en morceaux. `Board.stitch_zones()` regroupe les morceaux déjà reliés entre eux, puis pose un via là où un morceau isolé recouvre le plan principal de l'autre face. Un morceau sans recouvrement est enfermé entre des pistes : `Router.tie()` relie alors une de ses pastilles au cuivre de masse principal, comme le routeur trace un signal, par l'une ou l'autre face. Ce qui reste isolé après cela est affiché, avec ses pastilles : c'est une poche sans issue, qui se règle dans la structure, en donnant un via de masse au composant avant le routage.

L'ébarbage ensuite. La structure propose des accès que le routeur n'utilise pas tous : un via au bout d'une voie, une sortie devant une pastille à pas fin. `Board.trim()` demande à KiCad quels bouts de piste et quels vias sont pendants, par le test de son propre contrôle. Il raccourcit la piste jusqu'à son dernier raccord, ou la retire. Avant de retirer un via relié sur une seule face, il prolonge jusqu'à son centre les pistes qui finissaient dans sa pastille : c'est le cuivre du via qui les reliait. `--sans-ebarbage` saute cette étape, pour regarder la carte avant.

Pour voir un blocage, `tools/vue.py` dessine une zone de la carte avec le nom du réseau sur chaque pastille :

    tools/kicad python3 tools/vue.py v0/v0.kicad_pcb 92 13 117 28 --face=F --reseaux=PORT_PU,IO2
    tools/kicad python3 tools/vue.py v0/v0.kicad_pcb 19 19 40 28 --face=B --plans

`--reseaux` met ces réseaux en couleurs vives, `--plans` dessine le cuivre des plans de masse : un morceau isolé s'y voit tout de suite.

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
- Le poseur ne remplace pas un plan de bloc. Il met chaque composant au plus près de son cuivre, sans voir l'ordre dans lequel les signaux arrivent. Autour d'un transistor ou d'un circuit, les broches se suivent toujours dans le même sens : si les pistes arrivent dans l'autre, il faut un croisement, donc un via, et il n'y a pas toujours la place. Les blocs où plusieurs signaux se partagent quelques composants sont donc posés et reliés par script : port côté module, USB, protecteur du port, résistances du chargeur, ponts de mesure. Le lot de douze graines est passé de zéro tracé complet à douze sur douze, et de vingt minutes à trois.
- Des voies qui remontent côte à côte forment un nid : de l'intérieur, seule la plus intérieure est accessible. Chaque voie du faisceau finit maintenant là où est son composant.
- Entre deux lignes qui traversent un composant, ce qui est au milieu est enfermé. Pour un protecteur USBLC6, c'est sa broche de masse d'un côté et sa broche d'alimentation de l'autre : il leur faut un via chacune, à un endroit où l'autre face est libre.
- L'USB-C et le Grove sont dos à dos : entre eux, presque aucun via n'est possible. Le bloc de l'USB est tracé pour s'en passer, et les broches CC passent sous la coque du connecteur.
- Une piste d'alimentation tracée en face avant coupe la bande qu'elle traverse. Les signaux qui doivent la franchir passent par le dos ; il faut donc y garder un passage libre, et y ranger les voies au ras du faisceau.
- La zone de garde du module radio a la forme d'un T, boîtier puis zone d'antenne. Prise pour un rectangle, elle interdisait tout le coin de la carte au poseur : `Board.courtyard_boxes()` la découpe suivant ses arêtes.
- La largeur de 28 mm a libéré deux zones que les régions du poseur, écrites pour 22 mm, n'utilisaient pas : sous le coin du module, sur les deux faces, et le milieu de la bande du bas.

### Ce que la revue du routage du 18 novembre 2026 a appris

Le tri complet est dans le wiki, page « Revue du routage du 18 novembre 2026 ».

- Le contrôle des règles ne voit pas les chemins. Un circuit de puissance sans via sous sa plage thermique, une ligne qui se sépare avant sa protection, un condensateur d'alimentation à 59 mm de la broche qu'il découple : tout cela passait le contrôle.
- Une protection contre les décharges se traverse. La ligne entre par une broche et repart de l'autre. Si elle se sépare avant, la décharge prend aussi le chemin qui évite la protection.
- Un circuit de puissance qui chauffe reçoit ses vias sous sa plage centrale au moment où on le pose, pas après.
- Poser par script les petits composants d'une commande de grille. Laissés au poseur, ceux de la protection contre l'inversion avaient donné 36 mm de piste et six vias pour deux pastilles distantes de 10 mm.
- Une piste courte entre deux grandes pastilles ne chauffe presque pas : la chaleur part par ses deux bouts. Les abaques de largeur supposent une piste longue. Chiffrer avant de redessiner un bloc.
- Toute piste ajoutée en face avant peut fermer une poche du plan de masse. Le compte des groupes restés isolés, à la fin de chaque essai, l'a signalé aux douze graines pour une correction mal placée.
- Un relecteur se trompe aussi. Sur trente constats, trois reposaient sur une lecture fausse des pièces ou de la nomenclature. Chaque constat se vérifie sur la carte avant d'être corrigé.

### Simulations

    v0/simu/lancer.sh            alimentation : inversion de la batterie, partage USB/batterie, chargeur
    v0/simu-signaux/lancer.sh    port Grove, donnée des LED, reset, boutons, pont du convertisseur

Chaque dossier porte ses fichiers ngspice, ses modèles (fabricant quand il existe, écrit d'après la fiche sinon), un README qui dit quoi lire, et ses résultats. ngspice est dans l'image KiCad : rien à installer. Les valeurs du schéma sont recopiées en tête de `commun.inc` (alimentation) : les y changer avant de toucher à `circuit.py` dit en trois minutes si un changement tient dans tous les cas d'usage. Une ligne « ATTENTION » de `lancer.sh` signale un calcul qui n'a pas abouti ; son tableau n'est pas un résultat.

### Ce que les simulations et la comparaison aux montages de référence ont appris (18 novembre 2026)

- Un raisonnement écrit dans un commentaire n'est pas une vérification. Le schéma disait que le transistor Q6 bloquait Q2 « en moins d'une microseconde » quand une cellule inversée est branchée à chaud. La simulation a montré 16 à 35 µs, avec la sortie du chargeur tirée à −3 V. Deux analyses indépendantes l'ont trouvé le même jour, après quatre relectures par lecture.
- Un transistor déjà passant ne se bloque pas par le circuit qui surveille la tension à ses bornes : cette tension est nulle tant qu'il conduit. Il faut tenir sa grille (C42), pas seulement la commander.
- Couper vite un courant fort donne une pointe de tension. La première correction essayée (blocage rapide) remplaçait une tension négative par −20 V sur un transistor de 12 V. Simuler la correction autant que le défaut.
- Les valeurs maximales des fiches comptent : la fuite inverse d'une diode Schottky va de 5 µA à 25 °C à plus de 1 mA à 45 °C pour une pièce en limite de fiche. Elle suffit à fausser une détection de tension ou à recharger lentement une cellule pleine.
- Le moment fragile de cette carte est le branchement de la cellule. Règle d'atelier : la cellule d'abord, USB débranché, puis l'USB.
- Comparer à un montage de référence trouve surtout des limites d'usage (accessoires sans résistances de rappel, sens du ruban selon la marque), pas des erreurs de câblage : celles-ci avaient été trouvées par les relectures du schéma.

### Plan des pastilles de test

    tools/kicad python3 tools/pastilles.py v0/v0.kicad_pcb v0/revue/pastilles.png

La carte ne porte aucune inscription près de ses pastilles. Ce plan les situe, avec le nom de leur réseau.

### Aperçu 3D

    tools/apercu.sh v0

À lancer après `tools/build.sh`. La commande écrit :

- `v0/3d/luciole-v0.step`, que Fusion 360 et les autres logiciels de CAO ouvrent tels quels : la carte et ses pièces en volumes, pour dessiner un boîtier autour ;
- `v0/out/apercu/carte.glb`, le même modèle allégé pour un navigateur, et `vue-top.png`, `vue-bottom.png`, une vue à plat de chaque face.

L'image KiCad n'a qu'une partie des modèles 3D, et les empreintes dessinées ici n'en ont pas. Sans rien faire, la carte sort sans ses LED, son module radio ni ses connecteurs. `tools/volumes.py` donne donc à chaque pièce sans modèle un pavé à l'emprise de son contour de fabrication, de la hauteur inscrite dans sa table `VOLUMES`. Une hauteur marquée « ~ » est approximative : les deux connecteurs clairs et le bouton de bord de la v0 sont dans ce cas, à vérifier dans leurs fiches avant de dessiner un boîtier au plus près. Une pièce sans modèle et absente de la table est signalée.

Le modèle exporté par KiCad compte un morceau par face, près de 17 000 pour la v0. `tools/compacte.py` en fait un maillage par matière.

### Ce que le contrôle de la pose du 18 novembre 2026 a appris

- Sans correction, 19 pièces sur 136 étaient mal tournées dans l'aperçu de JLCPCB : un demi-tour pour les transistors et le convertisseur des LED, un quart de tour pour le chargeur, le régulateur, les protections et l'accéléromètre. La carte n'aurait pas fonctionné.
- La correction dépend de la pièce commandée, pas du boîtier. JLCPCB dessine une empreinte par référence : deux SOT-23-5 de fabricants différents demandaient l'un un demi-tour, l'autre un quart de tour. La table de `tools/jlc.py` porte donc un motif sur l'empreinte et un motif sur la valeur.
- Changer la référence d'une pièce, même pour un équivalent, demande de refaire le contrôle de son orientation.
- Au dos, la formule « 180° moins l'angle de KiCad » est la bonne, et une correction s'y ajoute dans le même sens que sur le dessus.
- JLCPCB décoche d'office une pièce qu'il juge difficile à poser, ici la LED : elle disparaît de l'aperçu et du devis tant qu'on ne la recoche pas dans la nomenclature.
- Dans l'aperçu, le repère de broche 1 de leur modèle est un point rose. Il doit tomber sur la pastille 1, que notre sérigraphie marque d'un triangle. Pour un boîtier à pattes dissymétriques, les pattes doivent tomber sur les pastilles.
- La vue de l'aperçu se déplace au bouton droit et se grossit à la molette. Glisser au bouton gauche la fait pivoter.

### Ce que les retours d'expérience ont appris (18 novembre 2026)

Quatre agents ont cherché sur le web ce qui fait échouer une première carte de ce genre : la puce et la radio, la batterie, les LED et le port, l'assemblage chez JLCPCB. Chacun devait ouvrir ses sources et confronter chaque leçon à nos fichiers. Aucune leçon n'a imposé de changer le schéma. Trois ont changé la carte ou la commande.

- JLCPCB ajoute des rails à une carte de moins de 70 mm de large : ici sur les deux grands côtés, détachés par une rainure. Il demande 0,4 mm sans cuivre le long de la rainure, qu'il place à 0,4 mm près. Une piste d'alimentation longeait le bord haut à 0,40 mm, sans marge : elle est à 0,6 mm, et les plans de masse s'arrêtent à 0,5 mm des grands côtés.
- 22 pièces sont à moins de 2,5 mm des grands côtés. Casser les rails à la main les contraint : l'option de retrait par JLCPCB est à prendre.
- La LED est classée 5a pour l'humidité, parmi les plus sensibles. JLCPCB propose l'étuvage en option (48 heures à 60 °C) et n'accepte aucune réclamation sur des LED non étuvées.
- La fiche du module radio demande un seul passage au four. JLCPCB soude d'abord la face qui porte les pièces les moins nombreuses ou les plus petites : l'ordre n'est donc pas acquis, il se demande en remarque.
- L'aperçu de pose n'engage pas JLCPCB, et un écart avec la vue de ses ingénieurs a été rapporté pour le dos. L'option « Confirm Parts Placement » leur fait confirmer la pose avant fabrication.
- JLCPCB dessine son pochoir lui-même, sans suivre nos ouvertures de pâte, et n'ouvre rien pour les pattes traversantes. Les quatre pattes du blindage de l'USB-C ne seront donc soudées que sur demande : à écrire en remarque, à contrôler à la loupe à l'arrivée, à souder au fer sinon.
- Un via ouvert au milieu d'un dépôt de pâte en boit une partie. Les vias de la plage du chargeur sont passés de six à cinq et placés entre les dépôts de l'empreinte. C'est une précaution : le pochoir de JLCPCB peut différer.
- Le superviseur coupe à 3,08 V, avant le détecteur de sous-tension de la puce. Un creux du 3,3 V à l'émission radio se lit donc comme une mise sous tension ordinaire. D'après les fiches, la marge est de 60 à 90 mV au pire : à mesurer à l'arrivée, et le firmware lit la batterie avant d'allumer la radio.
- Laissé en l'état : la piste du 3,3 V sous l'accéléromètre. ST déconseille toute piste sous ce boîtier, parce qu'elle décale le zéro. Pour détecter un mouvement, ce décalage ne compte pas ; il se mesurera.

Une leçon rapportée par un agent se vérifie à la source avant d'agir. Deux agents avaient lu la même page de JLCPCB sur le pochoir et en tiraient deux actions contraires ; la page a tranché.

Le reste tient en consignes : onze pour la première mise sous tension (page du wiki), et les règles du firmware final, en fin de `firmware/banc-v0/README.md`.

### Dossier de revue

    tools/kicad python3 tools/dossier.py v0/v0.kicad_pcb v0/revue
    for f in F B; do n=avant; [ $f = B ] && n=dos; i=1
      for r in "0 0 41.5 28" "40.5 0 82 28" "81 0 122.2 28"; do
        tools/kicad python3 tools/vue.py v0/v0.kicad_pcb $r --face=$f --zoom=40 --plans --sortie=v0/revue/$n-$i.png; i=$((i+1))
      done
    done
    cp v0/out/v0-rendu-dessus.png v0/revue/rendu-avant.png; cp v0/out/v0-rendu-dessous.png v0/revue/rendu-dos.png

`v0/revue/consigne.md` est la consigne donnée aux relecteurs, sans nos hypothèses. `v0/revue/corrections.md` est celle de la contre-relecture. Codex ne peut lancer aucune commande sur serverlab : ses pièces sont recopiées dans sa demande et les images jointes par `-i`.

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

### Options de la commande de la carte v0

Relevées le 18 novembre 2026 dans le devis de JLCPCB, sans rien commander.

| Réglage | Valeur | Raison |
|---|---|---|
| PCB Assembly | Standard, « Both Sides », 5 cartes | |
| Nomenclature | recocher la ligne de la LED C5183448 | JLCPCB la décoche à chaque traitement |
| Confirm Parts Placement | Yes, et cocher « Do not confirm automatically » | sans cette case, la pose est validée d'office après 72 heures |
| Bake Components | Yes, remarque : « Please bake the LEDs C5183448 (SK6812MINI-B-012, MSL 5a) before soldering. » | LED sensibles à l'humidité |
| Depanel boards & edge rail before delivery | Yes | 22 pièces à moins de 2,5 mm des rails |
| Assembly remark | Yes, texte ci-dessous | ordre des faces, pattes de l'USB-C, bouton |
| Livraison | une offre taxes comprises (DDP) si elle existe | sinon le transporteur avance les taxes et facture des frais |

Texte de la remarque d'assemblage :

    1. Please assemble the TOP side (LEDs) first and the BOTTOM side (ESP32-C6-MINI-1 module U6) last: the module must go through reflow only once. 2. Please solder the four shield legs of the USB-C connector J1 (through-hole slots). 3. SW3 (SKRTLAE010): the pads follow the Alps land pattern, 0.10-0.15 mm from its NPTH pegs; please keep them.

Devis du 18 novembre 2026 au soir pour cinq cartes : 214,06 €, dont 15 € de contrôle aux rayons X et 0,41 € de confirmation de la pose. S'y ajoutent, facturés après examen : l'étuvage (7,22 €), le retrait des rails (3,01 €) et ce que la remarque coûtera. Hors port (21,37 € par DHL) et taxes. Ces options allongent la fabrication de trois jours.

## Brochage du connecteur Grove

Le plan du fabricant ne numérote pas les broches. Vu de dessus, ouverture vers soi, on lit de gauche à droite : 4 masse, 3 alimentation, 2 SDA ou donnée d'un ruban LED, 1 SCL. La justification est en tête de l'empreinte, dans `lib/build_lib.py`. Elle repose sur des photos de produits M5Stack : brancher un vrai câble sur la première carte reçue reste la vérification finale.

La bibliothèque de JLCPCB numérote ce connecteur dans l'autre sens. Ne pas s'aligner sur elle.
