"""Single-boot e2e harness — runs EVERY gap-fix suite in ONE headless Blender process.

Booting a flatpak Blender per file costs ~30–60s each; 11 files ≈ 10 min, useless for
iteration. This boots Blender ONCE and exec's each suite in its own fresh namespace, so
the whole round runs in a single ~30–60s process.

Usage (exactly one Blender boot):
    flatpak run org.blender.Blender --background --python tests/run_all_in_one.py

Each suite file is written to run standalone: it sets up its own objects via clean(),
records `failures`, and calls sys.exit(1) ONLY on failure (printing "ALL PASSED" on
success). Here we trap that sys.exit so one failing suite doesn't abort the rest, and we
scrub cross-suite state (scene objects + validation intents) between suites.
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import bpy  # noqa: E402
from extension import validation  # noqa: E402

SUITES = [
    "e2e_g132_g122_by_radius.py",
    "e2e_g129_topology_floor.py",
    "e2e_g119_g125_g133_floor_budget.py",
    "e2e_g102_g128_radial.py",
    "e2e_g106_g109_g127_hollow_boolean.py",
    "e2e_g120_g121_creation_guards.py",
    "e2e_g123_relational.py",
    "e2e_g103_g113_instanced.py",
    "e2e_g126_pbr_alpha.py",
    "e2e_g131_visibility.py",
    "e2e_g100_coverage.py",
    "e2e_g136_g141_gapfixes.py",
]


def scrub():
    """Reset the world between suites so leaked state can't cross-contaminate a verdict."""
    if bpy.context.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    # drop the validation registry AND its scene-persisted backing (G125 reload source)
    try:
        sc = bpy.context.scene
        if sc is not None and "bb_intents" in sc:
            del sc["bb_intents"]
    except Exception:
        pass
    validation._intents.clear()
    validation._drift = 0.0


results = []  # (suite, "PASS"|"FAIL"|"ERROR", detail)

for suite in SUITES:
    path = os.path.join(HERE, suite)
    print(f"\n{'=' * 70}\n=== {suite} ===\n{'=' * 70}")
    scrub()
    ns = {"__name__": "__main__", "__file__": path}
    try:
        with open(path) as fh:
            code = compile(fh.read(), path, "exec")
        exec(code, ns)
        # fell through without sys.exit → suite passed (it prints "ALL PASSED")
        results.append((suite, "PASS", ""))
    except SystemExit as e:
        code = e.code
        if code in (0, None):
            results.append((suite, "PASS", ""))
        else:
            results.append((suite, "FAIL", f"exit {code}"))
    except Exception:
        traceback.print_exc()
        results.append((suite, "ERROR", traceback.format_exc().strip().splitlines()[-1]))

print(f"\n\n{'#' * 70}\n# SUMMARY\n{'#' * 70}")
npass = sum(1 for _, v, _ in results if v == "PASS")
nfail = len(results) - npass
for suite, verdict, detail in results:
    mark = "ok  " if verdict == "PASS" else "XX  "
    print(f"  {mark}{verdict:5} {suite}" + (f"   ({detail})" if detail else ""))
print(f"\n==== {npass}/{len(results)} suites passed ====")
if nfail:
    print("HARNESS RESULT: FAIL")
else:
    print("HARNESS RESULT: ALL SUITES PASSED")
