"""Pure-Python test for the Poly Haven client (server/polyhaven.py) — no Blender.

Covers the network/cache half of T6/T7 that the headless Blender harness can't:
catalog search, download-then-cache-hit via the download counter, and clean
errors on bad ids. Network-gated: skips cleanly when Poly Haven is unreachable.

Usage: .venv/bin/python tests/test_polyhaven.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import polyhaven as ph  # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + (f"  {detail}" if not cond else ""))
    if not cond:
        failures.append(label)


# Reachability gate
try:
    ph.catalog("textures", force=True)
except ph.PolyHavenError as e:
    print(f"Poly Haven unreachable ({e}) — skipping network tests.")
    sys.exit(0)

print("== search ==")
res = ph.search("brick", "textures", 5)
check("search returns hits", len(res) > 0, res)
check("hits have id + tags", all("id" in r and "tags" in r for r in res))

print("== texture download + cache ==")
import shutil  # noqa: E402
aid = res[0]["id"]
# Start from a cold cache for this asset so the first resolve truly downloads.
shutil.rmtree(ph.CACHE_ROOT / "textures" / aid, ignore_errors=True)
ph.reset_download_count()
maps = ph.ensure_texture_maps(aid, "1k")
check("diffuse map resolved", "diffuse" in maps, maps)
check("map files exist on disk", all(os.path.exists(p) for p in maps.values()))
check("first resolve downloaded", ph.download_count() > 0, ph.download_count())
ph.reset_download_count()
ph.ensure_texture_maps(aid, "1k")
check("second resolve hits cache (0 downloads)", ph.download_count() == 0, ph.download_count())

print("== bad id ==")
try:
    ph.ensure_texture_maps("definitely_not_a_real_asset_xyz_123", "1k")
    check("bad id raises", False, "no error raised")
except ph.PolyHavenError:
    check("bad id raises PolyHavenError", True)

print("== hdri search + download ==")
hres = ph.search("studio", "hdris", 5)
check("hdri search returns hits", len(hres) > 0, hres)
hid = hres[0]["id"]
shutil.rmtree(ph.CACHE_ROOT / "hdris" / hid, ignore_errors=True)
ph.reset_download_count()
hpath = ph.ensure_hdri(hid, "1k")
check("hdri resolved to .hdr/.exr", hpath.endswith((".hdr", ".exr")), hpath)
check("hdri file exists in cache dir", os.path.exists(hpath) and str(ph.CACHE_ROOT) in hpath, hpath)
check("hdri first resolve downloaded", ph.download_count() == 1, ph.download_count())
ph.reset_download_count()
ph.ensure_hdri(hid, "1k")
check("hdri second resolve cached", ph.download_count() == 0, ph.download_count())

print()
if failures:
    print(f"POLYHAVEN: {len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("POLYHAVEN: ALL TESTS PASSED")
