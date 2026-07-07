# Pico W Firmware — Retro Voice Terminal

Push-to-talk voice capture → live WebSocket stream → green-phosphor TFT answer.

## Toolchain

- **Arduino IDE** (2.x) with the **Earle Philhower arduino-pico** core.
  - Boards Manager URL:
    `https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json`
  - Board: **Raspberry Pi Pico W**.
  - Recommended board options: CPU 133 MHz, Flash size with a small FS is fine,
    **Optimize: -O2**. USB stack: default. Leave 8 KB+ for the heap.

## Libraries (Library Manager unless noted)

- **TFT_eSPI** (Bodmer) — ST7796 driver. Requires the pin config below.
- **WebSockets** by **Markus Sattler / Links2004** (aka `arduinoWebSockets`) — WSS client.
- **ArduinoJson** (Benoit Blanchon) — parses server frames safely.
- **Adafruit NeoPixel** — the WS2812 status LED.
- Custom PIO I2S receiver — included in this sketch (`pico_i2s.*`, `pico_i2s.pio.h`); no external lib.

## TFT_eSPI pin configuration (required, one-time)

TFT_eSPI reads its config from inside the *library* folder, not the sketch.
Copy the settings from [`pico_voice_agent/TFT_eSPI_User_Setup.h`](pico_voice_agent/TFT_eSPI_User_Setup.h)
into your `TFT_eSPI/User_Setup.h`. Typical locations:

- macOS: `~/Documents/Arduino/libraries/TFT_eSPI/User_Setup.h`
- Windows: `Documents\Arduino\libraries\TFT_eSPI\User_Setup.h`
- Linux: `~/Arduino/libraries/TFT_eSPI/User_Setup.h`

Either paste the block over the default `User_Setup.h`, or add it as a new
setup file and select it in `User_Setup_Select.h`. If the screen stays white,
this config is the first thing to check.

## Secrets

Copy [`pico_voice_agent/secrets.h.example`](pico_voice_agent/secrets.h.example)
to `pico_voice_agent/secrets.h` and fill in:

- Wi-Fi SSID + password
- Backend host/port (`WS_HOST`, `WS_PORT`) and `WS_USE_TLS`
  (`1` for Fly.io/HTTPS, `0` for a plain local backend)
- `DEVICE_ID` + `PICO_AUTH_TOKEN` — generated in the dashboard
  (**Devices → Add a Pico**); it shows both values once, ready to paste.

`secrets.h` is gitignored and never committed.

## Bring-up order (do not skip steps)

The custom PIO I2S receiver and TLS are the two riskiest pieces; validate each
in isolation before layering the full flow on top.

1. **WiFi + TFT boot animation first.** Flash as-is; confirm the boot sequence
   renders and WiFi/link report OK. This proves display + networking before
   any audio.

2. **Validate the mic in isolation (critical).** The SPH0645 has a 1-bit clock
   delay and this PIO receiver is hand-written — get it wrong and audio is
   static. Temporarily, in `setup()` after `i2s_mic_begin()`, call:
   ```cpp
   Serial.begin(115200);
   i2s_mic_debug_dump(3000);   // 3s of samples to Serial
   ```
   Whistle / clap / speak. In the Serial Plotter you should see a clean-ish
   waveform that tracks the sound, centered near 0, not full-scale noise.
   If it looks like garbage, tune these in `pico_i2s.cpp`:
   `SPH0645_DELAY_SHIFT` (try 0 or 1), `I2S_VALID_BITS` (18), and
   `I2S_GAIN_SHIFT` (raise for a quiet mic).

3. **Validate TLS in isolation.** With `USE_CA_PINNING 0` (default, in
   `ca_cert.h`) confirm the WSS handshake to `wss://<app>.fly.dev` succeeds
   and `{"type":"ready"}` comes back (link reports OK at boot). Only then, if
   you want an authenticated link, set `USE_CA_PINNING 1` and paste the ISRG
   Root X1 PEM (see `ca_cert.h`). Test on a trusted network first — TLS
   handshake RAM (~tens of KB) is the tightest memory moment.

4. **Full push-to-talk flow.** Remove the debug dump. Press Button 1 to record,
   press again to stop; the answer should draw on-screen within a couple of
   seconds. The socket is opened once and kept alive across turns.

5. **Status LED + buzzer** are already wired into the state machine; verify the
   colors/tones last (idle green, record red+beep, processing blue blink+beep,
   response green flash+chime, error amber blink+buzz).

## File map

| File | Role |
|---|---|
| `pico_voice_agent.ino` | app state machine, WiFi, WSS client, button, streaming loop |
| `config.h` | pin map + audio constants |
| `secrets.h` | your credentials (gitignored; copy from `.example`) |
| `pico_i2s.pio.h` | hand-assembled PIO I2S program (annotated source included) |
| `pico_i2s.cpp/.h` | I2S driver: PIO + DMA ring + SPH0645 sample conversion |
| `display.cpp/.h` | green terminal UI (boot anim, states, word-wrap) |
| `status.cpp/.h` | WS2812 + buzzer status codes |
| `ca_cert.h` | TLS trust config (pin CA or not) |
| `TFT_eSPI_User_Setup.h` | copy into the TFT_eSPI library |

## Memory notes

- One static PCM chunk buffer (`s_pcm`) and one static DMA ring — no per-chunk
  allocation anywhere in the audio path.
- No `String` in the audio/network path; fixed `char[]` + `snprintf`.
- No full-screen sprite (480×320×2 ≈ 300 KB > 264 KB SRAM); the UI draws
  directly to the panel.
