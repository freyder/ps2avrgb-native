"""Change one verified unpopulated cell, read back, then restore the original."""

import json
from pathlib import Path

from ps2avrgb import documents, flashing, protocol

base = Path.home() / "Backups/ps2avrgb"
original = documents.load(base / "keyboard-original-20261026.json")
old = bytes.fromhex(original["keymap"][0])[3 * 8 + 4]
assert old != 0
modified = documents.set_key(original, 0, 3, 4, 0)
documents.save(modified, base / "flash-validation-unused-slot.json")
result = {"test": "unused row 3 column 4 round trip", "originalIndex": old, "changedIndex": 0}
try:
    result["changed"] = flashing.operation(modified)
    with protocol.Keyboard() as device:
        observed = bytes.fromhex(device.keymap()[0])[3 * 8 + 4]
    assert observed == 0, "Changed byte did not read back"
    result["changedReadback"] = observed
finally:
    result["restored"] = flashing.operation(original)
    with protocol.Keyboard() as device:
        current = device.keymap()
    assert current == original["keymap"], "Original keymaps not restored"
    result["restoredReadback"] = bytes.fromhex(current[0])[3 * 8 + 4]
    output = base / "changed-byte-flash-validation-20261026.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    output.chmod(0o600)
print(json.dumps({k: v for k, v in result.items() if k not in ["changed", "restored"]}, indent=2))
print("All original keymaps restored; validation receipt:", output)
