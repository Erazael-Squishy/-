# Third-party licences

How each kind of licence is used: [ADR 0011](docs/adr/0011-third-party-code-and-licenses.md).
**Verified** means we read the licence in the package or repository on the date shown.
Add a row in the same commit that adds a dependency.

## In the app (all verified 2026-10-21 from each package's `package.json`)

| Component | Version | Licence | Use |
| --- | --- | --- | --- |
| [rp2040js](https://github.com/wokwi/rp2040js) | 1.4.1 | MIT | RP2040 emulator (ADR 0001) |
| [avr8js](https://github.com/wokwi/avr8js) | 0.21.1 | MIT | ATmega328P emulator (Arduino UNO) |
| RP2040 bootrom data (from [raspberrypi/pico-bootrom](https://github.com/raspberrypi/pico-bootrom), via rp2040js `demo/bootrom.ts`) | B1 | BSD-3-Clause (data), MIT (rp2040js file) | `src/emulator/rp2040/bootrom.ts`, with attribution |
| React, React DOM | 19.3.1 | MIT | UI |
| zustand | 5.0.15 | MIT | UI state |
| zod | 4.6.7 | MIT | Project file validation (ADR 0010) |
| CodeMirror (`codemirror` 6.0.2, `@codemirror/state` 6.7.6, `view` 6.43.15, `language` 6.13.1, `lang-python` 6.2.1, `lang-cpp` 6.0.3, `lint` 6.9.7, `autocomplete` 6.20.4), `@lezer/highlight` 1.2.5 | see left | MIT | Code editor, compiler errors in the code, code suggestions |
| `@xterm/xterm` 6.0.0, `@xterm/addon-fit` 0.11.0 | see left | MIT | REPL terminal |
| Electron | 45.0.0 | MIT | Desktop app (ADR 0009) |

## The RP2350 (Pico 2) emulator, in all three versions (verified 2026-10-22 from the NuGet packages)

Built from `native/rp2350` by `npm run build:rp2350` into `public/rp2350/`, which ships inside
the browser file, the Windows app and the Android app.

| Component | Version | Licence | Use |
| --- | --- | --- | --- |
| [RP2350Sharp](https://github.com/PyMCU/RP2350Sharp) (Iván Montiel Cardona) | 1.2.0 | **Business Source License 1.1**, with an Additional Use Grant: free to use, copy and redistribute, also in production, **except for a fee or other commercial consideration** (that needs a commercial licence). Becomes **MIT on 2030-10-14** | The RP2350 emulator (ADR 0002) |
| …inside it: parts derived from rp2040js (Uri Shaked) | — | MIT | its USB, GDB and (by reference) PIO code |
| …inside it: the RP2350 boot ROM (Raspberry Pi Ltd), with sweet-b (Western Digital) | A2 | BSD-3-Clause | the chip's own ROM, run by the emulator |
| SiliconTwin.Abstractions (Silicon Twin) | 0.1.0 | MIT | RP2350Sharp's interfaces |
| .NET runtime for WebAssembly (Mono, System.Private.CoreLib and the libraries above; .NET Foundation) | 10.0.13 | MIT | runs RP2350Sharp in the browser |
| Emscripten-generated glue (`dotnet.native.js`) | 3.1.56 | MIT / University of Illinois NCSA | part of the .NET WebAssembly runtime |

RP2350Sharp's licence and its third-party notices go with every copy, as its NOTICE asks:
`RP2350Sharp-LICENSE.txt` and `RP2350Sharp-NOTICE.txt` next to the emulator in each version, and
in the release zip's `licencje/` folder. Checked in the package: RP2350Sharp has no HTTP client and
no licence or entitlement check (the "entitlement check" its licence mentions is in other
editions, for private CI systems); it reads only its own `EMU_STRICT*` diagnostics settings, and
its sockets serve its optional GDB server, which MicroLab never starts (and which can't run in
WebAssembly). MicroLab uses it for private, non-commercial use, as you decided (ADR 0002).

Build tools, on this computer only: the .NET 10 SDK 10.0.402 and its wasm-tools workload (MIT;
Emscripten MIT/NCSA, LLVM Apache-2.0 with LLVM exception, Node.js MIT, Python PSF), from
Microsoft, SHA-512-checked (`npm run setup:dotnet`); run with telemetry off.

## The ESP32 emulator, in the Windows app only (verified 2026-10-22)

Put together by `npm run build:esp32` into `build/esp32/`, installed next to the app as
`resources/esp32/`. These are **separate programs**: MicroLab starts `microlab-esp32-host.exe` and
talks to it through a named pipe (ADR 0004); nothing of them is linked into MicroLab.

| Component | Version | Licence | Use |
| --- | --- | --- | --- |
| QEMU with lcgamboa's ESP32 changes ([lcgamboa/qemu](https://github.com/lcgamboa/qemu), branch `picsimlab-esp32`), as `libqemu-xtensa.dll` built and shipped by [PICSimLab](https://github.com/lcgamboa/picsimlab) 0.9.3 | from PICSimLab 0.9.3 (`PICSimLab_0.9.3_260920_w64-dev.zip`, SHA-256 `9a3563ac…e101a25`; the same file as in its `win64.zip`) | **GPL-2.0** (QEMU; some parts LGPL-2.1 / BSD / MIT, see QEMU's `LICENSE`) | the ESP32 itself |
| The same QEMU with the fork's ESP32-C3 changes, as `libqemu-riscv32.dll` from the same release, unmodified | from PICSimLab 0.9.3 (the same archive) | **GPL-2.0** (as above) | the ESP32-C3 itself |
| `microlab-esp32-host.exe`, from `native/esp32-host/host.c` (written for MicroLab) | — | **GPL-2.0-or-later** | runs one ESP32 or ESP32-C3 and serves the pipe |
| MinGW-w64 DLLs from the same release: GLib, libintl (gettext), libiconv, libgcrypt, libgpg-error (LGPL-2.1), zlib (zlib), winpthreads (MIT/BSD), PCRE2 (BSD-3-Clause) | as in that release | see left | what the QEMU libraries need |
| ESP32 and ESP32-C3 boot ROM images `esp32-v3-rom.bin`, `esp32-v3-rom-app.bin`, `esp32c3-rom.bin` (Espressif, as distributed with Espressif's QEMU and PICSimLab) | — | Espressif's, redistributed with QEMU for emulation | the chips' own ROM, run by the emulator |
| **MicroPython 1.29.0 for ESP32** (`ESP32_GENERIC-20260824-v1.29.0.bin`) from micropython.org, SHA-256-checked (`firmware/manifest.json`, `esp32`) | 1.29.0 | MIT (MicroPython); ESP-IDF inside it Apache-2.0 | the board's stock firmware |
| **MicroPython 1.29.0 for ESP32-C3** (`ESP32_GENERIC_C3-20260824-v1.29.0.bin`) from micropython.org, SHA-256-checked (`firmware/manifest.json`, `esp32`) | 1.29.0 | MIT (MicroPython); ESP-IDF inside it Apache-2.0 | the ESP32-C3 SuperMini's stock firmware |

**MicroLab's change to the QEMU library.** One constant: in `hw/nvram/esp32_efuse.c`,
`esp32_efuse_op_timer_start`, the eFuse operation time `interval_ns` is 10 000 ns instead of
100 000 000 ns (100 ms; the source's own comment says 10 ms). A real ESP32 reads its eFuses in
microseconds; at 100 ms the boot ROM and ESP-IDF spend about 20 s of wall time polling. The patch
is 4 bytes at file offset `0x13280d` of the library with SHA-256 `276d656d…56db5b1e`, applied by
`scripts/build-esp32.mjs` only to that exact file, and written down in `SOURCES.txt` next to it.
The host also maps plain memory over the fork's unimplemented RTC IO registers through QEMU's own
memory API at run time (so pull-ups set by the firmware hold, as on the chip), keeps the ESP32's
GPIO32–39 output and enable registers the fork ignores (so GPIO32 and 33 drive), gives the
ESP32-C3's IO MUX its reset pull-ups, and reads the GPIO pin registers (open drain) from the fork's
state; the library files aren't changed for that. `libqemu-riscv32.dll` is shipped as it comes.

**Sources.** QEMU and the ESP32 changes: the repository above (GPL-2.0 §3: the corresponding
source is published there; this private, non-commercial copy passes that on). The host's source
goes with every copy (`source/host.c` next to it, and in the release zip's `licencje/`), with
`COPYING-GPL-2.0.txt` and `SOURCES.txt`. MicroLab uses all this for private, non-commercial use,
as you decided.

Build tools, on this computer only: **Zig** 0.17.0 (MIT; its bundled MinGW-w64 headers and libs
under their own permissive licences) from ziglang.org, SHA-256-checked (`npm run setup:zig`),
compiles the host.

## Build and test tools

| Component | Version | Licence |
| --- | --- | --- |
| Vite, `@vitejs/plugin-react` | 8.3.5, 6.1.2 | MIT |
| TypeScript | 7.0.2 | Apache-2.0 |
| Vitest | 5.0.5 | MIT |
| [eecircuit-engine](https://github.com/eelab-dev/EEcircuit-engine) (spike: ngspice in WASM as test reference) | 1.8.0 | MIT |
| ngspice (inside eecircuit-engine) | as bundled | BSD-3-Clause (main licence; check bundled parts when pinned) |
| uf2, tsx (spikes) | 1.0.0, 4.19.3 | MIT |

## In the Windows app and the Android app

- **Electron** 45.0.0 (MIT; contains Chromium, BSD-style and others, see `LICENSES.chromium.html`
  in the installed app), packed by **electron-builder** 26.17.0 (MIT) into an **NSIS** installer
  (zlib/libpng licence for the installer stub).
- **Capacitor** 8.5.3 core, Android runtime, Filesystem 8.1.4 and Share 8.0.3 plugins (MIT), with
  the **AndroidX** libraries they use (Apache-2.0), in the APK.

Build tools for those, installed on this computer and not shipped: Microsoft Build of OpenJDK 21
(GPL-2.0 with the Classpath Exception), Android SDK command-line tools, platform 36, build-tools
36.0.0 and platform-tools (Android Software Development Kit License Agreement, accepted by you),
Gradle 8.14.3 (Apache-2.0), Android Gradle Plugin (Apache-2.0).

## Downloaded by the app, not bundled

**MicroPython 1.29.0 for the Pico** (MIT): fetched from micropython.org by
`scripts/fetch-firmware.mjs`, SHA-256-checked, never committed.

**MicroPython 1.29.0 for the Pico W** (`RPI_PICO_W-20260824-v1.29.0.uf2`): fetched and checked the
same way. MicroPython itself is MIT, but this build contains Raspberry Pi's **cyw43-driver** and
Infineon's **CYW43439 Wi-Fi firmware** (a binary the driver uploads to the chip; MicroLab keeps it
but never runs it). The cyw43-driver licence allows free use with Raspberry Pi RP-series
microcontrollers and otherwise only non-commercial use; running it on an *emulated* RP2040 isn't
clearly covered. Fine for learning and personal projects; **review it before any commercial use
of MicroLab** (or ship without the Pico W firmware).

**MicroPython 1.29.0 for the Pico 2** (`RPI_PICO2-20260824-v1.29.0.uf2`, MIT): fetched and checked
the same way.

**MicroPython 1.29.0 for the Pico 2 W** (`RPI_PICO2_W-20260824-v1.29.0.uf2`): fetched and checked the
same way. As the Pico W's, it contains Raspberry Pi's cyw43-driver and Infineon's CYW43439 firmware
(kept by MicroLab, never run); the Pico 2 W's RP2350 is an RP-series microcontroller, which that
licence covers. The same note as for the Pico W applies to any commercial use.

**Test fixture `blink.uf2`** (Raspberry Pi pico-examples, BSD-3-Clause): fetched from
datasheets.raspberrypi.com by the same script into `test-fixtures/`, SHA-256-checked, never committed.

**MicroPython drivers** you can add to a project (copied into your project's files when you
choose them), fetched by the same script into `public/libs/micropython/`, SHA-256-checked:

- `ssd1306.py` from micropython-lib v1.29.0 (MIT, micropython-lib's default licence).
- `lcd_api.py`, `machine_i2c_lcd.py` from dhylands/python_lcd at commit 7affb0b (MIT, © Dave Hylands).
- `sdcard.py` from micropython-lib v1.29.0 (MIT).
- `sh1106.py` from robert-hh/SH1106 at commit fe67423 (MIT, © Radomir Dopieralski, Robert Hammelrath).
- `tm1637.py` from mcauser/micropython-tm1637 at commit cc9ecc6 (MIT, © Mike Causer).
- `max7219.py` from mcauser/micropython-max7219 at commit 22195dc (MIT, © Mike Causer).
- `ili9341.py`, `xglcd_font.py` from rdagger/micropython-ili9341 at commit 67c5131 (MIT, the
  repository's licence; the files carry no header).

**Arduino libraries**, installed with the toolchain from the Arduino library index and compiled
into your own sketch on your computer (not shipped with MicroLab). Licences as read from each
installed package (2026-10-22):

- LiquidCrystal I2C 1.1.2 (Frank de Brabander; no licence file in the package)
- Adafruit SSD1306 2.5.17, Adafruit GFX Library 1.13.0, Adafruit SH110X 2.1.15, Adafruit ILI9341
  1.7.0 (BSD)
- Adafruit ST7735 and ST7789 Library 1.12.0 (MIT, in its source headers)
- Adafruit BusIO 1.17.4 (MIT), DHT sensor library 1.4.7 (MIT), LedControl 1.0.6 (MIT, © Eberhard Fahle)
- Adafruit Unified Sensor 1.1.15 (Apache-2.0)
- Servo 1.3.0 and Stepper 1.1.3 (LGPL-2.1), Adafruit NeoPixel 1.15.5 and TM1637 1.2.0 (Avishay
  Orpaz; LGPL-3.0)
- Pulled in as dependencies of the display libraries, not used by MicroLab's parts: Adafruit
  TouchScreen 1.1.6, Adafruit TSC2007 1.1.2 (BSD), Adafruit STMPE610 1.1.6 (MIT), Adafruit seesaw
  Library 1.7.9 (BSD; its NeoPixel part LGPL-3.0)
- SD 1.3.0 and AccelStepper 1.64 (Mike McCauley; GPL-3.0, or a commercial licence from him):
  compiled into your own sketch on your computer; if you distribute that sketch's binary, GPL
  terms apply to it, which is your choice, not MicroLab's.

**Arduino toolchain**, installed once by `npm run setup:arduino` into a per-user folder
(`%LOCALAPPDATA%\MicroLab\toolchains`), then used offline:

- arduino-cli 1.5.1 (GPL-3.0): from its GitHub release, checked against the release's
  checksum file; run as a separate program, never linked.
- Arduino AVR core (`arduino:avr`, LGPL-2.1 core libraries) with avr-gcc 7.3.0 (GPL-3.0 with the
  GCC runtime library exception) and avrdude (GPL-2.0): installed by arduino-cli from
  downloads.arduino.cc. They build your own sketch; nothing of theirs is shipped with MicroLab.

Planned the same way (ADR 0008):

- Pico SDK (BSD-3-Clause)
- ESP-IDF (Apache-2.0)
- arduino-pico and arduino-esp32 (LGPL-2.1)
- Arm GNU Toolchain and GDB (GPL)
- Rust toolchains (MIT/Apache-2.0)
- TinyGo (BSD-3-Clause)
- clangd (Apache-2.0 with LLVM exception)
- rust-analyzer (MIT/Apache-2.0)
- gopls (BSD-3-Clause)

## Planned (decided in the ADRs, not added yet)

| Component | Licence | Use | Notes |
| --- | --- | --- | --- |
| Pyright, micropython-stubs, circuitpython-stubs | MIT | Editor types | |
| littlefs | BSD-3-Clause | Building MicroPython filesystem images | |
| Playwright, axe-core | Apache-2.0 / MPL-2.0 | UI and accessibility tests | |
| lcgamboa QEMU fork, RISC-V (`libqemu-riscv32`) | GPL-2.0 (+ LGPL-2.1 parts) | ESP32-C3 as a **separate process** (ADR 0004), like the ESP32 above | |
| MicroPython WASM port; Adafruit Blinka, Pyodide | MIT; MIT / MPL-2.0 | Interpreter / API tiers | |
| Fritzing parts | CC-BY-SA 3.0 | Breadboard art and pin positions | Keep attribution per part |

## Datasheets the models cite

Linked from the inspector, not redistributed: Raspberry Pi RP2040 and Pico datasheets, Kingbright
L-53L series, Vishay 1N4148 and 1N4001–1N4007, Omron B3F, Bourns 3386, Energizer E91, Microchip
ATmega328P (DS40002061A), Arduino UNO R3 datasheet and reference schematic (CC-BY-SA 4.0; cited,
not copied), Solomon Systech SSD1306, Hitachi HD44780U, TI PCF8574, Worldsemi WS2812B, Kingbright
L-154A4SUREQBFZGEW and SC56-11SURKWA, Senba GL55 series, Elecfreaks HC-SR04, Aosong AM2302,
Fairchild PN2222A, Infineon IRLZ44N, Mabuchi FA-130RA, TMB12A05 buzzer (Electrokit), TowerPro
micro servo (Adafruit product page), Kingbright WP7113ND / WP7113QBC/D / WP7113QWC/D, AMS1117,
TI SN74LVC125A; SD Association Physical Layer and File System Simplified Specifications (cited;
the FAT code in `src/storage/fat.ts` was written for MicroLab from Microsoft's published FAT
specification, nothing copied); Raspberry Pi Pico W and Pico 2 W datasheets; IEEE 802.11-2020 (cited for the
WPA2 passphrase and SSID lengths); Sinowealth SH1106, Titan Micro TM1637, Maxim MAX7219,
Kiatronics 28BYJ-48, TI ULN2003A, STMicroelectronics L298, Ilitek ILI9341, Sitronix ST7735R;
Espressif ESP32 Series datasheet v5.3, ESP32-WROOM-32E datasheet v2.1 and the ESP32-DevKitC V4
schematic; Diodes Inc. BAT760.

Register addresses and bits the ESP32 code uses (GPIO matrix signals, IO MUX fields, RTC IO pad
pulls and their reset values) were looked up in ESP-IDF's `soc/esp32` headers (Apache-2.0) and the
ESP32 TRM; written as MicroLab's own tables, no file copied.

The network in `src/net` (Ethernet, ARP, IPv4, ICMP, UDP, TCP, DHCP, DNS, NTP, HTTP) was written
for MicroLab from the RFCs (826, 791, 792, 768, 793, 2131, 1035, 5905, 9110). The CYW43439 model
in `src/emulator/cyw43` was written for MicroLab to answer what the cyw43-driver in the official
firmware expects on the gSPI bus (registers, SDPCM frames, ioctls, events); no code was copied
from cyw43-driver, Infineon's WHD or Linux's brcmfmac.

The HD44780 character patterns in `src/catalog/fonts/hd44780.ts` were drawn for MicroLab after
the shapes shown in the HD44780U datasheet; no font file was copied.
See `src/models/sources.ts`.

## Read for reference only, no code copied

Falstad CircuitJS (GPL-2.0), Velxio (AGPL-3.0), PICSimLab (GPL-2.0), RP2040Sharp (BUSL-1.1),
lcgamboa's QEMU ESP32 device models (GPL-2.0: read to learn the callback API and register
behaviour the host and `src/emulator/esp32` talk to).
