/*
 * Luciole² — réglages. Tout est en microsecondes (esp_timer) sauf mention contraire.
 *
 * Un seul axe, « seule → ensemble », mesuré par la cohésion (règles locales,
 * sans coordinateur). Le ruban est une jauge :
 *  - seule         : arc-en-ciel qui défile de gauche (pixel 0) à droite
 *  - en approchant : une zone unie, dans la couleur commune, se remplit depuis
 *                    la droite sur cohésion × longueur ; elle respire sur le
 *                    temps commun, de plus en plus profondément
 *  - ensemble      : ruban uni, souffle plein
 *  - onde          : bouton → front blanc qui traverse le ruban, puis gagne les
 *                    voisines de proche en proche (ondulation) ; chacune adopte
 *                    sa couleur au passage
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

#define L2_FW_VERSION       "6.0.0"

/* ------------------------------------------------------------------ */
/* Cartes supportées : une table de brochage par cible. -1 = absent.   */
#if CONFIG_IDF_TARGET_ESP32C6
#define L2_BOARD            "M5NanoC6"
#define L2_RGB_DATA_GPIO    20      /* LED RGB intégrée (WS2812) */
#define L2_RGB_POWER_GPIO   19      /* alimentation de cette LED */
#define L2_BUTTON_GPIO      9       /* bouton utilisateur, actif bas */
#define L2_BLUE_LED_GPIO    7       /* LED bleue : métronome */
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
#define L2_CROWD_BITS       2048     /* 256 octets par fenêtre ; ~10 % de sous-estimation à 1000 unités */

/* Synchronisation de phase */
#define L2_PHASE_GAIN       0.3f
#define L2_LINK_LATENCY_US  3000
#define L2_PHASE_DEADBAND_US 5000

/* Voisines : la table garde les 16 plus fortes. Oubliées après L2_NEIGHBOR_TTL_US
 * ou quatre intervalles de balise si c'est plus long (en foule les balises sont
 * rares : une balise perdue ne doit pas faire tomber la cohésion). */
#define L2_MAX_NEIGHBORS    16
#define L2_NEIGHBOR_TTL_US  6000000
#define L2_NEIGHBOR_TTL_INTERVALS 4
#define L2_NEIGHBOR_REPLACE_DB 3    /* une inconnue ne remplace la plus faible que si elle est plus forte d'autant */
/* En longue portée le récepteur descend vers -105 dBm : toute luciole entendue
 * compte comme voisine, le RSSI ne sert qu'à graduer la proximité (lien).
 * Mesures du 12 octobre : quelques cm sur le hub -36…-69 dBm, 7,5 m en
 * intérieur -93…-97 dBm. Le 13 octobre, hub : paire la plus faible -76…-89 dBm. */
#define L2_RSSI_ENTER       -100
#define L2_RSSI_LEAVE       -106
#define L2_RSSI_ALPHA       0.3f
#define L2_RSSI_NEAR        -80     /* dBm : proximité pleine. Sur le hub (quelques cm), la paire la plus faible reçoit -76…-89 : à ce niveau on est collées */
#define L2_RSSI_FAR         -100    /* dBm : proximité nulle (limite d'écoute) */

/* Cohésion 0 (seule) .. 1 (ensemble), mise à jour à chaque trame de rendu.
 * Chaque voisine entendue apporte une part égale à sa proximité (RSSI entre
 * FAR et NEAR) ; les parts s'additionnent en saturant : cible = 1 - Π(1 - prox).
 * Puis on glisse vers la moyenne annoncée par les voisines (corégulation). */
#define L2_COH_TAU_S        1.5f    /* constante de temps vers la cible : réactif en approchant */
#define L2_COH_SOCIAL_TAU_S 4.0f    /* vers la moyenne des voisines */

/* Jauge : la zone unie occupe cohésion × nombre de LED pixels depuis la droite,
 * avec une frontière fondue sur un pixel. L'arc-en-ciel occupe le reste, à
 * luminosité fixe L2_RAINBOW_B, et défile vers la droite à L2_RAINBOW_FLOW
 * tours/s (un tour = le motif complet a parcouru le ruban). */
#define L2_RAINBOW_B        0.45f
#define L2_RAINBOW_FLOW     0.10f
/* Souffle de la zone unie : sinus sur la mesure commune (L2_BAR_US), sommet au
 * temps commun. Autour de L2_SOLID_B, profondeur = cohésion : de MIN à MAX
 * quand elle est pleine. */
#define L2_SOLID_B          0.5f
#define L2_BREATH_MIN       0.03f
#define L2_BREATH_MAX       1.0f

/* Couleur par consensus, degrés */
#define L2_HUE_TAU_S        3.0f    /* vers la moyenne circulaire des voisines */
#define L2_HUE_DRIFT_DPS    2.4f    /* la couleur commune voyage : un tour en 2,5 min, même rythme partout */
#define L2_HUE_WANDER_DPS   8.0f    /* seule : vagabondage aléatoire en plus */
#define L2_HUE_WAVE_GAIN    1.0f    /* trace laissée par une onde : on adopte la couleur de l'origine */

/* Onde (ondulation de proche en proche, sans accusé ni destinataire).
 * Appui → je joue tout de suite et je diffuse (origine, id, saut 0, teinte).
 * Première copie entendue → je la jouerai dans (1 - proximité) × SPREAD :
 * les proches d'abord, l'ondulation s'éloigne de l'origine. Puis je rediffuse
 * une fois (saut + 1), les lointaines d'abord (SWEEP + SPREAD × (1 + proximité)),
 * sauf si j'ai déjà entendu SUPPRESS copies : mes voisines s'en sont chargées.
 * Une lecture par seconde, une rediffusion par 1,5 s : les appuis concurrents
 * se superposent sans tempête ; au-delà, une onde en retard est abandonnée. */
#define L2_BUTTON_ENABLED   1
#define L2_WAVE_SWEEP_US    500000  /* traversée du ruban */
#define L2_WAVE_TRAIL_US    3000000 /* traînée après le passage */
#define L2_WAVE_SPREAD_US   1500000 /* étalement du délai de lecture selon la proximité */
#define L2_WAVE_MAX_HOP     12      /* sauts radio au plus */
#define L2_WAVE_SUPPRESS    3       /* copies entendues au-delà desquelles on ne rediffuse pas */
#define L2_WAVE_RELAY_JITTER_US 200000
#define L2_WAVE_RELAY_MIN_US 1500000 /* au plus une rediffusion toutes les 1,5 s */
#define L2_WAVE_MIN_PLAY_US 1000000 /* au plus une onde jouée par seconde */
#define L2_WAVE_LATE_US     4000000 /* lecture ou rediffusion en retard de 4 s : abandonnée */
#define L2_WAVE_MIN_EMIT_US 10000000 /* au plus une onde émise toutes les 10 s */
#define L2_WAVE_RECORDS     32      /* ondes récentes en mémoire (dédoublonnage) */
#define L2_WAVE_FORGET_US   60000000
#define L2_BUTTON_DEBOUNCE_MS 30

/* Rendu */
#define L2_RENDER_MS        10
#define L2_GAMMA            2.2f    /* fondus perçus comme linéaires */
#define L2_TICK_US          15000

/* Ruban SK6812 sur le Grove. 5 V = VBUS direct. Le nombre de LED est une
 * configuration (NVS, clé « leds », commande série « leds N »), pas une
 * constante : un seul binaire par carte. Le plafond de luminosité suit le
 * nombre de LED pour rester sous L2_STRIP_BUDGET_MA. */
#define L2_STRIP_ENABLED        1
#define L2_STRIP_TEST           0
#define L2_STRIP_LEDS_DEFAULT   10
#define L2_STRIP_LEDS_MAX       144
#define L2_STRIP_MAX_BRIGHTNESS 120     /* ~47 %, plafond absolu quel que soit le nombre de LED */
#define L2_STRIP_BUDGET_MA      300     /* courant de pic admis pour le ruban (tout blanc) */
#define L2_LED_FULL_MA          60      /* une SK6812 blanche à fond */

/* Configuration persistante (NVS) */
#define L2_NVS_NAMESPACE    "luciole"
#define L2_NVS_KEY_LEDS     "leds"

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
/*    ne la comprendrait pas ne la rediffuserait pas, et l'ondulation   */
/*    aurait des trous ;                                                */
/*  - canal, mode longue portée, débit, cycle de 2,5 s et échelles      */
/*    (teinte 0-255, cohésion 0-255, phase en µs) ne changent pas.      */
/*  - L2_PROTO_VERSION n'est incrémenté que si l'une de ces règles doit */
/*    être rompue ; L2_PROTO_MIN_VERSION reste à la plus ancienne       */
/*    version encore lisible.                                           */
#define L2_PROTO_VERSION     1
#define L2_PROTO_MIN_VERSION 1
#define L2_MSG_BEACON    0
#define L2_MSG_WAVE      2

typedef struct __attribute__((packed)) {
    uint8_t  magic[2];      /* 'L' '2' */
    uint8_t  version;       /* L2_PROTO_VERSION de l'émettrice */
    uint8_t  type;          /* L2_MSG_* */
} l2_hdr_t;

/* Balise, une par intervalle : « voici où j'en suis ». 16 octets. */
typedef struct __attribute__((packed)) {
    l2_hdr_t hdr;
    uint8_t  density;       /* voisines à portée (0-255), information */
    uint8_t  hue;           /* teinte commune, 0-255 pour 0-360° */
    uint8_t  coh;           /* cohésion, 0-255 */
    uint8_t  flags;         /* réservé, 0 : capacités futures */
    uint32_t phase_us;      /* position dans le cycle de L2_BAR_US à l'envoi */
    uint32_t seq;           /* compteur d'émission */
} l2_beacon_t;

/* Onde : « (origin, id) passe par ici, saut hop ». Diffusée à toutes. 14 octets. */
typedef struct __attribute__((packed)) {
    l2_hdr_t hdr;
    uint8_t  origin[6];     /* MAC de l'unité qui a appuyé */
    uint16_t id;            /* compteur de l'origine : (origin, id) identifie l'onde */
    uint8_t  hop;           /* sauts radio depuis l'origine */
    uint8_t  hue;           /* teinte de l'onde, 0-255 */
} l2_wave_t;
