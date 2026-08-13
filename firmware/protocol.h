/*
 * protocol.h - USB (CDC) host protocol
 *
 * Framed binary protocol over the USB CDC serial port. USB is used
 * only for control and upload; it plays no part in waveform timing.
 * See docs/PROTOCOL.md.
 */
#pragma once

#include <stdint.h>

#define PLG_SYNC_REQ  0xA5u
#define PLG_SYNC_RESP 0x5Au

#define PLG_FW_VERSION 0x0001u

#define PLG_MAX_PAYLOAD 2048u

/* Commands */
enum {
    PLG_CMD_ID           = 0x01,
    PLG_CMD_UPLOAD_BEGIN = 0x10,
    PLG_CMD_UPLOAD_DATA  = 0x11,
    PLG_CMD_UPLOAD_END   = 0x12,
    PLG_CMD_STATUS       = 0x20,
    PLG_CMD_PLAY         = 0x21,
    PLG_CMD_STOP         = 0x22,
    PLG_CMD_CLEAR        = 0x23,
};

/* Response status codes */
enum {
    PLG_OK              = 0,
    PLG_ERR_BAD_CMD     = 1,
    PLG_ERR_BAD_CRC     = 2,  /* frame CRC mismatch */
    PLG_ERR_BAD_STATE   = 3,  /* command not valid in current state */
    PLG_ERR_BAD_FORMAT  = 4,  /* header magic/version/fields invalid */
    PLG_ERR_TOO_BIG     = 5,  /* waveform exceeds playback buffer */
    PLG_ERR_BAD_RATE    = 6,  /* unsupported sample_clock_hz */
    PLG_ERR_UPLOAD_SEQ  = 7,  /* DATA/END out of order or wrong size */
    PLG_ERR_BAD_LENGTH  = 8,  /* frame payload length invalid */
    PLG_ERR_PAYLOAD_CRC = 9,  /* uploaded payload CRC mismatch */
    PLG_ERR_BAD_DELAY   = 10, /* event with delay == 0 or state > 0xFF */
};

void protocol_init(void);
void protocol_poll(void);
