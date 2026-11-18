/* Faux ESP-IDF pour essayer le banc sur un ordinateur : les types et les prototypes
 * que main.c et soft_i2c.c utilisent, rien de plus. Les fonctions sont dans carte.c. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL (-1)
const char *esp_err_to_name(esp_err_t e);

/* FreeRTOS */
typedef void *SemaphoreHandle_t;
typedef void *TaskHandle_t;
typedef uint32_t TickType_t;
typedef int BaseType_t;
#define portMAX_DELAY 0xffffffffu
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))
SemaphoreHandle_t xSemaphoreCreateMutex(void);
SemaphoreHandle_t xSemaphoreCreateBinary(void);
BaseType_t xSemaphoreTake(SemaphoreHandle_t s, TickType_t t);
BaseType_t xSemaphoreGive(SemaphoreHandle_t s);
TaskHandle_t xSemaphoreGetMutexHolder(SemaphoreHandle_t s);
TaskHandle_t xTaskGetCurrentTaskHandle(void);
void vTaskDelay(TickType_t t);
BaseType_t xTaskCreate(void (*fn)(void *), const char *name, uint32_t stack, void *arg, int prio, TaskHandle_t *h);

/* journal, temps, système */
typedef int (*vprintf_like_t)(const char *, va_list);
typedef enum { ESP_LOG_NONE, ESP_LOG_ERROR, ESP_LOG_WARN, ESP_LOG_INFO } esp_log_level_t;
void esp_log_level_set(const char *tag, esp_log_level_t l);
vprintf_like_t esp_log_set_vprintf(vprintf_like_t f);
int64_t esp_timer_get_time(void);
typedef enum { ESP_RST_UNKNOWN, ESP_RST_POWERON, ESP_RST_EXT, ESP_RST_SW, ESP_RST_PANIC, ESP_RST_INT_WDT, ESP_RST_TASK_WDT,
               ESP_RST_WDT, ESP_RST_DEEPSLEEP, ESP_RST_BROWNOUT, ESP_RST_SDIO, ESP_RST_USB, ESP_RST_JTAG } esp_reset_reason_t;
esp_reset_reason_t esp_reset_reason(void);
void esp_restart(void);
typedef enum { ESP_MAC_WIFI_STA } esp_mac_type_t;
esp_err_t esp_read_mac(uint8_t *mac, esp_mac_type_t t);
uint32_t esp_cpu_get_cycle_count(void);
void esp_rom_delay_us(uint32_t us);
uint32_t esp_rom_get_cpu_ticks_per_us(void);
typedef struct { int model; uint32_t features; uint16_t revision; uint8_t cores; } esp_chip_info_t;
void esp_chip_info(esp_chip_info_t *c);
typedef struct esp_flash_t esp_flash_t;
esp_err_t esp_flash_get_physical_size(esp_flash_t *chip, uint32_t *size);

/* GPIO */
typedef enum { GPIO_MODE_INPUT = 1, GPIO_MODE_OUTPUT = 2, GPIO_MODE_INPUT_OUTPUT = 3, GPIO_MODE_OUTPUT_OD = 6, GPIO_MODE_INPUT_OUTPUT_OD = 7 } gpio_mode_t;
typedef struct { uint64_t pin_bit_mask; gpio_mode_t mode; int pull_up_en, pull_down_en, intr_type; } gpio_config_t;
esp_err_t gpio_config(const gpio_config_t *c);
esp_err_t gpio_set_level(int gpio, uint32_t level);
int gpio_get_level(int gpio);
esp_err_t gpio_set_direction(int gpio, gpio_mode_t mode);
esp_err_t gpio_pullup_en(int gpio);
#define REG_READ(r) mock_reg_read(r)
#define GPIO_STRAP_REG 0x38
uint32_t mock_reg_read(uint32_t r);
#define U0TXD_GPIO_NUM 16
#define U0RXD_GPIO_NUM 17

/* UART, USB */
typedef struct { int baud_rate, data_bits, parity, stop_bits, flow_ctrl, source_clk; } uart_config_t;
#define UART_NUM_0 0
#define UART_DATA_8_BITS 3
#define UART_PARITY_DISABLE 0
#define UART_STOP_BITS_1 1
#define UART_HW_FLOWCTRL_DISABLE 0
#define UART_SCLK_DEFAULT 0
#define UART_PIN_NO_CHANGE (-1)
esp_err_t uart_driver_install(int n, int rx, int tx, int q, void *qh, int flags);
esp_err_t uart_param_config(int n, const uart_config_t *c);
esp_err_t uart_set_pin(int n, int tx, int rx, int rts, int cts);
int uart_write_bytes(int n, const void *src, size_t size);
int uart_read_bytes(int n, void *buf, uint32_t len, TickType_t t);
typedef struct { uint32_t tx_buffer_size, rx_buffer_size; } usb_serial_jtag_driver_config_t;
esp_err_t usb_serial_jtag_driver_install(usb_serial_jtag_driver_config_t *c);
void usb_serial_jtag_vfs_use_driver(void);
int usb_serial_jtag_write_bytes(const void *src, size_t size, TickType_t t);
int usb_serial_jtag_read_bytes(void *buf, uint32_t len, TickType_t t);
bool usb_serial_jtag_is_connected(void);

/* ADC, température */
typedef void *adc_oneshot_unit_handle_t;
typedef void *adc_cali_handle_t;
typedef int adc_channel_t;
typedef enum { ADC_UNIT_1, ADC_UNIT_2 } adc_unit_t;
typedef enum { ADC_ATTEN_DB_0, ADC_ATTEN_DB_2_5, ADC_ATTEN_DB_6, ADC_ATTEN_DB_12 } adc_atten_t;
#define ADC_BITWIDTH_DEFAULT 0
typedef struct { adc_unit_t unit_id; int clk_src, ulp_mode; } adc_oneshot_unit_init_cfg_t;
typedef struct { adc_atten_t atten; int bitwidth; } adc_oneshot_chan_cfg_t;
typedef struct { adc_unit_t unit_id; adc_channel_t chan; adc_atten_t atten; int bitwidth; } adc_cali_curve_fitting_config_t;
esp_err_t adc_oneshot_io_to_channel(int io, adc_unit_t *unit, adc_channel_t *ch);
esp_err_t adc_oneshot_new_unit(const adc_oneshot_unit_init_cfg_t *c, adc_oneshot_unit_handle_t *h);
esp_err_t adc_oneshot_config_channel(adc_oneshot_unit_handle_t h, adc_channel_t ch, const adc_oneshot_chan_cfg_t *c);
esp_err_t adc_oneshot_read(adc_oneshot_unit_handle_t h, adc_channel_t ch, int *raw);
esp_err_t adc_cali_create_scheme_curve_fitting(const adc_cali_curve_fitting_config_t *c, adc_cali_handle_t *h);
esp_err_t adc_cali_raw_to_voltage(adc_cali_handle_t h, int raw, int *mv);
typedef void *temperature_sensor_handle_t;
typedef struct { int range_min, range_max; } temperature_sensor_config_t;
#define TEMPERATURE_SENSOR_CONFIG_DEFAULT(a, b) { .range_min = a, .range_max = b }
esp_err_t temperature_sensor_install(const temperature_sensor_config_t *c, temperature_sensor_handle_t *h);
esp_err_t temperature_sensor_enable(temperature_sensor_handle_t h);
esp_err_t temperature_sensor_get_celsius(temperature_sensor_handle_t h, float *c);

/* LED */
typedef void *led_strip_handle_t;
typedef enum { LED_MODEL_WS2812, LED_MODEL_SK6812, LED_MODEL_CUSTOM } led_model_t;
typedef struct { uint32_t t0h_ns, t1h_ns, t0l_ns, t1l_ns, reset_us; } led_strip_timings_t;
typedef int led_color_component_format_t;
#define LED_STRIP_COLOR_COMPONENT_FMT_GRB 1
typedef struct { int strip_gpio_num; uint32_t max_leds; led_model_t led_model; led_color_component_format_t color_component_format; led_strip_timings_t timings; } led_strip_config_t;
#define RMT_CLK_SRC_DEFAULT 0
typedef struct { int clk_src; uint32_t resolution_hz; } led_strip_rmt_config_t;
esp_err_t led_strip_new_rmt_device(const led_strip_config_t *c, const led_strip_rmt_config_t *r, led_strip_handle_t *h);
esp_err_t led_strip_set_pixel(led_strip_handle_t h, uint32_t i, uint32_t r, uint32_t g, uint32_t b);
esp_err_t led_strip_refresh(led_strip_handle_t h);
esp_err_t led_strip_del(led_strip_handle_t h);

/* Radio */
typedef struct { int dummy; } wifi_init_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() { 0 }
typedef struct { bool show_hidden; } wifi_scan_config_t;
typedef struct { uint8_t bssid[6]; uint8_t ssid[33]; uint8_t primary; int8_t rssi; } wifi_ap_record_t;
#define WIFI_STORAGE_RAM 1
#define WIFI_MODE_STA 1
#define WIFI_IF_STA 0
#define WIFI_SECOND_CHAN_NONE 0
esp_err_t esp_netif_init(void);
esp_err_t esp_event_loop_create_default(void);
esp_err_t esp_wifi_init(const wifi_init_config_t *c);
esp_err_t esp_wifi_set_storage(int s);
esp_err_t esp_wifi_set_mode(int m);
esp_err_t esp_wifi_start(void);
esp_err_t esp_wifi_stop(void);
esp_err_t esp_wifi_get_mac(int ifx, uint8_t *mac);
esp_err_t esp_wifi_scan_start(const wifi_scan_config_t *c, bool block);
esp_err_t esp_wifi_scan_get_ap_num(uint16_t *n);
esp_err_t esp_wifi_scan_get_ap_records(uint16_t *n, wifi_ap_record_t *ap);
esp_err_t esp_wifi_set_channel(uint8_t primary, int second);
typedef struct { int dummy; } esp_now_send_info_t;
typedef enum { ESP_NOW_SEND_SUCCESS, ESP_NOW_SEND_FAIL } esp_now_send_status_t;
typedef void (*esp_now_send_cb_t)(const esp_now_send_info_t *info, esp_now_send_status_t status);
typedef struct { uint8_t peer_addr[6]; uint8_t channel; int ifidx; bool encrypt; } esp_now_peer_info_t;
esp_err_t esp_now_init(void);
esp_err_t esp_now_deinit(void);
esp_err_t esp_now_register_send_cb(esp_now_send_cb_t cb);
esp_err_t esp_now_unregister_send_cb(void);
esp_err_t esp_now_add_peer(const esp_now_peer_info_t *p);
esp_err_t esp_now_del_peer(const uint8_t *addr);
esp_err_t esp_now_send(const uint8_t *addr, const uint8_t *data, size_t len);
