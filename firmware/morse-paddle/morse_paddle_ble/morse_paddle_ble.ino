// Morse paddle -> Bluetooth (BLE) keyboard
//
// Tip  (dit) -> DIT_PIN, holds DIT_KEY down while the paddle is closed
// Ring (dah) -> DAH_PIN, holds DAH_KEY down while the paddle is closed
// Sleeve     -> GND
//
// Keys are held for as long as the paddle is closed (press on close,
// release on open), so a trainer's own iambic keyer sees real key-down
// and key-up timing.
//
// Library: ESP32-BLE-Keyboard by T-vK (https://github.com/T-vK/ESP32-BLE-Keyboard)
// Tested target: ESP32 Arduino core 2.0.x. See README.md for core 3.x and NimBLE.

#include <BleKeyboard.h>

// ---------------------------------------------------------------------------
// Settings you might want to change
// ---------------------------------------------------------------------------

const uint8_t DIT_KEY = '[';   // tip
const uint8_t DAH_KEY = ']';   // ring
// Some trainers want the Ctrl keys instead:
//   const uint8_t DIT_KEY = KEY_LEFT_CTRL;
//   const uint8_t DAH_KEY = KEY_RIGHT_CTRL;
// Paddle backwards for you (left-handed, or wires swapped)? Swap the two keys.

const char *DEVICE_NAME  = "Morse Paddle";  // what shows up when pairing
const char *MANUFACTURER = "Homebrew";

// A paddle contact barely bounces, and a dit at 30 WPM is 40 ms long,
// so a few ms is plenty. Raise it if you see doubled dits.
const uint32_t DEBOUNCE_MS = 5;

// Wait this long after the host connects before sending anything, so the
// first key isn't lost while the host is still setting up the connection.
const uint32_t CONNECT_SETTLE_MS = 500;

// Pins. Defaults avoid strapping pins and input-only pins on each chip.
#if defined(CONFIG_IDF_TARGET_ESP32S2)
  #error "The ESP32-S2 has no Bluetooth. Use a classic ESP32, an S3 or a C3."
#elif defined(CONFIG_IDF_TARGET_ESP32)
  const uint8_t DIT_PIN = 32;   // classic ESP32: GPIO 32/33 have internal pull-ups
  const uint8_t DAH_PIN = 33;
#else
  const uint8_t DIT_PIN = 4;    // S3, C3 and friends
  const uint8_t DAH_PIN = 5;
#endif

// ---------------------------------------------------------------------------

// Restarting advertising after a disconnect. The library normally does this
// itself; this is a backstop so the paddle always comes back.
#if defined(USE_NIMBLE)
  #include <NimBLEDevice.h>
  #define RESTART_ADVERTISING() NimBLEDevice::startAdvertising()
#else
  #include <BLEDevice.h>
  #define RESTART_ADVERTISING() BLEDevice::startAdvertising()
#endif

BleKeyboard bleKeyboard(DEVICE_NAME, MANUFACTURER, 100);

struct Paddle {
  const char *name;
  uint8_t pin;
  uint8_t key;
  bool down;            // what we last told the host
  uint32_t lastChange;  // millis() of the last reported change
};

Paddle paddles[] = {
  {"dit", DIT_PIN, DIT_KEY, false, 0},
  {"dah", DAH_PIN, DAH_KEY, false, 0},
};

bool wasConnected = false;
uint32_t connectedAt = 0;
uint32_t disconnectedAt = 0;
bool advertisingKickPending = false;

void setLed(bool on) {
#ifdef LED_BUILTIN
  digitalWrite(LED_BUILTIN, on ? HIGH : LOW);
#endif
}

void forgetKeyStates() {
  // After a (re)connect the host knows no keys are down, so start fresh.
  // A paddle that's held closed gets pressed again on the next loop.
  for (Paddle &p : paddles) {
    p.down = false;
    p.lastChange = 0;
  }
}

void handleConnectionChanges() {
  bool connected = bleKeyboard.isConnected();
  if (connected == wasConnected) return;

  wasConnected = connected;
  forgetKeyStates();
  setLed(connected);

  if (connected) {
    connectedAt = millis();
    advertisingKickPending = false;
    Serial.println("Connected");
  } else {
    disconnectedAt = millis();
    advertisingKickPending = true;
    Serial.println("Disconnected, waiting to reconnect");
  }
}

void kickAdvertisingIfNeeded() {
  if (advertisingKickPending && millis() - disconnectedAt > 1000) {
    RESTART_ADVERTISING();
    advertisingKickPending = false;
  }
}

void scanPaddles() {
  uint32_t now = millis();

  for (Paddle &p : paddles) {
    bool closed = digitalRead(p.pin) == LOW;  // INPUT_PULLUP: closed pulls to GND
    if (closed == p.down) continue;

    // Report the first edge straight away, then ignore chatter for a bit.
    if (p.lastChange != 0 && now - p.lastChange < DEBOUNCE_MS) continue;

    p.down = closed;
    p.lastChange = now;
    if (closed) {
      bleKeyboard.press(p.key);
    } else {
      bleKeyboard.release(p.key);
    }
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(DIT_PIN, INPUT_PULLUP);
  pinMode(DAH_PIN, INPUT_PULLUP);
#ifdef LED_BUILTIN
  pinMode(LED_BUILTIN, OUTPUT);
#endif
  setLed(false);

  bleKeyboard.begin();
  Serial.printf("%s advertising. Dit on GPIO %d, dah on GPIO %d\n",
                DEVICE_NAME, DIT_PIN, DAH_PIN);
}

void loop() {
  handleConnectionChanges();

  if (!bleKeyboard.isConnected()) {
    kickAdvertisingIfNeeded();
    delay(10);
    return;
  }

  if (millis() - connectedAt < CONNECT_SETTLE_MS) return;

  scanPaddles();
  delay(1);  // ~1 kHz scan, keeps the watchdog and BLE stack happy
}
