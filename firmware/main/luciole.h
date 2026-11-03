/*
 * Luciole² — réglages. Tout est en microsecondes (esp_timer) sauf mention contraire.
 *
 * Deux états et une horloge partagée. Rien d'autre n'est affiché, parce que
 * rien d'autre n'est comparable entre deux vélos à dix mètres, de nuit :
 *  - seule     : arc-en-ciel calme qui défile lentement de gauche (pixel 0)
 *                à droite. Rien ne bat.
 *  - ensemble  : dès qu'une voisine est entendue assez fort, le ruban prend la
 *                couleur commune et bat le cœur du groupe : rythme fixe,
 *                pleine amplitude, au même instant sur tous les vélos (le cycle
 *                commun de 2,5 s sert de métronome). Fondu de deux secondes
 *                entre les deux états.
 *  - onde      : appui court → front qui traverse le ruban, le ruban garde la
 *                couleur de l'onde avec des paillettes, puis le cœur reprend
 *                dans cette nouvelle couleur : l'appui change durablement la
 *                couleur commune. L'onde gagne tout le groupe tout de suite
 *                (inondation). Période réfractaire : pas d'appui tant qu'une
 *                animation est en cours, qu'elle vienne de moi ou d'une autre.
 *  - veille    : appui long → la luciole seule est éteinte (ou rallumée) ;
 *                avec des voisines elle bat quand même. Pas enregistré :
 *                allumée au démarrage.
 *
 * Deux numéros de version, indépendants :
 *  - L2_FW_VERSION    : le firmware (rendu, réglages, cartes). Change souvent.
 *  - L2_PROTO_VERSION : le contrat radio (voir « Contrat radio » en bas).
 *                       Change rarement, et sans jamais rendre sourdes les
 *                       lucioles déjà distribuées.
 */
#pragma once
#include <stdint.h>
#include "sdkconfig.h"

#define L2_FW_VERSION       "7.0.0"

/* ------------------------------------------------------------------ */
/* Cartes supportées : une table de brochage par cible. -1 = absent.   */
#if CONFIG_IDF_TARGET_ESP32C6
#define L2_BOARD            "M5NanoC6"
#define L2_RGB_DATA_GPIO    20      /* LED RGB intégrée (WS2812) */
#define L2_RGB_POWER_GPIO   19      /* alimentation de cette LED */
#define L2_BUTTON_GPIO      9       /* bouton utilisateur, actif bas */
#define L2_BLUE_LED_GPIO    7       /* LED bleue : bat avec le cœur */
#define L2_STRIP_GPIO       2       /* Grove, fil jaune = G2 (mesuré le 12 octobre) */
#elif CONFIG_IDF_TARGET_ESP32S3
#define L2_BOARD            "M5AtomS3Lite"
#define L2_RGB_DATA_GPIO    35      /* LED RGB intégrée (WS2812C) */
#define L2_RGB_POWER_GPIO   -1
#define L2_BUTTON_GPIO      41
#define L2_BLUE_LED_GPIO    -1
#define L2_STRIP_GPIO       2       /* Grove G1/G2 : à vérifier à l'ohmmètre, fil jaune = G2 supposé */
#else
#error "carte non supportée : ajouter sa table de brochage dans luciole.h"
#endif

/* Grille rythmique (fait partie du contrat radio : la phase est exprimée dans ce cycle) */
#define L2_BEATS_PER_BAR    5
#define L2_BEAT_MS          500
#define L2_BEAT_US          ((int64_t)L2_BEAT_MS * 1000)
#define L2_BAR_US           (L2_BEAT_US * L2_BEATS_PER_BAR)

/* LED intégrée */
#define L2_MAX_BRIGHTNESS   255
#define L2_NIGHTLIGHT       8       /* /255 : lueur de la LED intégrée quand le ruban est noir et le bouton prêt */

/* Radio (fait partie du contrat radio : une unité sur un autre canal ou un autre mode est invisible) */
#define L2_WIFI_CHANNEL     1
#define L2_LONG_RANGE       1       /* mode longue portée Espressif (250 kbit/s, ~+10 dB) : toutes les unités doivent l'avoir */
#define L2_TX_POWER         80      /* quarts de dBm : 80 = 20 dBm, le maximum */
#define L2_SEND_JITTER_MS   60

/* Balises : une par temps quand on est peu. En foule, chacune ralentit pour que
 * le canal reste autour de L2_BEACON_CHANNEL_RATE trames/s en tout (une trame
 * longue portée occupe l'antenne ~4 ms : 60/s ≈ un quart du temps d'antenne).
 * La taille de la foule est le nombre d'émettrices distinctes entendues sur
 * une fenêtre glissante (bitmap de hachage : une seule balise reçue suffit à
 * compter, donc l'estimation ne s'effondre pas quand les collisions montent). */
#define L2_BEACON_CHANNEL_RATE 60.0f
#define L2_BEACON_MAX_MS    30000
#define L2_CROWD_WINDOW_US  20000000 /* deux fenêtres tuilées : on compte sur 20 à 40 s */
#define L2_CROWD_BITS       8192     /* 1 Ko par fenêtre ; ~6 % de sous-estimation à 1000 unités, 17 % à 3000 (2048 bits saturaient : 48 % à 3000) */

/* Synchronisation de phase */
#define L2_PHASE_GAIN       0.3f
#define L2_LINK_LATENCY_US  3000
#define L2_PHASE_DEADBAND_US 5000

/* Voisines : la table garde les 16 plus fortes. Oubliées après L2_NEIGHBOR_TTL_US
 * ou quatre intervalles de balise si c'est plus long (en foule les balises sont
 * rares : une balise perdue ne doit pas faire tomber le groupe). */
#define L2_MAX_NEIGHBORS    16
#define L2_NEIGHBOR_TTL_US  6000000
#define L2_NEIGHBOR_TTL_INTERVALS 4
#define L2_NEIGHBOR_REPLACE_DB 3    /* une inconnue ne remplace la plus faible que si elle est plus forte d'autant */
#define L2_RSSI_ALPHA       0.3f
/* En longue portée le récepteur descend vers -105 dBm : toute luciole entendue
 * est en table (ENTER/LEAVE), et compte pour la couleur commune. */
#define L2_RSSI_ENTER       -100
#define L2_RSSI_LEAVE       -106

/* Ensemble : une voisine entendue au-dessus de TOGETHER (signal lissé) nous
 * met ensemble ; on le reste tant qu'elle est au-dessus d'APART et vue depuis
 * moins de HOLD (ou 2,5 intervalles de balise, en foule). Un seuil, pas une
 * courbe. Mesures du 12 octobre : quelques cm sur le hub -36…-89 dBm, 7,5 m
 * en intérieur -93…-97 dBm. */
#define L2_RSSI_TOGETHER    -92
#define L2_RSSI_APART       -99
#define L2_TOGETHER_HOLD_US 6000000
#define L2_TOGETHER_HOLD_INTERVALS 2.5f
#define L2_TOGETHER_FADE_S  0.7f    /* constante de temps du fondu seule ↔ ensemble (~2 s) */

/* Couleur commune, degrés : moyenne circulaire des voisines entendues, et
 * chaque onde l'emporte (teinte opposée à ±40° de hasard). Pas de dérive. */
#define L2_HUE_TAU_S        3.0f
#define L2_WAVE_HUE_TURN    180.0f
#define L2_WAVE_HUE_SPREAD  80.0f

/* Arc-en-ciel (seule) : dégradé plein spectre sur le ruban, qui défile à
 * L2_RAINBOW_FLOW tours/s, luminosité L2_RAINBOW_B. */
#define L2_RAINBOW_B        0.7f
#define L2_RAINBOW_FLOW     0.10f

/* Cœur (ensemble) : L2_HEART_BPB battements par cycle commun de 2,5 s, donc
 * 48 bpm à 2, 72 à 3, 96 à 4. Un nombre entier par cycle garde toutes les
 * lucioles alignées sans horloge absolue. Forme « lub-dub » : attaque nette,
 * décroissance exponentielle, deuxième coup plus faible. Repos à FLOOR. */
#define L2_HEART_BPB        3
#define L2_HEART_FLOOR      0.25f
#define L2_HEART_TAU_MS     120
#define L2_HEART_DUB        0.6f
#define L2_HEART_GAP_MS     180

/* Onde (inondation de proche en proche, sans accusé ni destinataire).
 * Appui → je joue tout de suite, j'adopte la couleur, je diffuse (origine, id,
 * saut 0, teinte). Première copie entendue → j'adopte la couleur, je joue si
 * rien n'est en cours, et je rediffuse une fois dans 0…JITTER, sauf si j'ai
 * déjà entendu SUPPRESS copies : mes voisines s'en sont chargées. RELAY_MIN
 * borne mon débit de rediffusion ; une rediffusion en retard de LATE est
 * abandonnée. Période réfractaire : pas d'appui pendant une animation. */
#define L2_BUTTON_ENABLED   1
#define L2_WAVE_SWEEP_US    500000  /* traversée du ruban */
#define L2_WAVE_TRAIL_US    3000000 /* traînée après le passage */
#define L2_WAVE_JITTER_US   150000  /* rediffusion dans 0…JITTER après la première copie */
#define L2_WAVE_SUPPRESS    3       /* copies entendues au-delà desquelles on ne rediffuse pas */
#define L2_WAVE_RELAY_MIN_US 200000 /* au plus une rediffusion toutes les 200 ms */
#define L2_WAVE_LATE_US     2000000 /* rediffusion en retard de 2 s : abandonnée */
#define L2_WAVE_MAX_HOP     12      /* sauts radio au plus */
#define L2_WAVE_RECORDS     32      /* ondes récentes en mémoire (dédoublonnage) */
#define L2_WAVE_FORGET_US   60000000
#define L2_BUTTON_DEBOUNCE_MS 30
#define L2_BUTTON_LONG_MS   800     /* appui tenu au-delà : veille, pas d'onde */
#define L2_VEILLE_TAU_S     0.5f    /* fondu à l'extinction et au réveil */

/* Rendu */
#define L2_RENDER_MS        10
#define L2_GAMMA            2.2f    /* fondus perçus comme linéaires */
#define L2_TICK_US          15000   /* LED bleue : éclair à chaque battement */

/* Ruban SK6812 sur le Grove. 5 V = VBUS direct, derrière le fusible
 * réarmable de 1 A de la carte (NanoC6 et AtomS3). Le nombre de LED est une
 * configuration (NVS, clé « leds », commande série « leds N »), pas une
 * constante : un seul binaire par carte. La luminosité est bornée par un
 * limiteur de courant par image (L2_STRIP_PEAK_MA, estimation à L2_LED_MA
 * par composante à fond), pas par un plafond calculé pour le tout blanc. */
#define L2_STRIP_ENABLED        1
#define L2_STRIP_TEST           0
#define L2_STRIP_LEDS_DEFAULT   10
#define L2_STRIP_LEDS_MAX       144
#define L2_STRIP_MAX_BRIGHTNESS 255     /* plafond de goût, /255 */
#define L2_STRIP_PEAK_MA        900     /* courant de pic admis pour le ruban, par image */
#define L2_LED_MA               20      /* une composante (R, G ou B) à fond : 20 mA tant qu'on n'a pas mesuré (fiches SK6812 : 8 à 12) */
#define L2_LED_IDLE_MA          0.8f    /* une SK6812 éteinte */

/* Configuration persistante (NVS) */
#define L2_NVS_NAMESPACE    "luciole"
#define L2_NVS_KEY_LEDS     "leds"
#define L2_NVS_KEY_NAME     "name"
#define L2_NAME_LEN         8       /* surnom, 7 caractères + fin de chaîne */

/* ------------------------------------------------------------------ */
/* Contrat radio v1 (13 octobre 2026). Tout ce qui suit est partagé par  */
/* toutes les lucioles, quelle que soit leur version de firmware.       */
/*                                                                      */
/* Règles d'évolution :                                                 */
/*  - une trame est acceptée si version >= L2_PROTO_MIN_VERSION et      */
/*    longueur >= taille connue du type ; les octets en plus sont       */
/*    ignorés ; un type inconnu est ignoré ;                            */
/*  - un nouveau champ va toujours à la fin d'une trame existante, avec */
/*    une valeur par défaut qui garde l'ancien comportement ;           */
/*  - la trame d'onde ne se remplace jamais : une ancienne luciole qui  */
/*    ne la comprendrait pas ne la rediffuserait pas, et l'inondation   */
/*    aurait des trous ;                                                */
/*  - canal, mode longue portée, débit, cycle de 2,5 s et échelles      */
/*    (teinte 0-255, cohésion 0-255, phase en µs) ne changent pas.      */
/*  - L2_PROTO_VERSION n'est incrémenté que si l'une de ces règles doit */
/*    être rompue ; L2_PROTO_MIN_VERSION reste à la plus ancienne       */
/*    version encore lisible.                                           */
/* Depuis le firmware 7 : « cohésion » annoncée = 255 ensemble, 0 seule */
/* (une luciole 6.x la lit comme une cohésion pleine ou nulle).         */
#define L2_PROTO_VERSION     1
#define L2_PROTO_MIN_VERSION 1
#define L2_MSG_BEACON    0
#define L2_MSG_WAVE      2

typedef struct __attribute__((packed)) {
    uint8_t  magic[2];      /* 'L' '2' */
    uint8_t  version;       /* L2_PROTO_VERSION de l'émettrice */
    uint8_t  type;          /* L2_MSG_* */
} l2_hdr_t;

/* Balise, une par intervalle : « voici où j'en suis ». 16 octets dans le
 * contrat v1 ; les champs ajoutés ensuite vont à la fin et sont optionnels
 * (une balise plus courte est acceptée, les champs absents valent 0). */
#define L2_BEACON_MIN_LEN 16
typedef struct __attribute__((packed)) {
    l2_hdr_t hdr;
    uint8_t  density;       /* voisines proches (0-255), information */
    uint8_t  hue;           /* teinte commune, 0-255 pour 0-360° */
    uint8_t  coh;           /* cohésion, 0-255 (firmware 7 : 255 ensemble, 0 seule) */
    uint8_t  flags;         /* réservé, 0 : capacités futures */
    uint32_t phase_us;      /* position dans le cycle de L2_BAR_US à l'envoi */
    uint32_t seq;           /* compteur d'émission */
    /* ---- ajouts après le contrat v1 (firmware 6.2.0) ---- */
    char     name[L2_NAME_LEN]; /* surnom, ASCII, complété de zéros ; vide = pas de surnom */
} l2_beacon_t;

/* Onde : « (origin, id) passe par ici, saut hop ». Diffusée à toutes. 14 octets. */
typedef struct __attribute__((packed)) {
    l2_hdr_t hdr;
    uint8_t  origin[6];     /* MAC de l'unité qui a appuyé */
    uint16_t id;            /* compteur de l'origine : (origin, id) identifie l'onde */
    uint8_t  hop;           /* sauts radio depuis l'origine */
    uint8_t  hue;           /* teinte de l'onde, 0-255 */
} l2_wave_t;
