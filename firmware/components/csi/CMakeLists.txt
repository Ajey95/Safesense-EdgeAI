if(CONFIG_SAFESENSE_CSI_TFLM_MODEL)
    idf_component_register(
        SRCS "csi_pipeline.c" "csi_capture_esp_idf.c" "csi_model_tflm.cpp"
        INCLUDE_DIRS "include" "model"
        REQUIRES esp_wifi esp_timer freertos fusion esp-tflite-micro
    )
else()
    idf_component_register(
        SRCS "csi_pipeline.c" "csi_capture_esp_idf.c" "csi_model_stub.c"
        INCLUDE_DIRS "include"
        REQUIRES esp_wifi esp_timer freertos fusion
    )
endif()
