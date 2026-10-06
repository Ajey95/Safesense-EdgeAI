idf_component_register(
    SRCS "main.c" "../../components/delivery/delivery_queue.c"
         "../../components/csi/csi_capture_esp_idf.c"
         "../../components/csi/csi_pipeline.c"
    INCLUDE_DIRS "." "../../components/delivery/include" "../../components/csi/include"
    REQUIRES rx_protocol nvs_flash esp_http_server esp_wifi esp_netif
             esp_event esp_timer freertos lwip espressif__cjson)
