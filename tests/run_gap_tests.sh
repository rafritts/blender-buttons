#!/usr/bin/env bash
# Run the full gap-fix e2e round in ONE headless Blender boot (run_all_in_one.py exec's
# every suite in a single process — ~30-60s total, vs ~10 min booting Blender per file).
# The addon's socket server is NOT started on import, so this never collides with a live
# Blender session; we also launch exactly one new process and report its PID.
# Usage: tests/run_gap_tests.sh
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
flatpak run org.blender.Blender --background --python "$DIR/run_all_in_one.py" &
PID=$!
echo "harness PID=$PID"
wait $PID
