/*
 * protocol.c - USB CDC framed binary protocol + upload decoder
 *
 * Request frame:  0xA5 | cmd(1) | len(2, LE) | payload | crc32(4, LE)
 * Response frame: 0x5A | status(1) | len(2, LE) | payload | crc32(4, LE)
 * The CRC covers cmd/status + len + payload.
 *
 * Upload path: the host streams plw_event_t records (8 bytes each).
 * They are converted to 32-bit PIO words *during upload* (never during
 * playback): delays larger than PLW_MAX_WORD_DELAY are split into
 * no-change filler words, and each word is packed as
 * (state << 24) | (delay_samples - 1).
 */
#include "protocol.h"

#include <string.h>

#include "pico/stdio.h"
#include "pico/stdio_usb.h"
#include "pico/stdlib.h"

#include "app.h"
#include "crc32.h"
#include "wave_format.h"

/* ---------------------------------------------------------------- */
/* Frame parser state                                                */

typedef enum {
    RX_SYNC,
    RX_CMD,
    RX_LEN0,
    RX_LEN1,
    RX_PAYLOAD,
    RX_CRC,
} rx_phase_t;

static rx_phase_t s_phase = RX_SYNC;
static uint8_t    s_cmd;
static uint16_t   s_len;
static uint16_t   s_pos;
static uint8_t    s_payload[PLG_MAX_PAYLOAD];
static uint8_t    s_crc_buf[4];
static absolute_time_t s_last_byte;

#define FRAME_TIMEOUT_US 500000

/* ---------------------------------------------------------------- */
/* Upload decoder state                                              */

static uint32_t s_up_events_expected;
static uint32_t s_up_events_received;
static uint32_t s_up_crc;
static uint32_t s_up_words;
static uint8_t  s_up_cur_state;
static uint8_t  s_up_initial;
static uint16_t s_up_clkdiv;
static uint32_t s_up_sample_hz;
static uint8_t  s_up_partial[sizeof(plw_event_t)];
static uint32_t s_up_partial_len;
static plw_header_t s_up_hdr;

/* ---------------------------------------------------------------- */

static void send_response(uint8_t status, const void *payload, uint16_t len) {
    uint8_t head[4] = { PLG_SYNC_RESP, status,
                        (uint8_t)(len & 0xFF), (uint8_t)(len >> 8) };
    uint32_t crc = crc32_update(crc32_init(), &head[1], 3);
    if (len > 0) {
        crc = crc32_update(crc, payload, len);
    }
    for (int i = 0; i < 4; i++) putchar_raw(head[i]);
    for (uint16_t i = 0; i < len; i++) putchar_raw(((const uint8_t *)payload)[i]);
    for (int i = 0; i < 4; i++) putchar_raw((int)((crc >> (8 * i)) & 0xFF));
    stdio_flush();
}

static void upload_fail(uint8_t err) {
    g_app.state = PLG_STATE_ERROR;
    g_app.last_error = err;
    app_update_led();
    send_response(err, NULL, 0);
}

/* Append one PIO word; returns false when the buffer is full. */
static bool emit_word(uint32_t delay_samples, uint8_t state) {
    if (s_up_words >= PLG_MAX_WORDS) {
        return false;
    }
    g_play_buf[s_up_words++] =
        ((uint32_t)state << 24) | ((delay_samples - 1u) & 0x00FFFFFFu);
    return true;
}

/* Convert one host event into one or more PIO words. */
static uint8_t convert_event(uint32_t delay, uint32_t state) {
    if (delay == 0 || state > 0xFFu) {
        return PLG_ERR_BAD_DELAY;
    }
    while (delay > PLW_MAX_WORD_DELAY) {
        /* Filler: hold the current state for a full chunk (no change). */
        if (!emit_word(PLW_MAX_WORD_DELAY, s_up_cur_state)) {
            return PLG_ERR_TOO_BIG;
        }
        delay -= PLW_MAX_WORD_DELAY;
    }
    if (!emit_word(delay, (uint8_t)state)) {
        return PLG_ERR_TOO_BIG;
    }
    s_up_cur_state = (uint8_t)state;
    return PLG_OK;
}

static void handle_upload_begin(const uint8_t *payload, uint16_t len) {
    if (g_app.state == PLG_STATE_PLAYING || g_app.state == PLG_STATE_RECEIVING) {
        send_response(PLG_ERR_BAD_STATE, NULL, 0);
        return;
    }
    if (len != sizeof(plw_header_t)) {
        send_response(PLG_ERR_BAD_LENGTH, NULL, 0);
        return;
    }
    plw_header_t hdr;
    memcpy(&hdr, payload, sizeof(hdr));
    if (hdr.magic != PLW_MAGIC || hdr.version != PLW_VERSION ||
        hdr.flags != 0 || hdr.reserved != 0 ||
        hdr.channel_count != PLW_CHANNELS || hdr.event_count == 0) {
        upload_fail(PLG_ERR_BAD_FORMAT);
        return;
    }
    if (hdr.sample_clock_hz == 0 ||
        (PLW_BASE_CLOCK_HZ % hdr.sample_clock_hz) != 0 ||
        (PLW_BASE_CLOCK_HZ / hdr.sample_clock_hz) > PLW_MAX_CLKDIV) {
        upload_fail(PLG_ERR_BAD_RATE);
        return;
    }
    if (hdr.event_count > PLG_MAX_WORDS) {
        /* Each event needs at least one word; fail early when it can
         * never fit. Splitting may still overflow later. */
        upload_fail(PLG_ERR_TOO_BIG);
        return;
    }

    /* Replace the current waveform: unarm the engine now. */
    (void)app_clear();

    s_up_hdr = hdr;
    s_up_events_expected = hdr.event_count;
    s_up_events_received = 0;
    s_up_crc = crc32_init();
    s_up_words = 0;
    s_up_initial = hdr.initial_state;
    s_up_cur_state = hdr.initial_state;
    s_up_clkdiv = (uint16_t)(PLW_BASE_CLOCK_HZ / hdr.sample_clock_hz);
    s_up_sample_hz = hdr.sample_clock_hz;
    s_up_partial_len = 0;

    g_app.state = PLG_STATE_RECEIVING;
    app_update_led();
    send_response(PLG_OK, NULL, 0);
}

static void handle_upload_data(const uint8_t *payload, uint16_t len) {
    if (g_app.state != PLG_STATE_RECEIVING) {
        send_response(PLG_ERR_BAD_STATE, NULL, 0);
        return;
    }
    s_up_crc = crc32_update(s_up_crc, payload, len);

    uint16_t idx = 0;
    while (idx < len) {
        uint32_t need = sizeof(plw_event_t) - s_up_partial_len;
        uint32_t take = (len - idx < need) ? (uint32_t)(len - idx) : need;
        memcpy(&s_up_partial[s_up_partial_len], &payload[idx], take);
        s_up_partial_len += take;
        idx += (uint16_t)take;

        if (s_up_partial_len == sizeof(plw_event_t)) {
            s_up_partial_len = 0;
            if (s_up_events_received >= s_up_events_expected) {
                upload_fail(PLG_ERR_UPLOAD_SEQ);
                return;
            }
            plw_event_t ev;
            memcpy(&ev, s_up_partial, sizeof(ev));
            uint8_t rc = convert_event(ev.delay, ev.state);
            if (rc != PLG_OK) {
                upload_fail(rc);
                return;
            }
            s_up_events_received++;
        }
    }
    send_response(PLG_OK, NULL, 0);
}

static void handle_upload_end(void) {
    if (g_app.state != PLG_STATE_RECEIVING) {
        send_response(PLG_ERR_BAD_STATE, NULL, 0);
        return;
    }
    if (s_up_partial_len != 0 ||
        s_up_events_received != s_up_events_expected) {
        upload_fail(PLG_ERR_UPLOAD_SEQ);
        return;
    }
    if (s_up_crc != s_up_hdr.payload_crc32) {
        upload_fail(PLG_ERR_PAYLOAD_CRC);
        return;
    }

    playback_arm(g_play_buf, s_up_words, s_up_initial, s_up_clkdiv);
    g_app.hdr = s_up_hdr;
    g_app.word_count = s_up_words;
    g_app.clkdiv = s_up_clkdiv;
    g_app.state = PLG_STATE_LOADED;
    g_app.last_error = PLG_OK;
    app_update_led();
    send_response(PLG_OK, NULL, 0);
}

static void handle_id(void) {
    uint8_t p[16];
    p[0] = 'P'; p[1] = 'L'; p[2] = 'G'; p[3] = '1';
    p[4] = (uint8_t)(PLG_FW_VERSION & 0xFF);
    p[5] = (uint8_t)(PLG_FW_VERSION >> 8);
    p[6] = PLW_CHANNELS;
    p[7] = 0;
    uint32_t maxw = PLG_MAX_WORDS;
    uint32_t base = PLW_BASE_CLOCK_HZ;
    memcpy(&p[8], &maxw, 4);
    memcpy(&p[12], &base, 4);
    send_response(PLG_OK, p, sizeof(p));
}

static void handle_status(void) {
    uint8_t p[24];
    p[0] = (uint8_t)g_app.state;
    p[1] = g_app.last_error;
    p[2] = PLW_CHANNELS;
    p[3] = g_app.hdr.initial_state;
    memcpy(&p[4], &g_app.hdr.event_count, 4);
    memcpy(&p[8], &g_app.word_count, 4);
    memcpy(&p[12], &g_app.hdr.sample_clock_hz, 4);
    memcpy(&p[16], &g_app.plays_completed, 4);
    memcpy(&p[20], &g_app.hdr.payload_crc32, 4);
    send_response(PLG_OK, p, sizeof(p));
}

static void handle_frame(void) {
    switch (s_cmd) {
    case PLG_CMD_ID:
        handle_id();
        break;
    case PLG_CMD_UPLOAD_BEGIN:
        handle_upload_begin(s_payload, s_len);
        break;
    case PLG_CMD_UPLOAD_DATA:
        handle_upload_data(s_payload, s_len);
        break;
    case PLG_CMD_UPLOAD_END:
        handle_upload_end();
        break;
    case PLG_CMD_STATUS:
        handle_status();
        break;
    case PLG_CMD_PLAY:
        send_response(app_request_play() ? PLG_OK : PLG_ERR_BAD_STATE, NULL, 0);
        break;
    case PLG_CMD_STOP:
        send_response(app_request_stop() ? PLG_OK : PLG_ERR_BAD_STATE, NULL, 0);
        break;
    case PLG_CMD_CLEAR:
        send_response(app_clear() ? PLG_OK : PLG_ERR_BAD_STATE, NULL, 0);
        break;
    default:
        send_response(PLG_ERR_BAD_CMD, NULL, 0);
        break;
    }
}

void protocol_init(void) {
    s_phase = RX_SYNC;
}

void protocol_poll(void) {
    /* Drop a stalled partial frame so the parser cannot wedge. */
    if (s_phase != RX_SYNC &&
        absolute_time_diff_us(s_last_byte, get_absolute_time()) >
            FRAME_TIMEOUT_US) {
        s_phase = RX_SYNC;
    }

    for (;;) {
        int c = getchar_timeout_us(0);
        if (c == PICO_ERROR_TIMEOUT) {
            return;
        }
        uint8_t b = (uint8_t)c;
        s_last_byte = get_absolute_time();

        switch (s_phase) {
        case RX_SYNC:
            if (b == PLG_SYNC_REQ) {
                s_phase = RX_CMD;
            }
            break;
        case RX_CMD:
            s_cmd = b;
            s_phase = RX_LEN0;
            break;
        case RX_LEN0:
            s_len = b;
            s_phase = RX_LEN1;
            break;
        case RX_LEN1:
            s_len |= (uint16_t)b << 8;
            if (s_len > PLG_MAX_PAYLOAD) {
                s_phase = RX_SYNC;
                send_response(PLG_ERR_BAD_LENGTH, NULL, 0);
                break;
            }
            s_pos = 0;
            s_phase = (s_len > 0) ? RX_PAYLOAD : RX_CRC;
            break;
        case RX_PAYLOAD:
            s_payload[s_pos++] = b;
            if (s_pos == s_len) {
                s_pos = 0;
                s_phase = RX_CRC;
            }
            break;
        case RX_CRC:
            s_crc_buf[s_pos++] = b;
            if (s_pos == 4) {
                s_phase = RX_SYNC;
                uint8_t hdr[3] = { s_cmd, (uint8_t)(s_len & 0xFF),
                                   (uint8_t)(s_len >> 8) };
                uint32_t crc = crc32_update(crc32_init(), hdr, 3);
                crc = crc32_update(crc, s_payload, s_len);
                uint32_t rx_crc = (uint32_t)s_crc_buf[0] |
                                  ((uint32_t)s_crc_buf[1] << 8) |
                                  ((uint32_t)s_crc_buf[2] << 16) |
                                  ((uint32_t)s_crc_buf[3] << 24);
                if (crc != rx_crc) {
                    send_response(PLG_ERR_BAD_CRC, NULL, 0);
                } else {
                    handle_frame();
                }
            }
            break;
        }
    }
}
