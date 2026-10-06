idf_component_register(
    SRCS "main.c" "../../components/delivery/delivery_queue.c"
    INCLUDE_DIRS "." "../../components/delivery/include"
    REQUIRES bme680 gas_risk tx_protocol forecast bt_alert wifi_station nvs_flash
             esp_driver_i2c esp_driver_uart esp_http_client esp_wifi esp_timer freertos lwip)
