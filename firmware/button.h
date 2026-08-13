#pragma once

/* Replay button: GP15 to GND, internal pull-up, active low. */
#define PLG_BUTTON_PIN 15u

void button_init(void);
void button_poll(void);
