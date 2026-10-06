cmake_minimum_required(VERSION 3.16)
set(COMPONENTS main)
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../components/csi"
    "${CMAKE_CURRENT_LIST_DIR}/../components/fusion"
    "${CMAKE_CURRENT_LIST_DIR}/../components/wifi_station")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(safesense_csi_receiver)
