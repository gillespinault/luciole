idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_driver_usb_serial_jtag esp_wifi nvs_flash esp_timer esp_event esp_netif
)
