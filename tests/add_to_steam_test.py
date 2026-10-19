#!/usr/bin/env python3
"""Checks scripts/add-to-steam.py against a made-up Steam folder: the entry
is added next to the existing ones, a second run replaces it instead of
adding another (keeping launch options set in Steam), the artwork lands in
the grid folder under the shortcut's app id, and a run with nothing new to
write leaves Steam alone. Steam itself is never started or closed here.

    python3 tests/add_to_steam_test.py
"""
import importlib.util
import struct
import sys
import tempfile
import zlib
from pathlib import Path

sys.dont_write_bytecode = True
repo = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("add_to_steam", repo / "scripts/add-to-steam.py")
steam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(steam)

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + what)
    failures += not ok


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    home, dist, artwork = root / "home", root / "dist", root / "artwork"
    dist.mkdir()
    (dist / "roadtrip.sh").write_bytes(b"")
    artwork.mkdir()
    for name, _ in steam.GRID:
        (artwork / name).write_bytes(name.encode())
    config = home / ".local/share/Steam/userdata/123456/config"
    config.mkdir(parents=True)
    (home / ".local/share/Steam/userdata/0").mkdir()  # the anonymous account
    other = {"appid": -12345, "AppName": "Pinyon Shift", "Exe": '"/games/pinyon"', "StartDir": '"/games"',
             "IsHidden": 0, "tags": {"0": "favorite"}}
    (config / "shortcuts.vdf").write_bytes(steam.dump_vdf({"shortcuts": {"0": other}}))

    check(not steam.up_to_date(home, dist, artwork), "something to do before the first run")
    check(steam.add(home, dist, artwork) == 1, "one account updated, the anonymous one skipped")
    check(steam.add(home, dist, artwork) == 1, "and again")
    data = (config / "shortcuts.vdf").read_bytes()
    parsed, end = steam.parse_vdf(data)
    check(end == len(data), "shortcuts.vdf parses to its end")
    entries = list(parsed["shortcuts"].values())
    check(len(entries) == 2, "two entries after two runs: the other game and Road Trip Adventure")
    check(entries[0] == other, "the other game is unchanged")
    entry = entries[1]
    exe = f'"{dist.resolve() / "roadtrip.sh"}"'
    check(entry["AppName"] == "Road Trip Adventure" and entry["Exe"] == exe and entry["StartDir"] == f'"{dist.resolve()}"',
          "Road Trip Adventure runs roadtrip.sh from its folder")
    expected = zlib.crc32((exe + "Road Trip Adventure").encode()) | 0x80000000
    check(struct.pack("<i", entry["appid"]) == struct.pack("<I", expected), "app id is Steam's crc32 of exe and name")
    grid = config / "grid"
    check(all((grid / name.format(expected)).read_bytes() == source.encode() for source, name in steam.GRID),
          "the five images are in the grid folder under that id")
    check((config / "shortcuts.vdf.roadtrip-backup").read_bytes() ==
          steam.dump_vdf({"shortcuts": {"0": other}}), "the original shortcuts.vdf is backed up once")
    check(steam.dump_vdf(parsed) == data, "parse and dump round-trip")

    check(steam.up_to_date(home, dist, artwork), "nothing to do after a run, so Steam is not closed")
    parsed["shortcuts"]["1"]["LaunchOptions"] = "IR3_SHADER_DEBUG= %command%"
    parsed["shortcuts"]["1"]["LastPlayTime"] = 1760000000
    (config / "shortcuts.vdf").write_bytes(steam.dump_vdf(parsed))
    check(steam.up_to_date(home, dist, artwork), "launch options and play time set by Steam are not a change")
    (artwork / "hero.png").write_bytes(b"a new hero")
    check(not steam.up_to_date(home, dist, artwork), "a new image is")
    steam.add(home, dist, artwork)
    entries = list(steam.parse_vdf((config / "shortcuts.vdf").read_bytes())[0]["shortcuts"].values())
    check(len(entries) == 2 and entries[1]["LaunchOptions"] == "IR3_SHADER_DEBUG= %command%"
          and entries[1]["LastPlayTime"] == 1760000000, "replacing the entry keeps what Steam set on it")
    check((grid / f"{expected}_hero.png").read_bytes() == b"a new hero", "and writes the new image")
    check(steam.up_to_date(home, dist, artwork), "after which there is nothing to do again")

print("all checks passed" if not failures else "SOME CHECKS FAILED")
sys.exit(1 if failures else 0)
