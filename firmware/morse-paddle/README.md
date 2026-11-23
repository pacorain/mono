# Morse paddle Bluetooth keyboard

An ESP32 that pairs as a Bluetooth keyboard. Dit holds `[`, dah holds `]`, for as long as each side of the paddle is closed. The keys, pins and device name are at the top of `morse_paddle_ble/morse_paddle_ble.ino`.

## Wiring

1. Beep out the TRS pigtail with a multimeter to find which wire is tip, ring and sleeve (the colors aren't standard).
2. Solder them to the board:

| Plug | Paddle | Classic ESP32 | S3 / C3 |
|---|---|---|---|
| Tip | dit | GPIO 32 | GPIO 4 |
| Ring | dah | GPIO 33 | GPIO 5 |
| Sleeve | common | GND | GND |

No resistors needed: the sketch turns on the chip's internal pull-ups. An ESP32-S2 won't work, since it has no Bluetooth.

## Flashing (Arduino IDE)

1. **Board support:** in Boards Manager, install "esp32 by Espressif" version **2.0.17** (see the note below about 3.x).
2. **Library:** download the ZIP of ESP32-BLE-Keyboard from its GitHub releases page (T-vK/ESP32-BLE-Keyboard) and add it with Sketch > Include Library > Add .ZIP Library.
3. **Board:** pick ESP32 Dev Module, ESP32S3 Dev Module or ESP32C3 Dev Module to match yours. On an S3 or C3 using its built-in USB port, set "USB CDC On Boot" to Enabled if you want the serial monitor.
4. **Upload:** open `morse_paddle_ble.ino` and upload. If it won't connect, hold BOOT while it starts uploading.
5. **Pair:** on your computer, pair with "Morse Paddle" in Bluetooth settings. Open the serial monitor at 115200 to see connect and disconnect messages.

With arduino-cli instead:

```
arduino-cli core install esp32:esp32@2.0.17 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install --zip-path ESP32-BLE-Keyboard.zip
arduino-cli compile --fqbn esp32:esp32:esp32 morse_paddle_ble
arduino-cli upload --fqbn esp32:esp32:esp32 -p /dev/cu.usbserial-XXXX morse_paddle_ble
```

(`--zip-path` needs `arduino-cli config set library.enable_unsafe_install true` once. Swap the FQBN for `esp32:esp32:esp32s3` or `esp32:esp32:esp32c3`.)

## Core 3.x compile error

The library hasn't been updated for ESP32 Arduino core 3.x, which changed the built-in BLE library to take Arduino `String` instead of `std::string`. On 3.x you'll get errors like `no matching function for call to 'BLEDevice::init(std::string&)'` from `BleKeyboard.cpp`. Three ways out, easiest first:

1. **Stay on core 2.0.17.** Nothing to change.
2. **Use NimBLE.** Install the NimBLE-Arduino library **version 1.4.x** (2.x changed its API and breaks this library), then uncomment `#define USE_NIMBLE` at the top of the library's `BleKeyboard.h`. NimBLE is lighter on flash and RAM too, and the sketch handles it automatically.
3. **Patch the library.** In `BleKeyboard.cpp`, wrap the `std::string` arguments to `BLEDevice::init(...)` and the `setValue(...)` calls in `String(x.c_str())`.

## Tuning

- **Doubled dits:** raise `DEBOUNCE_MS` from 5 to 10.
- **Paddle backwards:** swap `DIT_KEY` and `DAH_KEY`.
- **Trainer wants Ctrl keys:** use `KEY_LEFT_CTRL` and `KEY_RIGHT_CTRL` (commented in the sketch).
- **Won't reconnect after sleep:** remove "Morse Paddle" from your computer's Bluetooth list and pair again. The sketch restarts advertising on every disconnect, so the paddle itself keeps trying.
