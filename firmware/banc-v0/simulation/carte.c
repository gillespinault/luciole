/* Fausse carte Luciole² v0, révision 0.6 : modèle des broches d'après circuit.py,
 * esclave I2C LIS2DH12, console sur stdin/stdout. Sert à dérouler toutes les
 * commandes du banc sur un ordinateur et à vérifier des règles : état sûr,
 * plafond des LED, règles du port Grove. Elle ne dit rien des pilotes réels
 * d'ESP-IDF ni de l'électronique. */
#include "faux_idf.h"
#include <stdlib.h>

void app_main(void);

static struct {
    bool usb, charging, acc_present, sda_stuck, port_pullup_broken, no_ap, no_ack, int_pullup_missing, button;
    int vbat_pin_mv, cc_mv, chip_rev;
} sc = { .chip_rev = 2, .usb = true, .charging = true, .acc_present = true, .vbat_pin_mv = 1170, .cc_mv = 205 };   /* 1170 mV : 3,92 V × 200/670 */

static uint64_t cyc = 1000;
#define US(x) ((uint64_t)((x) * 160))
static int violations, commands_seen, led_frames;
static bool boot_done;

static void violation(const char *what) { printf("\n*** VIOLATION : %s\n", what); violations++; }

/* ---------------------------------------------------------------- broches */
typedef struct { int mode, latch; uint64_t released_at; char last[40]; } pin_t;
static pin_t pin[32];
static bool is_out(int p) { return pin[p].mode & 2; }
static bool is_od(int p) { return (pin[p].mode & 4) != 0; }
static bool drives_low(int p) { return is_out(p) && pin[p].latch == 0; }
static bool drives_high(int p) { return is_out(p) && !is_od(p) && pin[p].latch == 1; }
static bool pushed(int p) { return is_out(p) && !is_od(p); }
static bool rail_on(void) { return drives_high(5); }
static bool ribbon_owns_line2;      /* le pilote du ruban tient la ligne 2 */

static const char *pin_name(int p)
{
    switch (p) { case 5: return "BOOST_EN"; case 14: return "ISET"; case 15: return "PORT_PU"; case 20: return "VSEL";
                 case 21: return "CHG_INH"; case 2: return "IO2 (ligne 2)"; case 1: return "IO1 (ligne 1)"; default: return "?"; }
}

static void trace(int p)
{
    char now[40];
    if (p != 5 && p != 14 && p != 15 && p != 20 && p != 21 && p != 1 && p != 2) return;
    if ((p == 1 || p == 2) && is_od(p)) return;             /* I2C logiciel : trop bavard */
    if (!is_out(p)) snprintf(now, sizeof now, "relachee (entree)");
    else if (is_od(p)) snprintf(now, sizeof now, pin[p].latch ? "relachee (drain ouvert)" : "TIREE A 0 (drain ouvert)");
    else snprintf(now, sizeof now, "poussee a %d", pin[p].latch);
    if (strcmp(now, pin[p].last)) { if (boot_done) printf("    ~ GPIO%d %s : %s\n", p, pin_name(p), now); strcpy(pin[p].last, now); }
}

/* Règles vraies à tout instant. */
static void check_always(int p)
{
    if (p == 12 || p == 13) violation("broche USB (12 ou 13) touchee");
    if (drives_high(21)) violation("CHG_INH poussee a 1");
    if (boot_done && !is_out(15)) violation("PORT_PU laissee en l'air");
    if (commands_seen == 0 && (drives_high(5) || drives_high(14) || drives_high(20) || drives_low(21) || drives_high(15) || drives_high(2) || drives_high(1)))
        violation("commande donnee avant toute demande de l'utilisateur");
}

/* Règles du port Grove, vraies entre deux commandes. */
static void check_port_at_rest(const char *when)
{
    char msg[120];
    const char *bad = NULL;
    if (!pushed(15)) bad = "PORT_PU n'est pas commandee";
    else if (!rail_on() && !(drives_low(15) && drives_low(1) && drives_low(2) && pushed(1) && pushed(2))) bad = "convertisseur arrete mais PORT_PU, IO1, IO2 ne sont pas toutes a 0";
    else if (rail_on() && drives_high(15) && (is_out(1) || is_out(2))) bad = "mode I2C mais une ligne du port n'est pas relachee";
    else if (rail_on() && drives_low(15) && !(drives_low(1) && pushed(2))) bad = "mode ruban mais IO1 n'est pas a 0 ou IO2 n'est pas poussee";
    if (ribbon_owns_line2) bad = "le pilote du ruban n'a pas ete rendu";
    if (bad) { snprintf(msg, sizeof msg, "%s (%s)", bad, when); violation(msg); }
}

/* ------------------------------------------------- esclave I2C LIS2DH12 */
static struct { int st, next, bit, sent; uint8_t sh, ptr; bool inc, ack_now, sda_low, master_ack; uint8_t reg[128]; } sl;
static int m_sda = 1, m_scl = 1;

static uint8_t reg_read(uint8_t r)
{
    static const uint8_t out[6] = { 0xC0, 0x00, 0xC0, 0xFE, 0x80, 0x3E };   /* x = +12 mg, y = -20 mg, z = +1000 mg */
    if (r == 0x0F) return 0x33;
    if (r == 0x27) return (sl.reg[0x20] >> 4) ? 0x0F : 0x00;
    if (r >= 0x28 && r <= 0x2D) return (sl.reg[0x20] >> 4) ? out[r - 0x28] : 0;
    return sl.reg[r & 0x7f];
}

static void load_byte(void) { sl.sh = reg_read(sl.ptr); if (sl.inc) sl.ptr = (sl.ptr + 1) & 0x7f; sl.sda_low = !(sl.sh & 0x80); sl.sent = 1; sl.st = 4; }

static void bus_update(void)
{
    int sda = !drives_low(22), scl = !drives_low(23);
    if (sda != m_sda && scl && m_scl) {                     /* SDA bouge, SCL haute */
        if (!sda) { sl.st = 1; sl.bit = 0; sl.sh = 0; sl.ack_now = false; sl.sda_low = false; }     /* départ */
        else { sl.st = 0; sl.sda_low = false; }                                                      /* arrêt */
    } else if (scl != m_scl && scl) {                       /* SCL monte */
        if (sl.st >= 1 && sl.st <= 3 && !sl.ack_now) { sl.sh = (uint8_t)(sl.sh << 1 | sda); sl.bit++; }
        else if (sl.st == 5) sl.master_ack = !sda;
    } else if (scl != m_scl && !scl) {                      /* SCL descend */
        if (sl.st >= 1 && sl.st <= 3) {
            if (sl.ack_now) {
                sl.ack_now = false; sl.sda_low = false; sl.bit = 0; sl.sh = 0;
                if (sl.next == 4) load_byte(); else sl.st = sl.next;
            } else if (sl.bit == 8) {
                bool ack = true;
                if (sl.st == 1) { if (sc.acc_present && (sl.sh >> 1) == 0x19) sl.next = (sl.sh & 1) ? 4 : 2; else ack = false; }
                else if (sl.st == 2) { sl.ptr = sl.sh & 0x7f; sl.inc = sl.sh & 0x80; sl.next = 3; }
                else { sl.reg[sl.ptr] = sl.sh; if (sl.inc) sl.ptr = (sl.ptr + 1) & 0x7f; sl.next = 3; }
                if (ack) { sl.sda_low = true; sl.ack_now = true; } else sl.st = 0;
            }
        } else if (sl.st == 4) {
            if (sl.sent < 8) { sl.sda_low = !(sl.sh & (0x80 >> sl.sent)); sl.sent++; }
            else { sl.sda_low = false; sl.st = 5; }
        } else if (sl.st == 5) {
            if (sl.master_ack) load_byte(); else sl.st = 0;
        }
    }
    m_sda = sda; m_scl = scl;
}

static void pin_changed(int p, bool was_low, bool rail_was_on)
{
    if (was_low && !drives_low(p)) pin[p].released_at = cyc;
    if (p == 5 && !rail_was_on && rail_on()) {              /* le convertisseur démarre */
        if (!pushed(15)) violation("BOOST_EN mis a 1 avant que PORT_PU soit commandee");
        if (!(drives_low(1) && drives_low(2))) violation("BOOST_EN mis a 1 alors qu'une ligne du port n'est pas a 0");
    }
    if (p == 5 && rail_was_on && !rail_on()) {              /* le convertisseur s'arrête */
        if (!(drives_low(15) && drives_low(1) && drives_low(2))) violation("rail coupe avant que PORT_PU, IO1 et IO2 soient a 0");
    }
    check_always(p);
    trace(p);
    if (p == 22 || p == 23) bus_update();
}

esp_err_t gpio_config(const gpio_config_t *c)
{
    for (int p = 0; p < 32; p++) if (c->pin_bit_mask >> p & 1) {
        bool was = drives_low(p), rail = rail_on();
        if (c->pull_up_en || c->pull_down_en) violation("rappel interne active");
        if (p == 2 && ribbon_owns_line2) violation("ligne 2 reprise alors que le pilote du ruban la tient");
        pin[p].mode = c->mode; pin_changed(p, was, rail);
    }
    return ESP_OK;
}
esp_err_t gpio_set_direction(int p, gpio_mode_t mode) { bool was = drives_low(p), rail = rail_on(); pin[p].mode = mode; pin_changed(p, was, rail); return ESP_OK; }
esp_err_t gpio_set_level(int p, uint32_t level) { bool was = drives_low(p), rail = rail_on(); pin[p].latch = level ? 1 : 0; cyc += 40; pin_changed(p, was, rail); return ESP_OK; }
esp_err_t gpio_pullup_en(int p) { if (p != U0RXD_GPIO_NUM) violation("rappel interne active ailleurs que sur RXD0"); return ESP_OK; }

static int risen(int p, uint64_t delay) { return cyc - pin[p].released_at >= delay; }

int gpio_get_level(int p)
{
    cyc += 10;
    if (!(pin[p].mode & 1)) return 0;                       /* entrée coupée : lue 0 */
    if (drives_low(p)) return 0;
    if (drives_high(p)) return 1;
    switch (p) {
        case 3:  return !sc.button;
        case 6:  return sc.acc_present ? !!(sl.reg[0x25] & 2) : 0;
        case 7:  return sc.usb;
        case 8: case 9: return 1;
        case 15: return rail_on();                          /* en l'air : R35 la tient à 1, sauf rail coupé (0,5 V par U10) */
        case 19: return (sc.usb && sc.charging && !drives_low(21)) ? 0 : 1;
        case 22: if (sc.sda_stuck || sl.sda_low) return 0; return sc.int_pullup_missing ? 0 : risen(p, US(0.2));
        case 23: return sc.int_pullup_missing ? 0 : risen(p, US(0.2));
        case 1: case 2:
            if (drives_low(15)) return 0;                   /* R33 et R34 tirent vers PORT_PU */
            if (!drives_high(15)) return rail_on() ? risen(p, US(25)) : 0;
            return risen(p, sc.port_pullup_broken ? US(25) : US(0.3));
        default: return 0;
    }
}

/* Registre figé au reset : GPIO8 et GPIO9 à 1 ; GPIO15 à 0, le rail étant coupé au reset ; MTMS et MTDI à 0. */
uint32_t mock_reg_read(uint32_t r) { (void)r; return 0x0c; }

/* ------------------------------------------------------ temps, système */
uint32_t esp_cpu_get_cycle_count(void) { cyc += 12; return (uint32_t)cyc; }
void esp_rom_delay_us(uint32_t us) { cyc += US(us); }
uint32_t esp_rom_get_cpu_ticks_per_us(void) { return 160; }
int64_t esp_timer_get_time(void) { return (int64_t)(cyc / 160); }
void vTaskDelay(TickType_t ms) { cyc += US(1000) * ms; }
static int a_mutex, a_sem;
SemaphoreHandle_t xSemaphoreCreateMutex(void) { return &a_mutex; }
SemaphoreHandle_t xSemaphoreCreateBinary(void) { return &a_sem; }
BaseType_t xSemaphoreTake(SemaphoreHandle_t s, TickType_t t) { (void)s; (void)t; return 1; }
BaseType_t xSemaphoreGive(SemaphoreHandle_t s) { (void)s; return 1; }
TaskHandle_t xSemaphoreGetMutexHolder(SemaphoreHandle_t s) { (void)s; return NULL; }
TaskHandle_t xTaskGetCurrentTaskHandle(void) { return (TaskHandle_t)1; }
static void (*task_fn)(void *);
BaseType_t xTaskCreate(void (*fn)(void *), const char *n, uint32_t st, void *a, int pr, TaskHandle_t *h) { (void)n; (void)a; (void)pr; (void)h; if (st < 4096) violation("pile trop petite"); task_fn = fn; return 1; }
void esp_log_level_set(const char *t, esp_log_level_t l) { (void)t; (void)l; }
vprintf_like_t esp_log_set_vprintf(vprintf_like_t f) { (void)f; return NULL; }
const char *esp_err_to_name(esp_err_t e) { return e ? "ESP_FAIL" : "ESP_OK"; }
esp_reset_reason_t esp_reset_reason(void) { return ESP_RST_POWERON; }
static void finish(void)
{
    check_port_at_rest("fin du scenario");
    printf("\n[simulation] fin : %d violation(s), %d trame(s) LED\n", violations, led_frames);
    exit(violations ? 1 : 0);
}
void esp_restart(void)
{
    if (rail_on()) violation("redemarrage convertisseur en marche");
    printf("\n[simulation] esp_restart\n");
    finish();
}
esp_err_t esp_read_mac(uint8_t *mac, esp_mac_type_t t) { (void)t; memcpy(mac, "\x40\x4c\xca\x12\x39\x6c", 6); return ESP_OK; }
void esp_chip_info(esp_chip_info_t *c) { memset(c, 0, sizeof *c); c->revision = (uint16_t)sc.chip_rev; }
esp_err_t esp_flash_get_physical_size(esp_flash_t *chip, uint32_t *size) { (void)chip; *size = 4 * 1024 * 1024; return ESP_OK; }

/* --------------------------------------------------------- UART et USB */
esp_err_t uart_driver_install(int n, int rx, int tx, int q, void *qh, int f) { (void)n; (void)rx; (void)tx; (void)q; (void)qh; (void)f; return ESP_OK; }
esp_err_t uart_param_config(int n, const uart_config_t *c) { (void)n; (void)c; return ESP_OK; }
esp_err_t uart_set_pin(int n, int tx, int rx, int rts, int cts) { (void)n; (void)rts; (void)cts; return tx == 16 && rx == 17 ? ESP_OK : ESP_FAIL; }
int uart_write_bytes(int n, const void *src, size_t size) { (void)n; (void)src; return (int)size; }
int uart_read_bytes(int n, void *buf, uint32_t len, TickType_t t) { (void)n; (void)buf; (void)len; (void)t; return 0; }
esp_err_t usb_serial_jtag_driver_install(usb_serial_jtag_driver_config_t *c) { (void)c; return ESP_OK; }
void usb_serial_jtag_vfs_use_driver(void) {}
bool usb_serial_jtag_is_connected(void) { return sc.usb; }
int usb_serial_jtag_write_bytes(const void *src, size_t size, TickType_t t)
{
    (void)t;
    const char *s = src;
    for (size_t i = 0; i < size; i++) if (s[i] != '\r') putchar(s[i]);
    fflush(stdout);
    return (int)size;
}

static char script[80][80];
static int script_n, script_i, script_pos, idle;
static const char *current_cmd = "";

static void scenario(const char *w)
{
    if (!strcmp(w, "batterie")) { sc.usb = false; sc.cc_mv = 3; sc.charging = false; }
    else if (!strcmp(w, "1500")) sc.cc_mv = 460;
    else if (!strcmp(w, "3000")) sc.cc_mv = 840;
    else if (!strcmp(w, "pleine")) sc.charging = false;
    else if (!strcmp(w, "4v2")) sc.vbat_pin_mv = 1254;             /* 4,20 V */
    else if (!strcmp(w, "vbat-basse")) sc.vbat_pin_mv = 836;       /* 2,80 V */
    else if (!strcmp(w, "3v3")) sc.vbat_pin_mv = 985;              /* 3,30 V */
    else if (!strcmp(w, "puce-v0.1")) sc.chip_rev = 1;
    else if (!strcmp(w, "r17-absente")) sc.vbat_pin_mv = 3200;     /* la broche monte vers VBAT */
    else if (!strcmp(w, "sans-acc")) sc.acc_present = false;
    else if (!strcmp(w, "sda-collee")) sc.sda_stuck = true;
    else if (!strcmp(w, "sans-rappel-interne")) sc.int_pullup_missing = true;
    else if (!strcmp(w, "rappels-port-absents")) sc.port_pullup_broken = true;
    else if (!strcmp(w, "sans-reseau")) sc.no_ap = true;
    else if (!strcmp(w, "sans-accuse")) sc.no_ack = true;
    else if (!strcmp(w, "bouton")) sc.button = true;
    else { printf("[simulation] scenario inconnu : %s\n", w); exit(2); }
    printf("    ~ [scenario : %s]\n", w);
}

int usb_serial_jtag_read_bytes(void *buf, uint32_t len, TickType_t t)
{
    (void)t;
    if (idle > 0) { idle--; return 0; }
    if (script_pos == 0) check_port_at_rest(commands_seen ? "apres une commande" : "au demarrage");
    while (script_i < script_n && script[script_i][0] == '@') {         /* directives du script */
        char *d = script[script_i++];
        if (!strncmp(d, "@attend ", 8)) { idle = atoi(d + 8) / 10; return 0; }
        if (!strncmp(d, "@scenario ", 10)) scenario(d + 10);
    }
    if (script_i >= script_n) finish();
    char *l = script[script_i];
    uint32_t n = 0;
    if (script_pos == 0) { commands_seen++; current_cmd = l; }
    while (n < len && l[script_pos]) ((char *)buf)[n++] = l[script_pos++];
    if (!l[script_pos] && n < len) { ((char *)buf)[n++] = '\r'; script_i++; script_pos = 0; idle = 3; }
    return (int)n;
}

/* ------------------------------------------------- ADC et température */
static adc_atten_t atten[8];
esp_err_t adc_oneshot_io_to_channel(int io, adc_unit_t *unit, adc_channel_t *ch) { if (io > 6) return ESP_FAIL; *unit = ADC_UNIT_1; *ch = io; return ESP_OK; }
esp_err_t adc_oneshot_new_unit(const adc_oneshot_unit_init_cfg_t *c, adc_oneshot_unit_handle_t *h) { (void)c; *h = &a_sem; return ESP_OK; }
esp_err_t adc_oneshot_config_channel(adc_oneshot_unit_handle_t h, adc_channel_t ch, const adc_oneshot_chan_cfg_t *c) { (void)h; atten[ch] = c->atten; return ESP_OK; }
esp_err_t adc_oneshot_read(adc_oneshot_unit_handle_t h, adc_channel_t ch, int *raw)
{
    (void)h;
    int mv = ch == 0 ? sc.vbat_pin_mv : ch == 4 ? sc.cc_mv : 0;
    /* La plage de 2,5 dB sature un peu au-dessus de 1,3 V. Une tension qui y tient ne doit pas être lue en 12 dB. */
    if (atten[ch] == ADC_ATTEN_DB_2_5 && mv > 1400) mv = 1400;
    if (atten[ch] == ADC_ATTEN_DB_12 && mv < 1300) violation("tension sous 1,3 V lue avec l'attenuation de 12 dB");
    if (atten[ch] != ADC_ATTEN_DB_2_5 && atten[ch] != ADC_ATTEN_DB_12) violation("attenuation inattendue");
    *raw = mv;
    return ESP_OK;
}
esp_err_t adc_cali_create_scheme_curve_fitting(const adc_cali_curve_fitting_config_t *c, adc_cali_handle_t *h) { (void)c; *h = &a_sem; return ESP_OK; }
esp_err_t adc_cali_raw_to_voltage(adc_cali_handle_t h, int raw, int *mv) { (void)h; *mv = raw; return ESP_OK; }
esp_err_t temperature_sensor_install(const temperature_sensor_config_t *c, temperature_sensor_handle_t *h) { (void)c; *h = &a_sem; return ESP_OK; }
esp_err_t temperature_sensor_enable(temperature_sensor_handle_t h) { (void)h; return ESP_OK; }
esp_err_t temperature_sensor_get_celsius(temperature_sensor_handle_t h, float *c) { (void)h; *c = 31.4f; return ESP_OK; }

/* ----------------------------------------------------------------- LED */
static uint8_t frame[15][3];
static int board_strip, ribbon_strip;                       /* deux pilotes : la carte, le ruban du port */
static uint8_t ribbon_frame[30], ribbon_sent[30];
static int ribbon_refreshes;

static void check_timings(const led_strip_config_t *c)
{
    if (c->led_model != LED_MODEL_CUSTOM || c->timings.t0h_ns < 250 || c->timings.t0h_ns > 400 || c->timings.t1h_ns < 650 || c->timings.t1h_ns > 1000
        || c->timings.t0l_ns < 800 || c->timings.t1l_ns < 200 || c->timings.reset_us <= 200) violation("temps de la LED hors fiche");
}

esp_err_t led_strip_new_rmt_device(const led_strip_config_t *c, const led_strip_rmt_config_t *r, led_strip_handle_t *h)
{
    (void)r;
    check_timings(c);
    if (c->strip_gpio_num == 18 && c->max_leds == 15) { *h = &board_strip; return ESP_OK; }
    if (c->strip_gpio_num == 2 && c->max_leds <= 30) {
        if (!rail_on() || !drives_low(15)) violation("ruban ouvert hors du mode ruban, ou convertisseur arrete");
        if (ribbon_owns_line2) violation("pilote du ruban ouvert deux fois");
        ribbon_owns_line2 = true; ribbon_refreshes = 0; memset(ribbon_frame, 0, sizeof ribbon_frame);
        *h = &ribbon_strip;
        return ESP_OK;
    }
    violation("reglage du pilote des LED");
    return ESP_FAIL;
}

esp_err_t led_strip_set_pixel(led_strip_handle_t h, uint32_t i, uint32_t r, uint32_t g, uint32_t b)
{
    if (h == &ribbon_strip) {
        if (i >= 30) { violation("LED hors ruban"); return ESP_FAIL; }
        if (r > 8 || g > 8 || b > 8) violation("niveau du ruban depasse");
        if (r != g || g != b) violation("ruban : blanc attendu");
        ribbon_frame[i] = (uint8_t)r;
        return ESP_OK;
    }
    if (i >= 15) { violation("LED hors chaine"); return ESP_FAIL; }
    if (r > 32 || g > 32 || b > 32) violation("plafond des LED depasse");
    frame[i][0] = (uint8_t)r; frame[i][1] = (uint8_t)g; frame[i][2] = (uint8_t)b;
    return ESP_OK;
}

esp_err_t led_strip_refresh(led_strip_handle_t h)
{
    int max = 0;
    if (commands_seen == 0) violation("trame LED envoyee avant toute commande");
    led_frames++;
    if (h == &ribbon_strip) {
        if (ribbon_refreshes && memcmp(ribbon_frame, ribbon_sent, sizeof ribbon_sent)) violation("ruban : deuxieme trame differente de la premiere");
        memcpy(ribbon_sent, ribbon_frame, sizeof ribbon_sent);
        ribbon_refreshes++;
        printf("    ~ ruban, envoi %d : ", ribbon_refreshes);
        for (int i = 0; i < 30; i++) putchar(ribbon_frame[i] ? 'W' : '.');
        printf("\n");
        return ESP_OK;
    }
    printf("    ~ LED : ");
    for (int i = 0; i < 15; i++) {
        uint8_t *p = frame[i];
        putchar(!p[0] && !p[1] && !p[2] ? '.' : p[0] && p[1] && p[2] ? 'W' : p[0] && !p[1] && !p[2] ? 'R' : p[1] && !p[0] && !p[2] ? 'G' : p[2] && !p[0] && !p[1] ? 'B' : '?');
        for (int k = 0; k < 3; k++) if (p[k] > max) max = p[k];
    }
    printf("  (niveau %d)\n", max);
    return ESP_OK;
}

esp_err_t led_strip_del(led_strip_handle_t h)
{
    if (h != &ribbon_strip) { violation("pilote des LED de la carte supprime"); return ESP_FAIL; }
    if (ribbon_refreshes != 2) violation("ruban : la trame n'est pas partie deux fois");
    ribbon_owns_line2 = false;
    pin[2].mode = GPIO_MODE_INPUT;                          /* le pilote rend la broche, en l'air */
    return ESP_OK;
}

/* --------------------------------------------------------------- radio */
static esp_now_send_cb_t now_cb;
static int wifi_started, now_count;
esp_err_t esp_netif_init(void) { return ESP_OK; }
esp_err_t esp_event_loop_create_default(void) { return ESP_OK; }
esp_err_t esp_wifi_init(const wifi_init_config_t *c) { (void)c; return ESP_OK; }
esp_err_t esp_wifi_set_storage(int s) { if (s != WIFI_STORAGE_RAM) violation("stockage Wi-Fi hors RAM"); return ESP_OK; }
esp_err_t esp_wifi_set_mode(int m) { (void)m; return ESP_OK; }
esp_err_t esp_wifi_start(void)
{
    /* Cellule seule sous 3,5 V : la radio ne doit démarrer que si on l'a forcée. */
    if (!sc.usb && sc.vbat_pin_mv * 670 / 200 < 3500 && !strstr(current_cmd, "force")) violation("radio lancee sur une cellule sous 3,5 V sans USB");
    wifi_started = 1; printf("    ~ radio : marche\n"); return ESP_OK;
}
esp_err_t esp_wifi_stop(void) { wifi_started = 0; printf("    ~ radio : arret\n"); return ESP_OK; }
esp_err_t esp_wifi_get_mac(int i, uint8_t *mac) { (void)i; return esp_read_mac(mac, ESP_MAC_WIFI_STA); }
esp_err_t esp_wifi_scan_start(const wifi_scan_config_t *c, bool block) { (void)c; (void)block; return wifi_started ? ESP_OK : ESP_FAIL; }
esp_err_t esp_wifi_scan_get_ap_num(uint16_t *n) { *n = sc.no_ap ? 0 : 3; return ESP_OK; }
esp_err_t esp_wifi_scan_get_ap_records(uint16_t *n, wifi_ap_record_t *ap)
{
    static const wifi_ap_record_t list[3] = {
        { .bssid = {1, 2, 3, 4, 5, 6}, .ssid = "Box-du-voisin", .primary = 13, .rssi = -40 },
        { .bssid = {1, 2, 3, 4, 5, 7}, .ssid = "Box-maison", .primary = 6, .rssi = -52 },
        { .bssid = {1, 2, 3, 4, 5, 8}, .ssid = "", .primary = 1, .rssi = -81 },
    };
    *n = sc.no_ap ? 0 : 3;
    memcpy(ap, list, sizeof(list[0]) * *n);
    return ESP_OK;
}
esp_err_t esp_wifi_set_channel(uint8_t p, int s) { (void)s; if (p != 6) violation("canal d'emission inattendu"); return ESP_OK; }
esp_err_t esp_now_init(void) { now_count = 0; return ESP_OK; }
esp_err_t esp_now_deinit(void) { return ESP_OK; }
esp_err_t esp_now_register_send_cb(esp_now_send_cb_t cb) { now_cb = cb; return ESP_OK; }
esp_err_t esp_now_unregister_send_cb(void) { now_cb = NULL; return ESP_OK; }
esp_err_t esp_now_add_peer(const esp_now_peer_info_t *p) { if (p->peer_addr[5] != 7) violation("destinataire inattendu"); return ESP_OK; }
esp_err_t esp_now_del_peer(const uint8_t *a) { (void)a; return ESP_OK; }
esp_err_t esp_now_send(const uint8_t *a, const uint8_t *d, size_t len) { (void)a; (void)d; (void)len; now_count++; if (now_cb) now_cb(NULL, sc.no_ack || now_count == 4 ? ESP_NOW_SEND_FAIL : ESP_NOW_SEND_SUCCESS); return ESP_OK; }

int main(int argc, char **argv)
{
    FILE *f = argc > 1 ? fopen(argv[1], "r") : stdin;
    if (!f) { perror(argv[1]); return 2; }
    while (script_n < 80 && fgets(script[script_n], sizeof script[0], f)) {
        script[script_n][strcspn(script[script_n], "\n")] = 0;
        if (script[script_n][0] && script[script_n][0] != '#') script_n++;
    }
    for (int p = 0; p < 32; p++) pin[p].mode = GPIO_MODE_INPUT;
    sl.reg[0x20] = 0x07;
    app_main();
    boot_done = true;
    /* État sûr de la révision 0.6, tel que app_main doit le laisser. */
    if (!(drives_low(5) && drives_low(20) && drives_low(14) && is_od(21) && pin[21].latch == 1
          && drives_low(15) && drives_low(1) && drives_low(2))) violation("etat sur incorrect apres app_main");
    printf("    ~ [apres app_main : BOOST_EN %s, VSEL %s, ISET %s, CHG_INH %s, PORT_PU %s, IO1 %s, IO2 %s]\n",
           pin[5].last, pin[20].last, pin[14].last, pin[21].last, pin[15].last, pin[1].last, pin[2].last);
    if (!task_fn) { printf("tache du banc absente\n"); return 2; }
    task_fn(NULL);
    return 0;
}
