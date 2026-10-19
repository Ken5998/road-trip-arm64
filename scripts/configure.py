#!/usr/bin/env python3
"""Writes the ARMSX2 settings Road Trip Adventure plays with on a handheld
into ARMSX2's main settings file, keeping everything else in it:

    scripts/configure.py INI --bios FILE [--scale N] [--renderer vulkan|opengl]

INI is DATA/ARMSX2/inis/PCSX2.ini (ARMSX2 started with -datapath DATA keeps
its settings there). A new file gets the settings version ARMSX2 checks, so it
loads the file instead of resetting it and starting its setup wizard.

What it sets: the BIOS, the renderer and the internal resolution (1x is the
lightest, for the lowest power draw), full screen without the main window, no
update check or exit question, and player 1 on the first controller, which
under Steam is the handheld's own pad. BACK+START opens the pause menu (exit
the game from there).

Needs only Python's standard library (ArmadaOS's own python3 is enough).
"""
import argparse
import sys
from pathlib import Path

# ARMSX2 (as PCSX2) resets a file without this version to its defaults.
SETTINGS_VERSION = "1"

# The DualShock 2 on SDL controller 0, as ARMSX2's automatic mapping binds it
# (SDL 3 names: FaceSouth is A on an Xbox layout, Cross on the PlayStation).
PAD1 = {
    "Type": "DualShock2",
    "Up": "SDL-0/DPadUp", "Right": "SDL-0/DPadRight", "Down": "SDL-0/DPadDown", "Left": "SDL-0/DPadLeft",
    "Triangle": "SDL-0/FaceNorth", "Circle": "SDL-0/FaceEast", "Cross": "SDL-0/FaceSouth",
    "Square": "SDL-0/FaceWest", "Select": "SDL-0/Back", "Start": "SDL-0/Start",
    "L1": "SDL-0/LeftShoulder", "R1": "SDL-0/RightShoulder",
    "L2": "SDL-0/+LeftTrigger", "R2": "SDL-0/+RightTrigger",
    "L3": "SDL-0/LeftStick", "R3": "SDL-0/RightStick",
    "LUp": "SDL-0/-LeftY", "LRight": "SDL-0/+LeftX", "LDown": "SDL-0/+LeftY", "LLeft": "SDL-0/-LeftX",
    "RUp": "SDL-0/-RightY", "RRight": "SDL-0/+RightX", "RDown": "SDL-0/+RightY", "RLeft": "SDL-0/-RightX",
    "LargeMotor": "SDL-0/LargeMotor", "SmallMotor": "SDL-0/SmallMotor",
}

RENDERERS = {"vulkan": "14", "opengl": "12"}


def settings(bios: str, scale: int, renderer: str) -> dict[str, dict[str, list[str]]]:
    return {
        "UI": {
            "SettingsVersion": [SETTINGS_VERSION],
            "SetupWizardIncomplete": ["false"],
            "StartFullscreen": ["true"],
            "ConfirmShutdown": ["false"],
            "HideMouseCursor": ["true"],
        },
        "AutoUpdater": {"CheckAtStartup": ["false"]},
        "Filenames": {"BIOS": [bios]},
        "EmuCore": {"EnableFastBoot": ["true"]},
        "EmuCore/GS": {"Renderer": [RENDERERS[renderer]], "upscale_multiplier": [str(scale)]},
        "InputSources": {"SDL": ["true"]},
        "Pad1": {key: [value] for key, value in PAD1.items()},
        "Hotkeys": {"OpenPauseMenu": ["SDL-0/Back & SDL-0/Start", "Keyboard/Escape"]},
    }


def parse(text: str) -> list[tuple[str, list[tuple[str, str] | str]]]:
    """Sections in order, each with its lines: (key, value) pairs, or other
    lines (comments, blanks) kept as they are."""
    sections: list[tuple[str, list]] = [("", [])]
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            sections.append((stripped[1:-1], []))
        elif "=" in stripped and not stripped.startswith((";", "#")):
            key, value = stripped.split("=", 1)
            sections[-1][1].append((key.strip(), value.strip()))
        else:
            sections[-1][1].append(line)
    return sections


def merge(text: str, wanted: dict[str, dict[str, list[str]]]) -> str:
    """The file with each wanted key set to its values (a key can repeat, as
    ARMSX2 stores more than one binding), other keys left as they were."""
    sections = parse(text)
    for name, keys in wanted.items():
        found = next((lines for section, lines in sections if section == name), None)
        if found is None:
            found = []
            sections.append((name, found))
        for key, values in keys.items():
            at = next((i for i, line in enumerate(found) if isinstance(line, tuple) and line[0] == key), None)
            found[:] = [line for line in found if not (isinstance(line, tuple) and line[0] == key)]
            if at is None:
                # After the last setting, before trailing blank lines.
                at = len(found)
                while at > 0 and found[at - 1] == "":
                    at -= 1
            found[at:at] = [(key, value) for value in values]
    out: list[str] = []
    for name, lines in sections:
        if name:
            if out and out[-1] != "":
                out.append("")
            out.append(f"[{name}]")
        out.extend(f"{line[0]} = {line[1]}" if isinstance(line, tuple) else line for line in lines)
    return "\n".join(out).strip("\n") + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ini", type=Path)
    parser.add_argument("--bios", required=True, help="BIOS file name in ARMSX2's bios folder")
    parser.add_argument("--scale", type=int, default=2, choices=range(1, 9), metavar="1-8")
    parser.add_argument("--renderer", default="vulkan", choices=sorted(RENDERERS))
    args = parser.parse_args(argv[1:])
    text = args.ini.read_text(encoding="utf-8") if args.ini.is_file() else ""
    args.ini.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.ini.with_name(args.ini.name + ".tmp")
    temporary.write_text(merge(text, settings(args.bios, args.scale, args.renderer)), encoding="utf-8")
    temporary.replace(args.ini)
    print(f"ARMSX2 settings: {args.renderer}, {args.scale}x internal resolution, BIOS {args.bios}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
