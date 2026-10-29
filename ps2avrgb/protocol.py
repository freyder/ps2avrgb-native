"""Verified ps2avrGB GET_REPORT protocol. No SET_REPORT or bootloader writes."""

from dataclasses import dataclass

VID, PID = 0x20A0, 0x422D
VARIANTS = {
    0: ("ps2avrGB", 15, 0x6600),
    1: ("ps2avrGB4U", 17, 0x6500),
    2: ("ps2avrGB split", 15, 0x6600),
    3: ("ps2avrGB4U split", 17, 0x6500),
    4: ("ps2avrGB4U AIKON", 18, 0x6500),
}


@dataclass(frozen=True)
class Info:
    """Decoded options report: firmware version, variant and matrix geometry."""

    raw: bytes
    version: tuple
    variant: int
    rows: int
    columns: int = 8
    layers: int = 4

    @classmethod
    def decode(cls, raw):
        """Decode a 53-byte 1.5.x options report; reject unknown versions and variants."""
        if len(raw) != 53 or raw[0] != 53:
            raise ValueError(
                f"Unsupported options report: {len(raw)} bytes, size marker {raw[:1].hex()}"
            )
        if raw[47] not in VARIANTS:
            raise ValueError(f"Unknown firmware variant {raw[47]}")
        version = tuple(raw[44:47])
        if version[:2] != (1, 5):
            raise ValueError(
                f"Firmware {version} has not been validated; refusing geometry assumptions"
            )
        return cls(bytes(raw), version, raw[47], VARIANTS[raw[47]][1])

    def as_dict(self):
        """Return the info as the ``options`` dictionary stored in snapshots."""
        return {
            "version": ".".join(map(str, self.version)),
            "variant": self.variant,
            "name": VARIANTS[self.variant][0],
            "rows": self.rows,
            "columns": self.columns,
            "layers": self.layers,
            "raw": self.raw.hex(),
        }


def devices():
    """Return HIDAPI entries for every connected ps2avrGB control interface (interface 1)."""
    import hid

    return [d for d in hid.enumerate(VID, PID) if d.get("interface_number") == 1]


def describe(device):
    """Return a JSON-safe copy of a HIDAPI device entry (bytes decoded to text)."""
    return {
        key: (value.decode(errors="replace") if isinstance(value, bytes) else value)
        for key, value in device.items()
    }


class Keyboard:
    """Read-only session with one ps2avrGB control interface."""

    def __init__(self, path=None):
        """Select the keyboard at HID ``path``, or the only one connected if None."""
        self.path = path
        self.handle = None
        self.info = None
        self.identity = None

    def __enter__(self):
        """Open exactly one matching interface and read its options report."""
        import hid

        candidates = devices()
        if self.path:
            candidates = [d for d in candidates if d["path"] == self.path.encode()]
        if len(candidates) != 1:
            raise ValueError(
                f"Found {len(candidates)} matching control interfaces; "
                "use --device PATH to select exactly one"
            )
        self.identity = describe(candidates[0])
        self.handle = hid.device()
        try:
            self.handle.open_path(candidates[0]["path"])
            self.info = Info.decode(self._read(100, 53))
        except BaseException:
            self.handle.close()
            raise
        return self

    def __exit__(self, *_):
        """Close the HID handle."""
        self.handle.close()

    def _read(self, selector, expected):
        # The firmware abuses request LENGTH as its command selector. 101 is
        # a mutating bootmapper toggle despite being GET_REPORT. Never issue it.
        allowed = {
            100: 53,
            150: 128,
            **dict.fromkeys(range(168, 180), 168),
            **dict.fromkeys(range(180, 192), 48),
            **dict.fromkeys(range(192, 204), 28),
        }
        if self.info:
            size = self.info.rows * self.info.columns
            allowed.update({size + 1 + i: size for i in range(4)})
        if allowed.get(selector) != expected:
            raise ValueError(f"GET_REPORT selector {selector} is not a whitelisted read")
        value = bytes(self.handle.get_feature_report(1, selector))
        if len(value) != expected:
            raise ValueError(f"Report {selector} returned {len(value)} bytes; expected {expected}")
        return value

    def keymap(self):
        """Read the four keymap layers as hex strings."""
        size = self.info.rows * self.info.columns
        return [self._read(size + 1 + i, size).hex() for i in range(4)]

    def read_state(self):
        """Read keymaps, macros and dual-action twice; raise if the two passes differ."""
        result = {
            "device": self.identity,
            "options": self.info.as_dict(),
            "keymap": self.keymap(),
            "macros": {
                "flash": [self._read(i, 168).hex() for i in range(168, 180)],
                "quick": [self._read(i, 48).hex() for i in range(180, 192)],
                "quick_extra": [self._read(i, 28).hex() for i in range(192, 204)],
                "dual_action": self._read(150, 128).hex(),
            },
        }
        # Read everything twice: a backup must not contain silently short or
        # inconsistent transfers. Neither pass changes persistent settings.
        second = {
            "keymap": self.keymap(),
            "flash": [self._read(i, 168).hex() for i in range(168, 180)],
            "quick": [self._read(i, 48).hex() for i in range(180, 192)],
            "quick_extra": [self._read(i, 28).hex() for i in range(192, 204)],
            "dual_action": self._read(150, 128).hex(),
        }
        # Explicit raises, not asserts: `python -O` strips assert statements,
        # which would silently disable this backup-integrity check.
        if second["keymap"] != result["keymap"]:
            raise RuntimeError("Keymap changed between the two verification reads")
        if any(second[k] != result["macros"][k] for k in result["macros"]):
            raise RuntimeError("Macro data changed between the two verification reads")
        return result
