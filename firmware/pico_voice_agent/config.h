// config.h — hardware pin map and tunables for the Pico W voice agent.
// Pin map is fixed by the 52Pi Pico Breadboard Kit Plus + direct-plugged
// SPH0645 mic (see project brief §2). Do not change pins without rewiring.
#pragma once

// ---- TFT (ST7796SU1, 480x320, SPI0) --------------------------------------
// NOTE: TFT_eSPI is configured at COMPILE TIME, not here. These values are
// documentation; the real pin config lives in TFT_eSPI's User_Setup (see
// firmware/README.md). They must match:
//   TFT_SCLK=GP2  TFT_MOSI=GP3  TFT_CS=GP5  TFT_DC=GP6  TFT_RST=GP7
#define TFT_WIDTH_PX   480
#define TFT_HEIGHT_PX  320

// ---- I2S mic (SPH0645), direct-plugged to GP18..GP22 ---------------------
#define PIN_MIC_SEL    18   // drive LOW at boot: selects left channel (mono)
#define PIN_MIC_LRCLK  19   // WS  — PIO SET pin (word-select, generated)
#define PIN_MIC_DOUT   20   // DATA — PIO IN pin  (sampled)
#define PIN_MIC_BCLK   21   // BCLK — PIO sideset pin (bit clock, generated)
#define PIN_MIC_3V     22   // drive HIGH at boot and hold: powers the mic

// ---- Controls ------------------------------------------------------------
#define PIN_BUTTON1    15   // push-to-talk: press = start, press again = stop
#define PIN_BUTTON2    14   // reserved (unused in v1)

// ---- Status output -------------------------------------------------------
#define PIN_WS2812     12   // single WS2812 RGB status LED
#define PIN_BUZZER     13   // passive buzzer (tone())

// ---- Audio format (must match backend config.py SAMPLE_RATE) -------------
#define SAMPLE_RATE_HZ 16000
// Streamed PCM chunk size in bytes. One static buffer of this size is
// allocated once at boot and reused for every frame (brief §6 memory rules).
#define PCM_CHUNK_BYTES 512          // 256 samples of 16-bit mono
#define PCM_CHUNK_SAMPLES (PCM_CHUNK_BYTES / 2)

// ---- Button debounce -----------------------------------------------------
#define BUTTON_DEBOUNCE_MS 40
