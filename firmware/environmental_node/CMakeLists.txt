cmake_minimum_required(VERSION 3.16)
set(COMPONENTS main)
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../components/bme280"
    "${CMAKE_CURRENT_LIST_DIR}/../components/delivery"
    "${CMAKE_CURRENT_LIST_DIR}/../components/gas_risk")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(safesense_environmental_node)
