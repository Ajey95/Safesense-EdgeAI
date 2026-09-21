idf_component_register(
    SRCS "safety_output.c" "safety_output_esp_idf.c"
    INCLUDE_DIRS "include"
    REQUIRES driver fusion
)
