# ps2avrGB Native

Python/Qt replacement project for Bootmapper's AIR/Wine interface, with one
shared device backend for the CLI and desktop GUI.

**Version 0.2: verified keymap programming, CLI and Qt editor.**

The 23-key physical view has one double-wide bottom-right key. A separate
firmware matrix view exposes every stored position. The on-screen key picker
provides standard keys, F13-F24, modifiers, media functions, layers and macros.
Assignments edit the snapshot until you explicitly choose **Write keymap**.

Hardware keymap programming has been verified on the author's ps2avrGB 1.5.0 variant 0
using Linux HIDAPI/libusb. It writes only the four pages at 0x6600-0x67FF,
automatically backs up the connected keyboard, reboots and checks readback.
Other firmware variants, Windows/macOS flashing and full firmware replacement
are not enabled. No bootloader image is written. RGB/macro editing is future work;
existing macro/dual-action regions are backed up and checked after keymap writes.

## Run

After installing (see below):

```sh
ps2avrgb list
ps2avrgb keys
ps2avrgb info
ps2avrgb backup ~/Backups/ps2avrgb/my-keyboard.json
ps2avrgb gui ~/Backups/ps2avrgb/my-keyboard.json
ps2avrgb show ~/Backups/ps2avrgb/my-keyboard.json --layer 0
ps2avrgb show ~/Backups/ps2avrgb/my-keyboard.json --layer 1 --json
ps2avrgb set-key ~/Backups/ps2avrgb/my-keyboard.json \
  --layer 0 --row 2 --column 3 --key F23 --output ~/Backups/ps2avrgb/edited.json
ps2avrgb export-hex ~/Backups/ps2avrgb/edited.json ~/Backups/ps2avrgb/keymap.hex
```

Coordinates are zero based. `set-key` changes the output FILE, not the keyboard.
Keep the original snapshot. Backup refuses an existing output filename; set-key
refuses to overwrite its input. JSON errors go to stderr with nonzero exit.
Use `--device PATH` before the subcommand if multiple matching keyboards exist.

For a portable source install, use Python 3.10+ and `pip install .` in a virtual
environment. Linux HID access requires the device-specific rule in `packaging/`;
that grants the active local desktop user access, rather than chmod 0666.
Qt is loaded only for `gui`; scripts can run all other commands without a
display server.

## Program a keymap

```sh
# Preview only: does not open the keyboard or enter its bootloader.
ps2avrgb flash-keymap ~/Backups/ps2avrgb/edited.json
# Apply: backup -> bootloader -> four keymap pages -> reboot -> double-read verification.
ps2avrgb flash-keymap ~/Backups/ps2avrgb/edited.json --apply
```

In the GUI, click a keypad key and choose a function from the on-screen picker.
Changed keys are highlighted; **Undo** reverses the latest assignment, including
edits on other layers. **Review changes…** lists the before/after assignments
under Show Details. Then click **Write keymap to keyboard…**. Saving an edited file is optional;
the programming transaction saves its target and original backup automatically.
The **Advanced** section exposes the raw firmware matrix and numeric key indices.
HEX export remains available along the bottom. Normal editing uses the 23-key physical view.
All firmware coordinates are zero based; the physical wide key maps to (3,5).
The firmware also supports FN/FN2/FN3 layer keys. These are distinct from the
128-byte flash storage pages. The current Normal layer has no FN key assigned.

The keypad briefly disconnects while in HIDBoot mode. Leave it connected during
writes. Linux bootloader uaccess is configured by the supplied udev rule.
`bootloader-probe SNAPSHOT` checks entry/geometry/exit without programming.
If a write fails, its error identifies the original backup and receipt. With
that same keypad on the same USB port, `ps2avrgb recover RECEIPT --apply` restores
the original keymaps from the receipt. Do not use a receipt for another device.
Recovery uses the tested write protocol but an interrupted hardware flash has
not been deliberately induced; the interrupted-write recovery branch has no
live fault-injection validation yet.

The standard uploader programs full 128-byte pages. The final page includes
32 reserved padding bytes before the macro partition; they are filled with FF.
Those padding bytes cannot be read through the application snapshot API and
are not presented as part of a complete firmware-image backup.

## Why Python + Qt

- PySide6 supplies a native desktop GUI on Linux, Windows and macOS.
- HIDAPI handles USB HID without an AIR runtime, Wine prefix or browser helper.
- The CLI calls exactly the same protocol/document code as the GUI.
- Transport, snapshot validation, key indices and presentation are separate.
- A browser UI would still require an OS/browser-dependent HID permission path
  or a separately installed local bridge. This desktop design has fewer pieces.

On Debian/Ubuntu-based systems the distribution packages `python3-hid` and
PySide6 are sufficient; no system Python replacement is needed.

## Verification

```sh
python3 -m unittest discover -s tests -v          # 21 tests, includes the offscreen Qt tests
QT_QPA_PLATFORM=offscreen python3 tests/test_gui.py
ruff check . && ruff format --check .             # lint + formatting, configured in pyproject.toml
```

Ruff is a development tool only; it isn't needed to run the application. It can
be installed in a throwaway virtual environment rather than system Python
(`python3 -m venv /tmp/lint && /tmp/lint/bin/pip install ruff`). Lint
rules are pyflakes/pycodestyle, import order, bugbear, pyupgrade (3.10),
simplify, comprehensions, Ruff's own rules and PEP 257 docstrings for the
`ps2avrgb` package. Code is formatted with `ruff format` at 100 columns.

Live device: winkeyless.kr ps2avrGB, VID:PID 20a0:422d, firmware **1.5.0**,
variant 0, four layers, 15 rows x 8 columns. HIDAPI control interface 1 reads
were verified as root and as a normal desktop user. All keymap/macro regions were
read twice and matched. Snapshot checksum verifies metadata and every captured
region; exports have Intel HEX record checksums. Physical tests included a
bootloader entry/exit probe, a same-keymap write and a changed-byte write followed
by restoration, each with read-back verification.

## Remaining work

1. Package/test other desktop platforms and controller variants.
2. Add RGB, macro and dual-action editors; key assignment to existing macro
   slots already exists in the picker.
3. Add more physical board layouts and test interrupted-write recovery.
4. Full firmware replacement is separate from keymap programming and would
   need image-identity validation and its own backup/recovery design.

See `docs/PROTOCOL.md`. Original firmware research is
retained separately under `research/` with its upstream GPL notice. The new
application is GPL-3.0-or-later. No firmware or AIR runtime is bundled.

## Public release preparation

The intended first release supports the tested 23-key winkeyless.kr keypad with
original ps2avrGB 1.5.0 firmware on Linux. The physical layout is a board profile,
not a claim that every ps2avrGB board has 23 keys. Other boards need their own
layout and hardware validation. Cross-platform Qt/file editing is a design goal;
Windows and macOS have not been physically tested.

A source installation uses the portable `ps2avrgb` entry point from
`pip install .`. Downloaded bootloader research is ignored by Git and excluded
from source distributions; it is not required to run the application. Installer
packaging and a first-use hardware walkthrough remain before describing it as a
polished public release.
