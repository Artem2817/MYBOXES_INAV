#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 1 ]]; then
    echo "Usage: bash $0 <dedicated INAV checkout>" >&2
    exit 2
fi

overlay_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
checkout=$1
tag=9.1.0
revision=e519b69b02e27c8bdc03b4a0889f1baaae211a54

export PATH="$checkout/tools/mybox-ruby/bin:$PATH"
for tool in git cmake make ruby; do
    if ! command -v "$tool" >/dev/null; then
        echo "Missing build dependency: $tool" >&2
        exit 1
    fi
done

if [[ ! -e "$checkout" ]]; then
    git -c advice.detachedHead=false clone --depth 1 --single-branch --branch "$tag" \
        https://github.com/iNavFlight/inav.git "$checkout"
fi

if [[ ! -d "$checkout/.git" || $(git -C "$checkout" rev-parse HEAD) != "$revision" ]]; then
    echo "Use a dedicated INAV $tag checkout at $revision." >&2
    exit 1
fi

target_dir="$checkout/src/main/target/MYBOXH743MINI"
if [[ -e "$target_dir" ]]; then
    diff -qr -- "$overlay_dir/target/MYBOXH743MINI" "$target_dir" || {
        echo "The checkout already has a different MYBOX target. Use a fresh checkout." >&2
        exit 1
    }
else
    cp -R -- "$overlay_dir/target/MYBOXH743MINI" "$target_dir"
fi

for patch in "$overlay_dir/spa06-003.patch" "$overlay_dir/i2c4-pb9.patch"; do
    if ! git -C "$checkout" apply --reverse --check "$patch" 2>/dev/null; then
        git -C "$checkout" apply "$patch"
    fi
done

build_dir="$checkout/build-mybox"
cmake -S "$checkout" -B "$build_dir" -G 'Unix Makefiles' -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --parallel "${JOBS:-4}" \
    --target MYBOXH743MINI MYBOXH743MINIV2 MYBOXH743MINIV2VIB_BENCH

printf '\nHEX files are in %s\n' "$build_dir"
