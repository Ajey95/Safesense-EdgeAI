idf_component_register(
    SRCS "delivery_queue.c" "delivery_ack.c" "delivery_nvs.c" "delivery_mqtt.c"
    INCLUDE_DIRS "include"
    REQUIRES nvs_flash mqtt
)
