idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES csi fusion safety_output node_protocol delivery wifi_station esp_wifi esp_timer lwip
)
