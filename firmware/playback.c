/*
 * playback.c - PIO + DMA waveform playback engine
 *
 * Architecture (see docs/TIMING.md for the cycle accounting proof):
 *
 *   g_play_buf (SRAM, 32-bit words)
 *        |
 *        |  DMA channel, 32-bit transfers, read increment,
 *        |  paced by the PIO SM's TX DREQ, high bus priority
 *        v
 *   PIO0 SM0 TX FIFO (joined, 8 words deep)
 *        |
 *        v
 *   waveplay program -> GP0..GP7
 *
 * After playback_start() returns, the CPU is not involved in timing at
 * all: no interrupts are used and the DMA transfer covers the entire
 * waveform in one shot. USB traffic and CPU load cannot affect edge
 * placement.
 */
#include "playback.h"

#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"

#include "waveplay.pio.h"

#define WAVE_PIO pio0
#define WAVE_SM  0u

static uint            s_offset;
static int             s_dma_chan = -1;
static const uint32_t *s_words;
static uint32_t        s_count;
static uint8_t         s_initial;
static uint16_t        s_clkdiv = 1; /* 25 MHz sample clock */

/* (Re)initialise the state machine: program counter at program start,
 * FIFOs cleared, shift counters reset, clock divider applied. */
static void sm_configure(void) {
    pio_sm_config c = waveplay_program_get_default_config(s_offset);
    sm_config_set_out_pins(&c, PLG_PIN_BASE, PLG_PIN_COUNT);
    /* Shift right, autopull at 32 bits: 'out x, 24' takes bits [23:0]
     * (delay), 'out pins, 8' takes bits [31:24] (state). */
    sm_config_set_out_shift(&c, true, true, 32);
    sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
    sm_config_set_clkdiv_int_frac(&c, s_clkdiv, 0); /* integer only: no jitter */
    pio_sm_init(WAVE_PIO, WAVE_SM, s_offset, &c);
}

/* Drive an arbitrary 8-bit state on the pins while the SM is disabled,
 * using the SM's own OUT path so all 8 pins change from one
 * instruction. Leaves the SM cleanly reset at the program start. */
static void drive_state_now(uint8_t state) {
    pio_sm_clear_fifos(WAVE_PIO, WAVE_SM);
    pio_sm_put(WAVE_PIO, WAVE_SM, state);
    pio_sm_exec(WAVE_PIO, WAVE_SM, pio_encode_pull(false, true));
    pio_sm_exec(WAVE_PIO, WAVE_SM, pio_encode_out(pio_pins, 8));
    pio_sm_restart(WAVE_PIO, WAVE_SM); /* reset shift counters + stall flags */
    pio_sm_clear_fifos(WAVE_PIO, WAVE_SM);
    pio_sm_exec(WAVE_PIO, WAVE_SM, pio_encode_jmp(s_offset));
}

/* Stop the SM and DMA and leave no stale FIFO data behind. */
static void engine_halt(void) {
    pio_sm_set_enabled(WAVE_PIO, WAVE_SM, false);
    if (s_dma_chan >= 0) {
        dma_channel_abort((uint)s_dma_chan);
    }
    pio_sm_clear_fifos(WAVE_PIO, WAVE_SM);
    pio_sm_restart(WAVE_PIO, WAVE_SM);
}

void playback_init(void) {
    s_offset = pio_add_program(WAVE_PIO, &waveplay_program);
    s_dma_chan = (int)dma_claim_unused_channel(true);

    for (uint i = 0; i < PLG_PIN_COUNT; i++) {
        pio_gpio_init(WAVE_PIO, PLG_PIN_BASE + i);
        gpio_set_slew_rate(PLG_PIN_BASE + i, GPIO_SLEW_RATE_FAST);
    }
    pio_sm_set_consecutive_pindirs(WAVE_PIO, WAVE_SM,
                                   PLG_PIN_BASE, PLG_PIN_COUNT, true);
    sm_configure();
    drive_state_now(0x00); /* idle state: all outputs low */
}

void playback_arm(const uint32_t *words, uint32_t count,
                  uint8_t initial_state, uint16_t clkdiv) {
    engine_halt();
    s_words = words;
    s_count = count;
    s_initial = initial_state;
    s_clkdiv = (clkdiv == 0) ? 1 : clkdiv;
    sm_configure();
    drive_state_now(s_initial);
}

bool playback_start(void) {
    if (s_words == NULL || s_count == 0) {
        return false;
    }

    /* 1-4: stop engine, reset DMA, reset PIO SM/FIFO, restore the
     * initial output state. */
    engine_halt();
    sm_configure();
    drive_state_now(s_initial);

    /* 5: restart DMA over the full, unchanged word buffer. */
    dma_channel_config dc = dma_channel_get_default_config((uint)s_dma_chan);
    channel_config_set_transfer_data_size(&dc, DMA_SIZE_32);
    channel_config_set_read_increment(&dc, true);
    channel_config_set_write_increment(&dc, false);
    channel_config_set_dreq(&dc, pio_get_dreq(WAVE_PIO, WAVE_SM, true));
    channel_config_set_high_priority(&dc, true);
    dma_channel_configure((uint)s_dma_chan, &dc,
                          &WAVE_PIO->txf[WAVE_SM], /* write: TX FIFO   */
                          s_words,                 /* read: word buffer */
                          s_count, true);

    /* Let DMA pre-fill the 8-deep joined TX FIFO so the SM never
     * stalls at startup (a startup stall would only delay t=0, never
     * inter-edge spacing, but pre-filling keeps t=0 well defined). */
    while (!pio_sm_is_tx_fifo_full(WAVE_PIO, WAVE_SM) &&
           dma_channel_is_busy((uint)s_dma_chan)) {
        tight_loop_contents();
    }

    /* 6: start PIO. Clear the TXSTALL debug flag first; it becoming
     * set again (with DMA done and FIFO empty) marks completion. */
    WAVE_PIO->fdebug = 1u << (PIO_FDEBUG_TXSTALL_LSB + WAVE_SM);
    pio_sm_clkdiv_restart(WAVE_PIO, WAVE_SM);
    pio_sm_set_enabled(WAVE_PIO, WAVE_SM, true);
    return true;
}

void playback_stop(void) {
    engine_halt();
    sm_configure();
    drive_state_now((s_words != NULL) ? s_initial : 0x00);
}

void playback_clear(void) {
    engine_halt();
    s_words = NULL;
    s_count = 0;
    s_initial = 0;
    s_clkdiv = 1;
    sm_configure();
    drive_state_now(0x00);
}

bool playback_is_done(void) {
    if (s_dma_chan < 0 || dma_channel_is_busy((uint)s_dma_chan)) {
        return false;
    }
    if (!pio_sm_is_tx_fifo_empty(WAVE_PIO, WAVE_SM)) {
        return false;
    }
    /* SM stalled on 'out x, 24' with an empty FIFO: the final 'out
     * pins' of the last event has already executed. */
    return (WAVE_PIO->fdebug & (1u << (PIO_FDEBUG_TXSTALL_LSB + WAVE_SM))) != 0;
}
