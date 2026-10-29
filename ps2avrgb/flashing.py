"""Bounded BootloadHID keymap writes; never a whole-firmware/bootloader flasher."""

import contextlib
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

from . import documents, protocol

BOOT_VID, BOOT_PID = 0x16C0, 0x05DF
START, STOP = 0x6600, 0x6800


def port(path):
    """Return the physical USB port part of a Linux libusb HID path such as ``1-1.2.4:1.1``."""
    if not re.fullmatch(r"\d+-[\d.]+:\d+\.\d+", path):
        raise ValueError("Hardware writes currently require a verified Linux libusb port path")
    return path.split(":", 1)[0]


def boot_info(raw):
    """Decode the BootloadHID information report; reject any geometry except 128 B / 32 KB."""
    if len(raw) != 7 or raw[0] != 1:
        raise ValueError("Unexpected BootloadHID information report")
    page = int.from_bytes(raw[1:3], "little")
    size = int.from_bytes(raw[3:7], "little")
    if page != 128 or size != 32768:
        raise ValueError(f"Unvalidated bootloader geometry: page={page}, flash={size}")
    return {
        "pageSize": page,
        "flashSize": size,
        "applicationEnd": size - 2048,
        "raw": bytes(raw).hex(),
    }


def plan(data):
    """Build the four-page write plan for 0x6600..0x67FF from a validated snapshot.

    Only ps2avrGB 1.5.0 variant 0 is accepted. Nothing is sent to hardware.
    """
    documents.validate(data)
    info = data["options"]
    if info["variant"] != 0 or info["version"] != "1.5.0" or info["rows"] != 15:
        raise ValueError("Live programming is validated only for ps2avrGB 1.5.0 variant 0")
    raw = b"".join(bytes.fromhex(v) for v in data["keymap"])
    if len(raw) != 480:
        raise ValueError("Expected exactly 480 keymap bytes")
    # The keymap partition is 512 bytes, ending at the next fixed partition.
    # BootloadHID programs full 128-byte pages. Original Bootmapper fills the
    # unused final 32 bytes with FF; they are not macro or application code.
    payload = raw + b"\xff" * 32
    blocks = [
        {"address": a, "data": payload[a - START : a - START + 128].hex()}
        for a in range(START, STOP, 128)
    ]
    return {
        "start": START,
        "endExclusive": STOP,
        "keymapBytes": 480,
        "paddingBytes": 32,
        "paddingValue": 255,
        "pageSize": 128,
        "blocks": blocks,
    }


def packet(address, data):
    """Return one 132-byte BootloadHID data report, refusing any page outside the keymap."""
    if address not in range(START, STOP, 128) or len(data) != 128:
        raise ValueError("Write outside validated keymap pages")
    return bytes([2]) + address.to_bytes(3, "little") + data


def wait_boot(target_port, timeout=12):
    """Wait for exactly one HIDBoot interface on ``target_port``; raise TimeoutError if none."""
    import hid

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        matches = [
            d
            for d in hid.enumerate(BOOT_VID, BOOT_PID)
            if d.get("product_string") == "HIDBoot" and port(d["path"].decode()) == target_port
        ]
        if len(matches) > 1:
            raise ValueError("Multiple bootloader interfaces match target port")
        if matches:
            return matches[0]
        time.sleep(0.2)
    raise TimeoutError("Target did not enumerate as HIDBoot; no flash data was sent")


def wait_runtime(target_port, timeout=15):
    """Wait for the keyboard to re-enumerate on ``target_port``; return its HID path."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        matches = [d for d in protocol.devices() if port(d["path"].decode()) == target_port]
        if len(matches) == 1:
            return matches[0]["path"].decode()
        time.sleep(0.2)
    raise TimeoutError("Keyboard did not return from bootloader within timeout")


def enter(device):
    """Ask the running firmware to reboot into its BootloadHID bootloader."""
    # Firmware vusb.c: report 1, option index 0 = bootloader; FF clears the
    # boot-start EEPROM flag. USB disconnect/reset can race the status reply.
    try:
        length = device.handle.send_feature_report(bytes([1, 0, 255, 0, 0, 0, 0, 0]))
        if length != 8:
            raise RuntimeError("Short bootloader-entry request")
    except OSError:
        pass  # Success is established only by same-port bootloader enumeration.


class Bootloader:
    """Context manager for a validated BootloadHID session on one physical USB port."""

    def __init__(self, target_port):
        """Prepare a session for the keyboard on ``target_port``; nothing is opened yet."""
        self.target_port = target_port
        self.handle = None

    def __enter__(self):
        """Open the same-port bootloader and validate its geometry."""
        import hid

        device = wait_boot(self.target_port)
        self.handle = hid.device()
        try:
            self.handle.open_path(device["path"])
            self.info = boot_info(bytes(self.handle.get_feature_report(1, 132)))
        except BaseException:
            self.handle.close()
            raise
        return self

    def __exit__(self, *_):
        """Close the bootloader handle."""
        self.handle.close()

    def write(self, write_plan):
        """Send exactly the four ordered keymap pages from ``write_plan``."""
        if [b["address"] for b in write_plan["blocks"]] != list(range(START, STOP, 128)):
            raise ValueError("Flash plan must contain exactly the four ordered keymap pages")
        for block in write_plan["blocks"]:
            data = packet(block["address"], bytes.fromhex(block["data"]))
            if block["address"] + 128 > self.info["applicationEnd"]:
                raise ValueError("Write reaches bootloader")
            if self.handle.send_feature_report(data) != len(data):
                raise RuntimeError("Short flash transfer; bootloader left available for recovery")
            time.sleep(0.02)

    def reboot(self):
        """Leave the bootloader and start the application firmware."""
        # Upstream bootloadHID -r uses feature ID 1, 7-byte info-shaped report.
        # The bootloader disconnects as it reboots; wait_runtime() verifies the return.
        with contextlib.suppress(OSError):
            self.handle.send_feature_report(bytes([1, 0, 0, 0, 0, 0, 0]))


def verify(path, expected, before):
    """Read the keyboard back and compare it with the expected and original snapshots.

    The keymap must equal ``expected``; macros and options must equal ``before``.
    """
    with protocol.Keyboard(path) as device:
        after = documents.snapshot(device.read_state())
    if after["keymap"] != expected["keymap"]:
        raise RuntimeError("Post-write keymap readback mismatch")
    if after["macros"] != before["macros"]:
        raise RuntimeError("Macro/dual-action data changed unexpectedly")
    if after["options"] != before["options"]:
        raise RuntimeError("Options changed unexpectedly across reboot")
    return after


def operation(data, device_path=None, backup_dir=None, probe=False):
    """Caller must explicitly select apply; all inputs validated before mutation."""
    if not sys.platform.startswith("linux"):
        raise ValueError("Hardware programming is currently validated on Linux only")
    import fcntl

    write_plan = plan(data)
    backup_dir = Path(backup_dir or Path.home() / "Backups/ps2avrgb")
    backup_dir.mkdir(parents=True, exist_ok=True)
    lock_path = Path.home() / ".cache/ps2avrgb-flash.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with protocol.Keyboard(device_path) as device:
            before = documents.snapshot(device.read_state())
            if (before["options"]["variant"], before["options"]["version"]) != (
                data["options"]["variant"],
                data["options"]["version"],
            ):
                raise ValueError("Snapshot does not match connected firmware")
            target_port = port(device.identity["path"])
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            original = backup_dir / f"pre-flash-{stamp}.json"
            documents.save(before, original)
            receipt = backup_dir / f"flash-{stamp}.json"
            record = {
                "format": "ps2avrgb.flash-receipt.v1",
                "port": target_port,
                "before": str(original),
                "target": data,
                "plan": write_plan,
                "probe": probe,
                "status": "backup-complete",
            }

            def status(value):
                record["status"] = value
                stage = receipt.with_suffix(".new")
                stage.write_text(json.dumps(record, indent=2) + "\n")
                stage.chmod(0o600)
                os.replace(stage, receipt)

            status("entering-bootloader")
            enter(device)
        try:
            with Bootloader(target_port) as loader:
                record["bootloader"] = loader.info
                status("bootloader-validated")
                if not probe:
                    status("writing-keymap")
                    loader.write(write_plan)
                status("rebooting")
                loader.reboot()
            path = wait_runtime(target_port)
            after = verify(path, before if probe else data, before)
            documents.save(after, backup_dir / f"post-flash-{stamp}.json")
            status("verified")
        except BaseException as error:
            record["error"] = str(error)
            status("failed")
            raise RuntimeError(
                f"{error}. Original backup: {original}. Recovery receipt: {receipt}"
            ) from error
        return {
            "status": "verified",
            "receipt": str(receipt),
            "backup": str(original),
            "hardwareWritten": not probe,
            "bootloader": record["bootloader"],
            "plan": write_plan,
        }


def recover(receipt_path):
    """Restore the pre-write keymap recorded in a flash receipt.

    Uses the normal backup/verify path if the keyboard is running, or writes
    directly if it is still in the same-port bootloader.
    """
    if not sys.platform.startswith("linux"):
        raise ValueError("Hardware recovery is currently validated on Linux only")
    record = json.loads(Path(receipt_path).read_text())
    if record.get("format") != "ps2avrgb.flash-receipt.v1":
        raise ValueError("Not a flash receipt")
    before = documents.load(record["before"])
    write_plan = plan(before)
    target_port = record["port"]
    # If application returned, use the ordinary fresh-backup/identity checks.
    for device in protocol.devices():
        if port(device["path"].decode()) == target_port:
            return operation(before, device["path"].decode())
    import fcntl

    lock_path = Path.home() / ".cache/ps2avrgb-flash.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with Bootloader(target_port) as loader:
            loader.write(write_plan)
            loader.reboot()
        after = verify(wait_runtime(target_port), before, before)
        output = Path(receipt_path).with_suffix(".recovered.json")
        documents.save(after, output)
    return {"status": "recovered", "snapshot": str(output), "hardwareWritten": True}
