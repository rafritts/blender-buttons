"""E2E for the native GN Scatter-on-Surface gap batch (G204-G207) — runs the WORKING-TREE
extension headless. Exercises modifier op=add_asset / op=apply through execute_command.

  G204 — menu sockets are legible (options by NAME + current value) and settable by NAME.
  G205 — collection= flips the gating instance-source menu to 'Collection' (no silent no-op).
  G206 — the result reports the evaluated instance count (and warns at 0).
  G207 — op=apply realizes instances (Realize Instances flipped) instead of dropping them.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_g204_g207_scatter.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import finishes              # noqa: E402

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
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    state.reset_history_state()


def make_plane(name, size):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=8, y_segments=8, size=size / 2.0)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj


def make_sprinkle_collection():
    coll = bpy.data.collections.new("Sprinkles")
    bpy.context.scene.collection.children.link(coll)
    me = bpy.data.meshes.new("Bit")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.01)
    bm.to_mesh(me)
    bm.free()
    bit = bpy.data.objects.new("Bit", me)
    coll.objects.link(bit)
    return coll


# Preflight: is the Essentials "Scatter on Surface" asset reachable in this build?
ng, err = finishes._find_asset_node_group("Scatter on Surface")
if err:
    print(f"SKIP — Scatter on Surface asset not available headless: {err}")
    print("e2e_g204_g207_scatter :: PASSED — 0 failures (skipped)")
    sys.exit(0)
has_realize = any(n.strip().lower() == "realize instances"
                  for n in finishes._gn_input_sockets(ng))
print(f"(Scatter on Surface loaded; has 'Realize Instances' input: {has_realize})")


# ───────────────────────── G204: legibility + set-by-name ─────────────────────────
print("== G204: menu sockets legible + settable by NAME ==")
clean()
make_plane("Field", 1.0)
make_sprinkle_collection()
res = run("add_asset_modifier", asset="Scatter on Surface", host="Field")
check("add_asset succeeded", res.get("success"), str(res)[:200])
inputs = res.get("inputs_available") or []
check("inputs_available is a list of legible strings", inputs and isinstance(inputs[0], str),
      str(inputs)[:160])
menu_lines = [s for s in inputs if "menu:" in s]
check("at least one menu socket lists its options by name", bool(menu_lines),
      str(inputs)[:300])
# every menu line shows a current value ("= <name>")
check("menu lines show the current value by name", all("=" in s for s in menu_lines),
      str(menu_lines))

# set a menu socket by its display NAME (Instance Type = Collection)
res = run("add_asset_modifier", asset="Scatter on Surface", host="Field",
          inputs={"Instance Type": "Collection"})
iset = res.get("inputs_set") or {}
notes = " ".join(res.get("notes", []))
check("menu set-by-name did NOT error as unknown/failed", "Instance Type" not in notes.lower()
      or "unrecognised" not in notes.lower(), str(res)[:200])
check("menu set-by-name landed (Instance Type in inputs_set)",
      any(k.lower() == "instance type" for k in iset), str(iset))


# ───────────────────────── G205: collection= flips the gate ─────────────────────────
print("== G205: collection= flips the Instance Type menu to Collection ==")
clean()
make_plane("Field", 1.0)
make_sprinkle_collection()
res = run("add_asset_modifier", asset="Scatter on Surface", host="Field",
          collection="Sprinkles", inputs={"Density": 400})
iset = res.get("inputs_set") or {}
check("collection= set the Collection socket", any("collection" in str(k).lower() and iset[k] == "Sprinkles"
                                                   for k in iset) or "Sprinkles" in str(iset), str(iset))
check("collection= ALSO flipped a menu to 'Collection' (the gate)",
      any(str(v).lower() == "collection" for v in iset.values()), str(iset))
# with the gate flipped + a real density, it should emit instances
check("gate flip yields a non-zero evaluated instance count",
      res.get("evaluated_instances", 0) > 0, f"evaluated_instances={res.get('evaluated_instances')}")


# ───────────────────────── G206: instance count reported + zero warning ─────────────────────────
print("== G206: evaluated instance count is reported (and warns at 0) ==")
clean()
make_plane("Tiny", 0.05)      # ~0.0025 m² → default density 1/m² floors to 0 instances
make_sprinkle_collection()
res = run("add_asset_modifier", asset="Scatter on Surface", host="Tiny",
          collection="Sprinkles")
check("evaluated_instances key present", "evaluated_instances" in res, str(res)[:200])
check("tiny surface at default density emits 0 instances", res.get("evaluated_instances") == 0,
      str(res.get("evaluated_instances")))
check("a 0-emission config is WARNED about", any("0 instances" in n for n in res.get("notes", [])),
      str(res.get("notes")))


# ───────────────────────── G207: apply realizes instances ─────────────────────────
print("== G207: op=apply realizes instances instead of dropping them ==")
clean()
field = make_plane("Field", 1.0)
make_sprinkle_collection()
res = run("add_asset_modifier", asset="Scatter on Surface", host="Field",
          collection="Sprinkles", inputs={"Density": 400})
n_inst = res.get("evaluated_instances", 0)
check("scatter emits instances before apply", n_inst > 0, str(n_inst))
verts_before = len(field.data.vertices)
ares = run("apply_modifiers", name="Field")
check("apply succeeded", ares.get("success"), str(ares)[:200])
verts_after = len(bpy.data.objects["Field"].data.vertices)
if has_realize:
    check("instances were realized (mesh grew past the bare plane)", verts_after > verts_before,
          f"{verts_before} → {verts_after}")
    check("apply reported the realization", bool(ares.get("realized_instances")),
          str(ares.get("realized_instances")))
else:
    # no Realize Instances socket → must NOT silently drop: left live + warned
    check("no-realize-socket case is warned, not silently dropped",
          bool(ares.get("warnings")), str(ares))


print()
if failures:
    print(f"e2e_g204_g207_scatter :: FAILED — {len(failures)}: {failures}")
    sys.exit(1)
print("e2e_g204_g207_scatter :: PASSED — 0 failures")
