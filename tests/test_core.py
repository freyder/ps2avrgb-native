import tempfile
import unittest
from pathlib import Path

from ps2avrgb import documents, keys, protocol


def fixture():
    raw = bytearray(53)
    raw[0] = 53
    raw[44:47] = bytes([1, 5, 0])
    info = protocol.Info.decode(bytes(raw))
    return documents.snapshot(
        {
            "device": {},
            "options": info.as_dict(),
            "keymap": [bytes(range(120)).hex()] * 4,
            "macros": {
                "flash": [bytes(168).hex()] * 12,
                "quick": [bytes(48).hex()] * 12,
                "quick_extra": [bytes(28).hex()] * 12,
                "dual_action": bytes(128).hex(),
            },
        }
    )


class CoreTests(unittest.TestCase):
    def test_physical_wide_key_mapping(self):
        from ps2avrgb.layout import matrix_position

        self.assertEqual(matrix_position(3, 4, True), (3, 5))
        self.assertEqual(matrix_position(3, 5, True), (3, 5))
        self.assertEqual(matrix_position(3, 4, False), (3, 4))
        with self.assertRaises(ValueError):
            matrix_position(3, 6, True)

    def test_firmware_indices_not_usb_usages(self):
        self.assertEqual(keys.parse_key("F13"), 145)
        self.assertEqual(keys.parse_key("F24"), 156)
        self.assertEqual(keys.parse_key("LeftShift"), 104)
        self.assertEqual(keys.parse_key("ScrollLock"), 71)
        self.assertNotEqual(keys.parse_key("F15"), keys.parse_key("ScrollLock"))

    def test_edit_is_copy_only_and_uses_row_major(self):
        original = fixture()
        edited = documents.set_key(original, 2, 3, 4, 145)
        self.assertEqual(bytes.fromhex(edited["keymap"][2])[28], 145)
        self.assertEqual(bytes.fromhex(original["keymap"][2])[28], 28)
        self.assertEqual(edited["macros"], original["macros"])
        with self.assertRaises(ValueError):
            documents.set_key(original, 4, 0, 0, 4)

    def test_tamper_and_geometry_detection(self):
        data = fixture()
        data["keymap"][0] = "00"
        with self.assertRaises(ValueError):
            documents.validate(data)
        data["sha256"] = documents.checksum(data)
        with self.assertRaises(ValueError):
            documents.validate(data)
        with self.assertRaises(ValueError):
            protocol.Info.decode(bytes(53))

    def test_hex_addresses_checksums_and_eof(self):
        text = documents.intel_hex(fixture())
        lines = text.splitlines()
        self.assertEqual(lines[-1], ":00000001FF")
        self.assertEqual(bytes.fromhex(lines[0][1:])[1:3], bytes([0x66, 0]))
        raw = b""
        for line in lines:
            record = bytes.fromhex(line[1:])
            self.assertEqual(sum(record) & 255, 0)
            if record[3] == 0:
                raw += record[4:-1]
        self.assertEqual(len(raw), 480)
        self.assertEqual(raw, bytes(range(120)) * 4)

    def test_read_whitelist_blocks_mutating_get(self):
        k = protocol.Keyboard()
        k.info = protocol.Info.decode(bytes.fromhex(fixture()["options"]["raw"]))

        class Fake:
            def get_feature_report(self, report, selector):
                return bytes(120)

        k.handle = Fake()
        with self.assertRaises(ValueError):
            k._read(101, 1)
        with self.assertRaises(ValueError):
            k._read(132, 132)
        with self.assertRaises(ValueError):
            k._read(100, 120)
        with self.assertRaises(ValueError):
            k._read(150, 128)
        self.assertEqual(len(k._read(121, 120)), 120)

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "backup.json"
            data = fixture()
            documents.save(data, path)
            self.assertEqual(documents.load(path), data)

    def test_cli_offline_no_hardware_import_required(self):
        from ps2avrgb.cli import main

        with tempfile.TemporaryDirectory() as folder:
            a = Path(folder) / "a.json"
            b = Path(folder) / "b.json"
            documents.save(fixture(), a)
            self.assertEqual(
                main(
                    [
                        "set-key",
                        str(a),
                        "--layer",
                        "0",
                        "--row",
                        "0",
                        "--column",
                        "0",
                        "--key",
                        "F23",
                        "--output",
                        str(b),
                    ]
                ),
                0,
            )
            self.assertEqual(bytes.fromhex(documents.load(b)["keymap"][0])[0], 155)
            self.assertEqual(bytes.fromhex(documents.load(a)["keymap"][0])[0], 0)


if __name__ == "__main__":
    unittest.main()


class FakeKeyboard(protocol.Keyboard):
    """In-memory keyboard; ``flip`` changes one keymap byte on the second read pass."""

    def __init__(self, flip=False):
        super().__init__()
        raw = bytearray(53)
        raw[0] = 53
        raw[44:47] = bytes([1, 5, 0])
        self.info = protocol.Info.decode(bytes(raw))
        self.identity = {}
        self.flip = flip
        self.keymap_reads = 0

    def _read(self, selector, expected):
        if selector in range(121, 125):
            self.keymap_reads += 1
            if self.flip and self.keymap_reads == 5:  # first layer of the second pass
                return bytes([1]) + bytes(expected - 1)
        return bytes(expected)


class ReadStateTests(unittest.TestCase):
    def test_consistent_double_read_is_accepted(self):
        state = FakeKeyboard().read_state()
        self.assertEqual(len(state["keymap"]), 4)

    def test_inconsistent_double_read_raises_even_under_python_O(self):
        # Regression: this check used `assert`, which `python -O` removes.
        with self.assertRaises(RuntimeError):
            FakeKeyboard(flip=True).read_state()
