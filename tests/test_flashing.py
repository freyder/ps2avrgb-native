import unittest

from test_core import fixture

from ps2avrgb import flashing


class FlashTests(unittest.TestCase):
    def test_plan_preserves_hidden_key_and_bounds(self):
        data = fixture()
        plan = flashing.plan(data)
        self.assertEqual([b["address"] for b in plan["blocks"]], [0x6600, 0x6680, 0x6700, 0x6780])
        raw = b"".join(bytes.fromhex(b["data"]) for b in plan["blocks"])
        self.assertEqual(raw[:480], b"".join(bytes.fromhex(k) for k in data["keymap"]))
        self.assertEqual(raw[480:], b"\xff" * 32)
        self.assertEqual(plan["endExclusive"], 0x6800)

    def test_packet_header_little_endian_and_exact_size(self):
        data = flashing.packet(0x6680, bytes(128))
        self.assertEqual(data[:4], bytes([2, 0x80, 0x66, 0]))
        self.assertEqual(len(data), 132)
        for address in [0, 0x6580, 0x6601, 0x6800, 0x7800]:
            with self.assertRaises(ValueError):
                flashing.packet(address, bytes(128))
        with self.assertRaises(ValueError):
            flashing.packet(0x6600, bytes(127))

    def test_geometry_fail_closed(self):
        result = flashing.boot_info(bytes([1, 128, 0, 0, 128, 0, 0]))
        self.assertEqual(result["flashSize"], 32768)
        for raw in [bytes(7), bytes([1, 64, 0, 0, 128, 0, 0]), bytes([1, 128, 0, 0, 64, 0, 0])]:
            with self.assertRaises(ValueError):
                flashing.boot_info(raw)

    def test_port_identity(self):
        self.assertEqual(flashing.port("1-1.2.4:1.0"), "1-1.2.4")
        self.assertEqual(flashing.port("1-1.2.4:1.1"), "1-1.2.4")
        for path in ["/dev/hidraw2", "anything", "1-1.2.4"]:
            with self.assertRaises(ValueError):
                flashing.port(path)

    def test_short_transfer_is_failure(self):
        from unittest.mock import Mock

        loader = flashing.Bootloader("1-1.2.4")
        loader.info = {"applicationEnd": 0x7800}
        loader.handle = Mock()
        loader.handle.send_feature_report.return_value = 131
        with self.assertRaises(RuntimeError):
            loader.write(flashing.plan(fixture()))
        self.assertEqual(loader.handle.send_feature_report.call_count, 1)

    def test_incomplete_plan_is_rejected_before_io(self):
        from unittest.mock import Mock

        loader = flashing.Bootloader("1-1.2.4")
        loader.info = {"applicationEnd": 0x7800}
        loader.handle = Mock()
        bad = flashing.plan(fixture())
        bad["blocks"].pop()
        with self.assertRaises(ValueError):
            loader.write(bad)
        loader.handle.send_feature_report.assert_not_called()

    def test_writer_does_not_touch_bootloader_or_firmware(self):
        loader = flashing.Bootloader("1-1.2.4")
        loader.info = {"applicationEnd": 0x7800}

        class Fake:
            def __init__(self):
                self.sent = []

            def send_feature_report(self, data):
                self.sent.append(data)
                return len(data)

        loader.handle = Fake()
        loader.write(flashing.plan(fixture()))
        self.assertEqual(len(loader.handle.sent), 4)
        self.assertEqual(
            [int.from_bytes(p[1:4], "little") for p in loader.handle.sent],
            [0x6600, 0x6680, 0x6700, 0x6780],
        )


if __name__ == "__main__":
    unittest.main()
