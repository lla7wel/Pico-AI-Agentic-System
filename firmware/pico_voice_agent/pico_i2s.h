// pico_i2s.h — public interface for the custom SPH0645 I2S receiver.
#pragma once
#include <Arduino.h>

// Bring up the mic: power/select GPIOs, PIO state machine, and the DMA ring.
// Call once in setup(). Safe to call after WiFi/TFT are up.
void i2s_mic_begin();

// Pull up to `max_samples` freshly captured samples, converted to 16-bit
// mono PCM, into `out`. Returns the number of samples written (0 if none
// are ready yet). Non-blocking — call it repeatedly in the record loop.
size_t i2s_mic_read(int16_t *out, size_t max_samples);

// Debug helper (brief §7 step 4): stream converted samples to Serial as
// signed decimals so you can eyeball a tone/clap before trusting the mic.
// Blocks for `ms` milliseconds. Not used in the normal flow.
void i2s_mic_debug_dump(uint32_t ms);
