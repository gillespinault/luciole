/* Une luciole simulée : le firmware tel quel (main.c est inclus ici), avec un
 * faux ESP-IDF dessous. Le banc (essai.py) charge cette bibliothèque une fois
 * par luciole, chaque copie ayant ses propres variables, fait avancer le
 * temps par pas de 10 ms et porte les trames de l'une à l'autre. */
#include <stdarg.h>
#include <stdlib.h>
#include "../main/main.c"
#undef printf
#undef read

static int64_t  sim_now;
static uint8_t  sim_mac[6];
static uint64_t sim_rng;
static int      sim_btn = 1, sim_verbose = 0;
static char     sim_outbuf[65536]; static int sim_outlen;
static char     sim_inbuf[1024];   static int sim_inlen, sim_inpos;
#define TXQ 64
static struct { int len; uint8_t data[250]; } sim_txq[TXQ]; static int sim_txh, sim_txn;
static uint8_t  sim_px[L2_STRIP_LEDS_MAX][3];
static esp_now_recv_cb_t sim_cb;
struct sim_strip { int ext; };
static struct sim_strip sim_strips[2]; static int sim_nstrips;

static void out_put(const char *fmt, va_list ap)
{
    int room = (int)sizeof(sim_outbuf) - sim_outlen - 1;
    if (room <= 0) return;
    int n = vsnprintf(sim_outbuf + sim_outlen, room, fmt, ap);
    sim_outlen += n < room ? n : room - 1;
}
int sim_printf(const char *fmt, ...) { va_list ap; va_start(ap, fmt); out_put(fmt, ap); va_end(ap); return 0; }
void sim_log(const char *fmt, ...) { if (!sim_verbose) return; va_list ap; va_start(ap, fmt); out_put(fmt, ap); va_end(ap); }
int sim_read(void *buf, int n) { if (sim_inpos >= sim_inlen) return -1; *(char *)buf = sim_inbuf[sim_inpos++]; return 1; }

const char *esp_err_to_name(esp_err_t e) { return "err"; }
void esp_log_level_set(const char *tag, esp_log_level_t l) {}
typedef struct { int n, size, head, count; uint8_t *buf; } sim_queue_t;
QueueHandle_t xQueueCreate(int n, int size) { sim_queue_t *q = calloc(1, sizeof(*q)); q->n = n; q->size = size; q->buf = malloc((size_t)n * size); return q; }
BaseType_t xQueueSend(QueueHandle_t h, const void *item, TickType_t t) { sim_queue_t *q = h; if (q->count == q->n) return 0; memcpy(q->buf + (size_t)((q->head + q->count) % q->n) * q->size, item, q->size); q->count++; return pdTRUE; }
BaseType_t xQueueReceive(QueueHandle_t h, void *item, TickType_t t) { sim_queue_t *q = h; if (!q->count) return 0; memcpy(item, q->buf + (size_t)q->head * q->size, q->size); q->head = (q->head + 1) % q->n; q->count--; return pdTRUE; }
void vTaskDelay(TickType_t t) {}
BaseType_t xTaskCreate(void (*fn)(void *), const char *name, uint32_t stack, void *arg, int prio, void *h) { return pdTRUE; }
int64_t esp_timer_get_time(void) { return sim_now; }
uint32_t esp_random(void) { sim_rng ^= sim_rng << 13; sim_rng ^= sim_rng >> 7; sim_rng ^= sim_rng << 17; return (uint32_t)(sim_rng >> 16); }
void esp_restart(void) {}
esp_err_t esp_netif_init(void) { return 0; }
esp_err_t esp_event_loop_create_default(void) { return 0; }
esp_err_t esp_wifi_init(const wifi_init_config_t *c) { return 0; }
esp_err_t esp_wifi_set_storage(int s) { return 0; }
esp_err_t esp_wifi_set_mode(int m) { return 0; }
esp_err_t esp_wifi_start(void) { return 0; }
esp_err_t esp_wifi_set_ps(int p) { return 0; }
esp_err_t esp_wifi_set_channel(int c, int second) { return 0; }
esp_err_t esp_wifi_set_max_tx_power(int8_t p) { return 0; }
esp_err_t esp_wifi_get_max_tx_power(int8_t *p) { *p = 80; return 0; }
esp_err_t esp_wifi_set_protocol(int ifx, int proto) { return 0; }
esp_err_t esp_wifi_get_mac(int ifx, uint8_t *mac) { memcpy(mac, sim_mac, 6); return 0; }
esp_err_t esp_now_init(void) { return 0; }
esp_err_t esp_now_register_recv_cb(esp_now_recv_cb_t cb) { sim_cb = cb; return 0; }
esp_err_t esp_now_add_peer(const esp_now_peer_info_t *p) { return 0; }
esp_err_t esp_now_set_peer_rate_config(const uint8_t *mac, esp_now_rate_config_t *r) { return 0; }
esp_err_t esp_now_send(const uint8_t *mac, const uint8_t *data, size_t len)
{
    if (sim_txn == TXQ || len > 250) return -1;
    int i = (sim_txh + sim_txn++) % TXQ; sim_txq[i].len = (int)len; memcpy(sim_txq[i].data, data, len); return 0;
}
esp_err_t nvs_flash_init(void) { return 0; }
esp_err_t nvs_flash_erase(void) { return 0; }
esp_err_t nvs_open(const char *ns, int mode, nvs_handle_t *h) { *h = 1; return 0; }
void nvs_close(nvs_handle_t h) {}
esp_err_t nvs_commit(nvs_handle_t h) { return 0; }
esp_err_t nvs_erase_key(nvs_handle_t h, const char *k) { return 0; }
esp_err_t nvs_get_u16(nvs_handle_t h, const char *k, uint16_t *v) { return ESP_ERR_NVS_NOT_FOUND; }
esp_err_t nvs_set_u16(nvs_handle_t h, const char *k, uint16_t v) { return 0; }
esp_err_t nvs_get_u32(nvs_handle_t h, const char *k, uint32_t *v) { return ESP_ERR_NVS_NOT_FOUND; }
esp_err_t nvs_set_u32(nvs_handle_t h, const char *k, uint32_t v) { return 0; }
esp_err_t nvs_get_str(nvs_handle_t h, const char *k, char *v, size_t *len) { return ESP_ERR_NVS_NOT_FOUND; }
esp_err_t nvs_set_str(nvs_handle_t h, const char *k, const char *v) { return 0; }
esp_err_t gpio_config(const gpio_config_t *c) { return 0; }
esp_err_t gpio_set_level(int gpio, uint32_t level) { return 0; }
int gpio_get_level(int gpio) { return gpio == L2_BUTTON_GPIO ? sim_btn : 1; }
esp_err_t usb_serial_jtag_driver_install(usb_serial_jtag_driver_config_t *c) { return 0; }
void usb_serial_jtag_vfs_use_driver(void) {}
esp_err_t led_strip_new_rmt_device(const led_strip_config_t *c, const led_strip_rmt_config_t *r, led_strip_handle_t *h)
{ sim_strips[sim_nstrips].ext = c->strip_gpio_num == L2_STRIP_GPIO; *h = &sim_strips[sim_nstrips++]; return 0; }
esp_err_t led_strip_clear(led_strip_handle_t h) { return 0; }
esp_err_t led_strip_set_pixel(led_strip_handle_t h, uint32_t i, uint32_t r, uint32_t g, uint32_t b)
{ if (h->ext && i < L2_STRIP_LEDS_MAX) { sim_px[i][0] = r; sim_px[i][1] = g; sim_px[i][2] = b; } return 0; }
esp_err_t led_strip_refresh(led_strip_handle_t h) { return 0; }

/* ---- ce que le banc appelle ---- */
typedef struct {
    int together, near, playing, leds;
    int scene, scene_set, arg, epoch, seed, known, master, expired, age_s;
    int mine, n, counts[L2_GAUGE_STEPS_MAX + 2];
    int team, table, crowd;
    uint8_t px[L2_STRIP_LEDS_MAX][3];
} sim_state_t;

void sim_boot(const uint8_t *mac, uint32_t seed, int64_t now, int verbose)
{
    memcpy(sim_mac, mac, 6); sim_rng = 0x9e3779b97f4a7c15ull ^ ((uint64_t)seed << 20) ^ seed; sim_now = now; sim_verbose = verbose;
    for (int i = 0; i < 8; i++) esp_random();
    app_main(); luciole_start();
}
void sim_step(int64_t now) { sim_now = now; if (sim_inpos >= sim_inlen) sim_inpos = sim_inlen = 0; luciole_step(now); }
void sim_rx(const uint8_t *mac, int rssi, const uint8_t *data, int len, int64_t now)
{
    wifi_pkt_rx_ctrl_t ctrl = { .rssi = rssi }; uint8_t src[6]; memcpy(src, mac, 6);
    esp_now_recv_info_t info = { .src_addr = src, .rx_ctrl = &ctrl };
    int64_t keep = sim_now; sim_now = now; if (sim_cb) sim_cb(&info, data, len); sim_now = keep;
}
int sim_tx(uint8_t *buf) { if (!sim_txn) return 0; int n = sim_txq[sim_txh].len; memcpy(buf, sim_txq[sim_txh].data, n); sim_txh = (sim_txh + 1) % TXQ; sim_txn--; return n; }
void sim_button(int level) { sim_btn = level; }
void sim_console(const char *line) { int n = (int)strlen(line); if (sim_inlen + n + 1 < (int)sizeof(sim_inbuf)) { memcpy(sim_inbuf + sim_inlen, line, n); sim_inlen += n; sim_inbuf[sim_inlen++] = '\n'; } }
int sim_out(char *buf, int max) { int n = sim_outlen < max - 1 ? sim_outlen : max - 1; memcpy(buf, sim_outbuf, n); buf[n] = 0; sim_outlen = 0; return n; }
void sim_get(sim_state_t *o)
{
    memset(o, 0, sizeof(*o));
    o->together = s_together; o->near = s_near_count; o->playing = animating(); o->leds = s_leds;
    o->scene = scene_type(); o->scene_set = S.type; o->arg = S.arg; o->epoch = S.epoch; o->seed = S.seed;
    o->known = S.known; o->master = S.master; o->expired = scene_expired(); o->age_s = (int)S.age_s;
    o->table = s_table_count; o->crowd = s_crowd;
    if (o->scene == L2_SCENE_TEAMS) { o->team = team_of(mac_id(s_mac), S.seed, teams_n()); o->mine = o->team; o->n = team_counts(S.seed, teams_n(), sim_now, o->counts); }
    else if (scene_votes()) { o->mine = s_my_vote; o->n = vote_tally(o->counts, o->scene == L2_SCENE_VOTE ? 3 : gauge_steps() + 2); }
    memcpy(o->px, sim_px, sizeof(o->px));
}
