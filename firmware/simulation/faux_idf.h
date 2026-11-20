/* Faux ESP-IDF pour dérouler main.c sur un ordinateur : les types et les
 * fonctions que le firmware utilise, rien de plus. Leur corps est dans sim.c.
 * Chaque en-tête d'ESP-IDF inclus par main.c renvoie ici (voir essai.py). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_NVS_NOT_FOUND 0x1102
#define ESP_ERR_NVS_NO_FREE_PAGES 0x110d
#define ESP_ERR_NVS_NEW_VERSION_FOUND 0x1110
#define ESP_ERROR_CHECK(x) ((void)(x))
const char *esp_err_to_name(esp_err_t e);

/* Console : ce que le firmware écrit est gardé pour le banc, ce qu'il lit vient du banc. */
int sim_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
int sim_read(void *buf, int n);
void sim_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
#define printf sim_printf
#define read(fd, buf, n) sim_read(buf, n)
static inline int sim_fcntl(void) { return 0; }
#define fcntl(...) sim_fcntl()
typedef enum { ESP_LOG_NONE, ESP_LOG_ERROR, ESP_LOG_WARN, ESP_LOG_INFO, ESP_LOG_DEBUG } esp_log_level_t;
#define ESP_LOGI(tag, fmt, ...) sim_log(fmt "\n", ##__VA_ARGS__)
#define ESP_LOGW(tag, fmt, ...) sim_log("W " fmt "\n", ##__VA_ARGS__)
#define ESP_LOGD(tag, fmt, ...) ((void)0)
void esp_log_level_set(const char *tag, esp_log_level_t l);

/* FreeRTOS */
typedef void *QueueHandle_t;
typedef uint32_t TickType_t;
typedef int BaseType_t;
#define pdTRUE 1
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))
QueueHandle_t xQueueCreate(int n, int size);
BaseType_t xQueueSend(QueueHandle_t q, const void *item, TickType_t t);
BaseType_t xQueueReceive(QueueHandle_t q, void *item, TickType_t t);
void vTaskDelay(TickType_t t);
BaseType_t xTaskCreate(void (*fn)(void *), const char *name, uint32_t stack, void *arg, int prio, void *h);

/* temps, hasard, système */
int64_t esp_timer_get_time(void);
uint32_t esp_random(void);
void esp_restart(void);

/* Wi-Fi et ESP-NOW */
typedef struct { int dummy; } wifi_init_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() { 0 }
enum { WIFI_STORAGE_RAM, WIFI_MODE_STA, WIFI_PS_NONE, WIFI_SECOND_CHAN_NONE, WIFI_IF_STA, WIFI_PROTOCOL_LR, WIFI_PHY_MODE_LR, WIFI_PHY_RATE_LORA_250K };
esp_err_t esp_netif_init(void);
esp_err_t esp_event_loop_create_default(void);
esp_err_t esp_wifi_init(const wifi_init_config_t *c);
esp_err_t esp_wifi_set_storage(int s);
esp_err_t esp_wifi_set_mode(int m);
esp_err_t esp_wifi_start(void);
esp_err_t esp_wifi_set_ps(int p);
esp_err_t esp_wifi_set_channel(int c, int second);
esp_err_t esp_wifi_set_max_tx_power(int8_t p);
esp_err_t esp_wifi_get_max_tx_power(int8_t *p);
esp_err_t esp_wifi_set_protocol(int ifx, int proto);
esp_err_t esp_wifi_get_mac(int ifx, uint8_t *mac);
typedef struct { int rssi; } wifi_pkt_rx_ctrl_t;
typedef struct { uint8_t *src_addr; uint8_t *des_addr; wifi_pkt_rx_ctrl_t *rx_ctrl; } esp_now_recv_info_t;
typedef struct { uint8_t peer_addr[6]; int channel, ifidx; bool encrypt; } esp_now_peer_info_t;
typedef struct { int phymode, rate; } esp_now_rate_config_t;
typedef void (*esp_now_recv_cb_t)(const esp_now_recv_info_t *info, const uint8_t *data, int len);
esp_err_t esp_now_init(void);
esp_err_t esp_now_register_recv_cb(esp_now_recv_cb_t cb);
esp_err_t esp_now_add_peer(const esp_now_peer_info_t *p);
esp_err_t esp_now_set_peer_rate_config(const uint8_t *mac, esp_now_rate_config_t *r);
esp_err_t esp_now_send(const uint8_t *mac, const uint8_t *data, size_t len);

/* NVS : vide, les réglages sont ceux de luciole.h */
typedef int nvs_handle_t;
enum { NVS_READONLY, NVS_READWRITE };
esp_err_t nvs_flash_init(void);
esp_err_t nvs_flash_erase(void);
esp_err_t nvs_open(const char *ns, int mode, nvs_handle_t *h);
void nvs_close(nvs_handle_t h);
esp_err_t nvs_commit(nvs_handle_t h);
esp_err_t nvs_erase_key(nvs_handle_t h, const char *k);
esp_err_t nvs_get_u16(nvs_handle_t h, const char *k, uint16_t *v);
esp_err_t nvs_set_u16(nvs_handle_t h, const char *k, uint16_t v);
esp_err_t nvs_get_u32(nvs_handle_t h, const char *k, uint32_t *v);
esp_err_t nvs_set_u32(nvs_handle_t h, const char *k, uint32_t v);
esp_err_t nvs_get_str(nvs_handle_t h, const char *k, char *v, size_t *len);
esp_err_t nvs_set_str(nvs_handle_t h, const char *k, const char *v);

/* GPIO, USB, ruban */
typedef enum { GPIO_MODE_INPUT = 1, GPIO_MODE_OUTPUT = 2 } gpio_mode_t;
#define GPIO_PULLUP_ENABLE 1
typedef struct { uint64_t pin_bit_mask; gpio_mode_t mode; int pull_up_en; } gpio_config_t;
esp_err_t gpio_config(const gpio_config_t *c);
esp_err_t gpio_set_level(int gpio, uint32_t level);
int gpio_get_level(int gpio);
typedef struct { uint32_t tx_buffer_size, rx_buffer_size; } usb_serial_jtag_driver_config_t;
esp_err_t usb_serial_jtag_driver_install(usb_serial_jtag_driver_config_t *c);
void usb_serial_jtag_vfs_use_driver(void);
typedef struct sim_strip *led_strip_handle_t;
enum { RMT_CLK_SRC_DEFAULT, LED_MODEL_WS2812, LED_MODEL_SK6812, LED_STRIP_COLOR_COMPONENT_FMT_GRB };
typedef struct { int clk_src; uint32_t resolution_hz; } led_strip_rmt_config_t;
typedef struct { int strip_gpio_num; uint32_t max_leds; int led_model, color_component_format; } led_strip_config_t;
esp_err_t led_strip_new_rmt_device(const led_strip_config_t *c, const led_strip_rmt_config_t *r, led_strip_handle_t *h);
esp_err_t led_strip_clear(led_strip_handle_t h);
esp_err_t led_strip_set_pixel(led_strip_handle_t h, uint32_t i, uint32_t r, uint32_t g, uint32_t b);
esp_err_t led_strip_refresh(led_strip_handle_t h);
