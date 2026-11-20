/*
 * Luciole² — réglages. Tout est en microsecondes (esp_timer) sauf mention contraire.
 *
 * Deux états et une horloge partagée. Rien d'autre n'est affiché, parce que
 * rien d'autre n'est comparable entre deux vélos à dix mètres, de nuit :
 *  - seule     : arc-en-ciel calme qui défile lentement de gauche (pixel 0)
 *                à droite. Rien ne bat.
 *  - ensemble  : dès qu'une voisine est entendue régulièrement (plus de
 *                70 % de ses balises reçues), le ruban prend la
 *                couleur commune et bat le cœur du groupe : rythme fixe,
 *                pleine amplitude, au même instant sur tous les vélos (le cycle
 *                commun de 2,5 s sert de métronome). Fondu d'une seconde
 *                entre les deux états.
 *  - onde      : appui court → front qui traverse le ruban, puis le ruban
 *                garde la couleur de l'onde avec des paillettes et revient à
 *                la couleur de base, environ 5 s en tout : l'appui colore le
 *                groupe un moment, pas pour de bon. L'onde gagne tout le
 *                groupe tout de suite (inondation). Période réfractaire : pas
 *                d'appui tant qu'une animation est en cours, qu'elle vienne
 *                de moi ou d'une autre. Une onde entendue pendant la traînée
 *                relance l'animation ; pendant le front, elle ne change que
 *                la couleur.
 *  - veille    : appui long → la luciole seule est éteinte (ou rallumée) ;
 *                avec des voisines elle bat quand même, et une onde reste
 *                visible. Pas enregistré : allumée au démarrage.
 *
 * Scènes (firmware 8). Une luciole maître, celle qui reçoit une commande
 * « scene » par USB, fait passer tout le groupe dans une scène. La scène
 * change deux choses : la couleur de base et le rôle du bouton.
 *  - normale   : ce qui précède.
 *  - équipes   : chaque luciole prend l'une de N couleurs, tirée de son
 *                identifiant et d'un tirage commun. Le bouton lance une onde.
 *  - vote      : blanc tant qu'on n'a pas voté ; un appui : bleu, le suivant :
 *                orange, et ainsi de suite.
 *  - jauge     : chaque appui allume un cran de plus du ruban, jusqu'en haut,
 *                puis les appuis redescendent jusqu'à zéro.
 * La scène voyage dans les balises et dans les ondes : une luciole adopte la
 * plus récente qu'elle entend (contagion). Les votes voyagent de proche en
 * proche, et toute luciole peut donner le décompte. Voir « Scènes » plus bas.
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

#define L2_FW_VERSION       "8.0.0"

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

/* Balises : une par temps quand on est peu. En foule, chacune ralentit pour que
 * le canal reste autour de L2_BEACON_CHANNEL_RATE trames/s en tout (une trame
 * longue portée occupe l'antenne ~4 ms : 60/s ≈ un quart du temps d'antenne).
 * Les instants d'émission sont étalés uniformément sur ±50 % de l'intervalle,
 * sans lien avec le cycle commun : jusqu'en 7.1.1 chaque balise partait au
 * temps suivant, dans une fenêtre de 60 ms, et six unités sur un banc s'y
 * télescopaient (6 balises/s entendues sur 10, 10 novembre) ; en foule, tout
 * le canal serait tombé dans ces fenêtres.
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

/* Voisines : la table garde les 16 plus fortes ; toute luciole entendue y est
 * (en longue portée le récepteur descend vers -105 dBm). Une voisine est
 * oubliée après HOLD sans balise, ou 2,5 intervalles de balise si c'est plus
 * long (en foule les balises sont rares : une balise perdue ne doit pas nous
 * rendre seules). HOLD valait 3 s jusqu'en 7.2.0 : six balises perdues de
 * suite suffisaient à oublier une voisine posée à côté, qui repartait alors
 * d'un taux de réception nul (voir « Ensemble »). Le RSSI lissé ne sert qu'au
 * journal et à choisir qui remplacer quand la table est pleine. */
#define L2_MAX_NEIGHBORS    16
#define L2_NEIGHBOR_HOLD_US 10000000
#define L2_NEIGHBOR_HOLD_INTERVALS 2.5f
#define L2_NEIGHBOR_REPLACE_DB 3    /* une inconnue ne remplace la plus faible que si elle est plus forte d'autant */
#define L2_RSSI_ALPHA       0.3f

/* Ensemble : une voisine régulière nous met ensemble, et on le reste tant
 * qu'elle est en table. Régulière : on reçoit plus de L2_NEAR_ENTER de ses
 * balises ; elle cesse de l'être sous L2_NEAR_LEAVE (hystérésis). Le taux est
 * une moyenne glissante (poids L2_NEAR_ALPHA par balise) sur le compteur seq
 * de la balise : chaque numéro sauté est une balise perdue. Ainsi le critère
 * ne dépend ni du signal ni de l'intervalle de balise (en foule, les balises
 * sont rares mais numérotées pareil). Partant de zéro, une voisine à côté
 * (presque tout passe) est régulière après ~8 balises, 4 s en petit groupe.
 * Pas de seuil de signal : le RSSI varie de 10 dB d'un instant à l'autre et
 * la limite de portée est une zone de dizaines de mètres où une balise sur
 * dix passe. Un seuil au plancher (7.1.1, -100/-106 dBm) y faisait clignoter
 * « ensemble » au rythme des balises d'une luciole lointaine ; un seuil de
 * proximité (7.0.0, -92/-99) coupait à 7 m en intérieur. Le taux de
 * réception, lui, tombe net au bord de la portée : à côté, presque toutes
 * les balises arrivent ; au loin, une sur trois ou moins.
 * Entrer est strict, sortir est lent (8.0.0) : jusqu'en 7.2.0 on sortait
 * sous 50 %, et avec une seule voisine à 20 % de pertes la luciole retombait
 * en arc-en-ciel 9 fois par heure, 4 s à chaque fois (calcul du 20
 * novembre). Sous 25 %, une voisine proche ne sort plus jusqu'à 30 % de
 * pertes, et une luciole lointaine, dont une balise sur cinq arrive, n'entre
 * toujours pas. Le prix : quand une voisine s'en va pour de bon,
 * l'arc-en-ciel revient après HOLD, 10 s au lieu de 3. */
#define L2_NEAR_ALPHA       0.15f
#define L2_NEAR_ENTER       0.7f
#define L2_NEAR_LEAVE       0.25f
#define L2_TOGETHER_FADE_S  0.35f   /* constante de temps du fondu seule ↔ ensemble (~1 s) */

/* Couleur de base, degrés : l'ambre (L2_BASE_HUE), chaud comme un cœur, mais
 * pas rouge, qui est la couleur d'un feu arrière et se noie dans ceux des
 * autres vélos ; deux canaux allumés, donc plus visible que le rouge aux
 * faibles niveaux. Une onde porte une teinte tirée au hasard à plus de
 * L2_WAVE_HUE_MIN de la base. Depuis 8.0.0 elle ne change plus la couleur
 * de base : elle la recouvre le temps de son animation, puis s'efface.
 * Jusqu'en 7.2.0 la teinte du groupe revenait vers l'ambre en une
 * demi-minute, en faisant le tour du cercle des couleurs. */
#define L2_BASE_HUE         30.0f
#define L2_WAVE_HUE_MIN     60.0f

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
 * abandonnée. Période réfractaire : pas d'appui pendant une animation.
 * L'origine émet sa trame deux fois (la seconde après REPEAT) : une trame
 * directe se perd même à 30 cm, et un groupe serré ne rediffuse que deux
 * fois. La seconde copie de l'origine ne compte pas pour la suppression. */
#define L2_WAVE_SWEEP_US    500000  /* traversée du ruban */
#define L2_WAVE_TRAIL_US    4500000 /* traînée après le passage : la couleur de l'onde s'efface, 5 s en tout */
#define L2_WAVE_REPEAT_US   70000   /* seconde émission par l'origine */
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

/* ------------------------------------------------------------------ */
/* Scènes. Une scène est (type, réglage, numéro, tirage). Le numéro croît à
 * chaque commande du maître ; une luciole adopte la scène de numéro le plus
 * récent qu'elle entend, dans une balise ou dans une onde. À numéro égal,
 * le plus grand (tirage, type, réglage) l'emporte, pour que deux maîtres ne
 * laissent pas le groupe coupé en deux. Rien n'est enregistré : au
 * démarrage une luciole ne connaît aucune scène et prend celle du groupe.
 * Âge : secondes depuis le dernier signe du maître. Le maître émet l'âge 0,
 * chaque luciole garde le plus petit âge entendu et le laisse vieillir. Passé
 * L2_SCENE_TTL_S, la scène s'efface et la luciole redevient normale : un
 * maître éteint ou parti ne laisse pas le groupe bloqué. Elle revient si le
 * maître reparaît. */
#define L2_SCENE_NORMAL     0
#define L2_SCENE_TEAMS      1       /* réglage : nombre d'équipes, 2 à L2_TEAMS_MAX */
#define L2_SCENE_VOTE       2       /* bleu ou orange */
#define L2_SCENE_GAUGE      3       /* réglage : nombre de crans, 2 à L2_GAUGE_STEPS_MAX */
#define L2_SCENE_TYPES      4
#define L2_SCENE_TTL_S      600
#define L2_SCENE_AGE_UNIT_S 4       /* l'âge voyage sur un octet : 4 s par unité, 254 au plus */

/* Équipes : équipe = hachage(identifiant, tirage) modulo N. Rien à transmettre
 * que le tirage, donc valable à toute taille, et une luciole qui redémarre
 * retrouve sa couleur. Le hasard seul équilibre mal un petit groupe (15
 * lucioles en 3 équipes : 5/5/5 une fois sur vingt), alors le maître essaie
 * des tirages jusqu'à l'équilibre sur les lucioles qu'il entend. Six teintes
 * au plus : au-delà, on ne les distingue plus de nuit. */
#define L2_TEAMS_MAX        6
#define L2_TEAM_HUES        { 230, 25, 120, 300, 180, 0 }   /* bleu, orange, vert, magenta, cyan, rouge (rouge et orange voisins : cinq équipes se distinguent mieux que six) */
#define L2_ROSTER           128     /* lucioles entendues en direct, pour équilibrer les équipes */
#define L2_ROSTER_HOLD_US   30000000
#define L2_TEAM_TRIES       4000    /* tirages essayés au plus */

/* Vote et jauge. Valeur d'une luciole : 0 = pas encore voté ; vote : 1 bleu,
 * 2 orange ; jauge : 1 + cran, de 0 à N crans. Bleu et orange plutôt que
 * rouge et vert, que 8 % des hommes confondent. Tant qu'on n'a pas voté, le
 * ruban est blanc. */
#define L2_VOTE_HUE_A       230.0f  /* bleu */
#define L2_VOTE_HUE_B       25.0f   /* orange */
#define L2_GAUGE_HUE        180.0f  /* cyan */
#define L2_GAUGE_STEPS      10
#define L2_GAUGE_STEPS_MAX  20
#define L2_UNVOTED_B        0.5f    /* luminosité du blanc « pas encore voté » */
#define L2_GAUGE_OFF_B      0.04f   /* partie éteinte de la jauge */

/* Décompte : le panel (étude du 19 novembre 2026). Chaque luciole a un
 * ticket, hachage de son identifiant et du tirage de la scène, et garde la
 * table des L2_VOTE_K plus petits tickets qu'elle connaît, avec la valeur et
 * la version de chaque vote. Fusion : pour un ticket, la version la plus
 * haute ; si la table est pleine, les plus petits tickets. Ni l'ordre ni les
 * doublons ne changent le résultat, et toutes les lucioles finissent avec la
 * même table. Jusqu'à K lucioles le décompte est exact ; au-delà c'est un
 * échantillon tiré au hasard, un sondage.
 * Trois chemins, du plus lent au plus rapide :
 *  - la balise porte le vote de son émettrice : les voisines directes
 *    l'apprennent sans trame de plus ;
 *  - relais : au début de chaque temps du cycle commun (créneaux de 0,5 s
 *    partagés par tout le groupe), une luciole qui vient d'apprendre des
 *    votes les rediffuse avec une probabilité de L2_VOTE_RELAYERS sur le
 *    nombre de lucioles à portée, sauf ceux déjà entendus L2_VOTE_ECHOES fois
 *    dans les trames des autres ;
 *  - rattrapage : à chaque créneau, une luciole sur celles à portée rediffuse
 *    une tranche de sa table. Une trame perdue est ainsi réparée, sans accusé.
 * En foule (balises espacées de plus d'un temps), une luciole annonce son
 * propre vote par une trame, deux fois, si son ticket est assez petit pour
 * prétendre au panel : sous 4·K sur le nombre de lucioles à portée. */
#define L2_VOTE_K           256
#define L2_VOTE_RELAYERS    6.0f
#define L2_VOTE_ECHOES      2
#define L2_VOTE_SLOT_JITTER_US 300000   /* les trames partent dans les 300 premières ms du créneau */
#define L2_VOTE_ANNOUNCES   2

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
#define L2_MSG_VOTES     4      /* firmware 8 : ignorée par les lucioles plus anciennes */

/* Scène, telle qu'elle voyage en fin de balise et en fin d'onde (firmware 8). */
#define L2_SCENE_KNOWN   0x01
typedef struct __attribute__((packed)) {
    uint8_t  type;          /* L2_SCENE_* */
    uint8_t  arg;           /* équipes : leur nombre ; jauge : ses crans */
    uint16_t epoch;         /* numéro de la scène : le plus récent l'emporte */
    uint16_t seed;          /* tirage commun : équipes, tickets du vote */
    uint8_t  age;           /* depuis le dernier signe du maître, en L2_SCENE_AGE_UNIT_S */
    uint8_t  flags;         /* L2_SCENE_KNOWN : les champs valent ; sinon l'émettrice ne connaît aucune scène */
} l2_scene_t;

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
    /* ---- firmware 8.0.0 ---- */
    l2_scene_t scene;       /* la scène que suit l'émettrice */
    uint8_t  vote;          /* sa valeur dans cette scène, 0 = pas encore voté */
    uint8_t  vote_ver;      /* croît à chaque changement */
} l2_beacon_t;
#define L2_BEACON_V8_LEN ((int)sizeof(l2_beacon_t))

/* Onde : « (origin, id) passe par ici, saut hop ». Diffusée à toutes. 14 octets
 * dans le contrat v1, que toute luciole comprend et rediffuse. Le firmware 8
 * ajoute en fin la scène de l'émettrice : un changement de scène gagne ainsi
 * le groupe à la vitesse d'une onde. Une luciole plus ancienne rediffuse
 * l'onde sans cet ajout ; les balises le rattrapent. */
#define L2_WAVE_MIN_LEN 14
typedef struct __attribute__((packed)) {
    l2_hdr_t hdr;
    uint8_t  origin[6];     /* MAC de l'unité qui a appuyé */
    uint16_t id;            /* compteur de l'origine : (origin, id) identifie l'onde */
    uint8_t  hop;           /* sauts radio depuis l'origine */
    uint8_t  hue;           /* teinte de l'onde, 0-255 */
    /* ---- firmware 8.0.0 ---- */
    l2_scene_t scene;
} l2_wave_t;

/* Votes : des entrées de la table du panel, pour la scène (epoch, seed). */
typedef struct __attribute__((packed)) {
    uint8_t  ticket[3];     /* 24 bits, poids fort d'abord */
    uint8_t  ver;
    uint8_t  val;
} l2_vote_entry_t;
#define L2_VOTES_MAX 48     /* 9 + 48 × 5 = 249 octets, sous les 250 d'une trame ESP-NOW */
typedef struct __attribute__((packed)) {
    l2_hdr_t hdr;
    uint16_t epoch;
    uint16_t seed;
    uint8_t  n;
    l2_vote_entry_t e[L2_VOTES_MAX];
} l2_votes_t;
#define L2_VOTES_HDR_LEN 9
