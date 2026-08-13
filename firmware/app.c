/*
 * app.c - device state machine
 *
 * State transitions:
 *
 *   IDLE --UPLOAD_BEGIN--> RECEIVING --UPLOAD_END ok--> LOADED
 *   RECEIVING --error--> ERROR
 *   LOADED/COMPLETE --button or PLAY--> PLAYING
 *   PLAYING --waveform finished--> COMPLETE
 *   PLAYING --STOP--> LOADED
 *   any --CLEAR--> IDLE
 *
 * Button presses while PLAYING (or in any state other than
 * LOADED/COMPLETE) are ignored: the simpler deterministic behavior.
 */
#include "app.h"

#include <string.h>

#include "pico/stdlib.h"

#if PLG_HAS_CYW43_LED
#include "pico/cyw43_arch.h"
#endif

plg_app_t g_app;
uint32_t  g_play_buf[PLG_MAX_WORDS];

#if PLG_HAS_CYW43_LED
static bool s_led_ok = false;
#endif

static void led_set(bool on) {
#if PLG_HAS_CYW43_LED
    if (s_led_ok) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, on);
    }
#else
    (void)on;
#endif
}

void app_update_led(void) {
    /* LED on = a waveform is armed (LOADED / PLAYING / COMPLETE). */
    led_set(g_app.state == PLG_STATE_LOADED ||
            g_app.state == PLG_STATE_PLAYING ||
            g_app.state == PLG_STATE_COMPLETE);
}

void app_init(void) {
    memset(&g_app, 0, sizeof(g_app));
    g_app.state = PLG_STATE_IDLE;
    g_app.clkdiv = 1;
#if PLG_HAS_CYW43_LED
    s_led_ok = (cyw43_arch_init() == 0);
#endif
    playback_init();
    app_update_led();
}

void app_poll(void) {
    if (g_app.state == PLG_STATE_PLAYING && playback_is_done()) {
        g_app.state = PLG_STATE_COMPLETE;
        g_app.plays_completed++;
        app_update_led();
    }
}

bool app_request_play(void) {
    if (g_app.state != PLG_STATE_LOADED && g_app.state != PLG_STATE_COMPLETE) {
        return false;
    }
    if (!playback_start()) {
        return false;
    }
    g_app.state = PLG_STATE_PLAYING;
    app_update_led();
    return true;
}

bool app_request_stop(void) {
    if (g_app.state != PLG_STATE_PLAYING && g_app.state != PLG_STATE_LOADED &&
        g_app.state != PLG_STATE_COMPLETE) {
        return false;
    }
    playback_stop(); /* outputs return to the initial state */
    g_app.state = PLG_STATE_LOADED;
    app_update_led();
    return true;
}

bool app_clear(void) {
    playback_clear(); /* outputs all low */
    memset(&g_app.hdr, 0, sizeof(g_app.hdr));
    g_app.word_count = 0;
    g_app.clkdiv = 1;
    g_app.state = PLG_STATE_IDLE;
    app_update_led();
    return true;
}
