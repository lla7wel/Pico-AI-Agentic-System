// status.h — RGB LED + buzzer status codes.
#pragma once
#include <Arduino.h>

enum StatusState {
  ST_BOOT,        // startup (LED off / handled by boot anim)
  ST_IDLE,        // ready: solid dim green
  ST_RECORDING,   // solid red
  ST_PROCESSING,  // blinking blue
  ST_RESPONSE,    // brief green flash (transient)
  ST_ERROR,       // blinking amber/orange
};

void status_begin();

// Set the current visual state. Also fires the one-shot tone associated with
// entering that state (start beep, stop beep, chime, error buzz).
void status_set(StatusState s);

// Call frequently from the main loop to drive non-blocking blink animation.
void status_tick();
