#!/usr/bin/env bash
# Sets up Road Trip Adventure (PlayStation 2) on an ARM64 Linux handheld:
# gets ARMSX2's Linux arm64 AppImage from its GitHub releases (or keeps the
# one already here when it is the newest), puts the player's own BIOS where
# ARMSX2 looks for it, writes ARMSX2's settings for a handheld, and writes
# DIR/game/roadtrip.sh, which starts the game. Running it again updates
# ARMSX2 and rewrites the settings; finished steps are skipped.
#
#   scripts/install.sh DISC BIOS [DIR]
#
# DISC  the game's disc image (.iso, .chd, .cso, .zso, .gz or .cue), or - to
#       keep the one set before
# BIOS  a BIOS file dumped from your own PlayStation 2, or - to keep the one
#       set before
# DIR   where everything goes (default ~/.local/share/RoadTrip-arm64)
#
# Environment:
#   RT_SCALE=1..8           internal resolution (default 2; 1 draws the least power)
#   RT_RENDERER=vulkan|opengl
#   RT_CHANNEL=stable|nightly   ARMSX2 releases to take (stable falls back
#                               to the newest nightly while there is none)
#   RT_ADD_TO_STEAM=1       add the game to Steam at the end
#   RT_ARTWORK=0            skip the Steam artwork download
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
disc="${1:?usage: install.sh DISC BIOS [DIR]}"
bios="${2:?usage: install.sh DISC BIOS [DIR]}"
dir="${3:-$HOME/.local/share/RoadTrip-arm64}"
scale="${RT_SCALE:-2}"
renderer="${RT_RENDERER:-vulkan}"
channel="${RT_CHANNEL:-stable}"
mkdir -p "$dir"
dir="$(cd "$dir" && pwd)"
data="$dir/ARMSX2"
game="$dir/game"
artwork="$dir/artwork"
emulators="$dir/armsx2"
mkdir -p "$data/bios" "$data/inis" "$game" "$artwork" "$emulators"

step() { echo "==> $*"; }
fail() { echo "error: $*" >&2; exit 1; }

case "$(uname -m)" in
    aarch64|arm64) ;;
    *) [ -n "${RT_ALLOW_OTHER_ARCH:-}" ] || fail "ARMSX2's Linux build is for ARM64 handhelds, not $(uname -m)" ;;
esac

# --- The disc --------------------------------------------------------------
step "Checking the disc image"
if [ "$disc" != - ]; then
    [ -f "$disc" ] || fail "$disc is not a file"
    disc="$(cd "$(dirname "$disc")" && pwd)/$(basename "$disc")"
    case "${disc,,}" in
        *.iso|*.chd|*.cso|*.zso|*.gz|*.cue|*.bin|*.mdf|*.img) ;;
        *) fail "$(basename "$disc") is not a disc image ARMSX2 opens (.iso, .chd, .cso, .zso, .gz or .cue)" ;;
    esac
    printf '%s\n' "$disc" > "$game/disc.txt"
fi
[ -s "$game/disc.txt" ] || fail "choose your Road Trip Adventure disc image first"
disc="$(cat "$game/disc.txt")"
[ -f "$disc" ] || fail "the disc image set before, $disc, is gone: choose it again"
echo "Disc: $disc"

# --- The BIOS --------------------------------------------------------------
step "Putting your BIOS in place"
if [ "$bios" != - ]; then
    [ -f "$bios" ] || fail "$bios is not a file"
    size="$(stat -c %s "$bios")"
    # PlayStation 2 BIOS dumps are 4 MB (some with the 1 MB of the DVD
    # player's ROM and the like beside them, in files of their own).
    [ "$size" -ge $((4 << 20)) ] && [ "$size" -le $((16 << 20)) ] ||
        fail "$(basename "$bios") ($size bytes) does not look like a PlayStation 2 BIOS, which is 4 MB"
    name="$(basename "$bios")"
    if [ "$(cd "$(dirname "$bios")" && pwd)" != "$data/bios" ]; then
        cp -f "$bios" "$data/bios/$name"
        # The ROM1/ROM2/NVM/MEC files of the same dump, when they sit beside it.
        stem="${bios%.*}"
        for extra in "$stem".rom1 "$stem".rom2 "$stem".nvm "$stem".mec "$stem".ROM1 "$stem".ROM2 "$stem".NVM "$stem".MEC; do
            [ ! -f "$extra" ] || cp -f "$extra" "$data/bios/"
        done
    fi
    printf '%s\n' "$name" > "$dir/bios.txt"
fi
[ -s "$dir/bios.txt" ] || fail "choose the BIOS dumped from your own PlayStation 2 first"
bios_name="$(cat "$dir/bios.txt")"
[ -f "$data/bios/$bios_name" ] || fail "the BIOS set before, $bios_name, is gone from $data/bios: choose it again"
echo "BIOS: $bios_name"

# --- ARMSX2 ----------------------------------------------------------------
step "Getting ARMSX2 ($channel)"
case "$(getconf PAGESIZE 2>/dev/null || echo 4096)" in
    16384) pages=16K ;;
    *) pages=4K ;;
esac
installed="$(cat "$emulators/installed" 2>/dev/null || true)"
# RT_RELEASES: a saved copy of the list instead (for the tests).
if [ -n "${RT_RELEASES:-}" ]; then
    releases="$(cat "$RT_RELEASES")"
else
    # GH_TOKEN only lifts GitHub's rate limit on shared machines such as CI.
    auth=()
    [ -z "${GH_TOKEN:-}" ] || auth=(-H "Authorization: Bearer $GH_TOKEN")
    releases="$(curl -fsSL --retry 3 -H 'Accept: application/vnd.github+json' "${auth[@]}" \
        'https://api.github.com/repos/ARMSX2/ARMSX2/releases?per_page=40' 2>/dev/null || true)"
fi
choice=""
if [ -n "$releases" ]; then
    choice="$(printf '%s' "$releases" | python3 "$repo/scripts/pick-release.py" "$channel" "$pages")" ||
        fail "ARMSX2 has no Linux arm64 ($pages pages) build in its releases right now"
fi
if [ -z "$choice" ]; then
    [ -n "$installed" ] && [ -x "$emulators/$installed/AppRun" ] ||
        fail "could not reach GitHub to download ARMSX2: connect to the internet and try again"
    echo "Could not reach GitHub: keeping ARMSX2 $installed"
    tag="$installed"
else
    IFS='|' read -r tag url sha256 note <<< "$choice"
    [ -z "$note" ] || echo "$note"
    if [ "$tag" = "$installed" ] && [ -x "$emulators/$tag/AppRun" ]; then
        echo "ARMSX2 $tag is already here, the newest"
    else
        echo "Downloading ARMSX2 $tag"
        download="$emulators/download.AppImage"
        curl -fL --retry 3 -o "$download" "$url"
        if [ -n "$sha256" ]; then
            echo "$sha256  $download" | sha256sum -c --quiet - || fail "the ARMSX2 download is damaged: try again"
        fi
        chmod +x "$download"
        # Unpacked once rather than mounted at every start: no FUSE needed.
        rm -rf "$emulators/squashfs-root" "$emulators/$tag"
        (cd "$emulators" && ./download.AppImage --appimage-extract > /dev/null)
        [ -x "$emulators/squashfs-root/AppRun" ] || fail "the ARMSX2 AppImage did not unpack"
        mv "$emulators/squashfs-root" "$emulators/$tag"
        rm -f "$download"
        printf '%s\n' "$tag" > "$emulators/installed"
        for old in "$emulators"/*/; do
            old="$(basename "$old")"
            [ "$old" = "$tag" ] || rm -rf "${emulators:?}/$old"
        done
        echo "ARMSX2 $tag is ready"
    fi
fi

# --- Settings and the start script -----------------------------------------
step "Writing the settings"
python3 "$repo/scripts/configure.py" "$data/inis/PCSX2.ini" --bios "$bios_name" --scale "$scale" --renderer "$renderer"

cat > "$game/roadtrip.sh.tmp" <<EOF
#!/usr/bin/env bash
# Starts Road Trip Adventure in ARMSX2 $tag, full screen. Written by
# road-trip-arm64's scripts/install.sh; run it again to change anything.
#
#   roadtrip.sh             plays the game
#   roadtrip.sh --settings  opens ARMSX2's own window, with the same settings
dir='$dir'
emulator="\$dir/armsx2/$tag/AppRun"
# The Qt build draws through X11 (XWayland on a Wayland desktop and in
# Steam's Game Mode, which runs games under gamescope's XWayland).
[ -z "\${DISPLAY:-}" ] || export QT_QPA_PLATFORM="\${QT_QPA_PLATFORM:-xcb}"
if [ "\${1:-}" = --settings ]; then
    exec "\$emulator" -datapath "\$dir"
fi
disc="\$(cat "\$dir/game/disc.txt")"
[ -f "\$disc" ] || { echo "error: the disc image \$disc is gone: choose it again in the launcher" >&2; exit 1; }
exec "\$emulator" -datapath "\$dir" -nogui -fullscreen "\$@" -- "\$disc"
EOF
chmod +x "$game/roadtrip.sh.tmp"
mv "$game/roadtrip.sh.tmp" "$game/roadtrip.sh"
echo "Start script: $game/roadtrip.sh"

# --- Artwork ---------------------------------------------------------------
if [ "${RT_ARTWORK:-1}" != 0 ]; then
    step "Getting the Steam artwork"
    # libretro-thumbnails names them after the No-Intro title of each release.
    name="$(basename "$disc")"
    case "${name,,}" in
        *usa*|*ntsc-u*|*slus*) title="Road Trip (USA)" ;;
        *korea*|*slka*) title="Choro Q HG 2 (Korea) (En,Fr,De)" ;;
        *japan*|*slpm*|*choro*) title="Choro Q HG 2 (Japan)" ;;
        *) title="Road Trip Adventure (Europe, Australia) (En,Fr,De)" ;;
    esac
    encoded="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$title.png")"
    base="https://raw.githubusercontent.com/libretro-thumbnails/Sony_-_PlayStation_2/master"
    got=0
    for pair in Named_Boxarts:capsule Named_Titles:wide Named_Snaps:hero Named_Boxarts:icon; do
        folder="${pair%%:*}" file="${pair#*:}.png"
        if [ -s "$artwork/$file" ] && [ "$(cat "$artwork/source" 2>/dev/null)" = "$title" ]; then
            got=$((got + 1))
            continue
        fi
        if curl -fsSL --retry 2 -o "$artwork/$file.tmp" "$base/$folder/$encoded" &&
            [ "$(head -c 4 "$artwork/$file.tmp" | od -An -tx1 | tr -d ' ')" = 89504e47 ]; then
            mv "$artwork/$file.tmp" "$artwork/$file"
            got=$((got + 1))
        else
            rm -f "$artwork/$file.tmp"
        fi
    done
    printf '%s\n' "$title" > "$artwork/source"
    echo "Artwork: $got of 4 pictures ($title)"
fi

if [ "${RT_ADD_TO_STEAM:-0}" = 1 ]; then
    step "Adding Road Trip Adventure to Steam"
    bash "$repo/scripts/add-to-steam.sh" "$dir"
fi
echo "Road Trip Adventure is ready: $game/roadtrip.sh"
