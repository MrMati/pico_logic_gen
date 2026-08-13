/*
 * wave_format.h - .plw binary waveform format (shared with host tool)
 *
 * Hardware-independent definitions. See docs/FORMAT.md.
 */
#pragma once

#include <stdint.h>

#define PLW_MAGIC           0x31574C50u /* "PLW1" when read as LE u32 */
#define PLW_VERSION         1u
#define PLW_CHANNELS        8u
#define PLW_BASE_CLOCK_HZ   25000000u
#define PLW_MAX_CLKDIV      65535u
/* Maximum hold time (in samples) encodable in a single PIO word.
 * Longer host-side delays are split into multiple no-change events
 * at upload time. */
#define PLW_MAX_WORD_DELAY  (1u << 24)

typedef struct __attribute__((packed)) {
    uint32_t magic;           /* PLW_MAGIC */
    uint16_t version;         /* PLW_VERSION */
    uint16_t flags;           /* must be 0 */
    uint32_t sample_clock_hz; /* must divide 25 MHz, divider <= 65535 */
    uint8_t  channel_count;   /* must be 8 */
    uint8_t  initial_state;   /* output state at t = 0 */
    uint16_t reserved;        /* must be 0 */
    uint32_t event_count;     /* number of 8-byte events, >= 1 */
    uint32_t payload_crc32;   /* CRC-32 (IEEE) of the event payload */
} plw_header_t;

typedef struct __attribute__((packed)) {
    uint32_t delay; /* hold current state for this many samples, >= 1 */
    uint32_t state; /* then drive this state; bits [7:0] used */
} plw_event_t;

_Static_assert(sizeof(plw_header_t) == 24, "plw header must be 24 bytes");
_Static_assert(sizeof(plw_event_t) == 8, "plw event must be 8 bytes");
