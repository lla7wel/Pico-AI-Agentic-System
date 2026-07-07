// TFT_eSPI_User_Setup.h — pin/driver config for THIS project's TFT.
//
// TFT_eSPI is configured at COMPILE TIME inside the library folder, not in the
// sketch. Copy the contents below into TFT_eSPI's User_Setup.h (see
// firmware/README.md for the exact file location and the alternative
// User_Setup_Select.h approach). Pins match the 52Pi Breadboard Kit.

#define ST7796_DRIVER          // ST7796SU1 controller

#define TFT_WIDTH  320
#define TFT_HEIGHT 480         // native portrait; sketch calls setRotation(1)

// SPI0 pins on the Pico W (arduino-pico numbering == GPxx):
#define TFT_MISO -1            // not used (write-only)
#define TFT_MOSI 3             // GP3
#define TFT_SCLK 2             // GP2
#define TFT_CS   5             // GP5
#define TFT_DC   6             // GP6
#define TFT_RST  7             // GP7

#define LOAD_GLCD              // font 1 (6x8 monospaced) — the terminal font
#define LOAD_FONT2
#define SMOOTH_FONT

#define SPI_FREQUENCY 40000000 // 40 MHz; drop to 27 MHz if you see glitches
