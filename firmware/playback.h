/*
 * playback.h - PIO + DMA waveform playback engine
 *
 * All hardware-specific playback code lives behind this interface.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* Waveform outputs: 8 consecutive GPIOs, GP0..GP7. */
#define PLG_PIN_BASE   0u
#define PLG_PIN_COUNT  8u

/* Playback buffer capacity in 32-bit PIO words (192 KiB). */
#define PLG_MAX_WORDS  49152u

void playback_init(void);

/* Arm a waveform: remember the word buffer, clock divider and initial
 * state, and drive the initial state on the pins. The engine must be
 * re-armed after the buffer contents change. */
void playback_arm(const uint32_t *words, uint32_t count,
                  uint8_t initial_state, uint16_t clkdiv);

/* Deterministic (re)start from the beginning: halts any running
 * playback, fully re-initialises SM + FIFO + DMA, restores the
 * initial output state, then starts the engine. */
bool playback_start(void);

/* Halt the engine and restore the armed initial output state. */
void playback_stop(void);

/* Halt the engine, forget the armed waveform, drive all outputs low. */
void playback_clear(void);

/* True once the armed waveform has fully played (DMA finished, FIFO
 * drained, SM stalled on 'out' with the final state on the pins). */
bool playback_is_done(void);
