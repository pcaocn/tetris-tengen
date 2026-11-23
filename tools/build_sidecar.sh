#!/usr/bin/env bash
# Build the standalone Python engine used by packaged Tauri builds.
#
# Prerequisites: Rust (for the target triple), uv, and Python 3.10+.
# PyInstaller is fetched by `uv run --with pyinstaller`.
#
# Output: app/src-tauri/binaries/tetris-core-<target-triple>
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
triple="$(rustc --print host-tuple 2>/dev/null || rustc -vV | sed -n 's/^host: //p')"
if [[ -z "$triple" ]]; then
  echo "error: cannot determine Rust target triple" >&2
  exit 1
fi

ext=""
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) ext=".exe" ;;
esac

out_dir="$repo_root/app/src-tauri/binaries"
out="$out_dir/tetris-core-$triple$ext"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/tetris-sidecar.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

echo "Building tetris-core sidecar for $triple..."
(
  cd "$repo_root/core"
  uv run --frozen --with pyinstaller pyinstaller \
    --onefile \
    --clean \
    --noconfirm \
    --name tetris-core \
    --distpath "$tmp" \
    --workpath "$tmp/work" \
    --specpath "$tmp" \
    --paths . \
    --collect-submodules tetris_core \
    "$repo_root/tools/tetris_core_entry.py"
)

mv "$tmp/tetris-core$ext" "$out"
chmod +x "$out"
echo "wrote $out"