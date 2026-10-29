# Observed ps2avrGB protocol

Primary sources, accessed 2026-10-26:
- https://github.com/showjean/ps2avrU/blob/master/firmware/ps2avrGB/vusb.c
- https://github.com/showjean/ps2avrU/blob/master/firmware/ps2avrGB/options.h
- https://github.com/showjean/ps2avrU/blob/master/firmware/ps2avrGB/hardwareinfo.h
- https://github.com/showjean/ps2avrU/blob/master/source/keymap.h
- Original Bootmapper source (https://github.com/showjean/Bootmapper),
  `src/GBManager.as` and `MatrixParser.as`. These establish the helper
  architecture and row-major order.

This is not an escape-sequence/terminal protocol. The control interface uses
USB class GET_REPORT, feature report ID 1 (`wValue=0x0301`), interface 1.
Firmware dispatches commands by the requested report **length**. Returned data
is raw firmware bytes, not a guaranteed leading report-ID byte. HIDAPI on Linux
returns the raw bytes directly, including a short response relative to wLength.

| Request length | Response | Meaning |
| --- | --- | --- |
| 100 | 53 bytes on 1.5.0 | options / firmware metadata |
| 101 | side effect | **Toggles bootmapper mode; NEVER a read-only probe** |
| matrix-size + 1..4 | matrix-size bytes | four flash keymap layers |
| 150 | 128 bytes | dual-action region |
| 168..179 | 168 bytes each | twelve custom flash macros |
| 180..191 | 48 bytes each | twelve EEPROM quick macros |
| 192..203 | 28 bytes each | quick-macro extension regions |

Variant 0/2: 15x8 matrix, 120 bytes/layer, keymap flash 0x6600.
Variant 1/3: 17x8 matrix, 136 bytes/layer, keymap flash 0x6500.
Variant 4: 18x8 matrix, 144 bytes/layer, keymap flash 0x6500.
Only variant 0 has been tested on physical hardware. Recognized 1.5.x options
layout: size byte 0; version bytes 44..46; variant byte 47. Unknown layout or
variant is rejected, not guessed. Read-only operations never issue SET_REPORT. Keymap programming is isolated
in flashing.py and uses the verified bootloader protocol described below.

Matrix byte offset is row*8+column within each layer. Internal key indices are
NOT identical to HID usages above 101. Modifiers use 103..110. F13..F24 use
145..156, while ScrollLock is 71. Unknown byte values are preserved numerically.
Do not rewrite key indices using a generic HID usage table.

## Native keymap writing

Firmware stores key data in flash. Upstream BootloadHID sources:
https://www.obdev.at/products/vusb/bootloadhid.html
(source archive 2012-12-08 retained under research/bootloadHID).

Application entry request: feature ID 1, bytes 01 00 FF 00 00 00 00 00.
This clears EEPROM boot-start flag at address 1 and triggers the firmware's
LED exit/watchdog reset path. Only normal runtime variant 0, 1.5.0 is enabled.
Boot identity: 16c0:05df HIDBoot at the same physical USB port. GET feature ID 1
returns seven bytes: ID, 16-bit LE page size, 32-bit LE flash size. This unit
returns 128/32768. Writer rejects every other geometry.

Data packet: feature ID 2 + 24-bit LE address + 128 data bytes (132 total).
Allowed pages: 0x6600/0x6680/0x6700/0x6780 only. Final 32 bytes are reserved FF
padding, as in original Bootmapper's uploader. No writes reach code below
0x6600, dual action at 0x6580, macros at 0x6800 or bootloader at/above 0x7800.
Reboot: 7-byte feature-ID-1 report, then verify runtime reappears and all exposed
regions read back correctly. Live changed-byte + restoration test passed.

There is no temporary RAM-map operation established for this firmware; script
changes are persistent flash operations. CLI previews are default; --apply is
required to write. Original settings and private receipts are saved first.
