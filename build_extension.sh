#!/usr/bin/env bash
# Build blender_buttons.zip from extension/ for installation in Blender.
set -euo pipefail

cd "$(dirname "$0")"

OUT=blender_buttons.zip
rm -f "$OUT"
# Bundle every .py in extension/ plus the manifest. Adding a new module
# (e.g. extension/decorate.py) needs no build script change.
(cd extension && zip -r "../$OUT" *.py blender_manifest.toml)

echo "Built $OUT:"
unzip -l "$OUT"
