#!/usr/bin/env bash
# Builds the launcher (launcher/) for this machine and packs it with the
# license files as OUT/RoadTrip-Launcher-linux-<arch>.tar.gz. The release
# workflow runs it on an ARM64 runner.
#
#   scripts/package-launcher.sh [OUT]
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
out="${1:-$repo/out}"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
arch="$(uname -m)"
case "$arch" in aarch64|arm64) arch=arm64 ;; x86_64|amd64) arch=x86_64 ;; esac

cargo build --release --locked --manifest-path "$repo/launcher/Cargo.toml"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/RoadTrip"
cp "$repo/launcher/target/release/roadtrip-launcher" "$repo/LICENSE" "$repo/NOTICE" "$stage/RoadTrip/"
archive="$out/RoadTrip-Launcher-linux-$arch.tar.gz"
tar -C "$stage" --owner=0 --group=0 -czf "$archive" RoadTrip
echo "$archive"
