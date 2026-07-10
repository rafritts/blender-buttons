"""E2E for SPEC-21 Phase 3 — offered selections + claiming, headless.

Three meshes with known-by-construction segmentation:
  A "Compound": a subdivided cube (6 crease-bounded regions, mirror-twinned
     sides) + a detached 3×3 plate (island) + a detached open tube (island with
     two boundary loops).
  B "Marked": a subdivided cube with two material slots and a "brand" vertex
     group spanning parts of two sides (material/vgroup patch candidates).
  C "Bird": a UV-sphere with two welded mirror arms (protrusion candidates,
     twinned, coverage < 100%).
Asserts: the offer (kinds, counts, dedup, coverage honesty line), claiming
(select-only, minting, updating, region algebra, twins), ephemerality on
window change, and legible errors.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_spec21_phase3.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402
import math       # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import windows as bb_windows # noqa: E402
from extension import handles as bb_handles # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    state.reset_history_state()
    bb_windows.reset()


def link(bm, name):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def build_compound(name="Compound"):
    bm = bmesh.new()
    # cube at origin, each side subdivided into 4 faces → 6 crease regions
    res = bmesh.ops.create_cube(bm, size=0.2)
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=1, use_grid_fill=True)
    # detached plate island at +X
    res = bmesh.ops.create_grid(bm, x_segments=3, y_segments=3, size=0.03)
    for v in res["verts"]:
        v.co.x += 0.3
    # detached open tube at -X (cap_ends False → two boundary loops)
    res = bmesh.ops.create_cone(bm, cap_ends=False, segments=12,
                                radius1=0.03, radius2=0.03, depth=0.1)
    for v in res["verts"]:
        v.co.x -= 0.3
    return link(bm, name)


def vgroup_verts(obj, vgname):
    vg = obj.vertex_groups.get(vgname)
    if vg is None:
        return None
    gi = vg.index
    return {v.index for v in obj.data.vertices
            if any(g.group == gi and g.weight > 0 for g in v.groups)}


def selected_verts(obj):
    return {v.index for v in obj.data.vertices if v.select}


print("== the offer: islands + regions + loops, coverage line ==")
clean()
obj = build_compound()
res = run("look_window", target="Compound")
check("root look succeeds", res.get("success"), str(res))
w = res.get("window", {})
cands = w.get("candidates", [])
kinds = {}
for c in cands:
    kinds.setdefault(c["kind"], []).append(c)
print(f"    offer: {[(c['id'], c['kind'], c['n_faces']) for c in cands]}")
print(f"    coverage: {w.get('coverage')}")
check("islands offered (3 shells)", len(kinds.get("island", [])) == 3, str(kinds))
check("cube's 6 crease regions offered", len(kinds.get("region", [])) == 6, str(kinds))
# three loops: the tube's two rims + the flat plate's outer boundary
check("boundary loops offered (2 tube rims + plate edge)",
      len(kinds.get("loop", [])) == 3, str(kinds.get("loop")))
check("tube rims do NOT twin the plate edge (ring centroids, exclusive pairing)",
      all(not c.get("twin") for c in kinds.get("loop", [])), str(kinds.get("loop")))
check("every candidate has id/kind/token/extent/verts",
      all(c.get("id") and c.get("kind") and c.get("token") and c.get("extent")
          and c.get("n_verts") for c in cands), str(cands))
check("no candidate is the whole window",
      all(c["n_faces"] < w["n_faces"] for c in cands), str(cands))
check("coverage line reports faces AND area",
      "cover" in w.get("coverage", "") and "% of its area" in w.get("coverage", ""),
      str(w.get("coverage")))
check("islands+regions cover all faces (100%)",
      "cover 100%" in w.get("coverage", ""), str(w.get("coverage")))
# the cube's ±X side regions are exact mirrors → twinned
twinned_regions = [c for c in kinds.get("region", []) if c.get("twin")]
check("mirror-side regions are twinned", len(twinned_regions) >= 2,
      str(kinds.get("region")))

print("== claim select-only (no name=): selects, narrates, mints nothing ==")
plate = next(c for c in kinds["island"] if c["n_faces"] == 9)
n_handles_before = len([o for o in bpy.data.objects if o.get("bb_handle")])
res = run("claim_candidate", candidate=plate["id"])
check("claim succeeds", res.get("success"), str(res))
check("selected count = candidate verts", res.get("selected") == plate["n_verts"],
      f"{res.get('selected')} vs {plate['n_verts']}")
check("selection narrated (G220 voice)", "sel:" in res.get("selection_report", ""),
      str(res))
check("island identity in the narration",
      "island" in res.get("selection_report", ""), str(res.get("selection_report")))
check("no handle minted without name=", "handle" not in res, str(res))
check("no Empty appeared", len([o for o in bpy.data.objects if o.get("bb_handle")])
      == n_handles_before, "")
check("mesh selection matches", len(selected_verts(obj)) == plate["n_verts"],
      str(len(selected_verts(obj))))

print("== claim with name=: mints a vgroup-backed handle ==")
res = run("claim_candidate", **{"candidate": plate["id"], "as": "plate"})
check("claim+mint succeeds", res.get("success") and res.get("handle") == "plate",
      str(res))
check("vgroup HANDLE_plate holds exactly the candidate's verts",
      vgroup_verts(obj, "HANDLE_plate") == set(selected_verts(obj))
      and len(vgroup_verts(obj, "HANDLE_plate")) == plate["n_verts"],
      str(res))
check("handle Empty exists in Handles collection",
      bpy.data.collections.get("Handles") is not None
      and "plate" in bpy.data.collections["Handles"].objects, "")

print("== region algebra: candidate ± handle / candidate ids ==")
cube = max(kinds["island"], key=lambda c: c["n_faces"])
left_region = twinned_regions[0]     # a cube side — its verts ⊂ the cube island
res = run("claim_candidate", candidate=cube["id"], subtract=left_region["id"])
check("subtract works (cube minus one side)", res.get("success"), str(res))
# every side vert belongs to the cube island, so the difference is exact
expected = cube["n_verts"] - left_region["n_verts"]
check("algebra arithmetic is exact", res.get("selected") == expected,
      f"{res.get('selected')} vs {expected}")
tube = next(c for c in kinds["island"]
            if c["id"] not in (plate["id"], cube["id"]))
res = run("claim_candidate", **{"candidate": tube["id"], "add": "plate",
                                "as": "extras"})
check("add=handle unions (tube + plate handle)", res.get("success")
      and res.get("selected") == tube["n_verts"] + plate["n_verts"], str(res))
check("handle 'extras' minted", res.get("handle") == "extras"
      and not res.get("handle_updated"), str(res))

print("== claiming into an existing name RE-POINTS the handle ==")
res = run("claim_candidate", **{"candidate": left_region["id"], "as": "extras"})
check("update reported", res.get("success") and res.get("handle_updated") is True,
      str(res))
check("vgroup re-pointed to the region's verts",
      vgroup_verts(obj, res.get("vgroup", "")) is not None
      and len(vgroup_verts(obj, res["vgroup"])) == left_region["n_verts"],
      str(res))
check("no duplicate 'extras.001' Empty",
      "extras.001" not in bpy.data.objects, "")

print("== errors are legible ==")
res = run("claim_candidate", candidate=plate["id"], subtract=plate["id"])
check("empty result errors, names the algebra", "empty" in res.get("error", ""),
      str(res))
res = run("claim_candidate", candidate="c99")
check("unknown candidate lists the offer", "Offered" in res.get("error", "")
      and "c1" in res.get("error", ""), str(res))
res = run("claim_candidate")
check("bare claim errors with guidance", "candidate=" in res.get("error", ""),
      str(res))
res = run("claim_candidate", candidate=plate["id"], add="no_such_thing")
check("unknown operand errors, lists groups", "matches no" in res.get("error", ""),
      str(res))

print("== ephemerality: candidates are per-window ==")
res = run("look_window", at=left_region["token"].split("·")[0]
          if "·" not in left_region["token"] else "left")
if not res.get("success"):
    res = run("look_window", at="left")
check("descent succeeds", res.get("success"), str(res))
w2 = res.get("window", {})
c2 = w2.get("candidates", [])
res = run("claim_candidate", candidate="c1")
if c2:
    check("claim c1 uses the NEW window's offer",
          res.get("success") and res.get("selected") == c2[0]["n_verts"],
          f"{res.get('selected')} vs {c2[0].get('n_verts') if c2 else '-'}")
else:
    check("claim c1 in a candidate-less window errors with the (empty) offer",
          "names no candidate" in res.get("error", ""), str(res))
run("look_window", up=True)

print("== stale window: claim errors legibly after a topology edit ==")
me = obj.data
bm = bmesh.new()
bm.from_mesh(me)
bmesh.ops.create_cube(bm, size=0.01)
bm.to_mesh(me)
bm.free()
res = run("claim_candidate", candidate="c1")
check("stale claim errors", "stale" in res.get("error", ""), str(res))
check("stale error says how to recover", "look target=" in res.get("error", ""),
      str(res))

print("== algebra without a window (handles only) ==")
bb_windows.reset()
res = run("claim_candidate", add="plate", subtract="extras")
check("window-less handle algebra works", res.get("success"), str(res))
res = run("claim_candidate", candidate="c1")
check("window-less candidate claim errors actionably",
      "look target=" in res.get("error", ""), str(res))

print("== material + vgroup patches offered ==")
clean()
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.2)
bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=1, use_grid_fill=True)
obj = link(bm, "Marked")
mat_a = bpy.data.materials.new("Skin")
mat_b = bpy.data.materials.new("Cloth")
obj.data.materials.append(mat_a)
obj.data.materials.append(mat_b)
# slot 1 (Cloth) on the top AND front sides — a 2-side patch that matches no
# single crease region, so dedup keeps it
for p in obj.data.polygons:
    n = p.normal
    if n.z > 0.5 or n.y < -0.5:
        p.material_index = 1
# vgroup "brand" on the left side + part of the front — full faces exist and
# the face set matches no single region either
vg = obj.vertex_groups.new(name="brand")
brand = [v.index for v in obj.data.vertices if v.co.x < -0.09
         or (v.co.y < -0.09 and v.co.z < 0.01)]
vg.add(brand, 1.0, 'REPLACE')
res = run("look_window", target="Marked")
w = res.get("window", {})
cands = w.get("candidates", [])
print(f"    offer: {[(c['id'], c['kind'], c.get('label'), c['n_faces']) for c in cands]}")
mats = [c for c in cands if c["kind"] == "material"]
vgs = [c for c in cands if c["kind"] == "vgroup"]
check("material patches offered with labels",
      len(mats) >= 1 and all(c.get("label") in ("Skin", "Cloth") for c in mats),
      str(mats))
check("vgroup patch offered as 'brand'",
      len(vgs) == 1 and vgs[0].get("label") == "brand", str(vgs))
res = run("claim_candidate", candidate=vgs[0]["id"]) if vgs else {"error": "no vg"}
check("claiming the vgroup patch selects its verts",
      res.get("success") and res.get("selected") == vgs[0]["n_verts"], str(res))

print("== twins on a bilateral figure: the claim prompt ==")
clean()
import mathutils
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=0.15)
for sx in (-1, 1):
    bm.faces.ensure_lookup_table()
    tgt = mathutils.Vector((sx * 0.15, 0.01, 0.0))
    face = min(bm.faces, key=lambda f: (f.calc_center_median() - tgt).length)
    res_e = bmesh.ops.extrude_face_region(bm, geom=[face])
    for v in [g for g in res_e["geom"] if isinstance(g, bmesh.types.BMVert)]:
        v.co.x += sx * 0.25
obj = link(bm, "Bird")
res = run("look_window", target="Bird")
w = res.get("window", {})
cands = w.get("candidates", [])
print(f"    offer: {[(c['id'], c['kind'], c.get('twin')) for c in cands]}")
print(f"    coverage: {w.get('coverage')}")
prots = [c for c in cands if c["kind"] == "protrusion"]
check("welded arms offered as protrusion cuts", len(prots) == 2, str(cands))
check("protrusion candidates are twinned",
      all(c.get("twin") for c in prots), str(prots))
res = run("claim_candidate", **{"candidate": prots[0]["id"], "as": "left_wing"})
check("claim mints left_wing", res.get("success")
      and res.get("handle") == "left_wing", str(res))
check("twin prompt names the mirror candidate",
      prots[1]["id"] in res.get("twin_prompt", ""), str(res.get("twin_prompt")))
check("twin prompt says how to claim it",
      "op=claim" in res.get("twin_prompt", ""), str(res.get("twin_prompt")))

print("== re-look: candidate ids stable ==")
res = run("look_window")
check("bare re-look keeps candidate ids",
      [c["id"] for c in res["window"]["candidates"]] == [c["id"] for c in cands],
      "ids changed")

print("== coverage honesty: empty and partial offers ==")
clean()
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=0.1)
obj = link(bm, "Ball")
res = run("look_window", target="Ball")
w = res.get("window", {})
check("smooth single-shell ball offers no candidates",
      w.get("candidates") == [], str(w.get("candidates")))
check("coverage says so and points at hand selection",
      "no candidates" in (w.get("coverage") or "")
      and "by hand" in (w.get("coverage") or ""), str(w.get("coverage")))
# a vgroup patch on the crown → the offer reaches only that patch
vg = obj.vertex_groups.new(name="crown")
vg.add([v.index for v in obj.data.vertices if v.co.z > 0.07], 1.0, 'REPLACE')
res = run("look_window", target="Ball")
w = res.get("window", {})
cands = w.get("candidates", [])
print(f"    offer: {[(c['id'], c['kind'], c.get('label'), c['n_faces']) for c in cands]}")
print(f"    coverage: {w.get('coverage')}")
check("crown vgroup patch offered",
      any(c["kind"] == "vgroup" and c.get("label") == "crown" for c in cands),
      str(cands))
check("partial offer reports honest <100% coverage",
      "cover 100%" not in (w.get("coverage") or "")
      and "unoffered" in (w.get("coverage") or ""), str(w.get("coverage")))

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("ALL PASS")
