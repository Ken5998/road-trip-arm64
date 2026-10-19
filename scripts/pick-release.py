#!/usr/bin/env python3
"""Picks the ARMSX2 release to install from the GitHub releases list on
standard input (newest first, as the API returns it):

    pick-release.py stable|nightly 4K|16K < releases.json

Prints TAG|URL|SHA256|NOTE for the newest release with a Linux arm64 Qt
AppImage for this page size: the newest stable one, or with "nightly" the
newest of any. SHA256 is empty when GitHub has no digest for the file. While
ARMSX2 has no stable Linux release, "stable" takes the newest nightly and
says so in NOTE. Exits 1 when there is no such build at all.
"""
import json
import sys


def pick(releases: list, channel: str, pages: str) -> str | None:
    suffix = f"Linux-arm64-{pages}-pages.AppImage"
    builds = []
    for release in releases:
        if release.get("draft"):
            continue
        for asset in release.get("assets", []):
            if asset.get("name", "").endswith(suffix):
                digest = asset.get("digest") or ""
                sha256 = digest.removeprefix("sha256:") if digest.startswith("sha256:") else ""
                builds.append((release, asset["browser_download_url"], sha256))
                break
    stable = [b for b in builds if not b[0].get("prerelease")]
    note = ""
    if channel == "nightly" or not stable:
        if channel != "nightly" and builds:
            note = "ARMSX2 has no stable Linux release yet: taking the newest nightly"
        chosen = builds[0] if builds else None
    else:
        chosen = stable[0]
    if not chosen:
        return None
    return "|".join((chosen[0]["tag_name"], chosen[1], chosen[2], note))


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("stable", "nightly") or argv[2] not in ("4K", "16K"):
        print(__doc__, file=sys.stderr)
        return 2
    line = pick(json.load(sys.stdin), argv[1], argv[2])
    if line is None:
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
