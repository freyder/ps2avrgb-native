"""Scriptable entry point; Qt is imported only for the gui subcommand."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__, documents, keys, protocol


def main(argv=None):
    """Parse ``argv``, run one subcommand and print JSON; return the process exit code.

    Errors are printed to stderr as ``{"error": ...}`` with exit code 1.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Native ps2avrGB tools. File edits are offline; flash-keymap --apply programs hardware."
        )
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--device", help="Exact control-interface path from list")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List matching HID control interfaces as JSON")
    commands.add_parser("keys", help="List firmware key names and indices as JSON")
    commands.add_parser("info", help="Read firmware and current options as JSON")
    backup = commands.add_parser(
        "backup", help="Read and verify keymaps/macros into a JSON snapshot"
    )
    backup.add_argument("output")
    show = commands.add_parser("show", help="Inspect a snapshot without opening a device")
    show.add_argument("input")
    show.add_argument("--layer", type=int, choices=range(4), default=0)
    show.add_argument("--json", action="store_true")
    edit = commands.add_parser("set-key", help="Edit a snapshot file; does not write the keyboard")
    edit.add_argument("input")
    edit.add_argument("--layer", type=int, required=True)
    edit.add_argument("--row", type=int, required=True)
    edit.add_argument("--column", type=int, required=True)
    edit.add_argument("--key", required=True)
    edit.add_argument("--output", required=True)
    export = commands.add_parser(
        "export-hex", help="Export only the four keymap layers to Intel HEX"
    )
    export.add_argument("input")
    export.add_argument("output")
    flash = commands.add_parser("flash-keymap", help="Preview or apply bounded keymap flash pages")
    flash.add_argument("input")
    flash.add_argument("--apply", action="store_true", help="Actually program hardware")
    probe = commands.add_parser(
        "bootloader-probe", help="Enter bootloader, read geometry and return without flashing"
    )
    probe.add_argument("input")
    recovery = commands.add_parser(
        "recover", help="Restore a failed write from its receipt and original backup"
    )
    recovery.add_argument("receipt")
    recovery.add_argument("--apply", action="store_true", required=True)
    gui = commands.add_parser("gui", help="Open the native Qt editor")
    gui.add_argument("input", nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.command == "gui":
            from .gui import run

            return run(args.input)
        if args.command in ["flash-keymap", "bootloader-probe", "recover"]:
            from . import flashing

            if args.command == "recover":
                result = flashing.recover(args.receipt)
            else:
                data = documents.load(args.input)
                if args.command == "flash-keymap" and not args.apply:
                    result = {"dryRun": True, "hardwareWritten": False, "plan": flashing.plan(data)}
                else:
                    result = flashing.operation(
                        data, args.device, probe=args.command == "bootloader-probe"
                    )
        elif args.command == "list":
            result = [protocol.describe(d) for d in protocol.devices()]
        elif args.command == "keys":
            result = [{"index": code, "key": name} for code, name in sorted(keys.NAMES.items())]
        elif args.command in ["info", "backup"]:
            with protocol.Keyboard(args.device) as device:
                if args.command == "info":
                    result = {"device": device.identity, "options": device.info.as_dict()}
                else:
                    if Path(args.output).expanduser().exists():
                        raise ValueError("Backup already exists; choose a new output filename")
                    data = documents.snapshot(device.read_state())
                    documents.save(data, args.output)
                    result = {
                        "saved": str(Path(args.output).expanduser()),
                        "sha256": data["sha256"],
                        "options": data["options"],
                        "verifiedReads": 2,
                        "hardwareWritten": False,
                    }
        elif args.command == "show":
            data = documents.load(args.input)
            values = bytes.fromhex(data["keymap"][args.layer])
            rows = [
                [{"index": code, "key": keys.label(code)} for code in values[r : r + 8]]
                for r in range(0, len(values), 8)
            ]
            if not args.json:
                for n, row in enumerate(rows):
                    print(f"{n:02d}: " + " | ".join(f"{v['key']:14}" for v in row))
                return 0
            result = {"layer": args.layer, "rows": rows}
        elif args.command == "set-key":
            if Path(args.input).resolve() == Path(args.output).resolve():
                raise ValueError("Use a different output path to preserve the original snapshot")
            data = documents.set_key(
                documents.load(args.input),
                args.layer,
                args.row,
                args.column,
                keys.parse_key(args.key),
            )
            documents.save(data, args.output)
            result = {"saved": args.output, "sha256": data["sha256"], "hardwareWritten": False}
        else:
            Path(args.output).write_text(documents.intel_hex(documents.load(args.input)))
            result = {"saved": args.output, "hardwareWritten": False}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, AssertionError, RuntimeError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
