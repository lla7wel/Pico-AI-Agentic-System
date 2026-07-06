// display.h — green-phosphor terminal UI on the 480x320 ST7796 TFT.
#pragma once
#include <Arduino.h>

void display_begin();

// Retro boot sequence (blocking, a few seconds). Call once in setup() after
// the subsystems it reports on are up; pass their results so the lines are
// honest rather than cosmetic.
void display_boot_sequence(bool mic_ok, bool wifi_ok, bool link_ok);

void display_idle();                       // "READY >" + blinking cursor
void display_listening();                  // "LISTENING..." animated
void display_thinking();                   // "THINKING..." animated
void display_response(const char *text);   // clear + word-wrapped answer
void display_error(const char *msg);       // "ERROR: <msg>"

// Non-blocking: drives cursor blink and the animated dots/ellipsis. Call
// often from loop().
void display_tick();
