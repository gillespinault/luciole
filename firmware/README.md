# Luciole² — firmware v5

Essaim de lumières de vélo pour M5NanoC6 (ESP32-C6) : ruban SK6812 10 LED, ESP-NOW longue portée en diffusion, sans Wi-Fi station ni serveur. Les unités ne parlent qu'entre elles et tout est borné pour tenir en foule (milliers d'unités à portée radio).

Documentation du projet : wiki Outline, collection Luciole². Simulation d'un Critical Mass avec les mêmes règles : `../sim/index.html`.

## Comportement (v5)

Un seul axe, « seule → ensemble », mesuré par la cohésion. Le ruban est une jauge, pixel 0 à gauche (côté connecteur Grove).

- Cohésion : chaque voisine entendue apporte une part égale à sa proximité (RSSI entre `L2_RSSI_FAR` -100 et `L2_RSSI_NEAR` -80 dBm). Les parts s'additionnent en saturant : une voisine collée suffit, trois voisines moyennes aussi. Puis elle glisse vers la moyenne annoncée par les voisines (corégulation). Constante de temps 1,5 s (`L2_COH_TAU_S`). Seule : zéro.
- Seule : arc-en-ciel linéaire sur toute la longueur, qui défile de gauche à droite (`L2_RAINBOW_FLOW` tours/s), luminosité fixe `L2_RAINBOW_B`.
- En approchant : une zone unie se remplit depuis la droite sur cohésion × 10 pixels, frontière fondue sur un pixel. Elle est dans la couleur commune et respire en sinus sur la mesure commune de 2,5 s, sommet au temps commun, autour de `L2_SOLID_B` avec une profondeur égale à la cohésion (de `L2_BREATH_MIN` à `L2_BREATH_MAX` quand elle est pleine). L'arc-en-ciel continue à défiler sur le reste et coule dans la zone unie.
- Ensemble : ruban uni, souffle plein, synchronisé sur l'essaim.
- Couleur : commune par consensus (moyenne circulaire des voisines, constante de temps 3 s), et elle voyage à 2,4°/s (`L2_HUE_DRIFT_DPS`), un tour en 2,5 min, même rythme partout. Seule, elle vagabonde en plus.
- Onde : un appui sur G9 fait traverser le ruban par un front blanc, puis l'onde gagne les voisines de proche en proche (ondulation, voir ci-dessous). Elle porte la teinte opposée à celle du moment ; chaque unité traversée l'adopte.
- Balises : une par temps quand on est peu ; en foule, chacune ralentit pour que le canal reste autour de `L2_BEACON_CHANNEL_RATE` trames/s en tout. Voisines oubliées après 6 s ou quatre intervalles de balise.
- LED intégrée : copie la LED centrale du ruban. LED bleue : métronome.

Protocole v5 : les unités v4 et antérieures ne sont plus entendues.

### Ondulation

Sans accusé ni destinataire. Appui → je joue tout de suite et je diffuse (origine, id, saut 0, teinte). Première copie entendue → je la jouerai dans (1 − proximité) × `L2_WAVE_SPREAD_US` : les proches d'abord, l'ondulation s'éloigne de l'origine. Puis je rediffuse une fois (saut + 1), les lointaines d'abord, sauf si j'ai déjà entendu `L2_WAVE_SUPPRESS` copies : mes voisines s'en sont chargées. Dédoublonnage par (origine, id) sur `L2_WAVE_RECORDS` ondes, `L2_WAVE_MAX_HOP` sauts au plus. Une lecture par seconde, une rediffusion par 1,5 s par unité : les appuis concurrents se superposent sans tempête ; une onde en retard de 4 s est abandonnée.

Simulation du 13 octobre (1000 lucioles sur un peloton de 2 km, portée 250 m, collisions ALOHA) : chaque onde atteint 100 % des lucioles en 10 à 17 s avec 55 à 60 trames ; charge du canal 30 % par les balises.

### Foule et balises

La taille de la foule est le nombre d'émettrices distinctes entendues sur 20 à 40 s (bitmap de hachage, `L2_CROWD_BITS`). Une balise reçue suffit à compter : l'estimation ne s'effondre pas quand les collisions montent, contrairement à un débit entendu. Intervalle = max(un temps, foule / `L2_BEACON_CHANNEL_RATE`), plafonné à 30 s. À 1000 unités à portée : une balise toutes les 17 s par unité, voisines gardées 67 s.

Réglages dans `main/luciole.h`. Ruban derrière `L2_STRIP_ENABLED`, arc-en-ciel de test derrière `L2_STRIP_TEST`, bouton derrière `L2_BUTTON_ENABLED`. Anciennes versions : `main/*.v3.bak`, `main/*.v4.bak`.

## Compiler et flasher

```bash
./flash.sh                 # un seul NanoC6 branché : port détecté
./flash.sh /dev/ttyACM1    # port explicite
./flash.sh --all --no-build --watch 30
```

Le script arrête le conteneur `limn-adopt-bridge` pendant le flash (il tient les ports série) et le relance ensuite. Ne jamais toucher `/dev/ttyACM0` (dongle Zigbee).

À la main :

```bash
source ~/esp/esp-idf-v5.5/export.sh
idf.py set-target esp32c6 build
idf.py -p /dev/ttyACM1 flash monitor
```

## Lire la console

Une ligne par cycle :

```
I (29465) luciole: cycle | decalage=3254 ms | teinte=167 cohesion=0.99 | densite=4 niveau=4 | foule 4, balises 7.5/s, intervalle 0.5 s | 0260:-63dBm/165/0.99 5bdc:-47dBm/165/0.99
```

`teinte` est la teinte courante en degrés, `foule` le nombre d'émettrices distinctes entendues, `intervalle` l'espacement de mes balises ; après le deux-points de chaque voisine : RSSI, teinte annoncée, cohésion annoncée. Les voisines marquées `(loin)` sont entendues mais sous le seuil.

Ondes :

```
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
