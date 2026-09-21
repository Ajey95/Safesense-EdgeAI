cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../components/bme680"
    "${CMAKE_CURRENT_LIST_DIR}/../components/gas_risk"
    "${CMAKE_CURRENT_LIST_DIR}/../components/node_protocol"
)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(safesense_node1_sensor_tx)
