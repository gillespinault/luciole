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
 */
#pragma once
#include <stdint.h>

/* Grille rythmique */
#define L2_BEATS_PER_BAR    5
#define L2_BEAT_MS          500
#define L2_BEAT_US          ((int64_t)L2_BEAT_MS * 1000)
#define L2_BAR_US           (L2_BEAT_US * L2_BEATS_PER_BAR)

/* LED intégrée */
#define L2_MAX_BRIGHTNESS   255

/* Radio */
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
 * intérieur -93…-97 dBm. Le 13 octobre, hub : paire la plus faible -76…-80 dBm. */
#define L2_RSSI_ENTER       -100
#define L2_RSSI_LEAVE       -106
#define L2_RSSI_ALPHA       0.3f
#define L2_RSSI_NEAR        -80     /* dBm : proximité pleine. Sur le hub (quelques cm), la paire la plus faible reçoit -76…-80 : à ce niveau on est collées */
#define L2_RSSI_FAR         -100    /* dBm : proximité nulle (limite d'écoute) */

/* Cohésion 0 (seule) .. 1 (ensemble), mise à jour à chaque trame de rendu.
 * Chaque voisine entendue apporte une part égale à sa proximité (RSSI entre
 * FAR et NEAR) ; les parts s'additionnent en saturant : cible = 1 - Π(1 - prox).
 * Puis on glisse vers la moyenne annoncée par les voisines (corégulation). */
#define L2_COH_TAU_S        1.5f    /* constante de temps vers la cible : réactif en approchant */
#define L2_COH_SOCIAL_TAU_S 4.0f    /* vers la moyenne des voisines */

/* Jauge : la zone unie occupe cohésion × L2_STRIP_LEDS pixels depuis la droite,
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

/* Brochage M5NanoC6 */
#define L2_RGB_DATA_GPIO    20
#define L2_RGB_POWER_GPIO   19
#define L2_BUTTON_GPIO      9
#define L2_BLUE_LED_GPIO    7
#define L2_TICK_US          15000

/* Ruban SK6812 sur le Grove : donnée fil jaune = G2. 5 V = VBUS direct, 600 mA max. */
#define L2_STRIP_ENABLED        1
#define L2_STRIP_TEST           0
#define L2_STRIP_GPIO           2
#define L2_STRIP_LEDS           10
#define L2_STRIP_MAX_BRIGHTNESS 120     /* ~47 % : 10 LED blanc ≈ 280 mA de pic */

/* Trames ESP-NOW : en-tête commun, puis le corps selon le type. */
#define L2_PROTO_VERSION 5
#define L2_MSG_BEACON    0
#define L2_MSG_WAVE      2

typedef struct __attribute__((packed)) {
    uint8_t  magic[2];      /* 'L' '2' */
    uint8_t  version;
    uint8_t  type;
} l2_hdr_t;

typedef struct __attribute__((packed)) {
    l2_hdr_t hdr;
    uint8_t  level;         /* niveau de densité de l'émettrice */
    uint8_t  hue;           /* teinte, 0-255 pour 0-360° */
    uint8_t  coh;           /* cohésion, 0-255 */
    uint8_t  reserved;
    uint32_t phase_us;      /* position dans le cycle à l'envoi */
    uint32_t seq;
} l2_beacon_t;

/* Onde : « (origin, id) passe par ici, saut hop ». Diffusée à toutes. */
typedef struct __attribute__((packed)) {
    l2_hdr_t hdr;
    uint8_t  origin[6];
    uint16_t id;
    uint8_t  hop;
    uint8_t  hue;
} l2_wave_t;
