/*
 * main.c - pico_logic_gen firmware entry point
 *
 * RP2040 deterministic logic waveform generator ("reverse logic
 * analyzer"). The main loop only handles control-plane work: USB
 * protocol frames, the debounced replay button, completion detection
 * and the status LED. Waveform timing is produced exclusively by
 * PIO0 SM0 fed by DMA; nothing in this loop can perturb it.
 *
 * Clocking: the system clock is pinned to 125 MHz (from the 12 MHz
 * crystal via PLL: 1500 MHz / 6 / 2). The PIO runs at
 * sysclk / clkdiv, and one waveform sample is 5 PIO cycles, so
 * sample_clock_hz = 25 MHz / clkdiv with an exact integer divider.
 * Cycle-to-cycle timing is deterministic by construction; absolute
 * frequency accuracy equals the board crystal accuracy (~ +/-30 ppm
 * on a Pico W).
 */
#include "hardware/clocks.h"
#include "pico/stdio_usb.h"
#include "pico/stdlib.h"

#include "app.h"
#include "button.h"
#include "protocol.h"

int main(void) {
    /* Pin the system clock explicitly: 125 MHz / 1 / 5 = 25 MHz base. */
    set_sys_clock_khz(125000, true);

    stdio_usb_init();
    /* Binary protocol: never translate LF <-> CRLF. */
    stdio_set_translate_crlf(&stdio_usb, false);

    app_init();
    button_init();
    protocol_init();

    for (;;) {
        protocol_poll();
        button_poll();
        app_poll();
    }
}
