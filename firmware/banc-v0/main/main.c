/*
 * Luciole² — banc d'essai de la carte v0 (schéma hardware/v0/circuit.py, révision 0.6).
 *
 * But : le jour où les cartes arrivent, essayer chaque fonction une par une
 * depuis un terminal, et qu'une panne soit dans la carte et non dans le code.
 *
 * Règles de ce programme :
 *  - au démarrage tout est dans l'état le plus sûr (safe_state) et rien ne
 *    change tant que l'utilisateur ne l'a pas demandé ;
 *  - aucune écriture en mémoire non volatile (pas de NVS, pas d'étalonnage
 *    radio enregistré, table de partitions sans NVS), aucun mode veille ;
 *  - rien n'arrête le programme : une erreur s'affiche et la console reste ;
 *  - chaque mesure s'affiche avec son unité et la plage attendue.
 *
 * Console : l'USB série/JTAG de la puce, et en secours l'UART0 sur les
 * pastilles TP8 (TXD0) et TP9 (RXD0), 115200 bauds. Les deux reçoivent les
 * mêmes textes et acceptent les mêmes commandes.
 *
 * Tout ce que le code sait de la carte (broches, ponts, plafond des LED) est
 * dans carte_v0.h. Les textes de la console sont sans accents : ils passent
 * ainsi sur n'importe quel terminal.
 */
#include <stdio.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_mac.h"
#include "esp_cpu.h"
#include "esp_rom_sys.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "driver/temperature_sensor.h"
#include "soc/soc.h"
#include "soc/gpio_reg.h"
#include "soc/uart_pins.h"
#include "led_strip.h"
#include "carte_v0.h"
#include "soft_i2c.h"

#define BANC_VERSION    "1.1"

/* ------------------------------------------------------------------ */
/* État des commandes. C'est la seule mémoire du banc ; elle repart de  */
/* l'état sûr à chaque démarrage.                                       */
typedef enum { CHARGE_SLOW, CHARGE_FAST, CHARGE_STOPPED } charge_t;
typedef enum { PORT_I2C, PORT_RIBBON } port_mode_t;
typedef enum { PAT_BLACK, PAT_ONE, PAT_ALL, PAT_CHASE, PAT_COLORS } pattern_t;

static bool        s_conv = false;          /* convertisseur des LED en marche */
static bool        s_rail_high = false;     /* consigne 5,04 V au lieu de 4,45 V */
static charge_t    s_charge = CHARGE_SLOW;
static port_mode_t s_port = PORT_I2C;       /* mode du port, posé quand le convertisseur marche */
static int         s_line2 = 0;             /* mode ruban : niveau poussé sur la ligne 2 */

static led_strip_handle_t s_strip;
static pattern_t   s_pat = PAT_BLACK;
static int         s_pat_led = 0;           /* LED allumée par « led N », de 0 à 14 */
static uint8_t     s_pat_rgb[3] = {1, 1, 1};/* couleurs allumées par « leds », « rouge »… */
static int         s_level = BANC_LED_DEFAULT;
static int         s_anim_step = 0;
static int64_t     s_anim_next = 0;
static int         s_rail_ma = 0;           /* courant estimé du rail pour l'image affichée */

static bool s_usb_ok = false, s_uart_ok = false;

/* ------------------------------------------------------------------ */
/* Sortie : tout texte part sur l'USB et sur l'UART de secours.         */
static SemaphoreHandle_t s_out_mux;
static bool s_usb_stalled = false;

static void out_raw(const char *s, size_t n)
{
    if (n == 0) return;
    if (s_usb_ok) {
        /* Si aucun terminal ne lit l'USB, le tampon du pilote se remplit. On
         * attend une fois 50 ms, puis on n'attend plus tant qu'il reste plein :
         * la console de secours ne doit pas ralentir parce que l'USB est muet. */
        int sent = usb_serial_jtag_write_bytes(s, n, s_usb_stalled ? 0 : pdMS_TO_TICKS(50));
        s_usb_stalled = (sent == 0);
    }
    if (s_uart_ok) uart_write_bytes(UART_NUM_0, s, n);
}

static void vsay(const char *fmt, va_list ap)
{
    static char raw[768], cooked[1536];     /* protégés par s_out_mux */
    if (!s_out_mux) return;
    xSemaphoreTake(s_out_mux, portMAX_DELAY);
    int n = vsnprintf(raw, sizeof(raw), fmt, ap);
    if (n > (int)sizeof(raw) - 1) {             /* texte plus long que le tampon : la coupure se voit */
        n = sizeof(raw) - 1;
        memcpy(raw + n - 6, "[...]\n", 6);
    }
    size_t k = 0;
    for (int i = 0; i < n; i++) {           /* un terminal série veut retour chariot et saut de ligne */
        if (raw[i] == '\n') cooked[k++] = '\r';
        cooked[k++] = raw[i];
    }
    out_raw(cooked, k);
    xSemaphoreGive(s_out_mux);
}

static void say(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void say(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vsay(fmt, ap);
    va_end(ap);
}

/* Les messages d'ESP-IDF (avertissements, erreurs) suivent le même chemin. */
static int log_vprintf(const char *fmt, va_list ap)
{
    /* Un message émis par un pilote pendant que cette tâche écrit déjà : on le
     * laisse tomber plutôt que d'attendre un verrou qu'on tient soi-même. */
    if (s_out_mux && xSemaphoreGetMutexHolder(s_out_mux) == xTaskGetCurrentTaskHandle()) return 0;
    vsay(fmt, ap);
    return 0;
}

static void console_init(void)
{
    s_out_mux = xSemaphoreCreateMutex();

    /* USB série/JTAG : pilote avec tampons, comme le firmware Luciole². */
    usb_serial_jtag_driver_config_t usj = { .tx_buffer_size = 4096, .rx_buffer_size = 512 };
    s_usb_ok = usb_serial_jtag_driver_install(&usj) == ESP_OK;
    if (s_usb_ok) usb_serial_jtag_vfs_use_driver();

    /* UART0 de secours sur les pastilles TP8 (TXD0, sortie de la carte) et TP9
     * (RXD0, entrée). Les numéros de GPIO sont ceux qu'ESP-IDF donne à l'UART0
     * de la puce. Rappel interne sur l'entrée : sans adaptateur branché, la
     * pastille ne doit pas flotter et inventer des caractères. */
    uart_config_t uc = {
        .baud_rate = 115200, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT,
    };
    s_uart_ok = uart_driver_install(UART_NUM_0, 256, 4096, 0, NULL, 0) == ESP_OK
             && uart_param_config(UART_NUM_0, &uc) == ESP_OK
             && uart_set_pin(UART_NUM_0, U0TXD_GPIO_NUM, U0RXD_GPIO_NUM, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE) == ESP_OK;
    if (s_uart_ok) gpio_pullup_en(U0RXD_GPIO_NUM);

    esp_log_set_vprintf(log_vprintf);
}

/* ------------------------------------------------------------------ */
/* Broches. Aucun rappel interne nulle part : seuls les rappels de la   */
/* carte jouent, et une résistance absente se voit.                     */
static void pin_input(int gpio)
{
    gpio_config_t c = { .pin_bit_mask = 1ULL << gpio, .mode = GPIO_MODE_INPUT };
    gpio_config(&c);
}

/* Sortie poussée, relisible. Le niveau est écrit avant que la broche devienne
 * une sortie : elle ne passe jamais par l'autre niveau. */
static void pin_output(int gpio, int level)
{
    gpio_set_level(gpio, level);
    gpio_config_t c = { .pin_bit_mask = 1ULL << gpio, .mode = GPIO_MODE_INPUT_OUTPUT };
    gpio_config(&c);
}

/* Sortie à drain ouvert, relâchée. */
static void pin_open_drain(int gpio, gpio_mode_t mode)
{
    gpio_set_level(gpio, 1);
    gpio_config_t c = { .pin_bit_mask = 1ULL << gpio, .mode = mode };
    gpio_config(&c);
}

/* Pose le port Grove dans l'un de ses trois états (règles du port, carte_v0.h) :
 *   repos   convertisseur arrêté : PORT_PU, IO1 et IO2 poussées à 0 ;
 *   I2C     PORT_PU à 1 (rappels actifs, tampon inactif), IO1 et IO2 relâchées ;
 *   ruban   PORT_PU à 0 (tampon actif), IO1 à 0, IO2 poussée à s_line2.
 * PORT_PU n'est jamais laissée en l'air. L'ordre compte : vers 0, les lignes
 * d'abord, pour que le tampon s'active sur une ligne déjà posée ; vers l'I2C,
 * PORT_PU d'abord, pour que le tampon soit coupé avant que les lignes montent. */
static void port_apply(void)
{
    if (!s_conv || s_port == PORT_RIBBON) {
        pin_output(V0_PORT_SDA_GPIO, s_conv ? s_line2 : 0);
        pin_output(V0_PORT_SCL_GPIO, 0);
        pin_output(V0_PORT_PU_GPIO, 0);
    } else {
        pin_output(V0_PORT_PU_GPIO, 1);
        pin_input(V0_PORT_SCL_GPIO);
        pin_input(V0_PORT_SDA_GPIO);
    }
}

/* État le plus sûr, d'après circuit.py :
 *  - BOOST_EN à 0 : convertisseur des LED arrêté, rail coupé ;
 *  - VSEL à 0 : consigne basse, 4,45 V ;
 *  - ISET à 0 : charge au courant le plus bas, 0,4 A ;
 *  - CHG_INH relâchée : la charge reste permise, comme sans firmware ;
 *  - PORT_PU, IO1 et IO2 à 0 : port au repos. Rail coupé, c'est l'état où ni
 *    les rappels ni le tampon n'agissent et où rien ne remonte vers le rail ;
 *  - LED_DATA à 0 (posée par led_init), aucune trame envoyée. */
static void safe_state(void)
{
    pin_output(V0_BOOST_EN_GPIO, 0);
    pin_output(V0_VSEL_GPIO, 0);
    pin_output(V0_ISET_GPIO, 0);
    /* CHG_INH : drain ouvert, jamais poussée à 1. Entrée coupée : relâchée,
     * la broche flotte vers 3,3 V moins le seuil de Q7, un niveau qui n'est
     * ni 0 ni 1 pour une entrée logique. */
    pin_open_drain(V0_CHG_INH_GPIO, GPIO_MODE_OUTPUT_OD);

    port_apply();

    pin_input(V0_BUTTON_GPIO);
    pin_input(V0_ACC_INT_GPIO);
    pin_input(V0_VBUS_DET_GPIO);
    pin_input(V0_STRAP8_GPIO);
    pin_input(V0_BOOT_GPIO);
    pin_input(V0_CHRG_GPIO);

    /* Bus de l'accéléromètre : drain ouvert, relâché. */
    pin_open_drain(V0_ACC_SDA_GPIO, GPIO_MODE_INPUT_OUTPUT_OD);
    pin_open_drain(V0_ACC_SCL_GPIO, GPIO_MODE_INPUT_OUTPUT_OD);
}

/* ------------------------------------------------------------------ */
/* Mesures analogiques                                                  */
static adc_oneshot_unit_handle_t s_adc;
static adc_channel_t s_ch_vbat, s_ch_cc;
static adc_cali_handle_t s_cal_vbat_fine, s_cal_vbat_wide, s_cal_cc_fine, s_cal_cc_wide;
static bool s_adc_ok = false, s_adc_calibrated = false;
static temperature_sensor_handle_t s_temp;

static adc_cali_handle_t cali_new(adc_channel_t ch, adc_atten_t atten)
{
    adc_cali_handle_t h = NULL;
    adc_cali_curve_fitting_config_t c = { .unit_id = ADC_UNIT_1, .chan = ch, .atten = atten, .bitwidth = ADC_BITWIDTH_DEFAULT };
    return adc_cali_create_scheme_curve_fitting(&c, &h) == ESP_OK ? h : NULL;
}

static void adc_init(void)
{
    adc_unit_t unit;
    adc_oneshot_unit_init_cfg_t uc = { .unit_id = ADC_UNIT_1 };
    /* Le canal vient du numéro de GPIO : rien n'est supposé sur la numérotation de l'ADC. */
    if (adc_oneshot_io_to_channel(V0_VBAT_SENSE_GPIO, &unit, &s_ch_vbat) != ESP_OK || unit != ADC_UNIT_1) return;
    if (adc_oneshot_io_to_channel(V0_CC_SENSE_GPIO, &unit, &s_ch_cc) != ESP_OK || unit != ADC_UNIT_1) return;
    if (adc_oneshot_new_unit(&uc, &s_adc) != ESP_OK) return;
    /* Les deux broches passent en entrée analogique dès maintenant : une tension
     * intermédiaire n'a rien à faire sur une entrée logique. */
    adc_oneshot_chan_cfg_t cc = { .atten = ADC_ATTEN_DB_2_5, .bitwidth = ADC_BITWIDTH_DEFAULT };
    if (adc_oneshot_config_channel(s_adc, s_ch_vbat, &cc) != ESP_OK || adc_oneshot_config_channel(s_adc, s_ch_cc, &cc) != ESP_OK) return;
    s_cal_vbat_fine = cali_new(s_ch_vbat, ADC_ATTEN_DB_2_5);
    s_cal_vbat_wide = cali_new(s_ch_vbat, ADC_ATTEN_DB_12);
    s_cal_cc_fine = cali_new(s_ch_cc, ADC_ATTEN_DB_2_5);
    s_cal_cc_wide = cali_new(s_ch_cc, ADC_ATTEN_DB_12);
    s_adc_calibrated = s_cal_vbat_fine && s_cal_vbat_wide && s_cal_cc_fine && s_cal_cc_wide;
    s_adc_ok = true;
}

/* Tension d'une broche en millivolts, moyenne de 32 lectures ; -1 si l'ADC ne
 * répond pas. Sans étalonnage d'usine, la valeur n'est qu'approchée. */
static int adc_read_mv(adc_channel_t ch, adc_atten_t atten, adc_cali_handle_t cal)
{
    if (!s_adc_ok) return -1;
    adc_oneshot_chan_cfg_t cc = { .atten = atten, .bitwidth = ADC_BITWIDTH_DEFAULT };
    if (adc_oneshot_config_channel(s_adc, ch, &cc) != ESP_OK) return -1;
    int raw, sum = 0, n = 0;
    for (int i = 0; i < 36; i++) {
        if (adc_oneshot_read(s_adc, ch, &raw) != ESP_OK) continue;
        if (i >= 4) { sum += raw; n++; }    /* les premières lectures suivent le changement de canal */
    }
    if (n == 0) return -1;
    int mv;
    if (cal && adc_cali_raw_to_voltage(cal, sum / n, &mv) == ESP_OK) return mv;
    return (sum / n) * (atten == ADC_ATTEN_DB_12 ? 3300 : 1300) / 4095;
}

/* Les deux tensions à mesurer tiennent sous 1,3 V : 4,2 V de batterie donnent
 * 1,25 V sur la broche, et la ligne CC ne dépasse pas 1,02 V. Elles se lisent
 * avec l'atténuation de 2,5 dB, plage de 0 à 1,3 V à ±12 mV (fiche de la
 * puce). Une lecture au bout de cette plage est refaite sur la grande (12 dB,
 * jusqu'à 3,3 V, ±40 mV) : elle dit jusqu'où monte une broche en défaut. */
static int adc_read_pin(adc_channel_t ch, adc_cali_handle_t fine, adc_cali_handle_t wide)
{
    int mv = adc_read_mv(ch, ADC_ATTEN_DB_2_5, fine);
    if (mv >= V0_ADC_FINE_MAX_MV) {
        int w = adc_read_mv(ch, ADC_ATTEN_DB_12, wide);
        if (w > mv) mv = w;
    }
    return mv;
}

static int vbat_pin_mv(void) { return adc_read_pin(s_ch_vbat, s_cal_vbat_fine, s_cal_vbat_wide); }
static int cc_sense_mv(void) { return adc_read_pin(s_ch_cc, s_cal_cc_fine, s_cal_cc_wide); }

static void temp_init(void)
{
    temperature_sensor_config_t c = TEMPERATURE_SENSOR_CONFIG_DEFAULT(-10, 80);
    if (temperature_sensor_install(&c, &s_temp) != ESP_OK || temperature_sensor_enable(s_temp) != ESP_OK) s_temp = NULL;
}

/* ------------------------------------------------------------------ */
/* Tableau « essai, mesure, attendu, bon ou non »                       */
#define W_TEST      22
#define W_VALUE     30
#define W_EXPECTED  42
#define TABLE_WIDTH (W_TEST + W_VALUE + W_EXPECTED + 9 + 7)
#define ROW_FORMAT  "%-22s | %-30s | %-42s | %s\n"
enum { V_NON = 0, V_BON = 1, V_VOIR = -1 };     /* « à voir » : le banc ne peut pas juger seul */
static struct { int bon, non, voir; } s_tally;

static void table_begin(void)
{
    memset(&s_tally, 0, sizeof(s_tally));
    char rule[TABLE_WIDTH + 1];
    memset(rule, '-', TABLE_WIDTH);
    rule[TABLE_WIDTH] = 0;
    rule[W_TEST + 1] = rule[W_TEST + W_VALUE + 4] = rule[W_TEST + W_VALUE + W_EXPECTED + 7] = '+';
    say(ROW_FORMAT, "essai", "mesure", "attendu", "bon ?");
    say("%s\n", rule);
}

static void row(const char *test, int verdict, const char *expected, const char *fmt, ...) __attribute__((format(printf, 4, 5)));
static void row(const char *test, int verdict, const char *expected, const char *fmt, ...)
{
    char value[48];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(value, sizeof(value), fmt, ap);
    va_end(ap);
    if (verdict == V_BON) s_tally.bon++; else if (verdict == V_NON) s_tally.non++; else s_tally.voir++;
    say(ROW_FORMAT, test, value, expected,
        verdict == V_BON ? "BON" : verdict == V_NON ? "NON <<<" : "a voir");
}

/* ------------------------------------------------------------------ */
/* Mesures sans effet sur la carte                                      */
typedef struct {
    int  vbat_pin_mv, vbat_mv, cc_mv;
    bool usb, host, chrg, button, acc_int;
    int  strap_reset;       /* registre figé au reset */
    int  g8, g9, g15;       /* niveaux lus maintenant */
    bool temp_ok;
    float temp_c;
} measures_t;

/* Registre des broches de démarrage, figé par la puce au reset (manuel de
 * référence de l'ESP32-C6, registre GPIO_STRAP) : bit 2 GPIO8, bit 3 GPIO9,
 * bit 4 GPIO15, bit 5 MTMS (GPIO4), bit 6 MTDI (GPIO5). */
#define STRAP_GPIO8   (1 << 2)
#define STRAP_GPIO9   (1 << 3)
#define STRAP_GPIO15  (1 << 4)
#define STRAP_MTMS    (1 << 5)
#define STRAP_MTDI    (1 << 6)

static void measure(measures_t *m)
{
    memset(m, 0, sizeof(*m));
    m->vbat_pin_mv = vbat_pin_mv();
    m->vbat_mv = m->vbat_pin_mv < 0 ? -1 : v0_vbat_mv(m->vbat_pin_mv);
    m->cc_mv = cc_sense_mv();
    m->usb = gpio_get_level(V0_VBUS_DET_GPIO);
    m->host = s_usb_ok && usb_serial_jtag_is_connected();
    m->chrg = gpio_get_level(V0_CHRG_GPIO);
    m->button = gpio_get_level(V0_BUTTON_GPIO);
    m->acc_int = gpio_get_level(V0_ACC_INT_GPIO);
    m->strap_reset = (int)(REG_READ(GPIO_STRAP_REG) & 0xffff);
    m->g8 = gpio_get_level(V0_STRAP8_GPIO);
    m->g9 = gpio_get_level(V0_BOOT_GPIO);
    m->g15 = gpio_get_level(V0_PORT_PU_GPIO);
    m->temp_ok = s_temp && temperature_sensor_get_celsius(s_temp, &m->temp_c) == ESP_OK;
}

static const char *cc_text(v0_cc_t c)
{
    switch (c) {
        case V0_CC_NONE:  return "aucune annonce";
        case V0_CC_500:   return "0.5 A (USB par defaut)";
        case V0_CC_1500:  return "1.5 A";
        case V0_CC_3000:  return "3.0 A";
        default:          return "hors norme";
    }
}

static void rows_measures(const measures_t *m)
{
    /* Batterie. La plage attendue de la broche est calculée d'après le pont. */
    char vbat_expected[48];
    snprintf(vbat_expected, sizeof(vbat_expected), "%d.%02d a %d.%02d V (broche %d a %d mV)",
             V0_VBAT_MIN_MV / 1000, V0_VBAT_MIN_MV % 1000 / 10, V0_VBAT_MAX_MV / 1000, V0_VBAT_MAX_MV % 1000 / 10,
             v0_vbat_pin_mv(V0_VBAT_MIN_MV), v0_vbat_pin_mv(V0_VBAT_MAX_MV));
    if (m->vbat_mv < 0) {
        row("batterie (VBAT)", V_NON, vbat_expected, "ADC muet");
    } else if (m->vbat_pin_mv > V0_ADC_FINE_MAX_MV) {
        row("batterie (VBAT)", V_NON, vbat_expected, "hors plage : broche %d mV", m->vbat_pin_mv);
    } else {
        row("batterie (VBAT)", m->vbat_mv >= V0_VBAT_MIN_MV && m->vbat_mv <= V0_VBAT_MAX_MV ? V_BON : V_NON,
            vbat_expected, "%d.%02d V (broche %d mV)", m->vbat_mv / 1000, m->vbat_mv % 1000 / 10, m->vbat_pin_mv);
    }

    /* USB : si un ordinateur dialogue par l'USB, VBUS est forcément là. */
    if (m->host) row("USB present (VBUS)", m->usb ? V_BON : V_NON, "oui : un ordinateur repond en USB", "%s", m->usb ? "oui" : "non");
    else         row("USB present (VBUS)", V_VOIR, "oui si un cable USB alimente", "%s", m->usb ? "oui" : "non");

    /* Ligne CC et courant annoncé */
    v0_cc_t cc = v0_cc_class(m->cc_mv < 0 ? 0 : m->cc_mv);
    if (m->cc_mv < 0) {
        row("ligne CC", V_NON, "voir le README", "ADC muet");
    } else if (m->usb) {
        row("ligne CC", cc == V0_CC_500 || cc == V0_CC_1500 || cc == V0_CC_3000 ? V_BON : V_NON,
            "100 a 1100 mV sous USB", "%d mV (broche CC : %d.%02d V)", m->cc_mv, m->cc_mv * 2 / 1000, m->cc_mv * 2 % 1000 / 10);
        row("courant annonce", cc == V0_CC_500 || cc == V0_CC_1500 || cc == V0_CC_3000 ? V_BON : V_NON,
            "0.5 A <330 mV, 1.5 A <615 mV, 3 A au-dela", "%s", cc_text(cc));
    } else {
        row("ligne CC", cc == V0_CC_NONE ? V_BON : V_NON, "moins de 100 mV sans USB", "%d mV", m->cc_mv);
        row("courant annonce", cc == V0_CC_NONE ? V_BON : V_NON, "aucune annonce sans USB", "%s", cc_text(cc));
    }

    /* Chargeur : seule la sortie CHRG est reliée à la puce. */
    const char *chrg = m->chrg ? "1 (pas en charge)" : "0 (en charge)";
    if (!m->usb)                         row("chargeur CHRG", m->chrg ? V_BON : V_NON, "1 sans USB", "%s", chrg);
    else if (s_charge == CHARGE_STOPPED) row("chargeur CHRG", m->chrg ? V_BON : V_NON, "1 : charge arretee par commande", "%s", chrg);
    else                                 row("chargeur CHRG", V_VOIR, "0 = en charge ; instable sans batterie", "%s", chrg);

    row("bouton", m->button ? V_BON : V_VOIR, "1 relache, 0 appuye", "%s", m->button ? "1 (relache)" : "0 (appuye)");

    /* Broches de démarrage. IO15 (PORT_PU) n'est pas jugée au reset : rail
     * coupé, la sortie de U10 la tire vers 0,5 V malgré R35 (commentaire du
     * schéma), et la puce ne s'en sert pas avec ses eFuses d'usine. IO4 porte
     * la tension de la ligne CC. */
    int s = m->strap_reset;
    row("demarrage, au reset", (s & STRAP_GPIO8) && (s & STRAP_GPIO9) && !(s & STRAP_MTDI) ? V_BON : V_NON,
        "IO8=1 IO9=1 IO5=0 ; IO15, IO4 indifferents", "IO8=%d IO9=%d IO15=%d IO5=%d IO4=%d",
        !!(s & STRAP_GPIO8), !!(s & STRAP_GPIO9), !!(s & STRAP_GPIO15), !!(s & STRAP_MTDI), !!(s & STRAP_MTMS));
    int g15_expected = s_conv && s_port == PORT_I2C ? 1 : 0;
    row("demarrage, maintenant", m->g8 && m->g9 && m->g15 == g15_expected ? V_BON : V_NON,
        g15_expected ? "1 1 1 (BOOT relache, port en I2C)" : "1 1 0 (BOOT relache, PORT_PU a 0)", "IO8=%d IO9=%d IO15=%d", m->g8, m->g9, m->g15);

    row("interruption accelero", m->acc_int ? V_NON : V_BON, "0 au repos", "%d", m->acc_int);

    if (m->temp_ok) row("temperature de la puce", m->temp_c >= 10 && m->temp_c <= 70 ? V_BON : V_NON, "10 a 70 C", "%.1f C", (double)m->temp_c);
    else            row("temperature de la puce", V_NON, "10 a 70 C", "capteur muet");
}

/* Sous USB, 4,1 V ou plus et pas de charge : trois causes, que la puce ne
 * peut pas distinguer. La troisième est une règle de la carte (révision 0.6) :
 * une cellule branchée alors que l'USB est déjà là peut rester déconnectée. */
static void hints(const measures_t *m)
{
    if (m->usb && m->chrg && s_charge != CHARGE_STOPPED && m->vbat_mv >= 4100 && m->vbat_pin_mv <= V0_ADC_FINE_MAX_MV)
        say("remarque : %d.%02d V sous USB et pas de charge. La cellule est pleine, ou absente, ou restee deconnectee parce\n"
            "  qu'elle a ete branchee apres l'USB. Dans le doute : debranchez l'USB, puis rebranchez-le.\n",
            m->vbat_mv / 1000, m->vbat_mv % 1000 / 10);
}

/* ------------------------------------------------------------------ */
/* LED                                                                  */

/* Temps du SK6812MINI-B-012 (fiche OPSCO rév. B1) : T0H 0,25 à 0,40 µs, T1H
 * 0,65 à 1,00 µs, T0L au moins 0,80 µs, T1L au moins 0,20 µs, remise à zéro
 * plus de 200 µs. Ordre des couleurs : vert, rouge, bleu. Les temps sont
 * écrits ici plutôt que pris du modèle « SK6812 » du pilote, dont les valeurs
 * ont changé d'une version à l'autre. */
#define LED_TIMINGS { .t0h_ns = 300, .t0l_ns = 900, .t1h_ns = 700, .t1l_ns = 600, .reset_us = 280 }

static void led_init(void)
{
    led_strip_config_t cfg = {
        .strip_gpio_num = V0_LED_DATA_GPIO,
        .max_leds = V0_LED_COUNT,
        .led_model = LED_MODEL_CUSTOM,
        .color_component_format = LED_STRIP_COLOR_COMPONENT_FMT_GRB,
        .timings = LED_TIMINGS,
    };
    led_strip_rmt_config_t rmt = { .clk_src = RMT_CLK_SRC_DEFAULT, .resolution_hz = 10 * 1000 * 1000 };
    if (led_strip_new_rmt_device(&cfg, &rmt, &s_strip) != ESP_OK) s_strip = NULL;
    /* Aucune trame n'est envoyée ici : la ligne de donnée reste à 0. */
}

/* Seul endroit d'où une couleur part vers les LED : le plafond s'y applique,
 * quoi que demande le reste du code. */
static void leds_show(uint8_t px[V0_LED_COUNT][3])
{
    int sum = 0;
    if (!s_strip) { say("LED : pilote absent, rien n'est envoye\n"); return; }
    for (int i = 0; i < V0_LED_COUNT; i++) {
        for (int k = 0; k < 3; k++) {
            if (px[i][k] > BANC_LED_MAX) px[i][k] = BANC_LED_MAX;
            sum += px[i][k];
        }
        led_strip_set_pixel(s_strip, i, px[i][0], px[i][1], px[i][2]);
    }
    esp_err_t err = led_strip_refresh(s_strip);
    if (err != ESP_OK) say("LED : envoi impossible (%s)\n", esp_err_to_name(err));
    s_rail_ma = v0_led_rail_ma(sum);
}

static void pattern_render(void)
{
    static const uint8_t COLORS[3][3] = { {1, 0, 0}, {0, 1, 0}, {0, 0, 1} };
    uint8_t px[V0_LED_COUNT][3];
    memset(px, 0, sizeof(px));
    for (int i = 0; i < V0_LED_COUNT; i++) {
        const uint8_t *rgb = NULL;
        switch (s_pat) {
            case PAT_BLACK:  break;
            case PAT_ONE:    if (i == s_pat_led) rgb = s_pat_rgb; break;
            case PAT_ALL:    rgb = s_pat_rgb; break;
            case PAT_CHASE:  if (i == s_anim_step % V0_LED_COUNT) rgb = s_pat_rgb; break;
            case PAT_COLORS: rgb = COLORS[s_anim_step % 3]; break;
        }
        if (rgb) for (int k = 0; k < 3; k++) px[i][k] = (uint8_t)(rgb[k] * s_level);
    }
    leds_show(px);
}

static void pattern_set(pattern_t pat, int r, int g, int b)
{
    s_pat = pat;
    s_pat_rgb[0] = (uint8_t)r; s_pat_rgb[1] = (uint8_t)g; s_pat_rgb[2] = (uint8_t)b;
    s_anim_step = 0;
    s_anim_next = esp_timer_get_time();
    pattern_render();
}

/* Motifs animés : chenillard, un pas toutes les 150 ms ; couleurs, une par seconde. */
static void pattern_tick(int64_t now)
{
    if (s_pat != PAT_CHASE && s_pat != PAT_COLORS) return;
    int64_t period = s_pat == PAT_CHASE ? 150000 : 1000000;
    if (now - s_anim_next < period) return;
    s_anim_next = now;
    s_anim_step++;
    pattern_render();
}

static void led_report(const char *what)
{
    say("LED : %s, niveau %d/255 (plafond %d/255). Courant estime du rail des LED : %d mA.\n", what, s_level, BANC_LED_MAX, s_rail_ma);
    if (!s_conv) say("  attention : convertisseur arrete, rien ne s'allume. Tapez 'conv 1' (ou alimentez le rail par TP15).\n");
}

/* ------------------------------------------------------------------ */
/* Convertisseur et charge                                              */
static int parse_on_off(const char *arg)
{
    if (!strcmp(arg, "1") || !strcmp(arg, "on") || !strcmp(arg, "marche") || !strcmp(arg, "oui")) return 1;
    if (!strcmp(arg, "0") || !strcmp(arg, "off") || !strcmp(arg, "arret") || !strcmp(arg, "non")) return 0;
    return -1;
}

/* Ce qu'on doit lire au voltmètre sur TP5 quand le convertisseur marche. Sous
 * USB, son entrée (VSYS, environ VBUS moins 0,4 V) dépasse la consigne basse :
 * le TPS61023 laisse alors passer l'entrée sans la réguler. */
static const char *rail_expected(void)
{
    if (s_rail_high) return "4.85 a 5.25 V";
    return gpio_get_level(V0_VBUS_DET_GPIO) ? "4.30 a 4.95 V (sous USB, le convertisseur laisse passer son entree)" : "4.30 a 4.60 V";
}

static const char *port_text(void)
{
    if (!s_conv) return s_port == PORT_I2C ? "au repos, tout a 0 (convertisseur arrete) ; mode choisi : I2C"
                                           : "au repos, tout a 0 (convertisseur arrete) ; mode choisi : ruban";
    return s_port == PORT_I2C ? "I2C : RAPPELS actifs, tampon inactif (PORT_PU a 1)"
                              : "ruban : TAMPON actif, rappels tires vers 0 (PORT_PU a 0)";
}

static void cmd_conv(const char *arg)
{
    int on = parse_on_off(arg);
    if (on < 0) { say("usage : conv 1 (marche) ou conv 0 (arret)\n"); return; }
    if (on && s_conv) { say("convertisseur deja en marche, consigne %s V.\n", s_rail_high ? "5.04" : "4.45"); return; }
    if (on) {
        /* Règle 2 du port : PORT_PU est commandée avant BOOST_EN, au niveau du
         * mode choisi. Les deux lignes restent à 0 jusqu'à ce que le rail soit là. */
        pin_output(V0_PORT_PU_GPIO, s_port == PORT_I2C ? 1 : 0);
        gpio_set_level(V0_BOOST_EN_GPIO, 1);
        s_conv = true;
        vTaskDelay(pdMS_TO_TICKS(20));          /* la fiche donne 0,7 ms de démarrage */
        port_apply();
        s_pat = PAT_BLACK;
        pattern_render();                       /* les LED s'allument éteintes ; une trame noire le garantit */
        say("convertisseur EN MARCHE, consigne %s V. A lire sur TP5 : %s. Les LED restent eteintes.\n",
            s_rail_high ? "5.04" : "4.45", rail_expected());
        say("port Grove : %s\n", port_text());
    } else {
        s_pat = PAT_BLACK;
        if (s_conv) pattern_render();
        /* Règle 1 du port : PORT_PU, IO1 et IO2 passent à 0 avant que le rail soit coupé. */
        s_conv = false;
        s_line2 = 0;
        port_apply();
        gpio_set_level(V0_BOOST_EN_GPIO, 0);
        say("convertisseur ARRETE. TP5 retombe vers 0 V ; le port Grove n'est plus alimente et revient au repos, tout a 0.\n");
    }
}

static void cmd_rail(const char *arg)
{
    if (!strcmp(arg, "4.5") || !strcmp(arg, "4,5") || !strcmp(arg, "4.45") || !strcmp(arg, "bas")) s_rail_high = false;
    else if (!strcmp(arg, "5") || !strcmp(arg, "5.0") || !strcmp(arg, "5,0") || !strcmp(arg, "5.04") || !strcmp(arg, "haut")) s_rail_high = true;
    else { say("usage : rail 4.5 ou rail 5.0\n"); return; }
    gpio_set_level(V0_VSEL_GPIO, s_rail_high);
    say("consigne du rail des LED : %s V. ", s_rail_high ? "5.04" : "4.45");
    if (s_conv) say("A lire sur TP5 : %s.\n", rail_expected());
    else say("Convertisseur arrete : sans effet tant que 'conv 1' n'est pas donne.\n");
}

static void cmd_charge(const char *arg)
{
    if (!strcmp(arg, "lente")) {
        gpio_set_level(V0_ISET_GPIO, 0);
        gpio_set_level(V0_CHG_INH_GPIO, 1);     /* relâchée */
        s_charge = CHARGE_SLOW;
        say("charge LENTE : %d mA. Sous USB avec une batterie a charger, CHRG passe a 0.\n", V0_CHARGE_SLOW_MA);
    } else if (!strcmp(arg, "rapide") || !strcmp(arg, "rapide force")) {
        /* 0,9 A ne se demande qu'à une source qui annonce au moins 1,5 A. */
        int cc = cc_sense_mv();
        v0_cc_t c = v0_cc_class(cc < 0 ? 0 : cc);
        if (c != V0_CC_1500 && c != V0_CC_3000 && strcmp(arg, "rapide force")) {
            say("charge rapide REFUSEE : la source annonce '%s' (ligne CC a %d mV), il faut 1.5 A ou plus.\n", cc_text(c), cc);
            say("  pour passer outre en connaissance de cause : charge rapide force\n");
            return;
        }
        gpio_set_level(V0_CHG_INH_GPIO, 1);
        gpio_set_level(V0_ISET_GPIO, 1);
        s_charge = CHARGE_FAST;
        say("charge RAPIDE : %d mA. A ne laisser que si la cellule accepte ce courant.\n", V0_CHARGE_FAST_MA);
    } else if (!strcmp(arg, "arret") || !strcmp(arg, "stop") || !strcmp(arg, "0")) {
        gpio_set_level(V0_CHG_INH_GPIO, 0);     /* tirée à 0 : CE du chargeur à 0,2 V */
        gpio_set_level(V0_ISET_GPIO, 0);
        s_charge = CHARGE_STOPPED;
        say("charge ARRETEE. CHRG doit lire 1. 'charge lente' la reprend.\n");
    } else {
        say("usage : charge lente | charge rapide | charge arret\n");
    }
}

/* ------------------------------------------------------------------ */
/* Lignes à rappel : I2C interne et port Grove                          */
static const soft_i2c_t BUS_ACC  = { .sda = V0_ACC_SDA_GPIO,  .scl = V0_ACC_SCL_GPIO };
static const soft_i2c_t BUS_PORT = { .sda = V0_PORT_SDA_GPIO, .scl = V0_PORT_SCL_GPIO };

/* Un rappel franc (4,7 ou 10 kΩ) remonte la ligne en moins d'une microseconde ;
 * un rappel de 1 MΩ, ou pas de rappel, en plus de dix. La limite est à 3 µs. */
#define RISE_PULLUP_MAX     30      /* dixièmes de microseconde */

/* Tire une ligne à drain ouvert à 0, la relâche, et mesure le temps qu'elle
 * met à être relue à 1, en dixièmes de microseconde ; -1 si elle n'est pas
 * remontée en 5 ms. Plus petite de cinq mesures : une interruption pendant
 * l'une d'elles l'allonge sans rien dire de la ligne. */
static int rise_time(int gpio)
{
    const uint32_t per_us = esp_rom_get_cpu_ticks_per_us();
    const uint32_t limit = 5000 * per_us;
    uint32_t best = UINT32_MAX;
    for (int i = 0; i < 5; i++) {
        gpio_set_level(gpio, 0);
        esp_rom_delay_us(50);
        uint32_t t0 = esp_cpu_get_cycle_count(), dt, turns = 0;
        gpio_set_level(gpio, 1);
        /* turns : borne de secours, si le compteur de cycles n'avançait pas. */
        do { dt = esp_cpu_get_cycle_count() - t0; } while (!gpio_get_level(gpio) && dt < limit && ++turns < 2000000);
        if (turns >= 2000000) dt = limit;
        if (dt < best) best = dt;
        esp_rom_delay_us(200);
    }
    return best >= limit ? -1 : (int)(best * 10 / per_us);
}

static const char *rise_text(char *buf, size_t size, int tenths)
{
    if (tenths < 0) snprintf(buf, size, "reste a 0");
    else snprintf(buf, size, "%d.%d us", tenths / 10, tenths % 10);
    return buf;
}

/* En mode I2C, les lignes du port sont des entrées : elles ne deviennent des
 * sorties à drain ouvert que le temps d'une mesure ou d'une recherche. */
static void port_lines_open_drain(bool on)
{
    for (int k = 0; k < 2; k++) {
        int gpio = k ? V0_PORT_SDA_GPIO : V0_PORT_SCL_GPIO;
        if (on) { gpio_set_level(gpio, 1); gpio_set_direction(gpio, GPIO_MODE_INPUT_OUTPUT_OD); }
        else gpio_set_direction(gpio, GPIO_MODE_INPUT);
    }
}

/* Cherche toutes les adresses de 0x08 à 0x77. Rend le nombre d'adresses qui
 * répondent, ou un code d'erreur négatif si une ligne est tenue à 0. */
static int i2c_scan(const soft_i2c_t *bus, uint8_t *found, int max)
{
    int n = 0;
    for (int addr = 0x08; addr <= 0x77; addr++) {
        int r = soft_i2c_probe(bus, (uint8_t)addr);
        if (r < 0) return r;
        if (r == SOFT_I2C_OK && n < max) found[n++] = (uint8_t)addr;
    }
    return n;
}

static void addr_list(char *buf, size_t size, const uint8_t *found, int n)
{
    size_t k = 0;
    buf[0] = 0;
    if (n == 0) snprintf(buf, size, "aucune");
    for (int i = 0; i < n && k + 6 < size; i++) k += (size_t)snprintf(buf + k, size - k, "%s0x%02x", i ? " " : "", found[i]);
}

static void cmd_i2c(void)
{
    char a[16], b[16], list[48];
    uint8_t found[8];
    int rs = rise_time(V0_ACC_SDA_GPIO), rc = rise_time(V0_ACC_SCL_GPIO);
    say("bus de l'accelerometre, remontee apres un passage a 0 : SDA %s, SCL %s (attendu : moins de 3.0 us, rappels de 10 kohm)\n",
        rise_text(a, sizeof(a), rs), rise_text(b, sizeof(b), rc));
    int n = i2c_scan(&BUS_ACC, found, 8);
    if (n < 0) { say("recherche impossible : %s\n", soft_i2c_strerror(n)); return; }
    addr_list(list, sizeof(list), found, n);
    say("adresses qui repondent : %s (attendu : 0x%02x seule, le LIS2DH12)\n", list, V0_ACC_ADDR);
}

#define ACC_NO_DATA 100     /* l'accéléromètre répond mais n'annonce aucune mesure */

/* Lit l'identifiant puis les trois axes, en millièmes de g. Réveille
 * l'accéléromètre le temps de la mesure et le rend à son état de mise sous
 * tension (éteint). Rend 0, un code d'erreur de l'I2C ou ACC_NO_DATA. */
static int acc_read(uint8_t *id, int mg[3])
{
    uint8_t d[6], status = 0;
    int err = soft_i2c_read_regs(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_WHO_AM_I, id, 1);
    if (err) return err;
    /* CTRL_REG4 = 0x80 : ±2 g, mode normal, sortie figée pendant la lecture.
     * CTRL_REG1 = 0x57 : 100 mesures par seconde, trois axes. */
    if ((err = soft_i2c_write_reg(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_CTRL_REG4, 0x80)) != 0) return err;
    if ((err = soft_i2c_write_reg(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_CTRL_REG1, 0x57)) != 0) return err;
    vTaskDelay(pdMS_TO_TICKS(30));
    err = soft_i2c_read_regs(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_OUT_X_L | LIS2DH12_AUTO_INC, d, 6);    /* première mesure : jetée */
    for (int i = 0; !err && i < 20; i++) {                  /* attend la suivante : bit 3 du registre d'état */
        vTaskDelay(pdMS_TO_TICKS(5));
        err = soft_i2c_read_regs(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_STATUS, &status, 1);
        if (status & 0x08) break;
    }
    if (!err) err = soft_i2c_read_regs(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_OUT_X_L | LIS2DH12_AUTO_INC, d, 6);
    /* Retour aux valeurs de mise sous tension, même après une erreur. */
    soft_i2c_write_reg(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_CTRL_REG1, 0x07);
    soft_i2c_write_reg(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_CTRL_REG4, 0x00);
    if (err) return err;
    if (!(status & 0x08)) return ACC_NO_DATA;
    for (int k = 0; k < 3; k++) mg[k] = lis2dh12_mg(d[2 * k], d[2 * k + 1]);
    return 0;
}

static const char *acc_strerror(int err)
{
    return err == ACC_NO_DATA ? "aucune mesure prete en 100 ms" : soft_i2c_strerror(err);
}

static int norm_mg(const int mg[3])
{
    return (int)(sqrtf((float)(mg[0] * mg[0] + mg[1] * mg[1] + mg[2] * mg[2])) + 0.5f);
}

static void cmd_acc(void)
{
    uint8_t id = 0;
    int mg[3] = {0, 0, 0};
    int err = acc_read(&id, mg);
    if (err && id == 0) { say("accelerometre, adresse 0x%02x : %s. NON <<<\n", V0_ACC_ADDR, acc_strerror(err)); return; }
    say("identifiant (registre WHO_AM_I) : 0x%02x (attendu : 0x%02x) %s\n", id, LIS2DH12_ID, id == LIS2DH12_ID ? "BON" : "NON <<<");
    if (err) { say("lecture des axes impossible : %s\n", acc_strerror(err)); return; }
    int n = norm_mg(mg);
    say("acceleration : x = %+.2f g, y = %+.2f g, z = %+.2f g ; norme %.2f g (attendu : 0.85 a 1.15 g, carte immobile) %s\n",
        mg[0] / 1000.0, mg[1] / 1000.0, mg[2] / 1000.0, n / 1000.0, n >= 850 && n <= 1150 ? "BON" : "NON <<<");
    say("  a plat sur la table, z vaut +1 ou -1 g et les deux autres environ 0 ; retournez la carte, le signe change.\n");
}

/* ------------------------------------------------------------------ */
/* Port Grove                                                           */
static void cmd_port_show(void)
{
    char a[16], b[16];
    say("port Grove : %s ; PORT_PU lue %d\n", port_text(), gpio_get_level(V0_PORT_PU_GPIO));
    say("  ligne 1 (broche 1, SCL)          : %d\n", gpio_get_level(V0_PORT_SCL_GPIO));
    say("  ligne 2 (broche 2, SDA ou ruban) : %d\n", gpio_get_level(V0_PORT_SDA_GPIO));
    if (!s_conv) {
        say("  convertisseur arrete : le banc tient PORT_PU et les deux lignes a 0, et la broche 3 (alimentation) est a 0 V.\n"
            "  attendu : 0, 0 et 0. Les rappels et le tampon s'essaient apres 'conv 1'.\n");
    } else if (s_port == PORT_RIBBON) {
        say("  mode ruban : la puce pousse la ligne 1 a 0 et la ligne 2 a %d ('ligne2'). Attendu : 0 et %d.\n", s_line2, s_line2);
    } else {
        port_lines_open_drain(true);
        int r1 = rise_time(V0_PORT_SCL_GPIO), r2 = rise_time(V0_PORT_SDA_GPIO);
        port_lines_open_drain(false);
        say("  attendu, port vide : 1 et 1.\n");
        say("  remontee apres un passage a 0 : ligne 1 %s, ligne 2 %s (attendu : moins de 3.0 us, rappels de 4.7 kohm)\n",
            rise_text(a, sizeof(a), r1), rise_text(b, sizeof(b), r2));
    }
}

static void port_mode_set(port_mode_t mode)
{
    s_port = mode;
    s_line2 = 0;
    if (s_conv) port_apply();
    say("port Grove : %s\n", port_text());
    if (!s_conv) say("  le convertisseur est arrete : PORT_PU et les deux lignes restent a 0. Le mode sera pose par 'conv 1'.\n");
}

/* Une seule broche commande les rappels et le tampon, et le banc ne la laisse
 * jamais en l'air : arrêter l'un, c'est activer l'autre. */
static void cmd_pullups(const char *arg)
{
    int on = parse_on_off(arg);
    if (on < 0) { say("usage : rappels 1 ou rappels 0\n"); return; }
    if (!on) say("une seule broche commande les deux : rappels arretes = tampon actif.\n");
    port_mode_set(on ? PORT_I2C : PORT_RIBBON);
}

static void cmd_buffer(const char *arg)
{
    int on = parse_on_off(arg);
    if (on < 0) { say("usage : tampon 1 ou tampon 0\n"); return; }
    if (!on) say("une seule broche commande les deux : tampon arrete = rappels actifs.\n");
    port_mode_set(on ? PORT_RIBBON : PORT_I2C);
}

static void cmd_line2(const char *arg)
{
    int level = parse_on_off(arg);
    if (level < 0) { say("usage : ligne2 1 ou ligne2 0\n"); return; }
    if (!s_conv || s_port != PORT_RIBBON) {
        say("refuse : 'ligne2' ne sert qu'en mode ruban, convertisseur en marche. Tapez 'tampon 1' puis 'conv 1'.\n");
        return;
    }
    s_line2 = level;
    port_apply();
    if (level) say("ligne 2 poussee a 1. La broche 2 du port doit monter a la tension du rail, et non vers 3 V.\n  rail attendu : %s.\n", rail_expected());
    else say("ligne 2 poussee a 0. La broche 2 du port doit etre a 0 V.\n");
}

/* Ruban d'essai sur le port Grove : allume en blanc faible les n premières LED
 * d'un ruban branché sur le port, éteint les suivantes. Le pilote n'existe que
 * le temps de l'envoi ; la ligne 2 redevient ensuite une sortie à 0. La trame
 * part deux fois : la première après la mise sous tension du rail, ou après
 * une pause de quelques secondes, est perdue (règle 3 du port, carte_v0.h). */
static void cmd_ribbon(const char *arg)
{
    int n = atoi(arg);
    if (arg[0] < '0' || arg[0] > '9' || n > BANC_RIBBON_MAX) { say("usage : ruban N, de 0 (tout eteint) a %d LED\n", BANC_RIBBON_MAX); return; }
    if (!s_conv || s_port != PORT_RIBBON) {
        say("refuse : le ruban demande le mode ruban et le convertisseur en marche. Tapez 'tampon 1' puis 'conv 1'.\n");
        return;
    }
    led_strip_handle_t ribbon = NULL;
    led_strip_config_t cfg = {
        .strip_gpio_num = V0_PORT_SDA_GPIO,
        .max_leds = BANC_RIBBON_MAX,
        .led_model = LED_MODEL_CUSTOM,
        .color_component_format = LED_STRIP_COLOR_COMPONENT_FMT_GRB,
        .timings = LED_TIMINGS,
    };
    led_strip_rmt_config_t rmt = { .clk_src = RMT_CLK_SRC_DEFAULT, .resolution_hz = 10 * 1000 * 1000 };
    s_line2 = 0;
    esp_err_t err = led_strip_new_rmt_device(&cfg, &rmt, &ribbon);
    if (err == ESP_OK) {
        for (int i = 0; i < BANC_RIBBON_MAX; i++) {
            uint32_t v = i < n ? BANC_RIBBON_LEVEL : 0;
            led_strip_set_pixel(ribbon, i, v, v, v);
        }
        err = led_strip_refresh(ribbon);
        if (err == ESP_OK) err = led_strip_refresh(ribbon);     /* le second envoi, celui qui compte */
        led_strip_del(ribbon);
    }
    pin_output(V0_PORT_SDA_GPIO, 0);                            /* la ligne 2 revient à la puce, à 0 */
    if (err != ESP_OK) { say("ruban : envoi impossible (%s)\n", esp_err_to_name(err)); return; }
    if (n == 0) { say("ruban : %d LED eteintes ; trame envoyee deux fois.\n", BANC_RIBBON_MAX); return; }
    say("ruban : %d LED en blanc faible (%d/255), les suivantes eteintes ; trame envoyee deux fois.\n", n, BANC_RIBBON_LEVEL);
    say("  courant des LED allumees : %d mA au pire (%d mA par couleur a fond).\n", v0_ribbon_ma(n), BANC_RIBBON_MA_PER_COLOR);
}

static void cmd_port_i2c(void)
{
    char a[16], b[16], list[48];
    uint8_t found[8];
    if (!s_conv || s_port != PORT_I2C) {
        say("refuse : la recherche demande le mode I2C et le convertisseur en marche, qui alimente l'accessoire.\n"
            "  Tapez 'rappels 1' puis 'conv 1'.\n");
        return;
    }
    port_lines_open_drain(true);
    int rc = rise_time(V0_PORT_SCL_GPIO), rs = rise_time(V0_PORT_SDA_GPIO);
    say("port, remontee apres un passage a 0 : SCL (ligne 1) %s, SDA (ligne 2) %s\n", rise_text(a, sizeof(a), rc), rise_text(b, sizeof(b), rs));
    if (rc < 0 || rs < 0 || rc > RISE_PULLUP_MAX || rs > RISE_PULLUP_MAX) {
        say("les rappels sont commandes mais les lignes ne remontent pas assez vite : recherche abandonnee.\n"
            "  R33, R34 et PORT_PU sont a controler, ou un accessoire tient une ligne a 0.\n");
    } else {
        int n = i2c_scan(&BUS_PORT, found, 8);
        if (n < 0) say("recherche impossible : %s\n", soft_i2c_strerror(n));
        else { addr_list(list, sizeof(list), found, n); say("adresses qui repondent sur le port : %s\n", list); }
    }
    port_lines_open_drain(false);
}

/* ------------------------------------------------------------------ */
/* Radio : rien n'est enregistré, la radio est arrêtée après l'essai.   */
typedef struct {
    bool ran;               /* l'essai est allé au bout du balayage */
    int  ap_count, best_rssi;
    bool tx_tried;
    int  tx_sent, tx_acked, tx_channel;
} radio_result_t;

static SemaphoreHandle_t s_now_sem;
static volatile int s_now_acked;

static void now_sent_cb(const esp_now_send_info_t *info, esp_now_send_status_t status)
{
    (void)info;
    if (status == ESP_NOW_SEND_SUCCESS) s_now_acked++;
    xSemaphoreGive(s_now_sem);
}

static bool radio_step(esp_err_t err, const char *what)
{
    if (err == ESP_OK) return true;
    say("radio : %s a echoue (%s)\n", what, esp_err_to_name(err));
    return false;
}

/* Émission : dix trames adressées à la box la plus forte. Toute station
 * Wi-Fi accuse réception d'une trame qui lui est adressée, avant même de
 * regarder ce qu'elle contient : chaque accusé prouve que la carte a émis,
 * que la box l'a entendue, et que la carte a entendu la réponse. Les trames
 * sont celles d'ESP-NOW ; la box les ignore. */
static void radio_tx_test(const wifi_ap_record_t *ap, radio_result_t *r)
{
    static const uint8_t payload[] = "banc Luciole v0";
    esp_now_peer_info_t peer = { .channel = 0, .ifidx = WIFI_IF_STA, .encrypt = false };
    memcpy(peer.peer_addr, ap->bssid, 6);
    r->tx_channel = ap->primary;
    if (!radio_step(esp_wifi_set_channel(ap->primary, WIFI_SECOND_CHAN_NONE), "le choix du canal")) return;
    if (!radio_step(esp_now_init(), "le demarrage d'ESP-NOW")) return;
    if (radio_step(esp_now_register_send_cb(now_sent_cb), "ESP-NOW (rappel d'emission)")
        && radio_step(esp_now_add_peer(&peer), "ESP-NOW (destinataire)")) {
        r->tx_tried = true;
        s_now_acked = 0;
        for (int i = 0; i < 10; i++) {
            xSemaphoreTake(s_now_sem, 0);
            if (esp_now_send(ap->bssid, payload, sizeof(payload)) == ESP_OK) {
                r->tx_sent++;
                xSemaphoreTake(s_now_sem, pdMS_TO_TICKS(500));
            }
            vTaskDelay(pdMS_TO_TICKS(20));
        }
        r->tx_acked = s_now_acked;
        esp_now_del_peer(ap->bssid);
    }
    esp_now_unregister_send_cb();
    esp_now_deinit();
}

static void radio_test(radio_result_t *r)
{
    static bool netif_ok, loop_ok, wifi_ok;
    static wifi_ap_record_t ap[20];
    uint8_t mac[6] = {0};
    memset(r, 0, sizeof(*r));
    if (!s_now_sem) s_now_sem = xSemaphoreCreateBinary();

    if (!netif_ok && !(netif_ok = radio_step(esp_netif_init(), "esp_netif_init"))) return;
    if (!loop_ok && !(loop_ok = radio_step(esp_event_loop_create_default(), "la boucle d'evenements"))) return;
    if (!wifi_ok) {
        wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
        if (!(wifi_ok = radio_step(esp_wifi_init(&cfg), "esp_wifi_init"))) return;
    }
    /* Réglages en mémoire vive seulement. */
    if (!radio_step(esp_wifi_set_storage(WIFI_STORAGE_RAM), "esp_wifi_set_storage")) return;
    if (!radio_step(esp_wifi_set_mode(WIFI_MODE_STA), "esp_wifi_set_mode")) return;
    if (!radio_step(esp_wifi_start(), "le demarrage de la radio")) return;
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    say("radio en marche, adresse %02x:%02x:%02x:%02x:%02x:%02x. Ecoute des reseaux Wi-Fi, 3 secondes environ...\n",
        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    wifi_scan_config_t sc = { .show_hidden = true };
    uint16_t total = 0, n = sizeof(ap) / sizeof(ap[0]);
    if (radio_step(esp_wifi_scan_start(&sc, true), "le balayage")
        && radio_step(esp_wifi_scan_get_ap_num(&total), "le compte des reseaux")
        && radio_step(esp_wifi_scan_get_ap_records(&n, ap), "la liste des reseaux")) {
        r->ran = true;
        r->ap_count = total;
        r->best_rssi = -127;
        const wifi_ap_record_t *target = NULL;
        for (int i = 0; i < n; i++) {
            if (ap[i].rssi > r->best_rssi) r->best_rssi = ap[i].rssi;
            /* Canaux 1 à 11 seulement : l'émission y est permise partout. */
            if (ap[i].primary >= 1 && ap[i].primary <= 11 && (!target || ap[i].rssi > target->rssi)) target = &ap[i];
        }
        say("reception : %d reseau(x) entendu(s)%s\n", total, total ? " :" : " (attendu : au moins 1 pres d'une box Wi-Fi)");
        for (int i = 0; i < n && i < 8; i++)
            say("  canal %2d  %4d dBm  %s\n", ap[i].primary, ap[i].rssi, ap[i].ssid[0] ? (const char *)ap[i].ssid : "(nom cache)");
        if (total) say("  attendu : le plus fort au-dessus de -85 dBm ; -30 a -60 dBm a quelques metres d'une box.\n");
        if (target) {
            radio_tx_test(target, r);
            if (r->tx_tried) {
                say("emission : %d trame(s) envoyee(s) a '%s' sur le canal %d, %d accuse(s) de reception\n",
                    r->tx_sent, target->ssid[0] ? (const char *)target->ssid : "(nom cache)", r->tx_channel, r->tx_acked);
                say("  attendu : au moins 5 sur 10. Zero accuse ne condamne pas l'emission (certaines box n'accusent pas\n"
                    "  ces trames) : refaire l'essai pres d'une autre box avant de conclure.\n");
            }
        } else if (total) {
            say("emission : pas essayee, aucun reseau sur les canaux 1 a 11.\n");
        }
    }
    esp_wifi_stop();
    say("radio arretee.\n");
}

/* ------------------------------------------------------------------ */
/* Commandes d'ensemble                                                 */
static const char *reset_text(void)
{
    switch (esp_reset_reason()) {
        case ESP_RST_POWERON:  return "mise sous tension ou bouton reset (SW1)";
        case ESP_RST_SW:       return "redemarrage demande (commande reset)";
        case ESP_RST_USB:      return "reset par l'USB (flashage, ouverture du terminal)";
        case ESP_RST_JTAG:     return "reset par JTAG";
        case ESP_RST_BROWNOUT: return "CHUTE DU 3.3 V (brownout) : alimentation a controler";
        case ESP_RST_PANIC:    return "ERREUR DU PROGRAMME (panique) : a signaler";
        case ESP_RST_INT_WDT:
        case ESP_RST_TASK_WDT:
        case ESP_RST_WDT:      return "CHIEN DE GARDE (programme bloque) : a signaler";
        default:               return "autre cause";
    }
}

static const char *charge_text(void)
{
    switch (s_charge) {
        case CHARGE_FAST:    return "rapide, 907 mA (ISET a 1, CHG_INH relachee)";
        case CHARGE_STOPPED: return "ARRETEE (CHG_INH tiree a 0)";
        default:             return "lente, 407 mA (ISET a 0, CHG_INH relachee)";
    }
}

static const char *pattern_text(void)
{
    switch (s_pat) {
        case PAT_ONE:    return "une LED";
        case PAT_ALL:    return "toutes";
        case PAT_CHASE:  return "chenillard";
        case PAT_COLORS: return "couleurs";
        default:         return "eteintes";
    }
}

/* Une sortie poussée se relit : si la broche ne suit pas, quelque chose la tient. */
static const char *follows(int gpio, int commanded)
{
    return gpio_get_level(gpio) == commanded ? "" : "  <<< LA BROCHE NE SUIT PAS LA COMMANDE";
}

static void cmd_state(void)
{
    measures_t m;
    measure(&m);
    table_begin();
    rows_measures(&m);
    hints(&m);
    if (!s_adc_calibrated) say("attention : ADC sans etalonnage d'usine, tensions approchees.\n");
    say("STDBY du chargeur (charge finie) n'est pas relie a la puce : a lire sur TP13, 0 V = charge finie.\n");
    say("commandes en cours (etat sur au demarrage : convertisseur arrete, charge lente, port au repos, LED eteintes) :\n");
    say("  convertisseur des LED : %s (BOOST_EN a %d)%s\n", s_conv ? "EN MARCHE" : "arrete", s_conv, follows(V0_BOOST_EN_GPIO, s_conv));
    say("  consigne du rail      : %s V (VSEL a %d)%s\n", s_rail_high ? "5.04" : "4.45", s_rail_high, follows(V0_VSEL_GPIO, s_rail_high));
    say("  charge                : %s%s\n", charge_text(), follows(V0_ISET_GPIO, s_charge == CHARGE_FAST));
    say("  port Grove            : %s ; ligne 1 = %d, ligne 2 = %d%s\n", port_text(), gpio_get_level(V0_PORT_SCL_GPIO),
        gpio_get_level(V0_PORT_SDA_GPIO), follows(V0_PORT_PU_GPIO, s_conv && s_port == PORT_I2C));
    say("  LED                   : %s, niveau %d/255, plafond %d/255\n", pattern_text(), s_level, BANC_LED_MAX);
    say("  cause du demarrage    : %s\n", reset_text());
}

static void cmd_autotest(void)
{
    char a[16], b[16], list[48];
    uint8_t found[8], id = 0;
    int mg[3] = {0, 0, 0};
    measures_t m;

    say("autotest : port Grove vide, carte immobile, bouton relache. Le convertisseur, les LED et le courant de\n"
        "charge ne sont pas touches. Dure moins de 10 secondes.\n");
    measure(&m);
    table_begin();
    rows_measures(&m);

    /* Mémoire du module : un ESP32-C6-MINI-1-N4 porte 4 Mo. */
    uint32_t flash = 0;
    esp_flash_get_physical_size(NULL, &flash);
    row("memoire du module", flash == 4 * 1024 * 1024 ? V_BON : V_NON, "4 Mo (module -N4)", "%d Mo", (int)(flash / (1024 * 1024)));

    /* Accéléromètre */
    int rs = rise_time(V0_ACC_SDA_GPIO), rc = rise_time(V0_ACC_SCL_GPIO);
    row("I2C interne, rappels", rs >= 0 && rc >= 0 && rs <= RISE_PULLUP_MAX && rc <= RISE_PULLUP_MAX ? V_BON : V_NON,
        "remontee en moins de 3.0 us", "SDA %s, SCL %s", rise_text(a, sizeof(a), rs), rise_text(b, sizeof(b), rc));
    int n = i2c_scan(&BUS_ACC, found, 8);
    if (n < 0) row("I2C interne, adresses", V_NON, "0x19 seule", "%s", soft_i2c_strerror(n));
    else { addr_list(list, sizeof(list), found, n); row("I2C interne, adresses", n == 1 && found[0] == V0_ACC_ADDR ? V_BON : V_NON, "0x19 seule", "%s", list); }
    int err = acc_read(&id, mg);
    if (err && id == 0) {
        row("LIS2DH12, identifiant", V_NON, "0x33", "%s", acc_strerror(err));
    } else {
        row("LIS2DH12, identifiant", id == LIS2DH12_ID ? V_BON : V_NON, "0x33", "0x%02x", id);
        int norm = norm_mg(mg);
        if (err) row("LIS2DH12, trois axes", V_NON, "norme 0.85 a 1.15 g", "%s", acc_strerror(err));
        else row("LIS2DH12, trois axes", norm >= 850 && norm <= 1150 ? V_BON : V_NON, "norme 0.85 a 1.15 g, carte immobile",
                 "%+.2f %+.2f %+.2f, norme %.2f", mg[0] / 1000.0, mg[1] / 1000.0, mg[2] / 1000.0, norm / 1000.0);
        /* Ligne d'interruption : on inverse sa polarité (CTRL_REG6, bit 1), elle doit passer à 1, puis revenir à 0. */
        int i0 = gpio_get_level(V0_ACC_INT_GPIO);
        soft_i2c_write_reg(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_CTRL_REG6, 0x02);
        vTaskDelay(pdMS_TO_TICKS(5));
        int i1 = gpio_get_level(V0_ACC_INT_GPIO);
        soft_i2c_write_reg(&BUS_ACC, V0_ACC_ADDR, LIS2DH12_CTRL_REG6, 0x00);
        vTaskDelay(pdMS_TO_TICKS(5));
        int i2 = gpio_get_level(V0_ACC_INT_GPIO);
        row("LIS2DH12, interruption", !i0 && i1 && !i2 ? V_BON : V_NON, "0 puis 1 puis 0", "%d puis %d puis %d", i0, i1, i2);
    }

    /* Port Grove. Convertisseur arrêté, il est au repos : seule la relecture de
     * ses trois broches se vérifie. Convertisseur en marche, les deux modes sont
     * essayés, puis le port revient au mode d'avant. */
    if (!s_conv) {
        int pu = gpio_get_level(V0_PORT_PU_GPIO), l1 = gpio_get_level(V0_PORT_SCL_GPIO), l2 = gpio_get_level(V0_PORT_SDA_GPIO);
        row("port au repos", !pu && !l1 && !l2 ? V_BON : V_NON, "0 0 0 (convertisseur arrete)", "PORT_PU=%d, lignes %d %d", pu, l1, l2);
        row("port, I2C et ruban", V_VOIR, "a refaire apres 'conv 1'", "pas essayes");
    } else {
        port_mode_t mode_before = s_port;
        int line2_before = s_line2;
        s_port = PORT_I2C;
        s_line2 = 0;
        port_apply();
        vTaskDelay(pdMS_TO_TICKS(20));
        port_lines_open_drain(true);
        int r1 = rise_time(V0_PORT_SCL_GPIO), r2 = rise_time(V0_PORT_SDA_GPIO);
        port_lines_open_drain(false);
        int l1 = gpio_get_level(V0_PORT_SCL_GPIO), l2 = gpio_get_level(V0_PORT_SDA_GPIO);
        row("port, rappels (I2C)", l1 && l2 && r1 >= 0 && r2 >= 0 && r1 <= RISE_PULLUP_MAX && r2 <= RISE_PULLUP_MAX ? V_BON : V_NON,
            "1 1, moins de 3.0 us (4.7 kohm)", "%d %d, %s, %s", l1, l2, rise_text(a, sizeof(a), r1), rise_text(b, sizeof(b), r2));
        /* Mode ruban : la puce pousse les lignes. Relâchées un instant, elles
         * doivent rester à 0, tirées vers PORT_PU par R33 et R34. */
        s_port = PORT_RIBBON;
        port_apply();
        pin_input(V0_PORT_SCL_GPIO);
        pin_input(V0_PORT_SDA_GPIO);
        vTaskDelay(pdMS_TO_TICKS(20));
        l1 = gpio_get_level(V0_PORT_SCL_GPIO); l2 = gpio_get_level(V0_PORT_SDA_GPIO);
        row("port, tampon (ruban)", !l1 && !l2 ? V_BON : V_NON, "0 0 (rappels tires vers 0)", "%d %d", l1, l2);
        s_port = mode_before;
        s_line2 = line2_before;
        port_apply();
    }

    /* Arrêt de la charge : ne se vérifie que si la batterie est en train de charger. */
    if (!m.usb) row("arret de la charge", V_VOIR, "a refaire sous USB", "pas d'USB");
    else if (s_charge == CHARGE_STOPPED) row("arret de la charge", V_VOIR, "tapez 'charge lente' d'abord", "deja arretee");
    else if (gpio_get_level(V0_CHRG_GPIO)) row("arret de la charge", V_VOIR, "a refaire batterie a charger", "pas en charge");
    else {
        int t;
        gpio_set_level(V0_CHG_INH_GPIO, 0);
        for (t = 0; t < 1000 && !gpio_get_level(V0_CHRG_GPIO); t += 10) vTaskDelay(pdMS_TO_TICKS(10));
        int stopped = gpio_get_level(V0_CHRG_GPIO);
        gpio_set_level(V0_CHG_INH_GPIO, 1);
        for (t = 0; t < 3000 && gpio_get_level(V0_CHRG_GPIO); t += 10) vTaskDelay(pdMS_TO_TICKS(10));
        int resumed = !gpio_get_level(V0_CHRG_GPIO);
        row("arret de la charge", stopped && resumed ? V_BON : V_NON, "CHRG : 0, puis 1 a l'arret, puis 0", "0, puis %d, puis %d", stopped, !resumed);
    }
    int bon = s_tally.bon, non = s_tally.non, voir = s_tally.voir;

    /* Radio, en dernier : ses lignes s'écrivent sous le tableau. */
    say("\n");
    radio_result_t r;
    radio_test(&r);
    say("\n");
    table_begin();
    if (!r.ran) row("radio, reception", V_NON, "au moins 1 reseau", "essai interrompu");
    else if (r.ap_count == 0) row("radio, reception", V_NON, "au moins 1 reseau, plus de -85 dBm", "aucun reseau");
    else row("radio, reception", r.best_rssi > -85 ? V_BON : V_NON, "au moins 1 reseau, plus de -85 dBm", "%d reseau(x), max %d dBm", r.ap_count, r.best_rssi);
    if (!r.tx_tried) row("radio, emission", V_VOIR, "au moins 5 accuses sur 10", "pas essayee");
    else row("radio, emission", r.tx_acked >= 5 ? V_BON : V_VOIR, "au moins 5 accuses sur 10", "%d accuse(s) sur %d", r.tx_acked, r.tx_sent);
    bon += s_tally.bon; non += s_tally.non; voir += s_tally.voir;

    say("\nbilan : %d bon(s), %d NON, %d a voir.%s\n", bon, non, voir, non ? " Chaque NON est a comprendre avant d'aller plus loin." : "");
    hints(&m);
    say("reste a essayer a la main, avec les yeux ou un voltmetre : conv, rail, led, charge rapide, ligne2, ruban (voir le README).\n");
}

static void cmd_help(void)
{
    say("Banc d'essai Luciole2, carte v0. Une commande par ligne, puis Entree.\n"
        "  ?  ou aide           cette liste\n"
        "  e  ou etat           toutes les mesures, et l'etat des commandes\n"
        "  a  ou autotest       tout ce qui se verifie sans intervention, en tableau\n");
    say(" convertisseur des LED (alimente aussi le port Grove)\n"
        "  conv 1 | conv 0      marche, arret\n"
        "  rail 4.5 | rail 5.0  consigne du rail : 4.45 V (au demarrage) ou 5.04 V\n"
        " charge de la batterie\n"
        "  charge lente         0.4 A (au demarrage)\n"
        "  charge rapide        0.9 A, si la source USB annonce 1.5 A ou plus\n"
        "  charge arret         charge arretee\n");
    say(" LED, luminosite plafonnee a %d/255\n"
        "  led N                la LED N seule, de 1 a %d, en blanc faible\n"
        "  leds                 toutes en blanc faible\n"
        "  rouge | vert | bleu  toutes dans une seule couleur\n"
        "  couleurs             rouge, vert, bleu : une couleur par seconde\n"
        "  chenillard           une LED allumee qui parcourt la rangee\n"
        "  n  ou noir           extinction\n"
        "  lum N                niveau des LED, de 1 a %d (au demarrage : %d)\n", BANC_LED_MAX, V0_LED_COUNT, BANC_LED_MAX, BANC_LED_DEFAULT);
    say(" accelerometre\n"
        "  i2c                  recherche des adresses sur son bus\n"
        "  acc                  identifiant du LIS2DH12, puis les trois axes\n");
    say(" port Grove : au repos, tout a 0, tant que le convertisseur est arrete\n"
        "  port                 etat du port, lecture des deux lignes\n"
        "  rappels 1            mode I2C : rappels actifs, tampon inactif (mode au demarrage)\n"
        "  tampon 1             mode ruban : tampon actif vers la broche 2, rappels inactifs\n"
        "  port i2c             en mode I2C : recherche des adresses sur le port\n");
    say("  ligne2 1 | 0         en mode ruban : pousse la ligne 2, pour mesurer la sortie du tampon\n"
        "  ruban N              en mode ruban : allume N LED d'un ruban branche sur le port (0 a %d)\n", BANC_RIBBON_MAX);
    say(" radio\n"
        "  radio                reseaux Wi-Fi entendus, puis emission avec accuse de reception\n"
        " divers\n"
        "  reset                redemarre la puce : retour a l'etat sur\n");
}

static void banner(void)
{
    esp_chip_info_t chip;
    uint8_t mac[6] = {0};
    esp_chip_info(&chip);
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    say("\n=== Banc d'essai Luciole2, carte v0 (schema rev. %s) - version %s ===\n", V0_SCHEMA_REV, BANC_VERSION);
    say("puce ESP32-C6 revision v%d.%d, unite %02x%02x. Cause du demarrage : %s.\n",
        chip.revision / 100, chip.revision % 100, mac[4], mac[5], reset_text());
    say("etat sur : convertisseur arrete, charge lente, port au repos, LED eteintes, radio arretee.\n");
    say("cellule : la brancher USB debranche, puis brancher l'USB. Branchee apres l'USB, elle peut rester deconnectee.\n");
    say("rien ne change sans commande. Tapez ? pour la liste, e pour l'etat, a pour l'autotest.\n");
    if (!s_adc_ok) say("ERREUR : l'ADC ne s'est pas initialise, les tensions ne seront pas mesurees.\n");
    if (!s_strip) say("ERREUR : le pilote des LED ne s'est pas initialise.\n");
}

/* ------------------------------------------------------------------ */
/* Console : une commande par ligne, écho des caractères tapés.         */
static void console_exec(char *line)
{
    while (*line == ' ') line++;
    char *end = line + strlen(line);
    while (end > line && end[-1] == ' ') *--end = 0;
    for (char *p = line; *p; p++) if (*p >= 'A' && *p <= 'Z') *p += 'a' - 'A';
    if (!*line) return;

    /* Premier mot, puis le reste. */
    char *arg = strchr(line, ' ');
    if (arg) { *arg++ = 0; while (*arg == ' ') arg++; } else arg = end;

    if (!strcmp(line, "?") || !strcmp(line, "aide") || !strcmp(line, "h") || !strcmp(line, "help")) cmd_help();
    else if (!strcmp(line, "e") || !strcmp(line, "etat")) cmd_state();
    else if (!strcmp(line, "a") || !strcmp(line, "autotest")) cmd_autotest();
    else if (!strcmp(line, "conv")) cmd_conv(arg);
    else if (!strcmp(line, "rail")) cmd_rail(arg);
    else if (!strcmp(line, "charge")) cmd_charge(arg);
    else if (!strcmp(line, "led")) {
        int n = atoi(arg);
        if (n < 1 || n > V0_LED_COUNT) { say("usage : led N, avec N de 1 a %d (D1 est la premiere de la chaine)\n", V0_LED_COUNT); return; }
        s_pat_led = n - 1;
        pattern_set(PAT_ONE, 1, 1, 1);
        char what[40];
        snprintf(what, sizeof(what), "D%d seule, en blanc", n);
        led_report(what);
    }
    else if (!strcmp(line, "leds"))  { pattern_set(PAT_ALL, 1, 1, 1); led_report("toutes en blanc"); }
    else if (!strcmp(line, "rouge")) { pattern_set(PAT_ALL, 1, 0, 0); led_report("toutes en rouge"); }
    else if (!strcmp(line, "vert"))  { pattern_set(PAT_ALL, 0, 1, 0); led_report("toutes en vert"); }
    else if (!strcmp(line, "bleu"))  { pattern_set(PAT_ALL, 0, 0, 1); led_report("toutes en bleu"); }
    else if (!strcmp(line, "couleurs")) { pattern_set(PAT_COLORS, 1, 1, 1); led_report("rouge, vert, bleu, une couleur par seconde"); }
    else if (!strcmp(line, "chenillard") || !strcmp(line, "ch")) { pattern_set(PAT_CHASE, 1, 1, 1); led_report("chenillard de D1 a D15"); }
    else if (!strcmp(line, "n") || !strcmp(line, "noir")) { pattern_set(PAT_BLACK, 0, 0, 0); say("LED eteintes.\n"); }
    else if (!strcmp(line, "lum")) {
        int n = atoi(arg);
        if (n < 1 || n > BANC_LED_MAX) { say("usage : lum N, avec N de 1 a %d (le plafond du banc)\n", BANC_LED_MAX); return; }
        s_level = n;
        pattern_render();
        led_report(pattern_text());
    }
    else if (!strcmp(line, "i2c")) cmd_i2c();
    else if (!strcmp(line, "acc")) cmd_acc();
    else if (!strcmp(line, "port")) { if (!strcmp(arg, "i2c")) cmd_port_i2c(); else cmd_port_show(); }
    else if (!strcmp(line, "rappels")) cmd_pullups(arg);
    else if (!strcmp(line, "tampon")) cmd_buffer(arg);
    else if (!strcmp(line, "ligne2")) cmd_line2(arg);
    else if (!strcmp(line, "ruban")) cmd_ribbon(arg);
    else if (!strcmp(line, "radio")) { radio_result_t r; radio_test(&r); }
    else if (!strcmp(line, "reset")) {
        if (s_conv) cmd_conv("0");              /* arrêt en ordre : le port à 0 avant le rail */
        say("redemarrage...\n");
        vTaskDelay(pdMS_TO_TICKS(200));
        esp_restart();
    }
    else say("commande inconnue : '%s'. Tapez ? pour la liste.\n", line);
}

/* Une ligne par source : un parasite sur la pastille de l'UART ne doit pas
 * se mêler à ce qui est tapé sur l'USB. */
typedef struct { char buf[64]; int len; bool after_cr; } line_t;

static void console_feed(line_t *l, const uint8_t *data, int n)
{
    for (int i = 0; i < n; i++) {
        char c = (char)data[i];
        if (c == '\n' && l->after_cr) { l->after_cr = false; continue; }    /* Entrée = retour chariot puis saut de ligne */
        l->after_cr = (c == '\r');
        if (c == '\r' || c == '\n') {
            l->buf[l->len] = 0;
            l->len = 0;
            say("\n");
            console_exec(l->buf);
            say("banc> ");
        } else if (c == 0x08 || c == 0x7f) {
            if (l->len > 0) { l->len--; say("\b \b"); }
        } else if (c >= 0x20 && c < 0x7f && l->len < (int)sizeof(l->buf) - 1) {
            l->buf[l->len++] = c;
            say("%c", c);
        }
    }
}

static void banc_task(void *arg)
{
    static line_t line_usb, line_uart;
    uint8_t buf[32];
    (void)arg;
    banner();
    say("banc> ");
    while (true) {
        int n = s_usb_ok ? usb_serial_jtag_read_bytes(buf, sizeof(buf), 0) : 0;
        if (n > 0) console_feed(&line_usb, buf, n);
        n = s_uart_ok ? uart_read_bytes(UART_NUM_0, buf, sizeof(buf), 0) : 0;
        if (n > 0) console_feed(&line_uart, buf, n);
        pattern_tick(esp_timer_get_time());
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void app_main(void)
{
    esp_log_level_set("gpio", ESP_LOG_WARN);    /* sinon une ligne de journal par broche configurée */
    safe_state();                               /* d'abord, avant toute autre initialisation */
    console_init();
    esp_log_level_set("*", ESP_LOG_WARN);       /* seuls les avertissements et les erreurs d'ESP-IDF s'affichent */
    led_init();
    adc_init();
    temp_init();
    xTaskCreate(banc_task, "banc", 8192, NULL, 5, NULL);
}
