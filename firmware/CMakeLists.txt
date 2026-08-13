add_executable(plg_firmware
    main.c
    app.c
    playback.c
    protocol.c
    button.c
    crc32.c
)

pico_generate_pio_header(plg_firmware ${CMAKE_CURRENT_LIST_DIR}/waveplay.pio)

target_link_libraries(plg_firmware
    pico_stdlib
    hardware_pio
    hardware_dma
    hardware_clocks
)

if (PICO_CYW43_SUPPORTED)
    # Pico W: status LED lives on the wireless chip.
    target_link_libraries(plg_firmware pico_cyw43_arch_none)
    target_compile_definitions(plg_firmware PRIVATE PLG_HAS_CYW43_LED=1)
else()
    target_compile_definitions(plg_firmware PRIVATE PLG_HAS_CYW43_LED=0)
endif()

pico_enable_stdio_usb(plg_firmware 1)
pico_enable_stdio_uart(plg_firmware 0)

pico_add_extra_outputs(plg_firmware)
