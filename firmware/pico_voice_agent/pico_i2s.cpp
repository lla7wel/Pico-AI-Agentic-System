// pico_i2s.cpp — SPH0645 I2S receiver: PIO + DMA ring + sample conversion.
//
// Data path:
//   mic --BCLK/DOUT/LRCLK--> PIO (pico_i2s.pio.h) --RX FIFO--> DMA --> ring[]
//   consumer: i2s_mic_read() reads new words from ring[], converts to PCM16.
//
// Memory rule: the ring buffer is a single static allocation made once here;
// nothing in the audio path allocates per-chunk.
#include "config.h"
#include "pico_i2s.h"
#include "pico_i2s.pio.h"

#include "hardware/pio.h"
#include "hardware/dma.h"
#include "hardware/clocks.h"
#include "hardware/gpio.h"

// ---- SPH0645 sample extraction knobs (TUNE DURING BRING-UP) --------------
// The SPH0645 has a well-known 1-bit clock delay; correct it by shifting the
// captured 32-bit word left before extracting the sample. If your serial dump
// (i2s_mic_debug_dump) shows noise/static on a clean tone, this shift and
// I2S_VALID_BITS are the first things to adjust.
#define SPH0645_DELAY_SHIFT 1     // bits to shift left to undo the 1-clk delay
#define I2S_VALID_BITS      18    // SPH0645 delivers 18 valid bits, MSB first
#define I2S_GAIN_SHIFT      0     // extra left-shift for loudness (0 = none)

// ---- DMA ring buffer -----------------------------------------------------
// 512 words = 2 KB. Must be a power of two and aligned to its byte size so the
// DMA "write ring" wrap works. 2 KB @ 16 kHz = ~32 ms of audio headroom.
#define RING_WORDS 512
#define RING_BYTES (RING_WORDS * 4)
#define RING_RING_BITS 11         // log2(RING_BYTES) = log2(2048)

static uint32_t ring[RING_WORDS] __attribute__((aligned(RING_BYTES)));

static PIO   s_pio = pio0;
static int   s_sm = -1;
static int   s_dma = -1;
static uint  s_read_idx = 0;      // consumer position, in words

// Current DMA write position (in words from ring base).
static inline uint dma_write_idx() {
  uint32_t waddr = dma_hw->ch[s_dma].write_addr;
  return (uint)(((uintptr_t)waddr - (uintptr_t)ring) / 4) & (RING_WORDS - 1);
}

static void gpio_setup() {
  // Power the mic and hold LRCLK-select for mono (left) channel.
  pinMode(PIN_MIC_3V, OUTPUT);
  digitalWrite(PIN_MIC_3V, HIGH);     // 3V — held HIGH forever
  pinMode(PIN_MIC_SEL, OUTPUT);
  digitalWrite(PIN_MIC_SEL, LOW);     // SEL LOW — selects left/mono
  delay(10);                          // let the mic power up
}

static void pio_setup() {
  s_sm = pio_claim_unused_sm(s_pio, true);
  uint offset = pio_add_program(s_pio, &i2s_rx_program);

  pio_sm_config c = i2s_rx_program_get_default_config(offset);

  // Independent pin groups (this is the whole point — no adjacency assumed):
  sm_config_set_sideset_pins(&c, PIN_MIC_BCLK);   // GP21 BCLK via sideset
  sm_config_set_set_pins(&c, PIN_MIC_LRCLK, 1);   // GP19 LRCLK via SET
  sm_config_set_in_pins(&c, PIN_MIC_DOUT);        // GP20 DOUT via IN

  // MSB-first: shift ISR left; autopush a full 32-bit word.
  sm_config_set_in_shift(&c, /*shift_right=*/false, /*autopush=*/true, 32);
  sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_RX);  // deeper RX FIFO

  // Clock: BCLK toggles once per instruction, so it runs at PIO_clk/2.
  // Target BCLK = SAMPLE_RATE * 64 (32 bits/channel * 2 channels).
  float bclk = (float)SAMPLE_RATE_HZ * 64.0f;
  float div = (float)clock_get_hz(clk_sys) / (bclk * 2.0f);
  sm_config_set_clkdiv(&c, div);

  // Hand the three GPIOs to PIO and set directions.
  pio_gpio_init(s_pio, PIN_MIC_BCLK);
  pio_gpio_init(s_pio, PIN_MIC_LRCLK);
  pio_gpio_init(s_pio, PIN_MIC_DOUT);
  pio_sm_set_consecutive_pindirs(s_pio, s_sm, PIN_MIC_BCLK, 1, true);   // out
  pio_sm_set_consecutive_pindirs(s_pio, s_sm, PIN_MIC_LRCLK, 1, true);  // out
  pio_sm_set_consecutive_pindirs(s_pio, s_sm, PIN_MIC_DOUT, 1, false);  // in

  pio_sm_init(s_pio, s_sm, offset, &c);
  pio_sm_set_enabled(s_pio, s_sm, true);
}

static void dma_setup() {
  s_dma = dma_claim_unused_channel(true);
  dma_channel_config dc = dma_channel_get_default_config(s_dma);
  channel_config_set_transfer_data_size(&dc, DMA_SIZE_32);
  channel_config_set_read_increment(&dc, false);            // fixed: RX FIFO
  channel_config_set_write_increment(&dc, true);            // walk the ring
  // Write-ring wrap: the write address auto-wraps to the ring base every
  // RING_BYTES, so the channel writes a circular buffer forever. (Do NOT
  // "chain to self" — on the RP2040 chain_to == own channel means NO chain,
  // which would stop capture after one ring.) A very large transfer count
  // keeps it running for ~74 h; the re-arm in i2s_mic_read() covers the rest.
  channel_config_set_ring(&dc, /*write=*/true, RING_RING_BITS);
  channel_config_set_dreq(&dc, pio_get_dreq(s_pio, s_sm, /*is_tx=*/false));

  dma_channel_configure(
      s_dma, &dc,
      ring,                          // write: ring base (address wraps here)
      &s_pio->rxf[s_sm],             // read: PIO RX FIFO
      0xFFFFFFFFu,                   // effectively endless
      true);                         // start now
}

// Restart the capture channel from the ring base. Only needed on the ~74 h
// edge where the huge transfer count would finally run out.
static void dma_rearm() {
  dma_channel_set_write_addr(s_dma, ring, false);
  dma_channel_set_trans_count(s_dma, 0xFFFFFFFFu, true);  // trigger
  s_read_idx = 0;
}

void i2s_mic_begin() {
  gpio_setup();
  pio_setup();
  dma_setup();
  s_read_idx = dma_write_idx();      // start reading from "now"
}

static inline int16_t word_to_pcm16(uint32_t raw) {
  int32_t v = (int32_t)(raw << SPH0645_DELAY_SHIFT);  // undo 1-bit delay
  v >>= (32 - I2S_VALID_BITS);                         // -> signed 18-bit
  v >>= (I2S_VALID_BITS - 16);                         // -> 16-bit range
#if I2S_GAIN_SHIFT
  int32_t g = v << I2S_GAIN_SHIFT;
  if (g > 32767) g = 32767; else if (g < -32768) g = -32768;  // clip
  v = g;
#endif
  return (int16_t)v;
}

size_t i2s_mic_read(int16_t *out, size_t max_samples) {
  if (!dma_channel_is_busy(s_dma)) dma_rearm();  // ~74 h safety net
  uint w = dma_write_idx();
  size_t n = 0;
  while (s_read_idx != w && n < max_samples) {
    out[n++] = word_to_pcm16(ring[s_read_idx]);
    s_read_idx = (s_read_idx + 1) & (RING_WORDS - 1);
  }
  return n;
}

void i2s_mic_debug_dump(uint32_t ms) {
  static int16_t tmp[PCM_CHUNK_SAMPLES];
  uint32_t end = millis() + ms;
  while ((int32_t)(end - millis()) > 0) {
    size_t n = i2s_mic_read(tmp, PCM_CHUNK_SAMPLES);
    for (size_t i = 0; i < n; i++) {
      Serial.println(tmp[i]);
    }
  }
}
