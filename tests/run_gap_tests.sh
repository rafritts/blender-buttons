#!/usr/bin/env bash
# Run all the gap-fix e2e tests (this round) one Blender process each, report pass/fail.
# Usage: tests/run_gap_tests.sh
# Each test boots a fresh headless Blender; the addon's socket server is NOT started on
# import, so this does not collide with a live Blender session.
set -u
cd "$(dirname "$0")/.."
BL="flatpak run org.blender.Blender"
TESTS=(
  e2e_g132_g122_by_radius.py
  e2e_g129_topology_floor.py
  e2e_g119_g125_g133_floor_budget.py
  e2e_g102_g128_radial.py
  e2e_g106_g109_g127_hollow_boolean.py
  e2e_g120_g121_creation_guards.py
  e2e_g123_relational.py
  e2e_g103_g113_instanced.py
  e2e_g126_pbr_alpha.py
  e2e_g131_visibility.py
  e2e_g100_coverage.py
)
pass=0; fail=0; failed=()
for t in "${TESTS[@]}"; do
  echo "=== $t ==="
  out=$($BL --background --python "$(pwd)/tests/$t" 2>&1)
  if echo "$out" | grep -q "ALL PASSED"; then
    echo "  PASS"; pass=$((pass+1))
  else
    echo "  FAIL"; fail=$((fail+1)); failed+=("$t")
    echo "$out" | grep -E 'FAIL |FAILED|Error|Traceback' | head -20
  fi
done
echo
echo "==== $pass passed, $fail failed ===="
[ $fail -eq 0 ] || { printf '  failed: %s\n' "${failed[@]}"; exit 1; }
