// status.cpp — WS2812 LED + passive buzzer feedback.
#include "config.h"
#include "status.h"
#include <Adafruit_NeoPixel.h>

static Adafruit_NeoPixel s_led(1, PIN_WS2812, NEO_GRB + NEO_KHZ800);

static StatusState s_state = ST_BOOT;
static uint32_t s_lastBlink = 0;
static bool s_blinkOn = false;
static uint32_t s_flashUntil = 0;   // for the transient green response flash

// Dim colors (WS2812 is bright; keep it easy on the eyes).
static uint32_t C_GREEN, C_RED, C_BLUE, C_AMBER, C_OFF;

static void beep(unsigned freq, unsigned ms) {
  tone(PIN_BUZZER, freq, ms);
}

void status_begin() {
  s_led.begin();
  s_led.setBrightness(40);          // global dim
  C_GREEN = s_led.Color(0, 180, 0);
  C_RED   = s_led.Color(220, 0, 0);
  C_BLUE  = s_led.Color(0, 60, 220);
  C_AMBER = s_led.Color(220, 90, 0);
  C_OFF   = s_led.Color(0, 0, 0);
  s_led.setPixelColor(0, C_OFF);
  s_led.show();
}

static void show(uint32_t color) {
  s_led.setPixelColor(0, color);
  s_led.show();
}

void status_set(StatusState s) {
  s_state = s;
  s_blinkOn = true;
  s_lastBlink = millis();

  switch (s) {
    case ST_IDLE:
      show(C_GREEN);
      break;
    case ST_RECORDING:
      show(C_RED);
      beep(1800, 90);              // one short high beep on start
      break;
    case ST_PROCESSING:
      show(C_BLUE);
      beep(1200, 90);              // one short beep on stop
      break;
    case ST_RESPONSE:
      show(C_GREEN);
      s_flashUntil = millis() + 250;
      beep(500, 160);              // one low chime
      break;
    case ST_ERROR:
      show(C_AMBER);
      beep(220, 600);              // one long low buzz
      break;
    case ST_BOOT:
    default:
      show(C_OFF);
      break;
  }
}

void status_tick() {
  uint32_t now = millis();

  // Transient response flash resolves into steady idle green.
  if (s_state == ST_RESPONSE && now > s_flashUntil) {
    s_state = ST_IDLE;
    show(C_GREEN);
    return;
  }

  // Blink for processing (blue) and error (amber).
  bool blinking = (s_state == ST_PROCESSING || s_state == ST_ERROR);
  if (!blinking) return;

  if (now - s_lastBlink >= 300) {
    s_lastBlink = now;
    s_blinkOn = !s_blinkOn;
    if (s_state == ST_PROCESSING) show(s_blinkOn ? C_BLUE : C_OFF);
    else                          show(s_blinkOn ? C_AMBER : C_OFF);
  }
}
