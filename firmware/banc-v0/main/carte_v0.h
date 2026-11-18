/*
 * Luciole² — banc d'essai de la carte v0 : ce que le code sait de la carte.
 *
 * Tout ce fichier est lu dans hardware/v0/circuit.py, révision 0.6 du
 * 18 novembre 2026. Le nom entre parenthèses est celui du réseau dans ce
 * schéma, les repères (R16, Q7…) sont ceux de ses composants. Aucune broche
 * n'est affectée de mémoire : si le schéma change, c'est ce fichier qu'on
 * relit ligne par ligne contre le bloc U6 de circuit.py.
 *
 * Ce fichier ne dépend pas d'ESP-IDF : ses calculs se compilent aussi sur un
 * ordinateur, pour les essayer sans carte.
 */
#pragma once
#include <stdint.h>

#define V0_SCHEMA_REV       "0.6"

/* ------------------------------------------------------------------ */
/* Table des broches (bloc U6 de circuit.py, ESP32-C6-MINI-1).          */

/* Mesures analogiques */
#define V0_VBAT_SENSE_GPIO  0   /* IO0 (VBAT_SENSE) : pont R16 470 kΩ / R17 200 kΩ sur VBAT, C4 100 nF */
#define V0_CC_SENSE_GPIO    4   /* IO4 (CC_SENSE) : moyenne de CC1 et CC2 par R37 et R38, 200 kΩ, C34 100 nF */

/* Port Grove J3 */
#define V0_PORT_SCL_GPIO    1   /* IO1 (IO1) : broche 1 du Grove, SCL, par Q8 et R31 220 Ω ; R33 4,7 kΩ vers PORT_PU */
#define V0_PORT_SDA_GPIO    2   /* IO2 (IO2) : broche 2 du Grove, SDA ou donnée du ruban, par Q9 et R32 220 Ω ;
                                   R34 4,7 kΩ vers PORT_PU ; c'est aussi l'entrée A du tampon U10 */
#define V0_PORT_PU_GPIO     15  /* IO15 (PORT_PU) : une seule broche pour les rappels et le tampon ; R35 1 MΩ
                                   au 3,3 V.
                                     - poussée à 1 : rappels R33 et R34 alimentés (I2C), tampon U10 inactif ;
                                     - poussée à 0 : tampon actif vers la broche 2 (ruban) ; R33 et R34 tirent
                                       alors les deux lignes vers 0.
                                   Rappels et tampon ne peuvent donc pas être actifs ensemble. Le banc ne la
                                   laisse jamais en l'air : voir les règles du port plus bas. */

/* Entrées logiques */
#define V0_BUTTON_GPIO      3   /* IO3 (BTN_IO) : bouton SW3 vers la masse, R21 100 kΩ au 3,3 V, R40 1 kΩ en série.
                                   0 = appuyé */
#define V0_ACC_INT_GPIO     6   /* IO6 (ACC_INT) : sortie INT1 du LIS2DH12. 1 = interruption (réglage d'usine) */
#define V0_VBUS_DET_GPIO    7   /* IO7 (VBUS_DET) : pont R5 470 Ω / R6 1 kΩ sur VBUS (×0,68), R7 100 kΩ en série.
                                   1 = USB présent. Broche sans ADC : on ne lit que présent ou absent */
#define V0_STRAP8_GPIO      8   /* IO8 (STRAP8) : R20 10 kΩ au 3,3 V. Broche de démarrage, attendue à 1 */
#define V0_BOOT_GPIO        9   /* IO9 (BOOT) : R19 10 kΩ au 3,3 V, bouton SW2 vers la masse, pastille TP11.
                                   Broche de démarrage : 0 au reset = mode téléchargement */
#define V0_CHRG_GPIO        19  /* IO19 (CHRG) : sortie /CHRG du TP4056, à drain ouvert, R13 100 kΩ au 3,3 V.
                                   0 = en charge */

/* Commandes */
#define V0_BOOST_EN_GPIO    5   /* IO5 (BOOST_EN) : EN du TPS61023, R24 100 kΩ à la masse.
                                   1 = convertisseur des LED en marche, 0 = rail coupé */
#define V0_ISET_GPIO        14  /* IO14 (ISET) : grille de Q1, R10 100 kΩ à la masse.
                                   1 = R9 2,2 kΩ en parallèle de R8 2,7 kΩ : charge rapide ; 0 = charge lente */
#define V0_VSEL_GPIO        20  /* IO20 (VSEL) : grille de Q5, R28 1 MΩ à la masse.
                                   1 = R27 en parallèle de R26 : rail à 5,04 V ; 0 = rail à 4,45 V */
#define V0_CHG_INH_GPIO     21  /* IO21 (CHG_INH) : vers CE du TP4056 par R47 4,7 kΩ et Q7.
                                   Tirée à 0 = charge arrêtée ; relâchée = charge permise (CE tiré à VBUS).
                                   Le schéma interdit de la pousser à 1 : sortie à drain ouvert */
#define V0_LED_DATA_GPIO    18  /* IO18 (LED_DATA) : donnée des LED, par le tampon U9 alimenté par le rail des
                                   LED, puis R29 470 Ω vers D1 */

/* Bus I2C de l'accéléromètre U7 */
#define V0_ACC_SDA_GPIO     22  /* IO22 (ACC_SDA) : R22 10 kΩ au 3,3 V */
#define V0_ACC_SCL_GPIO     23  /* IO23 (ACC_SCL) : R23 10 kΩ au 3,3 V */

/* Broches que ce code ne configure jamais :
 *   IO12 (USB_DN_R) et IO13 (USB_DP_R) : D− et D+ de l'USB, tenus par l'USB série/JTAG de la puce ;
 *   RXD0 et TXD0 du module : UART0, pastilles TP9 et TP8. Leurs numéros de GPIO ne sont pas dans
 *   circuit.py : le code prend ceux d'ESP-IDF (U0RXD_GPIO_NUM, U0TXD_GPIO_NUM). */

/* ------------------------------------------------------------------ */
/* Ponts de mesure                                                      */

/* Batterie : VBAT — R16 — broche — R17 — masse. La broche lit 200/670 = 0,2985
 * fois VBAT : 4,2 V donnent 1,25 V. Elle se lit avec l'atténuation de 2,5 dB
 * de l'ADC, plage de 0 à 1,3 V à ±12 mV (fiche de la puce), soit ±40 mV sur
 * VBAT. */
#define V0_VBAT_R_TOP_K     470
#define V0_VBAT_R_BOTTOM_K  200
static inline int v0_vbat_mv(int pin_mv)
{
    return pin_mv * (V0_VBAT_R_TOP_K + V0_VBAT_R_BOTTOM_K) / V0_VBAT_R_BOTTOM_K;
}
static inline int v0_vbat_pin_mv(int vbat_mv)
{
    return vbat_mv * V0_VBAT_R_BOTTOM_K / (V0_VBAT_R_TOP_K + V0_VBAT_R_BOTTOM_K);
}
#define V0_VBAT_MIN_MV      3000    /* sous 3,0 V une cellule Li-ion est vide */
#define V0_VBAT_MAX_MV      4350    /* fin de charge du TP4056 : 4,2 V ±1,5 %, plus la tolérance de l'ADC.
                                       C'est aussi le haut de la plage de l'ADC : 4,35 V donnent 1,30 V */
#define V0_ADC_FINE_MAX_MV  1300    /* haut de la plage de 2,5 dB ; au-delà, la mesure n'est plus fiable */

/* USB : la broche voit 0,68 × VBUS, soit 3,40 V pour 5,0 V, à travers R7.
 * Entrée logique, lue à 1 dès 3,65 V sur VBUS. Le pont prend 3,4 mA à l'USB. */

/* Ligne CC. La source USB-C annonce son courant par la tension qu'elle pose
 * sur celle des deux broches CC que le câble relie ; l'autre reste à 0 V,
 * tirée par sa résistance de 5,1 kΩ (R1 ou R2). CC_SENSE est la moyenne des
 * deux (R37 = R38), donc la moitié de la tension de la broche reliée.
 * Tensions de la norme USB Type-C sur la broche reliée : 0,25 à 0,61 V pour
 * l'USB par défaut, 0,70 à 1,16 V pour 1,5 A, 1,31 à 2,04 V pour 3 A ; seuils
 * de décision de la norme : 0,20 V, 0,66 V et 1,23 V. Les seuils ci-dessous
 * sont ces valeurs divisées par deux. */
#define V0_CC_NONE_MAX_MV   100     /* en dessous : aucune source n'annonce de courant */
#define V0_CC_500_MAX_MV    330     /* en dessous : USB par défaut */
#define V0_CC_1500_MAX_MV   615     /* en dessous : 1,5 A ; au-dessus : 3 A */
#define V0_CC_3000_MAX_MV   1100    /* au-dessus de 2,04 V / 2 plus une marge : hors norme */

typedef enum { V0_CC_NONE, V0_CC_500, V0_CC_1500, V0_CC_3000, V0_CC_INVALID } v0_cc_t;

static inline v0_cc_t v0_cc_class(int cc_sense_mv)
{
    if (cc_sense_mv < V0_CC_NONE_MAX_MV) return V0_CC_NONE;
    if (cc_sense_mv < V0_CC_500_MAX_MV) return V0_CC_500;
    if (cc_sense_mv < V0_CC_1500_MAX_MV) return V0_CC_1500;
    if (cc_sense_mv < V0_CC_3000_MAX_MV) return V0_CC_3000;
    return V0_CC_INVALID;
}

/* Alimentation 3,3 V. Le superviseur U5 (TLV803EA30, seuil 3,08 V) retient la
 * puce avant son détecteur interne de sous-tension (2,51 V) : un creux du
 * 3,3 V se lit comme une mise sous tension ordinaire, jamais comme une
 * sous-tension. Sur cellule seule et sous 3,5 V, le 3,3 V passerait sous ce
 * seuil pendant une émission radio : le banc ne lance alors pas l'essai radio. */
#define V0_RADIO_VBAT_MIN_MV 3500

/* ------------------------------------------------------------------ */
/* Règles du port Grove, révision 0.6 (simulations hardware/v0/simu-signaux) :
 *  1. Convertisseur arrêté, PORT_PU, IO1 et IO2 sont à 0. Un niveau haut
 *     renverrait du courant dans le rail éteint, par la sortie de U10.
 *  2. PORT_PU est commandée avant BOOST_EN. Rail présent et PORT_PU en l'air,
 *     le tampon se verrouille actif et tient la ligne 2 à 0.
 *  3. La première trame envoyée à un ruban après la mise sous tension du rail
 *     est perdue (C41 se charge) : chaque trame part deux fois.
 * Le banc en tire trois états du port et n'en connaît pas d'autre :
 *     repos   convertisseur arrêté : PORT_PU, IO1, IO2 poussées à 0 ;
 *     I2C     PORT_PU à 1, IO1 et IO2 relâchées ;
 *     ruban   PORT_PU à 0, IO1 à 0, IO2 poussée par la puce. */

/* Ruban d'essai sur le port : 30 LED au plus, à 8/255. Un ruban M5Stack
 * (SK6812, 20 mA par couleur supposés par le firmware Luciole²) tire alors
 * au pire 30 × 3 × 20 × 8 / 255 = 56 mA, plus environ 1 mA de repos par LED. */
#define BANC_RIBBON_MAX     30
#define BANC_RIBBON_LEVEL   8
#define BANC_RIBBON_MA_PER_COLOR 20
static inline int v0_ribbon_ma(int lit)
{
    return (lit * 3 * BANC_RIBBON_MA_PER_COLOR * BANC_RIBBON_LEVEL + 254) / 255;
}

/* ------------------------------------------------------------------ */
/* Chargeur TP4056 (note du schéma : « 0,4 A, 0,9 A si ISET est à 1 »).  */
#define V0_CHARGE_SLOW_MA   407     /* R8 seule : 1100 V / 2,7 kΩ (formule de la fiche du TP4056) */
#define V0_CHARGE_FAST_MA   907     /* R8 et R9 en parallèle, 1,21 kΩ */

/* Rail des LED (note du schéma : « 4,45 V, ou 5,04 V si VSEL est à 1 »). */
#define V0_RAIL_LOW_MV      4450
#define V0_RAIL_HIGH_MV     5040

/* ------------------------------------------------------------------ */
/* Accéléromètre LIS2DH12 (U7). SA0 est au 3,3 V : adresse 0011001b.     */
#define V0_ACC_ADDR         0x19
#define LIS2DH12_WHO_AM_I   0x0F
#define LIS2DH12_ID         0x33    /* fiche ST, table 24 : WHO_AM_I vaut 00110011b */
#define LIS2DH12_CTRL_REG1  0x20
#define LIS2DH12_CTRL_REG4  0x23
#define LIS2DH12_CTRL_REG6  0x25
#define LIS2DH12_STATUS     0x27
#define LIS2DH12_OUT_X_L    0x28
#define LIS2DH12_AUTO_INC   0x80    /* bit 7 de l'adresse de registre : lecture de plusieurs registres à la suite */

/* Mode normal, ±2 g : donnée de 10 bits calée à gauche sur 16, 4 mg par pas
 * (fiche ST, table 10). Rend des millièmes de g. */
static inline int lis2dh12_mg(uint8_t low, uint8_t high)
{
    int16_t raw = (int16_t)((uint16_t)high << 8 | low);
    return (raw / 64) * 4;
}

/* ------------------------------------------------------------------ */
/* LED SK6812MINI-B-012 (D1 à D15)                                      */
#define V0_LED_COUNT        15
#define V0_LED_MA_PER_COLOR 12      /* fiche OPSCO : 12 mA par couleur à fond (10 à 14,5) */
#define V0_LED_IDLE_UA      600     /* fiche : 0,6 mA par LED éteinte */

/* Plafond de luminosité du banc, sur 255. Aucune commande ne peut le dépasser.
 *
 * Justification par le courant. Toutes les LED en blanc à fond tireraient
 * 15 × 3 × 12 mA = 540 mA sur le rail. À 32/255, le courant moyen est de
 * 15 × 3 × 12 × 32 / 255 = 68 mA, plus 9 mA de repos : 77 mA au pire. Côté
 * batterie, à 3,3 V et 85 % de rendement, cela fait environ 120 mA. C'est
 * sans risque pour une carte dont on ne connaît encore ni le convertisseur
 * ni les soudures : pas d'échauffement, et une prise USB de 500 mA tient ce
 * courant en plus de la charge lente (407 mA) hors émission radio. La fiche
 * demande aussi de rester à 70 % au plus en blanc : 32/255 fait 12,5 %, et la
 * compilation s'arrête si le plafond dépasse un jour 70 %. */
#define BANC_LED_MAX        32
#define BANC_LED_DEFAULT    16      /* niveau « faible » au démarrage */
#define V0_LED_WHITE_MAX_PCT 70     /* fiche OPSCO : 70 % au plus quand les trois couleurs sont allumées */
_Static_assert(BANC_LED_DEFAULT <= BANC_LED_MAX && BANC_LED_MAX <= 64, "plafond des LED : rester prudent");
/* Le plafond vaut pour chaque couleur, donc aussi pour le blanc : 32/255 = 12,5 %. */
_Static_assert(BANC_LED_MAX * 100 <= 255 * V0_LED_WHITE_MAX_PCT, "plafond des LED au-dessus de 70 % en blanc");

/* Courant moyen du rail pour une image dont la somme des composantes (R + G + B
 * de toutes les LED, chacune sur 255) vaut sum : en milliampères. */
static inline int v0_led_rail_ma(int sum)
{
    return (V0_LED_COUNT * V0_LED_IDLE_UA + 500) / 1000 + (sum * V0_LED_MA_PER_COLOR + 127) / 255;
}
