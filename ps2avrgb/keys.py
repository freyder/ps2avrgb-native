"""Firmware key indices, which differ from USB usages above 101."""

NAMES = {0: "None"}
NAMES.update({4 + i: chr(65 + i) for i in range(26)})
NAMES.update({30 + i: v for i, v in enumerate("1234567890")})
NAMES.update(
    dict(
        enumerate(
            [
                "Enter",
                "Escape",
                "Backspace",
                "Tab",
                "Space",
                "Minus",
                "Equal",
                "LeftBracket",
                "RightBracket",
                "Backslash",
                "NonUSHash",
                "Semicolon",
                "Quote",
                "Grave",
                "Comma",
                "Period",
                "Slash",
                "CapsLock",
            ],
            40,
        )
    )
)
NAMES.update({58 + i: "F" + str(i + 1) for i in range(12)})
NAMES.update(
    dict(
        enumerate(
            [
                "PrintScreen",
                "ScrollLock",
                "Pause",
                "Insert",
                "Home",
                "PageUp",
                "Delete",
                "End",
                "PageDown",
                "Right",
                "Left",
                "Down",
                "Up",
                "NumLock",
                "KPDivide",
                "KPMultiply",
                "KPMinus",
                "KPPlus",
                "KPEnter",
                "KP1",
                "KP2",
                "KP3",
                "KP4",
                "KP5",
                "KP6",
                "KP7",
                "KP8",
                "KP9",
                "KP0",
                "KPDecimal",
                "NonUSBackslash",
                "Menu",
            ],
            70,
        )
    )
)
NAMES.update(
    dict(
        enumerate(
            [
                "LeftCtrl",
                "LeftShift",
                "LeftAlt",
                "LeftGUI",
                "RightCtrl",
                "RightShift",
                "RightAlt",
                "RightGUI",
            ],
            103,
        )
    )
)
NAMES.update(
    dict(
        enumerate(
            [
                "Power",
                "Sleep",
                "Wake",
                "Email",
                "WebSearch",
                "WebHome",
                "WebBack",
                "WebForward",
                "WebStop",
                "WebRefresh",
                "WebFavorites",
                "NextTrack",
                "PreviousTrack",
                "MediaStop",
                "PlayPause",
                "Mute",
                "VolumeUp",
                "VolumeDown",
                "Media",
                "Calculator",
                "MyComputer",
                "Screensaver",
                "Record",
                "Rewind",
                "Minimize",
                "Eject",
            ],
            113,
        )
    )
)
NAMES.update({141: "Hanja", 142: "Hangul", 143: "KeyboardPower", 144: "KPEqual"})
NAMES.update({145 + i: "F" + str(13 + i) for i in range(12)})
NAMES.update(
    {
        176: "EscapeTilde",
        242: "QuickMacro",
        243: "LockWindows",
        244: "LockAll",
        245: "LEDOnOff",
        246: "FN3",
        247: "FN3Toggle",
        248: "FN2",
        249: "LEDDim",
        250: "LEDBrighten",
        251: "NormalLayer",
        252: "FN2Toggle",
        253: "LED",
        254: "FN",
    }
)
NAMES.update({189 + i: "CustomMacro" + str(i + 1) for i in range(12)})
NAMES.update({201 + i: "Macro" + str(i + 1) for i in range(12)})


def label(code):
    """Return the firmware name for key index ``code``, or its hex value if unnamed."""
    return NAMES.get(code, f"0x{code:02X}")


def parse_key(value):
    """Return the key index for a name (case-insensitive) or a number such as ``0x29``."""
    for code, name in NAMES.items():
        if name.casefold() == value.casefold():
            return code
    try:
        code = int(value, 0)
    except ValueError:
        raise ValueError(f"Unknown key {value!r}; use a key name or byte such as 0x29") from None
    if not 0 <= code <= 255:
        raise ValueError("Key index must be 0..255")
    return code


# Firmware-specific dual-action indices. 213 and 238 are enum sentinels.
NAMES.update(
    dict(
        enumerate(
            [
                "FN_Hangul",
                "FN_Hanja",
                "FN2_Hangul",
                "FN2_Hanja",
                "RightShift_Hangul",
                "RightShift_Hanja",
                "LeftShift_Hangul",
                "LeftShift_Hanja",
                "RightAlt_Hangul",
                "RightAlt_Hanja",
                "LeftAlt_Hangul",
                "LeftAlt_Hanja",
                "RightCtrl_Hangul",
                "RightCtrl_Hanja",
                "LeftCtrl_Hangul",
                "LeftCtrl_Hanja",
                "FN_CapsLock",
                "FN2_CapsLock",
                "FN3_Hangul",
                "FN3_Hanja",
                "FN3_CapsLock",
                "FN_Menu",
                "FN2_Menu",
                "FN3_Menu",
            ],
            214,
        )
    )
)
NAMES.update({157: "KPComma", 158: "EqualSign", 241: "RGBMode"})
