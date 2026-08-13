cmake_minimum_required(VERSION 3.13)

# Target board: Raspberry Pi Pico W by default.
if (NOT DEFINED PICO_BOARD)
    set(PICO_BOARD pico_w CACHE STRING "Board type")
endif()

include(pico_sdk_import.cmake)

project(pico_logic_gen C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_subdirectory(firmware)
