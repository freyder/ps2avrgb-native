# ps2avrGB Native development

Read README.md and docs/PROTOCOL.md (and the maintainer's local, unpublished
docs/HANDOFF.md if present) before changing this application.
Preserve existing Bootmapper and verified original device backups.
Keep protocol/document logic independent of Qt; CLI and GUI use one backend.
Never issue arbitrary HID GET_REPORT lengths: 101 toggles bootmapper mode.
Version 0.2 supports explicitly requested bounded keymap programming on the
verified original ps2avrGB 1.5.0 variant 0 only. Keep writes strictly within
0x6600..0x67FF and validate same-port bootloader identity and 128-byte/32KB
geometry. Every write needs a verified fresh backup, receipt and post-write
keymap/macro/options comparison. Never silently fall back to arbitrary firmware
or bootloader writes. Do not rerun live flash tests merely to repeat a passing
check; hardware test receipts live in the local docs/HANDOFF.md.
Do not treat internal firmware key indices as standard USB usages above 101.
Run `python3 -m unittest discover -s tests -v` and the offscreen Qt test for changes.
Keep `ruff check .` and `ruff format --check .` clean (config in pyproject.toml);
every public function/class in `ps2avrgb/` needs a docstring.
Never use `assert` for runtime or safety checks: `python -O` removes asserts.
Raise an explicit exception instead.
Document physical testing separately from mocks and cross-platform aspirations.
