// pico_voice_agent.ino — Raspberry Pi Pico W retro voice agent (brief §6).
//
// Push-to-talk: Button1 starts recording, press again to stop. Audio is
// captured by the custom PIO I2S receiver, streamed live over WSS to the
// Fly.io backend, transcribed + answered by Claude, and the reply is drawn
// on the green-phosphor TFT. Nothing is stored on the device.
//
// Board settings (Arduino IDE): "Raspberry Pi Pico W", and set TFT_eSPI up
// per firmware/README.md. See that README for libraries + bring-up order.
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

#include "config.h"
#include "secrets.h"
#include "ca_cert.h"
#include "display.h"
#include "status.h"
#include "pico_i2s.h"

// ---- App state -----------------------------------------------------------
enum AppState { S_BOOTING, S_IDLE, S_RECORDING, S_PROCESSING };
static AppState s_state = S_BOOTING;

static WebSocketsClient ws;
static bool s_wsConnected = false;
static bool s_authed = false;

// Filled by the WS event handler, consumed by loop(). Single-threaded, so
// plain globals are safe (events fire synchronously inside ws.loop()).
static bool s_haveResponse = false;
static bool s_haveError = false;
static char s_msgBuf[512];        // response text or error message

// One static PCM chunk buffer, reused for every read (brief §6 memory rule).
static int16_t s_pcm[PCM_CHUNK_SAMPLES];

// ---- Button (active-low, press-to-toggle with debounce) ------------------
static int s_btnStable = HIGH;
static int s_btnLast = HIGH;
static uint32_t s_btnChangedAt = 0;

static bool button_pressed_edge() {
  int raw = digitalRead(PIN_BUTTON1);
  if (raw != s_btnLast) {
    s_btnLast = raw;
    s_btnChangedAt = millis();
  }
  if (millis() - s_btnChangedAt > BUTTON_DEBOUNCE_MS && raw != s_btnStable) {
    s_btnStable = raw;
    if (s_btnStable == LOW) return true;   // falling edge = a fresh press
  }
  return false;
}

// ---- WebSocket -----------------------------------------------------------
static void sendJson(const char *json) { ws.sendTXT(json); }

static void sendAuth() {
  char buf[256];
  snprintf(buf, sizeof(buf),
           "{\"type\":\"auth\",\"token\":\"%s\",\"device_id\":\"%s\"}",
           PICO_AUTH_TOKEN, DEVICE_ID);
  sendJson(buf);
}

static void copyMsg(const char *src) {
  snprintf(s_msgBuf, sizeof(s_msgBuf), "%s", src);  // always NUL-terminates
}

static void handleServerText(const char *payload) {
  JsonDocument doc;                                  // ArduinoJson 7
  DeserializationError err = deserializeJson(doc, payload);
  if (err) return;
  const char *type = doc["type"] | "";

  if (strcmp(type, "ready") == 0) {
    s_authed = true;
  } else if (strcmp(type, "response") == 0) {
    copyMsg(doc["text"] | "");
    s_haveResponse = true;
  } else if (strcmp(type, "error") == 0) {
    copyMsg(doc["message"] | "unknown");
    s_haveError = true;
  }
}

static void wsEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      s_wsConnected = true;
      s_authed = false;
      sendAuth();
      break;
    case WStype_DISCONNECTED:
      s_wsConnected = false;
      s_authed = false;
      break;
    case WStype_TEXT:
      handleServerText((const char *)payload);
      break;
    case WStype_ERROR:
      s_haveError = true;
      copyMsg("link error");
      break;
    default:
      break;
  }
}

// Pump the socket until authed or timeout; returns whether the link is ready.
static bool wsConnectBlocking(uint32_t timeoutMs) {
#if USE_CA_PINNING
  ws.beginSslWithCA(WS_HOST, WS_PORT, WS_PATH, WS_CA_CERT);
#else
  ws.beginSSL(WS_HOST, WS_PORT, WS_PATH);   // see README re: TLS verification
#endif
  ws.onEvent(wsEvent);
  ws.setReconnectInterval(3000);

  uint32_t end = millis() + timeoutMs;
  while ((int32_t)(end - millis()) > 0) {
    ws.loop();
    if (s_wsConnected && s_authed) return true;
    delay(10);
  }
  return s_wsConnected && s_authed;
}

// ---- WiFi ----------------------------------------------------------------
static bool wifiConnect(uint32_t timeoutMs) {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t end = millis() + timeoutMs;
  while (WiFi.status() != WL_CONNECTED && (int32_t)(end - millis()) > 0) {
    delay(200);
  }
  return WiFi.status() == WL_CONNECTED;
}

// ---- State transitions ---------------------------------------------------
static void enterIdle() {
  s_state = S_IDLE;
  status_set(ST_IDLE);
}

static void startRecording() {
  if (!(s_wsConnected && s_authed)) {
    display_error("no link");
    status_set(ST_ERROR);
    return;                       // stay idle; user can retry
  }
  s_haveResponse = s_haveError = false;
  sendJson("{\"type\":\"start\"}");
  display_listening();
  status_set(ST_RECORDING);
  s_state = S_RECORDING;
}

static void stopRecording() {
  sendJson("{\"type\":\"stop\"}");
  display_thinking();
  status_set(ST_PROCESSING);
  s_state = S_PROCESSING;
}

// ---- Arduino entry points ------------------------------------------------
void setup() {
  Serial.begin(115200);

  pinMode(PIN_BUTTON1, INPUT_PULLUP);
  pinMode(PIN_BUTTON2, INPUT_PULLUP);

  status_begin();
  display_begin();

  i2s_mic_begin();
  bool mic_ok = true;             // validated separately via serial dump (§7.4)

  bool wifi_ok = wifiConnect(15000);
  bool link_ok = wifi_ok && wsConnectBlocking(8000);

  display_boot_sequence(mic_ok, wifi_ok, link_ok);

  if (link_ok) {
    display_idle();
    enterIdle();
  } else {
    display_error(wifi_ok ? "no server link" : "no wifi");
    status_set(ST_ERROR);
    s_state = S_IDLE;             // allow retry on button press
  }
}

void loop() {
  ws.loop();
  status_tick();
  display_tick();

  bool pressed = button_pressed_edge();

  switch (s_state) {
    case S_IDLE:
      if (pressed) startRecording();
      break;

    case S_RECORDING:
      // Drain the mic and stream every ready chunk immediately.
      {
        size_t n = i2s_mic_read(s_pcm, PCM_CHUNK_SAMPLES);
        if (n > 0) ws.sendBIN((uint8_t *)s_pcm, n * sizeof(int16_t));
      }
      if (pressed) stopRecording();
      break;

    case S_PROCESSING:
      if (s_haveResponse) {
        s_haveResponse = false;
        display_response(s_msgBuf);
        status_set(ST_RESPONSE);        // green flash + chime, then idle LED
        s_state = S_IDLE;               // screen keeps the answer until next turn
      } else if (s_haveError) {
        s_haveError = false;
        display_error(s_msgBuf);
        status_set(ST_ERROR);
        s_state = S_IDLE;
      }
      // A stray press while processing is ignored (no start/stop race).
      break;

    default:
      break;
  }

  // Surface async errors that arrive outside PROCESSING (e.g. link drop).
  if (s_state != S_PROCESSING && s_haveError) {
    s_haveError = false;
    display_error(s_msgBuf);
    status_set(ST_ERROR);
  }
}
