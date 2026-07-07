// pico_i2s.pio.h — custom PIO I2S receiver for the direct-plugged SPH0645.
//
// WHY THIS EXISTS: the mic is soldered straight onto GP18..GP22
// in the breakout's physical pin order, so LRCLK(GP19) sits BEFORE BCLK(GP21)
// with DOUT(GP20) between them. The stock arduino-pico I2S library requires
// LRCLK == BCLK+1, which is impossible here. PIO doesn't care about pin
// adjacency: it drives each signal from an INDEPENDENT pin group:
//     sideset base -> GP21 (BCLK)   : bit clock, toggled every instruction
//     SET pins base -> GP19 (LRCLK) : word-select, driven explicitly
//     IN  pins base -> GP20 (DOUT)  : data, sampled on BCLK rising edge
//
// The Arduino IDE does not run pioasm, so the program is hand-assembled below.
// The human-readable source it was assembled from is kept in the comment block
// so it can be re-verified or regenerated with pioasm if ever changed.
//
// ---------------------------------------------------------------------------
// Reference source (.pio):
//
//   .program i2s_rx
//   .side_set 1                      ; sideset drives BCLK (GP21)
//   .wrap_target
//       set pins, 0     side 0       ; LRCLK=0 (left/mono channel), BCLK low
//       set x, 31       side 0       ; load left bit counter (32 bits)
//   left_loop:
//       in pins, 1      side 1       ; BCLK high: sample DOUT (MSB first)
//       jmp x-- left_loop side 0     ; BCLK low; repeat 32x
//                                    ; autopush (thresh 32) -> RX FIFO
//       set pins, 1     side 0       ; LRCLK=1 (right channel, ignored)
//       set y, 31       side 0       ; load right bit counter
//   right_loop:
//       nop             side 1       ; BCLK high, DATA ignored (no `in`)
//       jmp y-- right_loop side 0    ; BCLK low; repeat 32x
//   .wrap
//
// Because `in` only runs during the left half, autopush fires exactly once per
// LRCLK period, so the RX FIFO holds ONE 32-bit left-channel word per frame.
// ISR shifts LEFT (MSB-first). The SPH0645's 1-bit clock-delay quirk and the
// sample extraction are handled on the C side (see pico_i2s.cpp), not here.
// ---------------------------------------------------------------------------
#pragma once
#include "hardware/pio.h"

// Assembled instructions (8 total). See per-instruction encoding notes.
static const uint16_t i2s_rx_program_instructions[] = {
    //     (wrap target)
    0xe000, //  0: set    pins, 0         side 0   ; LRCLK=0, BCLK low
    0xe03f, //  1: set    x, 31           side 0   ; load left counter
    0x5001, //  2: in     pins, 1         side 1   ; sample DOUT, BCLK high
    0x0042, //  3: jmp    x--, 2          side 0   ; BCLK low, loop 32x
    0xe001, //  4: set    pins, 1         side 0   ; LRCLK=1 (right)
    0xe05f, //  5: set    y, 31           side 0   ; load right counter
    0xb042, //  6: nop                    side 1   ; BCLK high, ignore data
    0x0086, //  7: jmp    y--, 6          side 0   ; BCLK low, loop 32x
    //     (wrap)
};

static const struct pio_program i2s_rx_program = {
    .instructions = i2s_rx_program_instructions,
    .length = 8,
    .origin = -1,   // let the loader place it anywhere in PIO instr memory
};

// wrap_target = 0, wrap = 7 (see reference source above).
static inline pio_sm_config i2s_rx_program_get_default_config(uint offset) {
    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, offset + 0, offset + 7);
    sm_config_set_sideset(&c, 1, false, false);  // 1 sideset bit, not opt/pindirs
    return c;
}
