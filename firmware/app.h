/*
 * app.h - device state machine and shared application state
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "playback.h"
#include "wave_format.h"

typedef enum {
    PLG_STATE_IDLE      = 0, /* no waveform loaded            */
    PLG_STATE_RECEIVING = 1, /* upload in progress            */
    PLG_STATE_LOADED    = 2, /* waveform armed, ready to play */
    PLG_STATE_PLAYING   = 3, /* PIO/DMA engine running        */
    PLG_STATE_COMPLETE  = 4, /* finished; ready to replay     */
    PLG_STATE_ERROR     = 5, /* last upload failed            */
} plg_state_t;

typedef struct {
    plg_state_t state;
    uint8_t     last_error;      /* protocol status code of last failure */
    plw_header_t hdr;            /* header of the armed waveform */
    uint32_t    word_count;      /* PIO words in g_play_buf */
    uint32_t    plays_completed; /* total completed playbacks since boot */
    uint16_t    clkdiv;          /* integer PIO clock divider in use */
} plg_app_t;

extern plg_app_t g_app;
extern uint32_t  g_play_buf[PLG_MAX_WORDS];

void app_init(void);
void app_poll(void);         /* completion detection + status LED */
bool app_request_play(void); /* from button or host; ignored unless LOADED/COMPLETE */
bool app_request_stop(void);
bool app_clear(void);
void app_update_led(void);
