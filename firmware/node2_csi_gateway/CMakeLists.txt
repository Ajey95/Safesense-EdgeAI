cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../components/csi"
    "${CMAKE_CURRENT_LIST_DIR}/../components/delivery"
    "${CMAKE_CURRENT_LIST_DIR}/../components/fusion"
    "${CMAKE_CURRENT_LIST_DIR}/../components/gas_risk"
    "${CMAKE_CURRENT_LIST_DIR}/../components/node_protocol"
    "${CMAKE_CURRENT_LIST_DIR}/../components/safety_output"
    "${CMAKE_CURRENT_LIST_DIR}/../components/wifi_station"
)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(safesense_node2_csi_gateway)
