# Luciole² — banc d'essai de la carte v0

Un petit programme à flasher sur une carte v0 neuve pour essayer ses fonctions une par une, depuis un terminal. Il ne fait rien d'autre : pas d'effets lumineux, pas d'essaim.

Il correspond au schéma `hardware/v0/circuit.py`, révision 0.6. Tout ce qu'il sait de la carte (broches, ponts de mesure, plafond des LED) est dans `main/carte_v0.h`. Si le schéma change, c'est ce fichier qu'il faut relire.

Ce programme n'a encore tourné sur aucune carte : il n'en existe pas. La dernière section dit ce qui a été vérifié sans carte et ce qui reste à valider.

## État au démarrage

Au démarrage, le programme pose l'état le plus sûr et n'en bouge plus tant qu'une commande ne le demande pas. Avant qu'il prenne la main, les résistances de la carte tiennent déjà le convertisseur arrêté et la charge lente.

| Fonction | Broche | Niveau | Effet |
|----------|--------|--------|-------|
| Convertisseur des LED | BOOST_EN, GPIO5 | 0 | arrêté, rail des LED et port Grove à 0 V |
| Tension du rail | VSEL, GPIO20 | 0 | consigne basse, 4,45 V |
| Courant de charge | ISET, GPIO14 | 0 | charge lente, 0,4 A |
| Arrêt de la charge | CHG_INH, GPIO21 | relâchée | charge permise, comme sans programme |
| Port Grove | PORT_PU, IO1 et IO2 : GPIO15, 1 et 2 | 0 | au repos : ni rappels ni tampon, rien ne remonte vers le rail coupé |
| LED | LED_DATA, GPIO18 | 0 | aucune trame envoyée |
| Radio | | | arrêtée |

Le programme n'écrit rien en mémoire non volatile et ne met jamais la puce en veille. La table de partitions n'a pas de partition NVS : une écriture serait impossible.

## Compiler

```
cd ~/luciole/firmware/banc-v0
source ~/esp/esp-idf-v5.5/export.sh
idf.py build
```

La cible `esp32c6` est fixée par `sdkconfig.defaults`. La compilation se termine par la taille du binaire (`banc-v0.bin`, un peu moins de 1 Mo) et ne doit afficher aucun avertissement.

## Brancher la cellule

Branchez la cellule sur la carte USB débranché, puis branchez l'USB.

Dans l'autre ordre, une cellule correcte peut rester déconnectée de la carte. On lit alors 4,2 V sur la batterie alors qu'elle ne charge pas, et cela dure jusqu'au débranchement de l'USB. Dans ce cas, débranchez l'USB puis rebranchez-le.

Au premier branchement d'une cellule, ou après un échange, la protection de cellule peut rester ouverte : la carte paraît morte sur cellule seule. Ce n'est pas une panne. Branchez l'USB une seconde, la protection se referme. Sans USB, reliez un instant TP18 à TP6.

Cellule en place, débrancher l'USB ne coupe pas la carte : elle continue sur la cellule.

## Flasher et ouvrir la console

Les étapes de cette section n'ont pas pu être essayées. Elles reprennent ce que `../flash.sh` fait pour les NanoC6, qui ont la même puce.

### Par l'USB

1. Sur le serveur, arrêtez le conteneur qui tient les ports série, sinon le flash est corrompu : `docker stop limn-adopt-bridge`.
2. Branchez la carte en USB-C, cellule déjà en place. Trouvez son port : `ls /dev/serial/by-id/usb-Espressif*`. Sur le serveur, `/dev/ttyACM0` est le dongle Zigbee, pas la carte.
3. Flashez et ouvrez la console : `idf.py -p /dev/ttyACM1 flash monitor`, avec le port trouvé à l'étape 2.
4. La console affiche la bannière du banc, puis l'invite `banc>`. Tapez `?` puis Entrée pour la liste des commandes.
5. Pour quitter la console : Ctrl+]. À la fin de la séance, relancez le conteneur : `docker start limn-adopt-bridge`.

Tout terminal série convient aussi, à 115200 bauds. Le programme renvoie les caractères tapés ; la touche d'effacement fonctionne.

Sur une puce jamais programmée, le port série apparaît et disparaît toutes les 2 à 3 secondes : la puce redémarre en boucle faute de programme. C'est normal, et le flash passe quand même. Sinon, faites la manœuvre des boutons ci-dessous.

### Si l'USB ne répond pas

Une puce vierge ou un programme planté peuvent ne pas se présenter en USB. La manœuvre des boutons force le mode téléchargement :

1. Maintenez le bouton BOOT (SW2) appuyé.
2. Appuyez brièvement sur le bouton reset (SW1), puis relâchez BOOT.
3. Relancez `idf.py -p PORT flash`.
4. Après le flash, appuyez sur reset (SW1) pour lancer le programme.

Une console restée muette après un branchement est un défaut connu de cette puce, rapporté pour 6 à 15 % des mises sous tension : appuyez sur reset (SW1). Débrancher l'USB ne suffit pas quand la cellule est en place.

Si le port USB n'apparaît toujours pas, mesurez d'abord l'alimentation : 5 V sur TP1 (VBUS), 3,3 V sur TP4. Sans 3,3 V, la panne est avant la puce. Avec 3,3 V et sans port USB, passez par l'UART de secours.

### UART de secours

Le schéma prévoit l'UART0 de la puce sur deux pastilles. Le banc y recopie tout ce qu'il écrit sur l'USB et y accepte les mêmes commandes.

| Pastille | Rôle | À relier, sur un adaptateur USB-série 3,3 V |
|----------|------|---------------------------------------------|
| TP8 | TXD0, sortie de la carte | RX |
| TP9 | RXD0, entrée de la carte | TX |
| TP6 ou TP7 | masse | GND |
| TP10 | EN, reset | rien : le bouton SW1 fait le même effet |
| TP11 | BOOT | rien : le bouton SW2 fait le même effet |

Ne reliez pas la broche d'alimentation de l'adaptateur. Réglage : 115200 bauds, 8 bits, sans parité.

Pour flasher par l'UART, mettez la carte en mode téléchargement avec les boutons (ci-dessus), puis `idf.py -p /dev/ttyUSB0 flash`, et reset.

Au reset, la puce écrit d'abord quelques lignes à elle sur l'UART : `SPI_FAST_FLASH_BOOT` pour un démarrage normal, `DOWNLOAD` et `waiting for download` en mode téléchargement. La bannière du banc suit moins d'une seconde plus tard. Ces lignes suffisent à dire que la puce vit, même si rien d'autre ne marche.

## Commandes

Une commande par ligne, puis Entrée. Majuscules et minuscules sont équivalentes.

```
?  ou aide            la liste des commandes
e  ou etat            toutes les mesures, et l'état des commandes
a  ou autotest        tout ce qui se vérifie sans intervention, en tableau

conv 1 | conv 0       convertisseur des LED : marche, arrêt
rail 4.5 | rail 5.0   consigne du rail : 4,45 V ou 5,04 V

charge lente          0,4 A
charge rapide         0,9 A, si la source USB annonce 1,5 A ou plus
charge arret          charge arrêtée

led N                 la LED N seule, de 1 à 15, en blanc faible
leds                  toutes en blanc faible
rouge | vert | bleu   toutes dans une seule couleur
couleurs              rouge, vert, bleu : une couleur par seconde
chenillard            une LED allumée qui parcourt la rangée
n  ou noir            extinction
lum N                 niveau des LED, de 1 à 32 (16 au démarrage)

i2c                   recherche des adresses sur le bus de l'accéléromètre
acc                   identifiant du LIS2DH12, puis les trois axes

port                  état du port Grove, lecture des deux lignes
rappels 1             mode I2C : rappels actifs, tampon inactif (mode de départ)
tampon 1              mode ruban : tampon actif vers la broche 2, rappels inactifs
port i2c              en mode I2C : recherche des adresses sur le port
ligne2 1 | 0          en mode ruban : pousse la ligne 2, pour mesurer la sortie du tampon
ruban N               en mode ruban : allume N LED d'un ruban branché sur le port, de 0 à 30

radio                 réseaux Wi-Fi entendus, puis émission avec accusé de réception
reset                 redémarre la puce : retour à l'état sûr
```

Chaque mesure s'affiche avec son unité et la plage attendue. La dernière colonne des tableaux dit `BON`, `NON <<<` ou `a voir`. « À voir » signifie que le banc ne peut pas juger seul : la valeur dépend de ce qui est branché.

## Essais, dans l'ordre conseillé

Les tensions attendues viennent du schéma et des fiches techniques. Aucune n'a encore été mesurée.

### Démarrage

Après le flash, la bannière donne la révision de la puce, le nom de l'unité (les deux derniers octets de son adresse) et la cause du démarrage. Une chute du 3,3 V ne s'affiche pas comme telle : le superviseur U5 (3,08 V) retient la puce avant que son détecteur interne (2,51 V) la voie, et la cause lue est une mise sous tension ordinaire. Une bannière qui revient toute seule, pendant l'essai radio par exemple, signale donc un creux du 3,3 V. `ERREUR DU PROGRAMME` ou `CHIEN DE GARDE` signalent un défaut du banc lui-même, pas de la carte.

### État : `e`

Exemple, obtenu sur une carte simulée (USB branché sur un ordinateur, batterie en charge) :

```
essai                  | mesure                         | attendu                                    | bon ?
-----------------------+--------------------------------+--------------------------------------------+--------
batterie (VBAT)        | 3.91 V (broche 1170 mV)        | 3.00 a 4.35 V (broche 895 a 1298 mV)       | BON
USB present (VBUS)     | oui                            | oui : un ordinateur repond en USB          | BON
ligne CC               | 205 mV (broche CC : 0.41 V)    | 100 a 1100 mV sous USB                     | BON
courant annonce        | 0.5 A (USB par defaut)         | 0.5 A <330 mV, 1.5 A <615 mV, 3 A au-dela  | BON
chargeur CHRG          | 0 (en charge)                  | 0 = en charge ; instable sans batterie     | a voir
bouton                 | 1 (relache)                    | 1 relache, 0 appuye                        | BON
demarrage, au reset    | IO8=1 IO9=1 IO15=0 IO5=0 IO4=0 | IO8=1 IO9=1 IO5=0 ; IO15, IO4 indifferents | BON
demarrage, maintenant  | IO8=1 IO9=1 IO15=0             | 1 1 0 (BOOT relache, PORT_PU a 0)          | BON
interruption accelero  | 0                              | 0 au repos                                 | BON
temperature de la puce | 31.4 C                         | 10 a 70 C                                  | BON
revision de la puce    | v0.2                           | v0.2 ou plus : ADC complet                 | BON
```

Ce que disent les lignes :

- Batterie. La puce lit 0,2985 fois la tension, par le pont R16 (470 kΩ) et R17 (200 kΩ) : 4,2 V donnent 1,25 V sur la broche. Sans cellule et sous USB, on lit la sortie du chargeur, vers 4,2 V. Précision de l'ADC : ±0,04 V. Sous USB, à 4,1 V ou plus sans charge, le banc ajoute une remarque sous le tableau : la cellule est pleine, absente, ou restée déconnectée (voir « Brancher la cellule »).
- USB présent. Lecture en tout ou rien sur GPIO7 : la carte n'a pas de mesure de la tension de VBUS.
- Ligne CC. La source USB-C annonce son courant par une tension sur l'une des deux broches CC. La puce lit la moyenne des deux, donc la moitié. Un câble USB-A vers USB-C donne 0,5 A. Sous USB, « aucune annonce » désigne un câble sans résistance ou une liaison CC coupée.
- Chargeur. Seule la sortie CHRG est reliée à la puce. Sans batterie, CHRG peut alterner entre 0 et 1 : la fiche du TP4056 annonce une période de 1 à 4 secondes. La sortie STDBY (charge finie) se lit au voltmètre sur TP13.
- Bouton. Refaites `e` en tenant le bouton : la ligne doit passer à 0.
- Révision de la puce. Les puces v0.0 et v0.1, montées dans les modules d'avant novembre 2024, perdent les quatre bits bas de l'ADC : les tensions y sont lues plus grossièrement. Le banc le signale.
- Démarrage. « Au reset » est ce que la puce a figé à sa mise sous tension. IO15 (PORT_PU) n'y est pas jugée : rail coupé, le tampon du port la tire vers 0,5 V, et la puce ne s'en sert pas. « Maintenant » se relit à chaque `e` : tenez BOOT (SW2), IO9 passe à 0.

Sous le tableau, l'état des commandes. Une sortie que la puce pousse est relue : `LA BROCHE NE SUIT PAS LA COMMANDE` signale un court-circuit sur cette broche.

### Autotest : `a`

À lancer port Grove vide, carte immobile, bouton relâché. Il reprend le tableau de l'état, puis ajoute :

- la mémoire du module, 4 Mo ;
- les rappels du bus de l'accéléromètre, son adresse (0x19 seule), son identifiant (0x33), la norme de l'accélération (0,85 à 1,15 g) et sa ligne d'interruption, que le banc fait passer à 1 puis revenir à 0 ;
- le port Grove : ses trois broches relues à 0 si le convertisseur est arrêté ; ses deux modes, I2C et ruban, s'il est en marche ;
- l'arrêt de la charge, si la batterie est en train de charger : CHRG doit passer à 1 puis revenir à 0 ;
- la radio.

Il dure moins de dix secondes, ne touche ni au convertisseur ni aux LED, et rend le port et la charge dans l'état où il les a trouvés. Il finit par un bilan : `bilan : 19 bon(s), 0 NON, 2 a voir` convertisseur arrêté. Relancez-le après `conv 1` pour essayer le port.

### Convertisseur : `conv 1`, `rail 5.0`, `conv 0`

Voltmètre sur TP5 (rail des LED), masse sur TP6.

| Commande | Sur TP5 |
|----------|---------|
| au démarrage, ou `conv 0` | 0 V |
| `conv 1` sur batterie | 4,30 à 4,60 V |
| `conv 1` sous USB | 4,30 à 4,95 V |
| `conv 1` puis `rail 5.0` | 4,85 à 5,25 V |

Sous USB, l'entrée du convertisseur (environ 0,4 V sous VBUS) dépasse la consigne basse. Le TPS61023 laisse alors passer son entrée : on lit plus que 4,45 V, et c'est normal.

La broche 3 du port Grove suit le rail, à travers le fusible F1. `conv 1` commande d'abord PORT_PU, puis démarre le convertisseur ; `conv 0` remet le port à 0, puis coupe le rail.

### LED : `conv 1`, puis `led 1`, `leds`, `couleurs`, `chenillard`, `noir`

Le convertisseur doit être en marche, sinon rien ne s'allume et le banc le rappelle. Les commandes des LED marchent aussi convertisseur arrêté, pour le cas où le rail est alimenté de l'extérieur par TP15 et TP16.

- `led 1` à `led 15` : une seule LED, blanche et faible. D1 est la première de la chaîne. Si les LED sont bonnes jusqu'à D7 et noires ensuite, cherchez entre la sortie de D7 et l'entrée de D8.
- `leds` : les quinze, du même blanc. Une LED d'une autre teinte a une couleur en panne : `rouge`, `vert`, `bleu` disent laquelle.
- `couleurs` : rouge, vert, bleu, une seconde chacune. Un autre ordre signale une erreur d'ordre des couleurs dans le programme, pas dans la carte.
- `chenillard` : un point blanc qui va de D1 à D15, un pas toutes les 150 ms.

La luminosité est plafonnée à 32 sur 255, soit 12,5 % (`BANC_LED_MAX` dans `main/carte_v0.h`). La fiche de la LED demande de rester à 70 % au plus quand les trois couleurs sont allumées : la compilation s'arrête si ce plafond est un jour dépassé. Raison : quinze LED en blanc à fond tirent 540 mA sur le rail ; à 32 sur 255, 77 mA au plus. Chaque commande affiche le courant estimé du rail, à comparer à un ampèremètre si on en a un.

### Charge : `charge arret`, `charge lente`, `charge rapide`

Sous USB, avec une cellule à charger, branchée avant l'USB :

- `e` montre CHRG à 0 ;
- `charge arret` : CHRG passe à 1 en moins d'une seconde ;
- `charge lente` : CHRG revient à 0.

`charge rapide` se vérifie avec un ampèremètre USB : le courant pris au câble monte d'environ 0,5 A. Le banc la refuse si la source annonce moins de 1,5 A ; `charge rapide force` passe outre. Ne laissez la charge rapide qu'à une cellule qui accepte 0,9 A.

Sur TP17, on lit la consigne du chargeur à travers 10 kΩ : 1,0 V pendant la charge à courant constant, aux deux vitesses, puis de moins en moins à mesure que la batterie se remplit.

### Accéléromètre : `i2c`, `acc`

`i2c` doit trouver une seule adresse, 0x19, et des lignes qui remontent en moins de 3 µs. `SDA reste a 0` ou `SCL reste a 0` désignent la ligne en défaut : rappel absent (R22, R23) ou court-circuit.

`acc` doit lire l'identifiant 0x33, puis trois accélérations dont la norme vaut 1 g. À plat sur la table, z vaut +1 ou −1 g et les deux autres environ 0. Retournez la carte : le signe de z change.

### Port Grove : `port`, `rappels 1`, `port i2c`, `tampon 1`, `ligne2`, `ruban`

Le port n'est alimenté que convertisseur en marche : sa broche 3 vient du rail des LED. Trois règles viennent des simulations du schéma (`hardware/v0/simu-signaux`). Le banc les applique lui-même :

- convertisseur arrêté, PORT_PU et les deux lignes sont à 0 ;
- PORT_PU est commandée avant le démarrage du convertisseur, et n'est jamais laissée en l'air ;
- une trame envoyée à un ruban part deux fois : la première après la mise sous tension du rail est perdue.

Le port a donc trois états :

| État | Quand | PORT_PU | Lignes 1 et 2, port vide |
|------|-------|---------|--------------------------|
| repos | convertisseur arrêté | 0 | 0 et 0, tenues par la puce |
| I2C, `rappels 1` | convertisseur en marche | 1 | 1 et 1, remontée en moins de 3 µs |
| ruban, `tampon 1` | convertisseur en marche | 0 | 0, et le niveau donné par `ligne2` |

Une seule broche commande les rappels et le tampon : `rappels 0` revient à `tampon 1`, et `tampon 0` à `rappels 1`. Le mode de départ est l'I2C. Choisi convertisseur arrêté, un mode est posé par le `conv 1` suivant.

En mode I2C, `port` lit les deux lignes et mesure leur vitesse de remontée, en tirant chaque ligne à 0 un instant : moins de 3 µs avec les rappels de 4,7 kΩ. `port i2c` cherche les adresses d'un accessoire branché sur le port.

En mode ruban, voltmètre sur la broche 2 du port : `ligne2 1` doit donner la tension du rail des LED, et non 3 V ; `ligne2 0`, 0 V. Avec un ruban de LED branché sur le port, `ruban 5` allume ses cinq premières LED en blanc faible et `ruban 0` les éteint. Le banc pilote 30 LED au plus, à 8 sur 255 : 56 mA au pire pour un ruban à 20 mA par couleur.

### Radio : `radio`, `radio force`

Le banc met la radio en marche, écoute les réseaux Wi-Fi pendant trois secondes, puis envoie dix trames à la box la plus forte et compte les accusés de réception. Il arrête ensuite la radio. Rien n'est enregistré.

- Réception : au moins un réseau, le plus fort au-dessus de −85 dBm. À quelques mètres d'une box, −30 à −60 dBm. Aucun réseau près d'une box : antenne ou radio en défaut.
- Émission : au moins 5 accusés sur 10. Un accusé prouve que la carte a émis, que la box l'a entendue et que la carte a entendu la réponse. Zéro accusé ne condamne pas l'émission : certaines box peuvent ne pas répondre à ces trames. Refaites l'essai près d'une autre box.

Avant d'allumer la radio, le banc lit la batterie. Sur cellule seule et sous 3,5 V, il ne lance pas l'essai : le 3,3 V passerait sous le seuil du superviseur pendant l'émission, et la carte redémarrerait. Branchez l'USB, ou tapez `radio force` pour essayer quand même.

Si la bannière du banc revient pendant l'essai, le rail 3,3 V ne tient pas le courant de l'émission.

## Pastilles de test

| Pastille | Réseau | Ce qu'on y lit |
|----------|--------|----------------|
| TP1 | VBUS | 5 V sous USB |
| TP2 | VBAT | la batterie, 3,0 à 4,2 V |
| TP3 | VSYS | sous USB, VBUS moins environ 0,4 V ; sinon la batterie |
| TP4 | +3V3 | 3,3 V |
| TP5 | VLED | le rail des LED : voir l'essai du convertisseur |
| TP6, TP7, TP16 | GND | masse |
| TP8, TP9 | TXD0, RXD0 | UART de secours |
| TP10, TP11 | EN, BOOT | 3,3 V au repos, 0 V bouton appuyé |
| TP12 | CC_SENSE | la tension de la ligne « ligne CC » de l'état |
| TP13 | STDBY | sous USB : 0 V quand la charge est finie, VBUS sinon |
| TP14 | LED_OUT | la sortie de la dernière LED, pour un oscilloscope |
| TP15 | VLED | injection d'une tension sur le rail des LED |
| TP17 | PROG_TP | la consigne du chargeur : voir l'essai de la charge |
| TP18 | BATN | le pôle négatif de la batterie, avant la protection |

## Table des broches

Lue dans le bloc U6 de `hardware/v0/circuit.py`, et comparée à ce bloc ligne par ligne.

| GPIO | Réseau | Sens | Niveau actif et rappel de la carte |
|------|--------|------|-------------------------------------|
| 0 | VBAT_SENSE | mesure | VBAT × 0,2985 (R16 470 kΩ, R17 200 kΩ) |
| 1 | IO1 | port, ligne 1 | SCL ; R33 4,7 kΩ vers PORT_PU |
| 2 | IO2 | port, ligne 2 | SDA ou donnée du ruban ; R34 4,7 kΩ vers PORT_PU ; entrée du tampon U10 |
| 3 | BTN_IO | entrée | 0 = appuyé ; R21 100 kΩ au 3,3 V |
| 4 | CC_SENSE | mesure | moyenne de CC1 et CC2 (R37, R38 : 200 kΩ) |
| 5 | BOOST_EN | sortie | 1 = convertisseur en marche ; R24 100 kΩ à la masse |
| 6 | ACC_INT | entrée | 1 = interruption du LIS2DH12 |
| 7 | VBUS_DET | entrée | 1 = USB présent ; pont R5 470 Ω, R6 1 kΩ : ×0,68 |
| 8 | STRAP8 | entrée | 1 ; R20 10 kΩ au 3,3 V |
| 9 | BOOT | entrée | 0 = bouton SW2 appuyé ; R19 10 kΩ au 3,3 V |
| 12, 13 | USB_DN_R, USB_DP_R | USB | jamais touchées par le programme |
| 14 | ISET | sortie | 1 = charge rapide ; R10 100 kΩ à la masse |
| 15 | PORT_PU | sortie | 1 = rappels (I2C), 0 = tampon (ruban) ; à 0 convertisseur arrêté ; R35 1 MΩ au 3,3 V |
| 18 | LED_DATA | sortie | donnée des LED, par le tampon U9 |
| 19 | CHRG | entrée | 0 = en charge ; R13 100 kΩ au 3,3 V |
| 20 | VSEL | sortie | 1 = 5,04 V, 0 = 4,45 V ; R28 1 MΩ à la masse |
| 21 | CHG_INH | drain ouvert | tirée à 0 = charge arrêtée ; jamais poussée à 1 |
| 22 | ACC_SDA | I2C | R22 10 kΩ au 3,3 V |
| 23 | ACC_SCL | I2C | R23 10 kΩ au 3,3 V |
| RXD0, TXD0 | RXD0, TXD0 | UART0 | pastilles TP9 et TP8 |

Le programme n'active aucun rappel interne de la puce, sauf sur RXD0. Seules les résistances de la carte jouent : une résistance absente se voit dans les mesures.

## Ce qui a été vérifié, et ce qui ne l'a pas été

Vérifié sans carte, le 18 novembre 2026 :

- la compilation avec ESP-IDF 5.5.4, sans avertissement ;
- la table des broches, comparée ligne par ligne au bloc U6 de `circuit.py` ;
- toutes les commandes, déroulées sur un ordinateur contre une carte simulée (dossier `simulation/`, lancé par `simulation/essai.sh`) : faux pilotes ESP-IDF, modèle des broches d'après le schéma, accéléromètre simulé. Cela couvre l'I2C logiciel, l'analyse des commandes, les tableaux, l'état sûr au démarrage, le plafond des LED et les trois règles du port Grove. Des pannes simulées (accéléromètre absent, ligne I2C collée, rappels absents, batterie basse, pont de la batterie coupé) donnent bien des `NON`.

À valider en conditions réelles, parce que seule une puce peut le dire :

- la console par l'USB et par l'UART, et la manœuvre des boutons ;
- l'ADC, le capteur de température, le pilote des LED, sur la carte et sur un ruban ;
- la radio sans partition NVS, et l'accusé de réception des trames par une box ;
- la mesure de la vitesse de remontée des lignes, dont la limite de 3 µs est calculée et non mesurée.

## Règles pour le firmware final

Ce que le banc respecte et que le vrai firmware de la carte v0 devra respecter aussi. Elles viennent du schéma, des simulations et des retours d'expérience relevés le 18 novembre 2026.

- Lire la batterie avant d'allumer la radio. Sur cellule seule et sous 3,5 V, ne pas l'allumer.
- Plafonner la puissance des LED selon la batterie, et à 70 % au plus en blanc.
- Mettre la donnée des LED à 0 avant d'allumer le rail.
- Port Grove : PORT_PU, IO1 et IO2 à 0 tant que le rail est coupé ; PORT_PU avant BOOST_EN ; première trame d'un ruban envoyée deux fois ; I2C à 100 kHz.
- La puce n'a qu'un contrôleur I2C : bus logiciel pour l'accéléromètre ou pour le port.
- Borner la charge et les LED par le courant que la source annonce sur CC.
- Arrêter la charge par CHG_INH si la batterie reste sous 3,0 V après 30 minutes, ou si la charge dépasse une durée maximale : le chargeur n'a pas de minuterie.
- Si des trames de LED se corrompent quand la radio émet, piloter les LED par le SPI plutôt que par le RMT.
- Le Wi-Fi sans économie d'énergie et le 802.15.4 ne s'écoutent pas en même temps.
- Ne jamais flasher sur une carte v0 un binaire prévu pour le NanoC6 : il pousse GPIO19 contre la sortie CHRG du chargeur.

## Fichiers

| Fichier | Contenu |
|---------|---------|
| `main/carte_v0.h` | broches, ponts de mesure, seuils, plafond des LED |
| `main/main.c` | console, commandes, mesures, autotest |
| `main/soft_i2c.c` | I2C logiciel, pour les deux bus et pour dire quelle ligne est en défaut |
| `sdkconfig.defaults` | cible, console USB, rien en mémoire non volatile |
| `partitions.csv` | l'application seule |
| `simulation/` | la carte simulée et ses scénarios ; ne fait pas partie du programme flashé |
