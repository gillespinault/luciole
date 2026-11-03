# Luciole² — firmware

Essaim de lumières de vélo pour M5Stack NanoC6 (ESP32-C6) et AtomS3 Lite (ESP32-S3) : ruban SK6812, ESP-NOW longue portée en diffusion, sans Wi-Fi station ni serveur. Les unités ne parlent qu'entre elles et tout est borné pour tenir en foule (milliers d'unités à portée radio).

Documentation du projet : wiki Outline, collection Luciole². Simulation d'un Critical Mass avec les mêmes règles : `../sim/index.html`. Installation par USB depuis le navigateur : `../web/`.

Deux numéros de version, indépendants : `L2_FW_VERSION` (le firmware, 7.0.0) et `L2_PROTO_VERSION` (le contrat radio, 1). Le contrat est décrit en bas de `main/luciole.h` et dans la page Architecture et protocole du wiki : canal, mode longue portée, cycle, format des trames, règles d'évolution. Une luciole déjà distribuée doit rester membre de l'essaim avec les firmwares futurs.

## Cartes et configuration

Une table de brochage par cible dans `luciole.h` (`L2_BOARD`, broches du bouton, de la LED intégrée, du ruban). Un seul binaire par puce.

Le nombre de LED du ruban est une configuration en NVS (espace `luciole`, clé `leds`, 10 par défaut, 144 au plus), écrite par la page de flashage ou par la commande série `leds N`. Le courant est tenu par un limiteur par image : si l'image demande plus que `strip_peak_ma` (900 mA par défaut, estimation à `led_ma` par composante à fond), tout est atténué du même facteur. Les deux cartes ont un fusible réarmable de 1 A sur le 5 V, et le module prend ~110 mA ; une power bank d'au moins 1 A convient. Un cœur à pleine amplitude ne tire en moyenne que 10 à 25 % de son pic, l'autonomie n'est pas le facteur limitant.

Les réglages (seuils « ensemble », couleur, arc-en-ciel, cœur, onde, débit de balises, plafond et courant du ruban : 16 paramètres) sont des variables modifiées en direct par la console et enregistrées en NVS sous leur nom de clé ; les valeurs par défaut restent celles de `luciole.h`. Page web de mise au point : https://lucioles.limn-labs.xyz/luciole/.

Console série (USB, 115200 bauds), une commande par ligne, réponses en JSON sur une ligne :

```
version              fw, carte, protocole, MAC, nombre de LED
get                  tous les paramètres : [{"k","v","def","min","max","d"}, …]
get rssi_together    un paramètre
set rssi_together -85   applique et enregistre (refusé hors limites)
reset [rssi_together]   retour au défaut, pour un paramètre ou tous
status               état complet : ensemble/seule, teinte, foule, bouton prêt, courant, voisines (RSSI, proche, teinte, état, âge)…
stream 500 | off     même état toutes les 500 ms (100 au moins)
log off | on         coupe ou rétablit le journal humain (utile pendant un flux)
leds [N]             nombre de LED ; avec N : enregistre et redémarre
name [surnom]        surnom (7 caractères), enregistré et diffusé dans la balise (champ ajouté en fin, ignoré par les anciennes)
test off|white|black|chase|px N   mode test du ruban (non persistant)
onde                 lance une onde, comme un appui court sur le bouton
veille [on|off|toggle]   éteinte quand seule, comme un appui long (non persistant) ; sans argument : l'état
restart, help
```

Pendant un flux (`stream`), chaque événement d'onde sort aussi en JSON : `{"ev":"emit|heard|play|relay|skip|late","origin","id","hop","rssi","copies"}`. L'état comporte le surnom, le courant estimé du ruban (`ma`, après limiteur, et `limiter`, le facteur appliqué), `ready` (bouton armé) et, par voisine, le dernier écart de phase retenu (`ph`, ms).

## Comportement (firmware 7)

Deux états et une horloge partagée. Rien d'autre n'est affiché, parce que rien d'autre n'est comparable entre deux vélos à dix mètres, de nuit : l'instant et la couleur. Pixel 0 à gauche (côté connecteur Grove).

- Seule : arc-en-ciel linéaire sur toute la longueur, qui défile de gauche à droite (`L2_RAINBOW_FLOW` tours/s), luminosité fixe `L2_RAINBOW_B`. Rien ne bat.
- Ensemble : dès qu'une voisine est entendue au-dessus de `L2_RSSI_TOGETHER` (-92 dBm, signal lissé), le ruban prend la couleur commune et bat le cœur du groupe : `L2_HEART_BPB` battements par cycle commun de 2,5 s (3 = 72 bpm), forme « lub-dub » (attaque nette, décroissance en 120 ms, deuxième coup à 60 %), repos à `L2_HEART_FLOOR`. Un nombre entier de battements par cycle garde toutes les lucioles alignées sans horloge absolue. On reste ensemble tant qu'une voisine proche est au-dessus de `L2_RSSI_APART` (-99) et vue depuis moins de 3 s (ou 2,5 intervalles de balise, en foule). Fondu d'une seconde entre les deux états.
- Couleur commune : moyenne circulaire des voisines entendues (constante de temps 3 s, `L2_HUE_TAU_S`), diffusée dans la balise. Pas de dérive : seule une onde la change.
- Onde : un appui court sur le bouton fait traverser le ruban par un front blanc (`L2_WAVE_SWEEP_US`), puis le ruban garde la couleur de l'onde avec des paillettes (`L2_WAVE_TRAIL_US`, 3 s) et le cœur reprend dans cette couleur. L'onde porte la teinte opposée à la couleur commune (±40°), et l'impose à tout le groupe (inondation, ci-dessous). Période réfractaire : tant qu'une animation dure, qu'elle vienne de moi ou d'une autre, le bouton est ignoré. Une onde entendue pendant le front (0,5 s) ne change que la couleur ; pendant la traînée, elle relance l'animation (une voisine dont l'animation finit 100 ms après la mienne doit jouer l'onde que je viens de lancer).
- Veille : un appui long (800 ms, `L2_BUTTON_LONG_MS`) bascule la luciole seule entre éteinte et allumée (fondu de 0,5 s). Ensemble, elle bat quand même, et se rendort quand le groupe s'éloigne ; une onde reste visible en veille. Pas enregistré : allumée au démarrage. Commande `veille`, état dans `status`.
- Balises : une par temps quand on est peu ; en foule, chacune ralentit pour que le canal reste autour de `L2_BEACON_CHANNEL_RATE` trames/s en tout. Voisines oubliées après 6 s ou quatre intervalles de balise. La balise annonce `density` = voisines proches et `coh` = 255 ensemble, 0 seule (une luciole 6.x la lit comme une cohésion pleine ou nulle).
- LED intégrée : copie le pixel central tant que le bouton est prêt, s'éteint pendant la période réfractaire, veilleuse quand le ruban est noir. LED bleue (NanoC6) : un éclair à chaque battement.

Contrat radio v1 : une trame est acceptée si sa version est au moins la plus ancienne lisible et si elle est au moins aussi longue que le type connu ; le reste est ignoré. Les unités des firmwares 3 à 5 (anciens numéros de protocole) ne sont plus entendues : elles n'ont jamais été distribuées. Les 6.x s'entendent avec les 7.x : mêmes trames, mêmes champs.

### Inondation

Sans accusé ni destinataire. Appui → je joue tout de suite, j'adopte la couleur et je diffuse (origine, id, saut 0, teinte). Première copie entendue → j'adopte la couleur, je joue si rien n'est en cours, et je rediffuse une fois (saut + 1) dans un délai au hasard de 0 à `L2_WAVE_JITTER_US` (150 ms), sauf si j'ai déjà entendu `L2_WAVE_SUPPRESS` copies : mes voisines s'en sont chargées. Dédoublonnage par (origine, id) sur `L2_WAVE_RECORDS` ondes, `L2_WAVE_MAX_HOP` sauts au plus, une rediffusion par 200 ms par unité, rediffusion en retard de 2 s abandonnée. Un voisin direct joue l'onde ~15 ms après l'appui ; chaque saut coûte ~50 à 100 ms.

Simulation du 3 novembre (1000 lucioles sur un peloton de 2 km, portée 250 m, collisions ALOHA, balises et rafales d'ondes comprises) : chaque onde atteint 100 % des lucioles en 0,25 à 0,35 s avec 62 à 67 trames, contre 10 à 17 s avec l'ondulation étalée ; pic de charge des ondes 29 % du canal pendant la rafale, balises 30 %. La période réfractaire borne le débit d'ondes de tout un groupe connecté à une par 3,5 s, quelle que soit sa taille.

### Foule et balises

La taille de la foule est le nombre d'émettrices distinctes entendues sur 20 à 40 s (bitmap de hachage, `L2_CROWD_BITS`). Une balise reçue suffit à compter : l'estimation ne s'effondre pas quand les collisions montent, contrairement à un débit entendu. Intervalle = max(un temps, foule / `L2_BEACON_CHANNEL_RATE`), plafonné à 30 s. À 1000 unités à portée : une balise toutes les 17 s par unité, voisines gardées 67 s.

Réglages dans `main/luciole.h`. Ruban derrière `L2_STRIP_ENABLED`, arc-en-ciel de test derrière `L2_STRIP_TEST`, bouton derrière `L2_BUTTON_ENABLED`. Anciennes versions : historique git.

## Compiler et flasher

```bash
./flash.sh                 # un seul NanoC6 branché : port détecté
./flash.sh /dev/ttyACM1    # port explicite
./flash.sh --all --no-build --watch 30
```

Le script arrête le conteneur `limn-adopt-bridge` pendant le flash (il tient les ports série) et le relance ensuite. Ne jamais toucher `/dev/ttyACM0` (dongle Zigbee).

À la main, et pour l'AtomS3 Lite (dossier de build séparé, `sdkconfig.defaults.<cible>` ajoute la taille de flash) :

```bash
source ~/esp/esp-idf-v5.5/export.sh
idf.py set-target esp32c6 build
idf.py -p /dev/ttyACM1 flash monitor
idf.py -B build-esp32s3 -D SDKCONFIG=build-esp32s3/sdkconfig set-target esp32s3 build
```

Table de partitions `partitions.csv` : NVS à 0x9000 (la page de flashage y écrit la configuration), application de 3 Mo à 0x10000.

## Lire la console

Une ligne par cycle :

```
I (29465) luciole: cycle | decalage=3254 ms | teinte=167 ensemble (2 proches) | foule 4, balises 7.5/s, intervalle 0.5 s | ruban 143 mA | 0260:-63dBm/165* 5bdc:-47dBm/165*
```

`teinte` est la teinte courante en degrés, `foule` le nombre d'émettrices distinctes entendues, `intervalle` l'espacement de mes balises, `ruban` le courant estimé ; après le deux-points de chaque voisine : RSSI et teinte annoncée, `*` = proche (nous met ensemble), `(loin)` = entendue mais hors table.

Ondes :

```
I (12345) luciole: Luciole² 1414 | fw 6.0.0 | carte M5NanoC6 | protocole 1 (min 1) | canal 1 | 5 temps x 500 ms | teinte propre 111 | ruban 10 LED, plafond 120/255
I (12345) luciole: bouton : onde #3 emise, teinte 164 -> 350
I (12360) luciole: onde 1414#3 entendue de 1414 (saut 0, -52 dBm)
I (12400) luciole: onde 1414#3 : lecture (saut 0, proximite 0.96)
I (14900) luciole: onde 1414#3 : rediffusee (saut 1, 1 copies)
I (14950) luciole: onde 1414#3 : pas rediffusee (3 copies, saut 0)
```

`decalage` est la correction de phase accumulée. Quand plusieurs unités sont allumées, il doit se stabiliser.

## Mesures

9 octobre 2026, deux unités en intérieur, mode normal :

- RSSI à quelques mètres : -68 à -89 dBm.

12 octobre 2026, longue portée (`L2_LONG_RANGE`), 20 dBm :

- Quelques centimètres sur le hub : -36 à -69 dBm selon la paire (orientation des antennes).
- 7,5 m en intérieur : -87 à -97 dBm.
- Latence balise construite → callback de réception : environ 3 ms.
- Verrouillage de phase : moins d'une seconde. Écart résiduel : 0 à 2 ms.

13 octobre 2026, hub, cinq unités :

- Paire la plus faible : -76 à -89 dBm (1414 et ad84, aux deux bouts du hub). D'où `L2_RSSI_NEAR` -80 : à ce niveau on est collées, proximité pleine.
