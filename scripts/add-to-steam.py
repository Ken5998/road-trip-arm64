#!/usr/bin/env python3
"""Adds Road Trip Adventure to the Steam library of every Steam account on this
machine, as a non-Steam game that runs natively (no Proton), with its
artwork: the portrait and wide capsules, the hero and the icon.

    scripts/add-to-steam.py DIST ARTWORK

DIST is the game folder (with roadtrip.sh in it), ARTWORK the folder
install.sh downloaded the pictures to (capsule.png, wide.png, hero.png,
icon.png; a logo.png there would go in too).
Running it again replaces the entry instead of adding a second one, and
does nothing when the entry and the images are already there.

Steam keeps the library in memory and writes it back when it closes, so a
running Steam is closed first and started again afterwards.

Needs only Python's standard library (ArmadaOS's own python3 is enough).
"""
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

NAME = "Road Trip Adventure"
# Images in Steam's grid folder, named after the shortcut's app id.
GRID = (("capsule.png", "{}p.png"), ("wide.png", "{}.png"), ("hero.png", "{}_hero.png"),
        ("logo.png", "{}_logo.png"), ("icon.png", "{}_icon.png"))

# shortcuts.vdf is Steam's binary KeyValues format.
MAP, STRING, INT32, END = 0x00, 0x01, 0x02, 0x08


def read_string(data: bytes, at: int) -> tuple[str, int]:
    end = data.index(b"\0", at)
    return data[at:end].decode("utf-8", errors="surrogateescape"), end + 1


def parse_vdf(data: bytes, at: int = 0) -> tuple[dict, int]:
    result: dict = {}
    while at < len(data):
        kind = data[at]
        at += 1
        if kind == END:
            return result, at
        key, at = read_string(data, at)
        if kind == MAP:
            result[key], at = parse_vdf(data, at)
        elif kind == STRING:
            result[key], at = read_string(data, at)
        elif kind == INT32:
            result[key] = struct.unpack_from("<i", data, at)[0]
            at += 4
        else:
            raise ValueError(f"unknown field type {kind} in shortcuts.vdf")
    return result, at


def dump_vdf(value: dict) -> bytes:
    out = bytearray()
    for key, item in value.items():
        name = key.encode("utf-8", errors="surrogateescape") + b"\0"
        if isinstance(item, dict):
            out += bytes([MAP]) + name + dump_vdf(item)
        elif isinstance(item, int):
            out += bytes([INT32]) + name + struct.pack("<i", item)
        else:
            out += bytes([STRING]) + name + str(item).encode("utf-8", errors="surrogateescape") + b"\0"
    return bytes(out) + bytes([END])


def app_id(exe: str, name: str) -> int:
    """The id Steam gives a non-Steam game, which its grid images are named
    after (unsigned; shortcuts.vdf stores it signed)."""
    return zlib.crc32((exe + name).encode("utf-8")) | 0x80000000


def steam_roots(home: Path) -> list[Path]:
    roots: list[Path] = []
    for candidate in (home / ".local/share/Steam", home / ".steam/steam",
                      home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"):
        if (candidate / "userdata").is_dir() and all(candidate.resolve() != r.resolve() for r in roots):
            roots.append(candidate)
    return roots


def steam_running() -> bool:
    """Whether a Steam client process of this user runs: ArmadaOS's ARM64
    client (steamrtarm64/steam), the x86 one under FEX (ubuntu12_32/steam) or
    its helpers. Told by the executable rather than the command line, which
    can be relative (./steam) after Steam restarts itself: a Steam that was
    missed keeps its own copy of the library and writes it back later,
    without the game."""
    names = {"steam", "steamwebhelper", "steamservice"}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            exe = os.readlink(proc / "exe").removesuffix(" (deleted)")
            command = (proc / "cmdline").read_bytes().split(b"\0")[:2]
        except OSError:
            continue
        if Path(exe).name in names:
            return True
        # FEX runs the x86 client: the executable is FEX, the client is in argv.
        if any(part.endswith((b"/steamrtarm64/steam", b"/ubuntu12_32/steam")) for part in command):
            return True
    return False


def close_steam() -> bool:
    """Closes a running Steam; True when it was running."""
    if not steam_running():
        return False
    if not shutil.which("steam"):
        sys.exit("error: Steam is running: close it and run this again")
    print("Closing Steam, so it keeps the new entry (it starts again afterwards)")
    subprocess.run(["steam", "-shutdown"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 90
    while steam_running():
        if time.monotonic() > deadline:
            sys.exit("error: Steam did not close: close it and run this again")
        time.sleep(1)
    return True


def field(entry: dict, key: str):
    """A field of a shortcut, whatever case Steam wrote its key in."""
    for k, v in entry.items():
        if k.lower() == key.lower():
            return v
    return None


def accounts_configs(home: Path) -> list[Path]:
    """The config folders of the accounts that signed in (not the anonymous 0)."""
    return [user / "config" for root in steam_roots(home) for user in sorted((root / "userdata").iterdir())
            if user.is_dir() and user.name.isdigit() and user.name != "0"]


def is_ours(entry: dict, exe: str) -> bool:
    return field(entry, "AppName") == NAME or field(entry, "Exe") == exe


def up_to_date(home: Path, dist: Path, artwork: Path) -> bool:
    """Whether every account already has the entry as add() writes it and
    the same images, so there is nothing to do (and no reason to close Steam)."""
    exe = f'"{dist / "roadtrip.sh"}"'
    unsigned = app_id(exe, NAME)
    configs = accounts_configs(home)
    for config in configs:
        path = config / "shortcuts.vdf"
        try:
            entries = [e for e in parse_vdf(path.read_bytes())[0].get("shortcuts", {}).values()
                       if isinstance(e, dict) and is_ours(e, exe)]
        except (OSError, ValueError, IndexError):
            return False
        wanted = {"appid": struct.unpack("<i", struct.pack("<I", unsigned))[0], "AppName": NAME, "Exe": exe,
                  "StartDir": f'"{dist}"', "icon": str(artwork / "icon.png")}
        if len(entries) != 1 or any(field(entries[0], k) != v for k, v in wanted.items()):
            return False
        for source, name in GRID:
            image = config / "grid" / name.format(unsigned)
            if (artwork / source).is_file() and (
                    not image.is_file() or image.read_bytes() != (artwork / source).read_bytes()):
                return False
    return bool(configs)


def add(home: Path, dist: Path, artwork: Path) -> int:
    """Writes the entry and the images for every account; returns how many."""
    exe = f'"{dist / "roadtrip.sh"}"'
    unsigned = app_id(exe, NAME)
    signed = struct.unpack("<i", struct.pack("<I", unsigned))[0]
    accounts = 0
    for config in accounts_configs(home):
        config.mkdir(parents=True, exist_ok=True)
        path = config / "shortcuts.vdf"
        shortcuts: dict = {}
        if path.is_file() and path.stat().st_size:
            shortcuts = parse_vdf(path.read_bytes())[0].get("shortcuts", {})
            backup = path.with_name("shortcuts.vdf.roadtrip-backup")
            if not backup.exists():
                shutil.copyfile(path, backup)
        entry = {
            "appid": signed, "AppName": NAME, "Exe": exe, "StartDir": f'"{dist}"',
            "icon": str(artwork / "icon.png"), "ShortcutPath": "", "LaunchOptions": "",
            "IsHidden": 0, "AllowDesktopConfig": 1, "AllowOverlay": 1, "OpenVR": 0,
            "Devkit": 0, "DevkitGameID": "", "DevkitOverrideAppID": 0, "LastPlayTime": 0,
            "FlatpakAppID": "", "tags": {},
        }
        # An earlier Road Trip Adventure entry is replaced, keeping what was set on
        # it in Steam (launch options, collections, last played).
        ours = [e for e in shortcuts.values() if is_ours(e, exe)]
        for key, value in (ours[0] if ours else {}).items():
            if key.lower() in ("appid", "appname", "exe", "startdir", "icon"):
                continue
            entry[next((k for k in entry if k.lower() == key.lower()), key)] = value
        entries = [e for e in shortcuts.values() if not is_ours(e, exe)] + [entry]
        temporary = path.with_name("shortcuts.vdf.tmp")
        temporary.write_bytes(dump_vdf({"shortcuts": {str(i): e for i, e in enumerate(entries)}}))
        temporary.replace(path)
        grid = config / "grid"
        grid.mkdir(exist_ok=True)
        for source, name in GRID:
            if (artwork / source).is_file():
                shutil.copyfile(artwork / source, grid / name.format(unsigned))
        accounts += 1
    return accounts


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    dist, artwork = Path(argv[1]).resolve(), Path(argv[2]).resolve()
    if not (dist / "roadtrip.sh").is_file():
        sys.exit(f"error: {dist / 'roadtrip.sh'} is not there: install the game first")
    home = Path.home()
    if not steam_roots(home):
        sys.exit("error: Steam is not set up for this user: start it and sign in once")
    if up_to_date(home, dist, artwork):
        print(f"{NAME} is already in Steam with its artwork")
        return 0
    restart = close_steam()
    try:
        accounts = add(home, dist, artwork)
    finally:
        if restart:
            subprocess.Popen(["steam"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    if not accounts:
        sys.exit("error: no Steam account has signed in on this machine yet")
    print(f"Added {NAME} to Steam ({accounts} account{'s' if accounts > 1 else ''})"
          + (", which is starting again" if restart else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
