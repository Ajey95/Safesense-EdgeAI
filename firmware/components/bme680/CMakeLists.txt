idf_component_register(
    SRCS "bme680_driver.c" "bme680_esp_idf.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_i2c
)
