/*
 * Luciole² — firmware 6 : jauge de cohésion, couleur commune, souffle, ondulation.
 * Contrat radio v1 (luciole.h), nombre de LED en configuration, une table de
 * brochage par carte.
 * Règles locales uniquement : aucune unité n'est configurée ni appairée, tout
 * se découvre en écoutant. Le protocole ne transporte que phase, densité,
 * teinte, cohésion et ondes ; chaque kit les rend avec son propre matériel.
 * Pensé pour tenir en foule (milliers d'unités à portée radio) : balises
 * ralenties selon la taille de la foule, ondes diffusées de proche en proche
 * avec suppression, tout est borné.
 */
#include <string.h>
#include <stdbool.h>
#include <stdlib.h>
#include <math.h>
#include <fcntl.h>
#include <unistd.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_system.h"
#include "driver/gpio.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "led_strip.h"
#include "luciole.h"

static const char *TAG = "luciole";

static const uint8_t BROADCAST[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

/* ------------------------------------------------------------------ */
typedef struct {
    bool     used, in_range;
    uint8_t  mac[6];
    int64_t  last_seen_us;
    float    rssi_f;
    int8_t   last_rssi;
    uint8_t  level, hue, coh;
    int64_t  diffs[3];
    uint8_t  ndiffs;
} l2_neighbor_t;

typedef struct {
    uint8_t  mac[6];
    int8_t   rssi;
    int64_t  rx_us;
    uint8_t  len;
    uint8_t  data[sizeof(l2_beacon_t) > sizeof(l2_wave_t) ? sizeof(l2_beacon_t) : sizeof(l2_wave_t)];
} l2_rx_t;

/* Une onde connue : où j'en suis avec elle. */
typedef struct {
    bool     used, mine, played, relayed;
    uint8_t  origin[6];
    uint16_t id;
    uint8_t  hue, hop;      /* hop : plus petit saut entendu */
    uint8_t  copies;        /* copies entendues */
    float    prox;          /* proximité de l'émettrice la plus proche entendue */
    int64_t  t_first, play_at, relay_at;
} l2_wave_rec_t;

static l2_neighbor_t  s_neighbors[L2_MAX_NEIGHBORS];
static QueueHandle_t  s_rx_queue;
static led_strip_handle_t s_strip;
#if L2_STRIP_ENABLED
static led_strip_handle_t s_ext;
#endif
static uint8_t  s_mac[6];
static char     s_name[8];
static int      s_leds = L2_STRIP_LEDS_DEFAULT;   /* configuration NVS */
static uint8_t  s_strip_max = L2_STRIP_MAX_BRIGHTNESS;

static int64_t  s_offset_us = 0;
static uint32_t s_seq = 0;
static int64_t  s_last_beacon_tx = 0;
static float    s_heard_rate = 0;        /* balises/s entendues, lissé (journal) */
static int      s_heard_count = 0;
static int64_t  s_heard_window = 0;

/* Taille de la foule : émettrices distinctes sur deux fenêtres tuilées. */
static uint8_t  s_crowd_bits[2][L2_CROWD_BITS / 8];
static int      s_crowd_cur = 0;
static int64_t  s_crowd_window = 0;
static int      s_crowd = 0;

static float s_hue = 0, s_native_hue = 0;
static float s_coh = 0;                  /* cohésion : on naît seule */
static float s_rainbow_pos = 0;          /* défilement de l'arc-en-ciel, en tours */

/* Onde */
static l2_wave_rec_t s_waves[L2_WAVE_RECORDS];
static uint16_t s_wave_id = 0;
static int64_t  s_play_start = -1;
static float    s_play_hue = 0;
static int64_t  s_last_play = -100000000, s_last_emit = -100000000, s_last_relay = -100000000;

/* ------------------------------------------------------------------ */
static inline int64_t phase_at(int64_t now) { int64_t p = (now + s_offset_us) % L2_BAR_US; return p < 0 ? p + L2_BAR_US : p; }
static inline int64_t wrap_half(int64_t d) { while (d > L2_BAR_US / 2) d -= L2_BAR_US; while (d < -L2_BAR_US / 2) d += L2_BAR_US; return d; }
static inline float wrap_deg(float d) { while (d > 180) d -= 360; while (d < -180) d += 360; return d; }
static inline float norm_deg(float h) { while (h < 0) h += 360; while (h >= 360) h -= 360; return h; }
static inline float clamp01(float x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }
static inline float frand(void) { return (esp_random() & 0xffff) / 65535.0f; }
static inline bool mac_eq(const uint8_t *a, const uint8_t *b) { return memcmp(a, b, 6) == 0; }
static inline float proximity(float rssi) { return clamp01((rssi - L2_RSSI_FAR) / (float)(L2_RSSI_NEAR - L2_RSSI_FAR)); }

static inline uint64_t gpio_bit(int g) { return g >= 0 ? 1ULL << g : 0; }   /* -1 = broche absente */

static void hue_to_rgb(float h, float rgb[3])
{
    h = norm_deg(h) / 60.0f;
    int i = (int)h; float f = h - i, q = 1 - f, t = f;
    switch (i) {
        case 0:  rgb[0] = 1; rgb[1] = t; rgb[2] = 0; break;
        case 1:  rgb[0] = q; rgb[1] = 1; rgb[2] = 0; break;
        case 2:  rgb[0] = 0; rgb[1] = 1; rgb[2] = t; break;
        case 3:  rgb[0] = 0; rgb[1] = q; rgb[2] = 1; break;
        case 4:  rgb[0] = t; rgb[1] = 0; rgb[2] = 1; break;
        default: rgb[0] = 1; rgb[1] = 0; rgb[2] = q; break;
    }
}

/* ------------------------------------------------------------------ */
static void on_recv(const esp_now_recv_info_t *info, const uint8_t *data, int len)
{
    /* Contrat radio : version >= minimum, longueur >= taille connue, le reste
     * est ignoré. Un type inconnu est ignoré. */
    if (len < (int)sizeof(l2_hdr_t)) return;
    const l2_hdr_t *h = (const l2_hdr_t *)data;
    if (h->magic[0] != 'L' || h->magic[1] != '2' || h->version < L2_PROTO_MIN_VERSION) return;
    if (h->type == L2_MSG_BEACON)    { if (len < (int)sizeof(l2_beacon_t)) return; len = sizeof(l2_beacon_t); }
    else if (h->type == L2_MSG_WAVE) { if (len < (int)sizeof(l2_wave_t))   return; len = sizeof(l2_wave_t); }
    else return;
    l2_rx_t rx;
    memcpy(rx.mac, info->src_addr, 6);
    rx.rssi = info->rx_ctrl ? info->rx_ctrl->rssi : -100;
    rx.rx_us = esp_timer_get_time();
    rx.len = len;
    memcpy(rx.data, data, len);
    xQueueSend(s_rx_queue, &rx, 0);
}

/* ------------------------------------------------------------------ */
/* Foule : combien d'émettrices distinctes entendues récemment.          */
static void crowd_note(const uint8_t *mac)
{
    uint32_t h = ((uint32_t)mac[3] << 16) | ((uint32_t)mac[4] << 8) | mac[5];
    h ^= h >> 11; h *= 2654435761u; h >>= 32 - 11;      /* 11 bits = L2_CROWD_BITS */
    s_crowd_bits[s_crowd_cur][h >> 3] |= 1 << (h & 7);
}

static void crowd_tick(int64_t now)
{
    if (now - s_crowd_window < L2_CROWD_WINDOW_US) return;
    s_crowd_window = now;
    int n = 0;
    for (int i = 0; i < L2_CROWD_BITS / 8; i++) n += __builtin_popcount(s_crowd_bits[0][i] | s_crowd_bits[1][i]);
    s_crowd = n;
    s_crowd_cur ^= 1;
    memset(s_crowd_bits[s_crowd_cur], 0, sizeof(s_crowd_bits[0]));
}

/* En foule, on ralentit ses balises pour que le canal reste autour de la cible. */
static int64_t beacon_interval_us(void)
{
    int64_t us = (int64_t)((s_crowd + 1) / L2_BEACON_CHANNEL_RATE * 1000000.0f);
    if (us < L2_BEAT_US) us = L2_BEAT_US;
    if (us > (int64_t)L2_BEACON_MAX_MS * 1000) us = (int64_t)L2_BEACON_MAX_MS * 1000;
    return us;
}

static int64_t neighbor_ttl_us(void)
{
    int64_t us = L2_NEIGHBOR_TTL_INTERVALS * beacon_interval_us();
    return us > L2_NEIGHBOR_TTL_US ? us : L2_NEIGHBOR_TTL_US;
}

/* ------------------------------------------------------------------ */
/* Table bornée : si pleine, la nouvelle remplace la plus faible si elle est
 * nettement plus forte (hystérésis : en foule, sans elle, la table tournerait
 * à chaque balise). */
static l2_neighbor_t *neighbor_find_or_add(const uint8_t *mac, int8_t rssi, int64_t now)
{
    l2_neighbor_t *free_slot = NULL, *weakest = NULL;
    for (int i = 0; i < L2_MAX_NEIGHBORS; i++) {
        l2_neighbor_t *n = &s_neighbors[i];
        if (n->used && mac_eq(n->mac, mac)) return n;
        if (!n->used) { if (!free_slot) free_slot = n; }
        else if (!weakest || n->rssi_f < weakest->rssi_f) weakest = n;
    }
    if (!free_slot) {
        if (!weakest || weakest->rssi_f + L2_NEIGHBOR_REPLACE_DB > rssi) return NULL;
        free_slot = weakest;
    }
    memset(free_slot, 0, sizeof(*free_slot));
    free_slot->used = true;
    memcpy(free_slot->mac, mac, 6);
    free_slot->rssi_f = -100.0f;
    free_slot->last_seen_us = now;
    ESP_LOGD(TAG, "voisine %02x%02x apparue", mac[4], mac[5]);
    return free_slot;
}

static void handle_beacon(const l2_rx_t *rx)
{
    const l2_beacon_t *b = (const l2_beacon_t *)rx->data;
    s_heard_count++;
    crowd_note(rx->mac);
    l2_neighbor_t *n = neighbor_find_or_add(rx->mac, rx->rssi, rx->rx_us);
    if (!n) return;
    n->rssi_f = (n->rssi_f <= -99.0f) ? rx->rssi : n->rssi_f + L2_RSSI_ALPHA * (rx->rssi - n->rssi_f);
    n->last_rssi = rx->rssi;
    n->last_seen_us = rx->rx_us;
    n->level = b->density; n->hue = b->hue; n->coh = b->coh;
    if (!n->in_range && n->rssi_f >= L2_RSSI_ENTER) { n->in_range = true;  ESP_LOGD(TAG, "voisine %02x%02x a portee (%.0f dBm)", n->mac[4], n->mac[5], n->rssi_f); }
    else if (n->in_range && n->rssi_f <= L2_RSSI_LEAVE) { n->in_range = false; ESP_LOGD(TAG, "voisine %02x%02x trop loin (%.0f dBm)", n->mac[4], n->mac[5], n->rssi_f); }

    int64_t theirs = (int64_t)b->phase_us + L2_LINK_LATENCY_US;
    int64_t raw = wrap_half(theirs - phase_at(rx->rx_us));
    n->diffs[n->ndiffs % 3] = raw;
    if (n->ndiffs < 255) n->ndiffs++;
    int64_t diff = raw;
    if (n->ndiffs >= 3) {
        int64_t a = n->diffs[0], c = n->diffs[1], d = n->diffs[2];
        diff = (a > c) ? ((c > d) ? c : (a > d ? d : a)) : ((a > d) ? a : (c > d ? d : c));
    }
    if (diff > L2_PHASE_DEADBAND_US || diff < -L2_PHASE_DEADBAND_US)
        s_offset_us += (int64_t)(diff * L2_PHASE_GAIN);
}

/* ------------------------------------------------------------------ */
/* Ondes                                                               */
static l2_wave_rec_t *wave_find(const uint8_t *origin, uint16_t id)
{
    for (int i = 0; i < L2_WAVE_RECORDS; i++)
        if (s_waves[i].used && s_waves[i].id == id && mac_eq(s_waves[i].origin, origin)) return &s_waves[i];
    return NULL;
}

static l2_wave_rec_t *wave_add(const uint8_t *origin, uint16_t id, uint8_t hue, uint8_t hop, int64_t now)
{
    /* Une case libre (les ondes oubliées en libèrent), sinon la plus ancienne. */
    l2_wave_rec_t *slot = NULL, *oldest = &s_waves[0];
    for (int i = 0; i < L2_WAVE_RECORDS; i++) {
        l2_wave_rec_t *r = &s_waves[i];
        if (r->used && now - r->t_first > L2_WAVE_FORGET_US) r->used = false;
        if (!r->used) { slot = r; break; }
        if (r->t_first < oldest->t_first) oldest = r;
    }
    if (!slot) slot = oldest;
    memset(slot, 0, sizeof(*slot));
    slot->used = true;
    memcpy(slot->origin, origin, 6);
    slot->id = id; slot->hue = hue; slot->hop = hop; slot->t_first = now;
    slot->play_at = slot->relay_at = -1;
    return slot;
}

static void wave_send(const l2_wave_rec_t *r, uint8_t hop)
{
    l2_wave_t w = { .hdr = {{'L', '2'}, L2_PROTO_VERSION, L2_MSG_WAVE}, .id = r->id, .hop = hop, .hue = r->hue };
    memcpy(w.origin, r->origin, 6);
    esp_err_t err = esp_now_send(BROADCAST, (const uint8_t *)&w, sizeof(w));
    if (err != ESP_OK) ESP_LOGW(TAG, "esp_now_send onde: %s", esp_err_to_name(err));
}

/* Jouer une onde sur mon ruban : front qui traverse, trace de teinte. */
static void wave_play(l2_wave_rec_t *r, int64_t now)
{
    r->played = true;
    s_play_start = now;
    s_play_hue = r->hue * 360.0f / 255.0f;
    s_last_play = now;
    s_hue = norm_deg(s_hue + L2_HUE_WAVE_GAIN * wrap_deg(s_play_hue - s_hue));
}

/* Copie reçue. La première fixe l'heure de lecture et de rediffusion ; les
 * suivantes ne peuvent que les rapprocher (émettrice plus proche) et comptent
 * pour la suppression. */
static void handle_wave(const l2_rx_t *rx)
{
    const l2_wave_t *w = (const l2_wave_t *)rx->data;
    if (mac_eq(w->origin, s_mac)) return;
    float prox = proximity(rx->rssi);
    l2_wave_rec_t *r = wave_find(w->origin, w->id);
    if (!r) {
        r = wave_add(w->origin, w->id, w->hue, w->hop, rx->rx_us);
        ESP_LOGI(TAG, "onde %02x%02x#%u entendue de %02x%02x (saut %u, %d dBm)", w->origin[4], w->origin[5], w->id,
                 rx->mac[4], rx->mac[5], w->hop, rx->rssi);
    }
    if (r->copies < 255) r->copies++;
    if (w->hop < r->hop) r->hop = w->hop;
    if (prox > r->prox) r->prox = prox;
    int64_t play_at = rx->rx_us + (int64_t)((1 - prox) * L2_WAVE_SPREAD_US);
    if (!r->played && (r->play_at < 0 || play_at < r->play_at)) r->play_at = play_at;
    int64_t relay_at = r->t_first + L2_WAVE_SWEEP_US + (int64_t)((1 + r->prox) * L2_WAVE_SPREAD_US)
                       + (int64_t)(frand() * L2_WAVE_RELAY_JITTER_US);
    if (!r->relayed && (r->relay_at < 0 || relay_at < r->relay_at)) r->relay_at = relay_at;
}

static void wave_emit(int64_t now)
{
    if (now - s_last_emit < L2_WAVE_MIN_EMIT_US) return;
    s_last_emit = now;
    /* L'onde porte une couleur très différente de celle du moment : la teinte
     * opposée, à ±40° de hasard pour que deux appuis ne se ressemblent pas. */
    float wave_hue = norm_deg(s_hue + 180.0f + (frand() - 0.5f) * 80.0f);
    l2_wave_rec_t *r = wave_add(s_mac, ++s_wave_id, (uint8_t)(wave_hue * 255.0f / 360.0f), 0, now);
    r->mine = true; r->prox = 1;
    ESP_LOGI(TAG, "bouton : onde #%u emise, teinte %.0f -> %.0f", r->id, s_hue, wave_hue);
    wave_play(r, now);
    wave_send(r, 0); r->relayed = true;
}

/* Lectures et rediffusions dues. Lecture : une à la fois, la plus ancienne due
 * d'abord, abandonnée si trop en retard (foule qui appuie beaucoup). Rediffusion :
 * bornée en débit, supprimée si les voisines ont déjà couvert. */
static void wave_tick(int64_t now)
{
    l2_wave_rec_t *due = NULL;
    for (int i = 0; i < L2_WAVE_RECORDS; i++) {
        l2_wave_rec_t *r = &s_waves[i];
        if (!r->used) continue;
        if (!r->played && r->play_at >= 0 && now >= r->play_at) {
            if (now - r->play_at > L2_WAVE_LATE_US) { r->played = true; ESP_LOGI(TAG, "onde %02x%02x#%u : lecture abandonnee (retard)", r->origin[4], r->origin[5], r->id); }
            else if (!due || r->play_at < due->play_at) due = r;
        }
        if (!r->relayed && r->relay_at >= 0 && now >= r->relay_at) {
            if (r->copies >= L2_WAVE_SUPPRESS || r->hop + 1 > L2_WAVE_MAX_HOP) {
                r->relayed = true;
                ESP_LOGI(TAG, "onde %02x%02x#%u : pas rediffusee (%u copies, saut %u)", r->origin[4], r->origin[5], r->id, r->copies, r->hop);
            } else if (now - r->relay_at > L2_WAVE_LATE_US) {
                r->relayed = true;
            } else if (now - s_last_relay >= L2_WAVE_RELAY_MIN_US) {
                wave_send(r, r->hop + 1); r->relayed = true; s_last_relay = now;
                ESP_LOGI(TAG, "onde %02x%02x#%u : rediffusee (saut %u, %u copies)", r->origin[4], r->origin[5], r->id, r->hop + 1, r->copies);
            }
        }
    }
    if (due && now - s_last_play >= L2_WAVE_MIN_PLAY_US) {
        ESP_LOGI(TAG, "onde %02x%02x#%u : lecture (saut %u, proximite %.2f)", due->origin[4], due->origin[5], due->id, due->hop, due->prox);
        wave_play(due, now);
    }
}

/* ------------------------------------------------------------------ */
static int density_update(int64_t now)
{
    int count = 0; int64_t ttl = neighbor_ttl_us();
    for (int i = 0; i < L2_MAX_NEIGHBORS; i++) {
        l2_neighbor_t *n = &s_neighbors[i];
        if (!n->used) continue;
        if (now - n->last_seen_us > ttl) { ESP_LOGD(TAG, "voisine %02x%02x disparue", n->mac[4], n->mac[5]); n->used = false; continue; }
        if (n->in_range) count++;
    }
    return count;
}

/* À chaque trame : la couleur commune voyage et glisse vers celle des voisines ;
 * la cohésion vise la chaleur reçue (proximités cumulées) puis glisse vers celle
 * annoncée par les voisines. dt en secondes. */
static void regulate(float dt)
{
    float x = 0, y = 0, coh_sum = 0, miss = 1; int n_in = 0;
    for (int i = 0; i < L2_MAX_NEIGHBORS; i++) {
        l2_neighbor_t *n = &s_neighbors[i];
        if (!n->used || !n->in_range) continue;
        miss *= 1 - proximity(n->rssi_f);
        float a = n->hue * 360.0f / 255.0f * (float)M_PI / 180.0f;
        x += cosf(a); y += sinf(a); coh_sum += n->coh / 255.0f; n_in++;
    }
    float hue = s_hue + L2_HUE_DRIFT_DPS * dt;
    if (n_in == 0) {
        hue += (frand() - 0.5f) * 2 * L2_HUE_WANDER_DPS * dt;
        s_coh += dt / L2_COH_TAU_S * (0 - s_coh);
    } else {
        float mean_hue = atan2f(y, x) * 180.0f / (float)M_PI;
        hue += dt / L2_HUE_TAU_S * wrap_deg(mean_hue - s_hue);
        s_coh += dt / L2_COH_TAU_S * ((1 - miss) - s_coh) + dt / L2_COH_SOCIAL_TAU_S * (coh_sum / n_in - s_coh);
    }
    s_hue = norm_deg(hue);
    s_coh = clamp01(s_coh);
}

static void log_bar(int density, int level)
{
    char buf[200] = ""; int pos = 0;
    for (int i = 0; i < L2_MAX_NEIGHBORS && pos < (int)sizeof(buf) - 30; i++) {
        l2_neighbor_t *n = &s_neighbors[i];
        if (!n->used) continue;
        pos += snprintf(buf + pos, sizeof(buf) - pos, " %02x%02x:%ddBm/%.0f/%.2f%s", n->mac[4], n->mac[5], n->last_rssi,
                        n->hue * 360.0f / 255.0f, n->coh / 255.0f, n->in_range ? "" : "(loin)");
    }
    ESP_LOGI(TAG, "cycle | decalage=%lld ms | teinte=%.0f cohesion=%.2f | densite=%d niveau=%d | foule %d, balises %.1f/s, intervalle %.1f s |%s",
             (long long)(s_offset_us / 1000), s_hue, s_coh, density, level, s_crowd, s_heard_rate,
             beacon_interval_us() / 1000000.0f, buf[0] ? buf : " seule");
}

static void send_beacon(uint8_t level, int64_t now)
{
    l2_beacon_t b = {
        .hdr = {{'L', '2'}, L2_PROTO_VERSION, L2_MSG_BEACON},
        .density = level, .hue = (uint8_t)(s_hue * 255.0f / 360.0f), .coh = (uint8_t)(s_coh * 255.0f),
        .phase_us = (uint32_t)phase_at(now), .seq = s_seq++,
    };
    esp_err_t err = esp_now_send(BROADCAST, (const uint8_t *)&b, sizeof(b));
    if (err != ESP_OK) ESP_LOGW(TAG, "esp_now_send: %s", esp_err_to_name(err));
    s_last_beacon_tx = now;
}

/* ------------------------------------------------------------------ */
/* Configuration persistante : nombre de LED du ruban.                  */
static void strip_budget(void)
{
    /* Plafond de luminosité : L2_STRIP_MAX_BRIGHTNESS, ou moins si le ruban
     * tout blanc dépasserait le budget de courant. */
    int by_current = 255 * L2_STRIP_BUDGET_MA / (s_leds * L2_LED_FULL_MA);
    s_strip_max = by_current < L2_STRIP_MAX_BRIGHTNESS ? by_current : L2_STRIP_MAX_BRIGHTNESS;
}

static void config_load(void)
{
    nvs_handle_t h;
    if (nvs_open(L2_NVS_NAMESPACE, NVS_READONLY, &h) == ESP_OK) {
        uint16_t v = 0;
        if (nvs_get_u16(h, L2_NVS_KEY_LEDS, &v) == ESP_OK && v >= 1 && v <= L2_STRIP_LEDS_MAX) s_leds = v;
        nvs_close(h);
    }
    strip_budget();
}

static bool config_save_leds(int leds)
{
    nvs_handle_t h;
    if (nvs_open(L2_NVS_NAMESPACE, NVS_READWRITE, &h) != ESP_OK) return false;
    bool ok = nvs_set_u16(h, L2_NVS_KEY_LEDS, (uint16_t)leds) == ESP_OK && nvs_commit(h) == ESP_OK;
    nvs_close(h);
    return ok;
}

/* Commandes sur la console série (USB), une par ligne. Lecture non bloquante
 * de stdin dans la boucle de rendu. */
static void console_help(void)
{
    printf("commandes : leds N (1..%d, redemarre) | leds | onde | version | restart | help\n", L2_STRIP_LEDS_MAX);
}

static void console_exec(char *line, int64_t now)
{
    while (*line == ' ') line++;
    char *end = line + strlen(line);
    while (end > line && (end[-1] == ' ' || end[-1] == '\r')) *--end = 0;
    if (!*line) return;
    if (strncmp(line, "leds", 4) == 0) {
        char *arg = line + 4; while (*arg == ' ') arg++;
        if (*arg) {
            int n = atoi(arg);
            if (n < 1 || n > L2_STRIP_LEDS_MAX) { printf("leds : entre 1 et %d\n", L2_STRIP_LEDS_MAX); return; }
            if (!config_save_leds(n)) { printf("leds : ecriture NVS impossible\n"); return; }
            printf("leds=%d enregistre, redemarrage\n", n); fflush(stdout);
            vTaskDelay(pdMS_TO_TICKS(100)); esp_restart();
        }
        printf("leds=%d plafond=%d/255\n", s_leds, s_strip_max);
    } else if (strcmp(line, "onde") == 0) {
        wave_emit(now);
    } else if (strcmp(line, "version") == 0) {
        printf("luciole fw=%s carte=%s protocole=%d (min %d) mac=%s leds=%d\n", L2_FW_VERSION, L2_BOARD, L2_PROTO_VERSION, L2_PROTO_MIN_VERSION, s_name, s_leds);
    } else if (strcmp(line, "restart") == 0) {
        esp_restart();
    } else if (strcmp(line, "help") == 0 || strcmp(line, "?") == 0) {
        console_help();
    } else {
        printf("commande inconnue : %s\n", line); console_help();
    }
}

static void console_tick(int64_t now)
{
    static char buf[64]; static int len = 0;
    char c;
    while (read(STDIN_FILENO, &c, 1) == 1) {
        if (c == '\n') { buf[len] = 0; len = 0; console_exec(buf, now); }
        else if (len < (int)sizeof(buf) - 1) buf[len++] = c;
        else len = 0;
    }
}

/* ------------------------------------------------------------------ */
/* Rendu                                                                */
/* Calcule l'image du ruban en flottants 0..1, et la couleur de la LED intégrée. */
static void render(int64_t now, float dt, float px[L2_STRIP_LEDS_MAX][3])
{
    const int N = s_leds;
    memset(px, 0, sizeof(float) * N * 3);
    float coh = s_coh;

    /* Arc-en-ciel : dégradé linéaire sur toute la longueur, qui défile vers la droite. */
    s_rainbow_pos = fmodf(s_rainbow_pos + L2_RAINBOW_FLOW * dt, 1.0f);

    /* Zone unie : couleur commune, souffle sur la mesure commune, sommet au
     * temps commun, profondeur donnée par la cohésion. */
    float x = phase_at(now) / (float)L2_BAR_US;
    float breath = 0.5f + 0.5f * cosf(2 * (float)M_PI * x);
    float top = L2_SOLID_B + (L2_BREATH_MAX - L2_SOLID_B) * coh;
    float bottom = L2_SOLID_B + (L2_BREATH_MIN - L2_SOLID_B) * coh;
    float b_solid = bottom + (top - bottom) * breath;
    float solid[3]; hue_to_rgb(s_hue, solid);

    /* Jauge : la zone unie occupe `fill` pixels depuis la droite, frontière fondue sur un pixel. */
    float fill = coh * N;
    for (int p = 0; p < N; p++) {
        float from_right = N - 1 - p;                           /* 0 pour le pixel de droite */
        float w = clamp01(fill - from_right);                   /* part unie de ce pixel */
        float u = p / (float)N;
        float rain[3]; hue_to_rgb(360.0f * (u - s_rainbow_pos), rain);
        for (int k = 0; k < 3; k++) px[p][k] = rain[k] * L2_RAINBOW_B * (1 - w) + solid[k] * b_solid * w;
    }
    /* Onde : front blanc qui traverse, halo dans la couleur de l'onde, puis le
     * ruban entier reste dans cette couleur et s'éteint lentement avec des
     * paillettes. Pendant le passage, les autres couches s'effacent. */
    if (s_play_start >= 0) {
        int64_t t = now - s_play_start;
        float wrgb[3]; hue_to_rgb(s_play_hue, wrgb);
        float presence;
        if (t < L2_WAVE_SWEEP_US) presence = 1;
        else if (t < L2_WAVE_SWEEP_US + L2_WAVE_TRAIL_US) presence = 1 - (float)(t - L2_WAVE_SWEEP_US) / L2_WAVE_TRAIL_US;
        else { s_play_start = -1; return; }
        float keep = 1 - 0.9f * presence;
        for (int p = 0; p < N; p++) for (int k = 0; k < 3; k++) px[p][k] *= keep;
        if (t < L2_WAVE_SWEEP_US) {
            float head = t / (float)L2_WAVE_SWEEP_US * (N + 2) - 1.0f;
            for (int p = 0; p < N; p++) {
                float d = p - head;
                float core = expf(-d * d / 0.5f);                 /* front blanc, net */
                float halo = d > 0 ? expf(-d * d / 2.0f) : 0.9f;  /* devant : halo ; derrière : plein */
                for (int k = 0; k < 3; k++) px[p][k] += core + wrgb[k] * halo;
            }
        } else {
            float b = 0.9f * presence;
            for (int p = 0; p < N; p++) {
                float glint = (frand() < 0.03f * presence) ? 0.8f : 0;   /* paillettes blanches */
                for (int k = 0; k < 3; k++) px[p][k] += wrgb[k] * b + glint;
            }
        }
    }
}

static void show(float px[L2_STRIP_LEDS_MAX][3])
{
    /* Gamma : les LED sont linéaires en courant, l'œil ne l'est pas. Sans
     * correction, tout fondu paraît brutal et les faibles niveaux sont écrasés. */
    static uint8_t lut[256]; static bool lut_ok = false;
    if (!lut_ok) { for (int i = 0; i < 256; i++) lut[i] = (uint8_t)(powf(i / 255.0f, L2_GAMMA) * 255 + 0.5f); lut_ok = true; }
#if L2_STRIP_ENABLED
    float k = s_strip_max / 255.0f;
    for (int p = 0; p < s_leds; p++)
        led_strip_set_pixel(s_ext, p, lut[(int)(clamp01(px[p][0]) * 255)] * k, lut[(int)(clamp01(px[p][1]) * 255)] * k, lut[(int)(clamp01(px[p][2]) * 255)] * k);
    led_strip_refresh(s_ext);
#endif
    int c = s_leds / 2;
    float k2 = L2_MAX_BRIGHTNESS / 255.0f;
    led_strip_set_pixel(s_strip, 0, lut[(int)(clamp01(px[c][0]) * 255)] * k2, lut[(int)(clamp01(px[c][1]) * 255)] * k2, lut[(int)(clamp01(px[c][2]) * 255)] * k2);
    led_strip_refresh(s_strip);
}

#if L2_STRIP_ENABLED && L2_STRIP_TEST
static void strip_rainbow(int64_t now)
{
    float base = (now / 1000) % 5000 / 5000.0f * 360.0f, k = s_strip_max / 255.0f;
    for (int p = 0; p < s_leds; p++) { float c[3]; hue_to_rgb(base + p * 360.0f / s_leds, c);
        led_strip_set_pixel(s_ext, p, (uint8_t)(c[0] * 255 * k), (uint8_t)(c[1] * 255 * k), (uint8_t)(c[2] * 255 * k)); }
    led_strip_refresh(s_ext);
}
#endif

/* ------------------------------------------------------------------ */
static void luciole_task(void *arg)
{
    int last_beat = -1, level = 0, density = 0;
    int64_t tick_off = -1, send_due = -1;
    const float dt = L2_RENDER_MS / 1000.0f;
    float px[L2_STRIP_LEDS_MAX][3];
#if L2_BUTTON_ENABLED
    int btn_low_ms = 0; bool btn_pressed = false;
#endif
    s_heard_window = s_crowd_window = esp_timer_get_time();

    while (true) {
        int64_t now = esp_timer_get_time();

        l2_rx_t rx;
        while (xQueueReceive(s_rx_queue, &rx, 0) == pdTRUE) {
            const l2_hdr_t *h = (const l2_hdr_t *)rx.data;
            if (h->type == L2_MSG_BEACON) handle_beacon(&rx);
            else if (h->type == L2_MSG_WAVE) handle_wave(&rx);
        }
        wave_tick(now);
        crowd_tick(now);
        console_tick(now);

        /* Débit de balises entendu, fenêtre de 2 s (journal). */
        if (now - s_heard_window >= 2000000) {
            s_heard_rate = 0.5f * s_heard_rate + 0.5f * (s_heard_count / 2.0f);
            s_heard_count = 0; s_heard_window = now;
        }
#if L2_BUTTON_ENABLED
        if (gpio_get_level(L2_BUTTON_GPIO) == 0) {
            btn_low_ms += L2_RENDER_MS;
            if (!btn_pressed && btn_low_ms >= L2_BUTTON_DEBOUNCE_MS) { btn_pressed = true; wave_emit(now); }
        } else { btn_low_ms = 0; btn_pressed = false; }
#endif

        int beat = (int)(phase_at(now) / L2_BEAT_US);
        if (beat != last_beat) {
            last_beat = beat;
            if (beat == 0) {
                density = density_update(now);
                level = density > 4 ? 4 : density;
                log_bar(density, level);
            }
            if (L2_BLUE_LED_GPIO >= 0) gpio_set_level(L2_BLUE_LED_GPIO, 1);
            tick_off = now + L2_TICK_US;
            if (now - s_last_beacon_tx >= beacon_interval_us() - L2_BEAT_US / 2)
                send_due = now + (int64_t)(esp_random() % (L2_SEND_JITTER_MS + 1)) * 1000;
        }
        if (tick_off >= 0 && now >= tick_off) { if (L2_BLUE_LED_GPIO >= 0) gpio_set_level(L2_BLUE_LED_GPIO, 0); tick_off = -1; }
        if (send_due >= 0 && now >= send_due) { send_beacon((uint8_t)level, now); send_due = -1; }

        regulate(dt);
#if L2_STRIP_ENABLED && L2_STRIP_TEST
        strip_rainbow(now);
#else
        render(now, dt, px);
        show(px);
#endif
        vTaskDelay(pdMS_TO_TICKS(L2_RENDER_MS));
    }
}

/* ------------------------------------------------------------------ */
static void led_init(void)
{
    uint64_t outs = gpio_bit(L2_RGB_POWER_GPIO) | gpio_bit(L2_BLUE_LED_GPIO);
    if (outs) {
        gpio_config_t io = { .pin_bit_mask = outs, .mode = GPIO_MODE_OUTPUT };
        ESP_ERROR_CHECK(gpio_config(&io));
        if (L2_RGB_POWER_GPIO >= 0) gpio_set_level(L2_RGB_POWER_GPIO, 1);
        if (L2_BLUE_LED_GPIO >= 0)  gpio_set_level(L2_BLUE_LED_GPIO, 0);
    }
    gpio_config_t btn = { .pin_bit_mask = 1ULL << L2_BUTTON_GPIO, .mode = GPIO_MODE_INPUT, .pull_up_en = GPIO_PULLUP_ENABLE };
    ESP_ERROR_CHECK(gpio_config(&btn));

    led_strip_rmt_config_t rmt_cfg = { .clk_src = RMT_CLK_SRC_DEFAULT, .resolution_hz = 10 * 1000 * 1000 };
    led_strip_config_t strip_cfg = { .strip_gpio_num = L2_RGB_DATA_GPIO, .max_leds = 1, .led_model = LED_MODEL_WS2812,
                                     .color_component_format = LED_STRIP_COLOR_COMPONENT_FMT_GRB };
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_cfg, &rmt_cfg, &s_strip));
    led_strip_clear(s_strip);
#if L2_STRIP_ENABLED
    led_strip_config_t ext_cfg = { .strip_gpio_num = L2_STRIP_GPIO, .max_leds = s_leds, .led_model = LED_MODEL_SK6812,
                                   .color_component_format = LED_STRIP_COLOR_COMPONENT_FMT_GRB };
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&ext_cfg, &rmt_cfg, &s_ext));
    led_strip_clear(s_ext);
#endif
}

static void radio_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_channel(L2_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_max_tx_power(L2_TX_POWER));
#if L2_LONG_RANGE
    /* Longue portée seule : les trames ne sont lisibles que par des unités en LR. */
    ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_LR));
#endif
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(on_recv));
    esp_now_peer_info_t peer = { .channel = L2_WIFI_CHANNEL, .ifidx = WIFI_IF_STA, .encrypt = false };
    memcpy(peer.peer_addr, BROADCAST, 6);
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
#if L2_LONG_RANGE
    esp_now_rate_config_t rate = { .phymode = WIFI_PHY_MODE_LR, .rate = WIFI_PHY_RATE_LORA_250K };
    ESP_ERROR_CHECK(esp_now_set_peer_rate_config(BROADCAST, &rate));
#endif
    int8_t txp = 0; esp_wifi_get_max_tx_power(&txp);
    ESP_LOGI(TAG, "radio : canal %d, longue portee %s, puissance %d dBm", L2_WIFI_CHANNEL, L2_LONG_RANGE ? "oui" : "non", txp / 4);
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, s_mac));
    snprintf(s_name, sizeof(s_name), "%02x%02x", s_mac[4], s_mac[5]);
}

void app_main(void)
{
    s_rx_queue = xQueueCreate(64, sizeof(l2_rx_t));
    /* Console USB : avec le pilote, la lecture non bloquante de stdin marche
     * (sans lui, le VFS ne rend rien et l'hôte bloque à l'écriture) ; les
     * écritures restent bornées dans le temps quand aucun hôte n'écoute. */
    usb_serial_jtag_driver_config_t usj = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usj));
    usb_serial_jtag_vfs_use_driver();
    fcntl(STDIN_FILENO, F_SETFL, fcntl(STDIN_FILENO, F_GETFL) | O_NONBLOCK);
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) { ESP_ERROR_CHECK(nvs_flash_erase()); ESP_ERROR_CHECK(nvs_flash_init()); }
    config_load();
    led_init();
    radio_init();
    s_offset_us = esp_random() % L2_BAR_US;
    s_native_hue = (s_mac[3] * 97 + s_mac[4] * 31 + s_mac[5] * 151) % 360;
    s_hue = s_native_hue;
    ESP_LOGI(TAG, "Luciole² %s | fw %s | carte %s | protocole %d (min %d) | canal %d | %d temps x %d ms | teinte propre %.0f | ruban %d LED, plafond %d/255",
             s_name, L2_FW_VERSION, L2_BOARD, L2_PROTO_VERSION, L2_PROTO_MIN_VERSION, L2_WIFI_CHANNEL, L2_BEATS_PER_BAR, L2_BEAT_MS, s_native_hue, s_leds, s_strip_max);
    console_help();
    xTaskCreate(luciole_task, "luciole", 6144, NULL, 5, NULL);
}
