# Luciole² v0 : dossier pour une relecture d'une heure

Merci de prendre une heure pour cette carte. Elle a été conçue par scripts, relue par des modèles de langage, simulée, mais aucun électronicien ne l'a encore regardée et rien n'a été fabriqué. Ce qu'on cherche : ce qu'un œil de métier voit tout de suite et que ces relectures ont pu manquer.

## La carte en six lignes

- Barre lumineuse de vélo, 122 × 28 mm, deux couches, assemblée sur les deux faces chez JLCPCB. Premier lot : cinq cartes, pour mesurer.
- Module ESP32-C6-MINI-1, 15 LED SK6812 mini, accéléromètre LIS2DH12, port Grove.
- Une cellule Li-ion plaquée au dos. Chargeur linéaire TP4056 (0,41 A, ou 0,91 A sur ordre), protection DW01A et FS8205A, protection contre l'inversion par deux MOSFET P.
- Partage entre USB et batterie par diode Schottky et MOSFET P. Régulateur 3,3 V RT9080.
- Rail des LED par un TPS61023 : 4,45 V ou 5,04 V au choix du firmware, 1 A au plus.
- USB-C en périphérique, 12 Mbit/s, programmation par l'USB série de la puce.

## Les pièces, dans l'ordre où les ouvrir

Tout est dans ce dossier (`hardware/v0/revue/`) du dépôt `github.com/gillespinault/luciole`, branche `carte-v0`.

| Fichier | Contenu | Temps |
|---|---|---|
| `schema.pdf` | Le schéma, révision 0.6, une page A1 | 20 min |
| `rendu-avant.png`, `rendu-dos.png` | La carte en image | 2 min |
| `avant-1.png` à `avant-3.png`, `dos-1.png` à `dos-3.png` | Le cuivre des deux faces, de gauche à droite, avec le nom du réseau sur chaque pastille. Le dos est vu par transparence | 20 min |
| `routage.md` | La carte en clair : composants, et pour chaque réseau ses pastilles, ses pistes avec leur largeur, ses vias | à la demande |
| `pastilles.png` | Le plan des pastilles de test et des quatre ponts de soudure | 2 min |
| `../circuit.py` | Le schéma en code : chaque choix y est expliqué en commentaire, avec la référence LCSC de chaque pièce | à la demande |
| `../simu/README.md`, `../simu-signaux/README.md` | Ce qui a été simulé avec ngspice, et les résultats | à la demande |

## Ce qui a déjà été contrôlé

- Connexions : la liste voulue est écrite à la main et comparée à celle du schéma. Règles de tracé de KiCad : aucune alerte hors dérogations écrites.
- Brochage des 27 pièces autres que résistances et condensateurs : relevé dans la fiche de la référence commandée, sans voir la carte, puis comparé.
- Orientation de chaque pièce dans l'aperçu de pose de JLCPCB, sur les deux faces. 19 pièces étaient mal tournées : corrigées et recontrôlées.
- Schéma comparé bloc par bloc aux montages de référence des fabricants.
- Simulations : protection contre l'inversion, partage USB/batterie, commande du chargeur, port Grove, reset, boutons.

## Là où votre avis compte le plus

1. Protection contre l'inversion de la batterie (Q2, Q6, R43, R45, R46, C42). La simulation a trouvé qu'une cellule inversée branchée à chaud tirait la sortie du chargeur à −3 V pendant 16 à 35 µs. La révision 0.6 ajoute C42 (22 nF sur la grille de Q2), porte R46 à 10 kΩ et prend un transistor de 30 V. En simulation la sortie reste au-dessus de +0,8 V. Ce montage vous paraît-il sain ? Feriez-vous autrement ?
2. Partage de charge (D16, D22, Q4, grille de Q4 sur VBUS avec 1,47 kΩ vers la masse). Au retrait de l'USB, VSYS passe par D22 pendant 3 à 6 ms et perd 0,3 V. D22 fuit aussi vers la cellule quand l'USB est branché et la carte chaude. Garder D22 ?
3. Convertisseur TPS61023. La piste SW fait 4 mm en 0,24 mm et passe entre les bornes du condensateur d'entrée, comme sur la figure 10-1 de la fiche tournée d'un quart de tour. Acceptable à 1,9 A d'entrée ?
4. Masse sur deux couches. Les deux plans sont découpés par les pistes et recousus par des vias. Le courant de retour des LED des deux bouts de la rangée passe par les vias de couture voisins. Un point faible vous saute-t-il aux yeux sur les images du cuivre ?
5. Chargeur à 0,9 A : six vias de 0,3 mm dans la plage centrale du TP4056, vers un plan du dos estimé à 60 à 80 mm². Suffisant, ou faut-il limiter à 0,5 A ?
6. Module radio : l'antenne est au bord de la carte, sans cuivre dessous, mais le stratifié reste. La cellule finit à 12 mm de l'antenne. Faut-il découper la carte sous l'antenne dès ce lot ?
7. Ce que vous ne feriez jamais ainsi, même si cela marche.

## Ce qu'on sait déjà limité

- Un accessoire I2C sans résistances de rappel voit un niveau haut de 2,9 V sur le port Grove.
- Le port pilote un ruban de LED sur la broche 2 (convention M5Stack), pas sur la broche 1 (convention Seeed).
- Sous USB, le rail des LED suit VSYS : le réglage de 4,45 V n'est tenu que sur batterie.
- La thermistance est sur la carte, à 1,8 mm du bord de la cellule, sans contact.
- Brancher la cellule alors que l'USB est déjà là est déconseillé : c'est le cas que la protection traite le moins bien.

## Pour répondre

Un courriel, des notes sur le PDF, ou dix minutes de vive voix. Une remarque d'une ligne suffit : nous avons les outils pour la vérifier.
