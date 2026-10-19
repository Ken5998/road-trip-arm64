#!/usr/bin/env bash
# Runs scripts/install.sh against a made-up ARMSX2 release (a stand-in
# AppImage that unpacks to an AppRun printing its arguments), a fake disc and
# a fake 4 MB BIOS, then checks the settings, the start script and a second
# run that keeps everything.
#
#   tests/install_test.sh
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fail() { echo "FAIL $*"; exit 1; }
ok() { echo "ok   $*"; }

mkdir -p "$work/release" "$work/discs"
cat > "$work/release/ARMSX2.AppImage" <<'APPIMAGE'
#!/usr/bin/env bash
[ "$1" = --appimage-extract ] || exit 1
mkdir -p squashfs-root
printf '#!/usr/bin/env bash\necho "ARMSX2 $*"\n' > squashfs-root/AppRun
chmod +x squashfs-root/AppRun
APPIMAGE
sha="$(sha256sum "$work/release/ARMSX2.AppImage" | cut -d' ' -f1)"
pages="$( [ "$(getconf PAGESIZE)" = 16384 ] && echo 16K || echo 4K)"
cat > "$work/releases.json" <<JSON
[{"tag_name": "nightly-20261018", "draft": false, "prerelease": true,
  "assets": [{"name": "ARMSX2-nightly-20261018-abc-Linux-arm64-$pages-pages.AppImage",
              "browser_download_url": "file://$work/release/ARMSX2.AppImage", "digest": "sha256:$sha"}]},
 {"tag_name": "2.8.5", "draft": false, "prerelease": false,
  "assets": [{"name": "ARMSX2-2.8.5-Android.apk", "browser_download_url": "file:///nothing"}]}]
JSON
truncate -s 10M "$work/discs/Road Trip Adventure (Europe).iso"
truncate -s 4M "$work/scph-39004.bin"

export RT_RELEASES="$work/releases.json" RT_ALLOW_OTHER_ARCH=1 RT_ARTWORK="${RT_ARTWORK:-0}" RT_SCALE=1
out="$(bash "$repo/scripts/install.sh" "$work/discs/Road Trip Adventure (Europe).iso" "$work/scph-39004.bin" "$work/data")"
dir="$work/data"
grep -q "taking the newest nightly" <<< "$out" && ok "no stable Linux build: takes the nightly" || fail "nightly fallback: $out"
[ "$(cat "$dir/armsx2/installed")" = nightly-20261018 ] && [ -x "$dir/armsx2/nightly-20261018/AppRun" ] &&
    ok "ARMSX2 unpacked" || fail "ARMSX2 not unpacked"
[ -f "$dir/ARMSX2/bios/scph-39004.bin" ] && ok "BIOS copied" || fail "BIOS missing"
ini="$dir/ARMSX2/inis/PCSX2.ini"
grep -qx 'BIOS = scph-39004.bin' "$ini" && grep -qx 'upscale_multiplier = 1' "$ini" &&
    grep -qx 'SettingsVersion = 1' "$ini" && grep -qx 'Cross = SDL-0/FaceSouth' "$ini" &&
    ok "settings written" || fail "settings: $(cat "$ini")"
run="$("$dir/game/roadtrip.sh")"
[ "$run" = "ARMSX2 -datapath $dir -nogui -fullscreen -- $work/discs/Road Trip Adventure (Europe).iso" ] &&
    ok "roadtrip.sh starts the disc" || fail "roadtrip.sh ran: $run"

# Second run: keeps the disc, BIOS and ARMSX2, keeps a setting changed in ARMSX2.
sed -i 's/^\[EmuCore\/GS\]$/&\nOsdShowFPS = true/' "$ini"
out="$(RT_SCALE=3 bash "$repo/scripts/install.sh" - - "$work/data")"
grep -q "already here" <<< "$out" && ok "second run keeps ARMSX2" || fail "second run: $out"
grep -qx 'OsdShowFPS = true' "$ini" && grep -qx 'upscale_multiplier = 3' "$ini" &&
    [ "$(grep -c '^\[EmuCore/GS\]' "$ini")" = 1 ] && ok "settings merged, ARMSX2's own kept" || fail "merge: $(cat "$ini")"
[ "$(grep -c '^OpenPauseMenu = ' "$ini")" = 2 ] && ok "pause menu on two bindings" || fail "hotkeys"

# A run with nothing set fails with a message.
if bash "$repo/scripts/install.sh" - - "$work/empty" 2> "$work/err" > /dev/null; then fail "empty run passed"; fi
grep -q "choose your Road Trip Adventure disc image" "$work/err" && ok "asks for the disc" || fail "$(cat "$work/err")"
if [ "$RT_ARTWORK" != 0 ]; then
    [ "$(ls "$dir/artwork"/*.png | wc -l)" = 4 ] && ok "artwork downloaded" || fail "artwork: $(ls "$dir/artwork")"
fi
echo "all checks passed"
