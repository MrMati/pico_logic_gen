/*
 * button.c - debounced hardware replay button
 *
 * GP15 -> button -> GND, internal pull-up enabled, active low.
 * Debounce: the raw level must be stable for 10 ms before a press is
 * accepted. A press triggers app_request_play(), which only acts in
 * LOADED/COMPLETE, so presses during playback (or upload) are simply
 * ignored. The button never touches the PIO/DMA engine directly.
 */
#include "button.h"

#include "app.h"
#include "pico/stdlib.h"

#define DEBOUNCE_US 10000

void button_init(void) {
    gpio_init(PLG_BUTTON_PIN);
    gpio_set_dir(PLG_BUTTON_PIN, GPIO_IN);
    gpio_pull_up(PLG_BUTTON_PIN);
}

void button_poll(void) {
    static bool stable_pressed = false;
    static bool last_raw = false;
    static absolute_time_t t_change;

    bool raw = !gpio_get(PLG_BUTTON_PIN); /* active low */
    if (raw != last_raw) {
        last_raw = raw;
        t_change = get_absolute_time();
        return;
    }
    if (raw != stable_pressed &&
        absolute_time_diff_us(t_change, get_absolute_time()) >= DEBOUNCE_US) {
        stable_pressed = raw;
        if (stable_pressed) {
            (void)app_request_play();
        }
    }
}
