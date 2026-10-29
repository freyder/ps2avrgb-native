"""Portable snapshots, offline edits and Bootmapper-compatible Intel HEX."""

import copy
import datetime
import hashlib
import json
import os
from pathlib import Path

from .protocol import VARIANTS, Info

FORMAT = "ps2avrgb.snapshot.v1"


def checksum(data):
    """Return the SHA-256 of a snapshot's canonical JSON, excluding its own ``sha256`` field."""
    return hashlib.sha256(
        json.dumps(
            {k: v for k, v in data.items() if k != "sha256"}, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def validate(data):
    """Check format, checksum and region geometry; return ``data`` or raise ValueError."""
    if data.get("format") != FORMAT:
        raise ValueError("Not a ps2avrGB snapshot")
    if data.get("sha256") != checksum(data):
        raise ValueError("Snapshot checksum mismatch")
    info = Info.decode(bytes.fromhex(data["options"]["raw"]))
    for field in ["rows", "columns", "layers", "variant", "version"]:
        if data["options"][field] != info.as_dict()[field]:
            raise ValueError("Geometry/firmware metadata does not match options report")
    if len(data["keymap"]) != 4 or any(
        len(bytes.fromhex(v)) != info.rows * 8 for v in data["keymap"]
    ):
        raise ValueError("Invalid keymap geometry")
    for name, count, size in [("flash", 12, 168), ("quick", 12, 48), ("quick_extra", 12, 28)]:
        if len(data["macros"][name]) != count or any(
            len(bytes.fromhex(v)) != size for v in data["macros"][name]
        ):
            raise ValueError("Invalid " + name + " macro region")
    if len(bytes.fromhex(data["macros"]["dual_action"])) != 128:
        raise ValueError("Invalid dual-action region")
    return data


def snapshot(state):
    """Wrap a ``Keyboard.read_state()`` result in a timestamped, checksummed snapshot."""
    value = {
        "format": FORMAT,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **state,
    }
    value["sha256"] = checksum(value)
    return validate(value)


def load(path):
    """Read and validate a snapshot JSON file."""
    return validate(json.loads(Path(path).read_text()))


def save(data, path):
    """Validate and atomically write a snapshot with owner-only (0600) permissions."""
    validate(data)
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_name("." + path.name + ".new")
    stage.write_text(json.dumps(data, indent=2) + "\n")
    stage.chmod(0o600)
    os.replace(stage, path)


def set_key(data, layer, row, column, code):
    """Return an edited copy with one firmware key index changed; ``data`` is untouched.

    Coordinates are zero-based firmware matrix positions, not physical keypad cells.
    """
    validate(data)
    if not (
        0 <= layer < 4
        and 0 <= row < data["options"]["rows"]
        and 0 <= column < 8
        and 0 <= code <= 255
    ):
        raise ValueError("Layer, matrix coordinate or key index out of range")
    result = copy.deepcopy(data)
    values = bytearray.fromhex(result["keymap"][layer])
    values[row * 8 + column] = code
    result["keymap"][layer] = values.hex()
    result["sha256"] = checksum(result)
    return result


def intel_hex(data):
    """Return the four keymap layers as Bootmapper-compatible Intel HEX text."""
    validate(data)
    address = VARIANTS[data["options"]["variant"]][2]
    raw = b"".join(bytes.fromhex(v) for v in data["keymap"])
    lines = []
    for offset in range(0, len(raw), 16):
        part = raw[offset : offset + 16]
        a = address + offset
        record = bytes([len(part), a >> 8, a & 255, 0]) + part
        lines.append(":" + record.hex().upper() + f"{(-sum(record)) & 255:02X}")
    return "\n".join(lines + [":00000001FF"]) + "\n"
