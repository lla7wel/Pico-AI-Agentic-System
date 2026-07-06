// display.cpp — retro green terminal renderer.
//
// Memory: draws directly to the panel and uses only tiny scratch buffers.
// No full-screen sprite is ever allocated (a 480x320x16bpp buffer would be
// ~300 KB, larger than the RP2040's whole 264 KB SRAM — brief §6).
#include "config.h"
#include "display.h"
#include <TFT_eSPI.h>

static TFT_eSPI tft = TFT_eSPI();

// Phosphor palette.
#define PHOS       0x07E0        // TFT_GREEN
#define PHOS_DIM   0x03E0        // darker green
#define BG         TFT_BLACK

// Built-in font 1 is a 6x8 monospaced glyph; scale it for the terminal look.
#define TXT_SIZE   2
#define CH_W       (6 * TXT_SIZE)
#define CH_H       (8 * TXT_SIZE)
#define MARGIN     8

static int s_cols = 0;           // characters per line at current width
static int s_lastRow = 0;        // y of the interactive prompt row

// --- animation state (non-blocking) ---
enum Anim { AN_NONE, AN_IDLE, AN_LISTEN, AN_THINK };
static Anim s_anim = AN_NONE;
static uint32_t s_lastAnim = 0;
static bool s_cursorOn = false;
static int s_dots = 0;

static void term_setup_text() {
  tft.setTextFont(1);
  tft.setTextSize(TXT_SIZE);
  tft.setTextColor(PHOS, BG);
}

void display_begin() {
  tft.init();
  tft.setRotation(1);            // landscape 480x320
  tft.fillScreen(BG);
  term_setup_text();
  s_cols = (tft.width() - 2 * MARGIN) / CH_W;
  s_lastRow = tft.height() - MARGIN - CH_H;
}

// Print one status line during boot with a brief typewriter-ish pause.
static void boot_line(int row, const char *label, bool ok) {
  int y = MARGIN + row * CH_H;
  tft.setCursor(MARGIN, y);
  tft.setTextColor(PHOS, BG);
  tft.print(label);
  delay(350);
  tft.setTextColor(ok ? PHOS : TFT_RED, BG);
  tft.print(ok ? "OK" : "FAIL");
  tft.setTextColor(PHOS, BG);
  delay(250);
}

void display_boot_sequence(bool mic_ok, bool wifi_ok, bool link_ok) {
  tft.fillScreen(BG);
  term_setup_text();
  int row = 0;
  tft.setCursor(MARGIN, MARGIN + row++ * CH_H);
  tft.print("RETRO VOICE TERMINAL v1");
  row++;
  delay(400);
  boot_line(row++, "INIT DISPLAY... ", true);
  boot_line(row++, "INIT MIC...     ", mic_ok);
  boot_line(row++, "INIT WIFI...    ", wifi_ok);
  boot_line(row++, "INIT LINK...    ", link_ok);
  row++;
  tft.setCursor(MARGIN, MARGIN + row * CH_H);
  tft.print(link_ok ? "SYSTEM READY" : "SYSTEM DEGRADED");
  delay(700);
}

// Clear and print a header + optional body; leaves the prompt row free.
static void screen_header(const char *header) {
  tft.fillScreen(BG);
  term_setup_text();
  tft.setCursor(MARGIN, MARGIN);
  tft.print(header);
}

void display_idle() {
  screen_header("READY");
  tft.setCursor(MARGIN, s_lastRow);
  tft.print("> ");
  s_anim = AN_IDLE;
  s_cursorOn = false;
  s_lastAnim = millis();
}

void display_listening() {
  screen_header("LISTENING");
  s_anim = AN_LISTEN;
  s_dots = 0;
  s_lastAnim = millis();
}

void display_thinking() {
  screen_header("THINKING");
  s_anim = AN_THINK;
  s_dots = 0;
  s_lastAnim = millis();
}

void display_error(const char *msg) {
  s_anim = AN_NONE;
  tft.fillScreen(BG);
  term_setup_text();
  tft.setTextColor(TFT_ORANGE, BG);
  tft.setCursor(MARGIN, MARGIN);
  tft.print("ERROR: ");
  tft.print(msg);
  tft.setTextColor(PHOS, BG);
}

// Word-wrap `text` into the terminal width and print it. Long single words
// are hard-broken. Uses only a small line buffer.
void display_response(const char *text) {
  s_anim = AN_NONE;
  tft.fillScreen(BG);
  term_setup_text();

  const int maxCols = s_cols;
  int x = MARGIN, y = MARGIN;
  const int yMax = tft.height() - MARGIN - CH_H;
  int col = 0;

  char word[64];
  int wlen = 0;

  auto flushWord = [&](void) {
    if (wlen == 0) return;
    if (col + wlen > maxCols) {   // wrap before this word
      x = MARGIN; y += CH_H; col = 0;
    }
    if (y > yMax) return;         // out of screen; drop the rest (no scroll)
    word[wlen] = '\0';
    tft.setCursor(x, y);
    tft.print(word);
    col += wlen; x += wlen * CH_W;
    wlen = 0;
  };

  for (const char *p = text; *p; ++p) {
    char c = *p;
    if (c == ' ' || c == '\n') {
      flushWord();
      if (c == '\n') { x = MARGIN; y += CH_H; col = 0; }
      else if (col < maxCols && col > 0) { col++; x += CH_W; } // space
      continue;
    }
    if (wlen < (int)sizeof(word) - 1) word[wlen++] = c;
    if (wlen >= maxCols) flushWord();   // hard-break very long tokens
  }
  flushWord();
}

void display_tick() {
  uint32_t now = millis();
  switch (s_anim) {
    case AN_IDLE:
      if (now - s_lastAnim >= 500) {
        s_lastAnim = now;
        s_cursorOn = !s_cursorOn;
        // Block cursor after the "> " prompt.
        tft.fillRect(MARGIN + 2 * CH_W, s_lastRow, CH_W, CH_H,
                     s_cursorOn ? PHOS : BG);
      }
      break;
    case AN_LISTEN:
    case AN_THINK:
      if (now - s_lastAnim >= 350) {
        s_lastAnim = now;
        s_dots = (s_dots + 1) % 4;
        int y = MARGIN + 2 * CH_H;
        tft.fillRect(MARGIN, y, 4 * CH_W, CH_H, BG);
        tft.setCursor(MARGIN, y);
        for (int i = 0; i < s_dots; i++) tft.print('.');
      }
      break;
    default:
      break;
  }
}
