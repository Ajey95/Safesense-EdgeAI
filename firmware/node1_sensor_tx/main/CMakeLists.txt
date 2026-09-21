idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES bme680 gas_risk node_protocol esp_wifi esp_netif esp_event nvs_flash driver lwip esp_timer
)
