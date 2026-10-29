#!/usr/bin/env python3
"""One explicitly requested physical-key observation; no keyboard programming.

Run as root (it briefly grabs the keypad's input devices). Set DESKTOP_USER to
the logged-in desktop user who should get the notification and own the capture
file; it defaults to SUDO_USER. The capture is saved to ~/Backups/ps2avrgb of
that user.
"""

import datetime
import json
import os
import pwd
import select
import subprocess
import time
from pathlib import Path

from evdev import InputDevice, ecodes, list_devices

DESKTOP = pwd.getpwnam(os.environ.get("DESKTOP_USER") or os.environ["SUDO_USER"])
RUNTIME_DIR = f"/run/user/{DESKTOP.pw_uid}"

devices = []
for path in list_devices():
    device = InputDevice(path)
    if (device.info.vendor, device.info.product) == (0x20A0, 0x422D):
        devices.append(device)
    else:
        device.close()
assert devices, "Keypad not found"
result = {"at": datetime.datetime.now().astimezone().isoformat(), "events": [], "complete": False}
grabbed = []
down = None
deadline = time.monotonic() + 45
try:
    for device in devices:
        device.grab()
        grabbed.append(device)
    print("ARMED: press and release the double-wide keypad key once; 45-second timeout", flush=True)
    subprocess.run(
        [
            "runuser",
            "-u",
            DESKTOP.pw_name,
            "--",
            "env",
            f"XDG_RUNTIME_DIR={RUNTIME_DIR}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path={RUNTIME_DIR}/bus",
            "notify-send",
            "--app-name=ps2avrGB Native",
            "--expire-time=6000",
            "Keypad capture ready",
            "Press and release only the double-wide bottom-row key once.",
        ],
        check=False,
    )
    while time.monotonic() < deadline:
        ready, _, _ = select.select(devices, [], [], 0.25)
        for device in ready:
            for event in device.read():
                if event.type not in (ecodes.EV_KEY, ecodes.EV_MSC):
                    continue
                label = (
                    ecodes.KEY.get(event.code, str(event.code))
                    if event.type == ecodes.EV_KEY
                    else ecodes.MSC.get(event.code, str(event.code))
                )
                record = {
                    "device": device.name,
                    "type": event.type,
                    "code": event.code,
                    "name": label,
                    "value": event.value,
                }
                result["events"].append(record)
                print(json.dumps(record), flush=True)
                if event.type == ecodes.EV_KEY:
                    if event.value == 1 and down is None:
                        down = (device.path, event.code)
                    elif event.value == 0 and down == (device.path, event.code):
                        result["complete"] = True
                        deadline = 0
finally:
    for device in grabbed:
        try:
            device.ungrab()
        except OSError:
            pass
    for device in devices:
        device.close()
    out = Path(DESKTOP.pw_dir, "Backups/ps2avrgb") / datetime.datetime.now().strftime(
        "wide-key-capture-%Y%m%d-%H%M%S.json"
    )
    out.write_text(json.dumps(result, indent=2) + "\n")
    out.chmod(0o600)
    os.chown(out, DESKTOP.pw_uid, DESKTOP.pw_gid)
    print("RELEASED; capture saved to " + str(out), flush=True)
