idf_component_register(
    SRCS "main.c" "soft_i2c.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_gpio esp_driver_uart esp_driver_usb_serial_jtag esp_driver_tsens
             esp_adc esp_wifi esp_event esp_netif esp_timer spi_flash
)
