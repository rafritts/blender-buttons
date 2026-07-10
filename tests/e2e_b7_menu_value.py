"""E2E regression for B7 — GN menu/enum inputs must be written by the modifier's stored enum
VALUE (id_properties_ui), not the node-graph declaration index. On Scatter on Surface those
disagree (Instance Type Object=1/Collection=0, Density Method Density=1/Amount=0), so the old
index write silently selected the wrong option — collection= scattered from an empty Object
source and emitted nothing, while the readback laundered it as 'Collection'.

Headless GN eval does NOT honor menu sockets (both int values realize identical geometry), so
this asserts on the DATA the modifier stores — which is exactly what a GUI Blender evaluates
and what the N-panel round-trips. Setting a menu by name must land the authoritative value.

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_b7_menu_value.py
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


ng, err = finishes._find_asset_node_group("Scatter on Surface")
if err:
    print(f"SKIP — Scatter on Surface asset not available headless: {err}")
    print("e2e_b7_menu_value :: PASSED — 0 failures (skipped)")
    sys.exit(0)

sockets = finishes._gn_input_sockets(ng)


def ident_of(name):
    return next(i for n, (i, _t) in sockets.items() if n.lower() == name.lower())


def authoritative_value(mod, socket_name, option_name):
    """The int the N-panel writes for `option_name` — the ground truth this test defends."""
    items = mod.id_properties_ui(ident_of(socket_name)).as_dict()["items"]
    return next(it[4] for it in items if it[1].lower() == option_name.lower())


def walk_index(socket_name, option_name):
    """The pre-fix (buggy) value: the option's position in node-graph declaration order."""
    walk = finishes._menu_options(ng)
    names = walk.get(ident_of(socket_name), [])
    return next(i for i, nm in enumerate(names) if nm.lower() == option_name.lower())


# ── Preconditions: this asset's Instance Type / Density Method really are reversed, so the
#    test genuinely discriminates value-writes from index-writes. ─────────────────────────
print("== preconditions: menu value != declaration index on this asset ==")
clean()
make_plane("Field", 1.0)
probe = run("add_asset_modifier", asset="Scatter on Surface", host="Field")
mod0 = bpy.data.objects["Field"].modifiers[0]
it_val = authoritative_value(mod0, "Instance Type", "Collection")
it_idx = walk_index("Instance Type", "Collection")
check("Instance Type 'Collection' value != walk index (else test is vacuous)",
      it_val != it_idx, f"value={it_val} index={it_idx}")
dm_val = authoritative_value(mod0, "Density Method", "Density")
dm_idx = walk_index("Density Method", "Density")
check("Density Method 'Density' value != walk index (else test is vacuous)",
      dm_val != dm_idx, f"value={dm_val} index={dm_idx}")


# ── B7 core: set a menu BY NAME and assert the modifier stores the authoritative value ──
print("== set Instance Type='Collection' by name lands the stored VALUE, not the index ==")
clean()
make_plane("Field", 1.0)
make_sprinkle_collection()
res = run("add_asset_modifier", asset="Scatter on Surface", host="Field",
          inputs={"Instance Type": "Collection", "Density Method": "Density"})
mod = bpy.data.objects["Field"].modifiers[0]
it_ident = ident_of("Instance Type")
dm_ident = ident_of("Density Method")
check("Instance Type stored value == 'Collection' authoritative value",
      mod[it_ident] == authoritative_value(mod, "Instance Type", "Collection"),
      f"stored={mod[it_ident]} want={authoritative_value(mod, 'Instance Type', 'Collection')}")
check("Instance Type did NOT store the (buggy) walk index",
      mod[it_ident] != walk_index("Instance Type", "Collection"),
      f"stored={mod[it_ident]} buggy_index={walk_index('Instance Type', 'Collection')}")
check("Density Method stored value == 'Density' authoritative value",
      mod[dm_ident] == authoritative_value(mod, "Density Method", "Density"),
      f"stored={mod[dm_ident]} want={authoritative_value(mod, 'Density Method', 'Density')}")

# readback (inputs_set / inputs_available) reports the EFFECTIVE option name, not laundered intent
iset = res.get("inputs_set") or {}
check("inputs_set echoes effective 'Collection' for Instance Type",
      any(k.lower() == "instance type" and str(v).lower() == "collection" for k, v in iset.items()),
      str(iset))
avail = " || ".join(res.get("inputs_available") or [])
check("inputs_available shows Instance Type = Collection",
      "instance type" in avail.lower() and "= Collection" in avail, avail[:300])


# ── collection= gate flip lands the authoritative Collection value (the live donut path) ──
print("== collection= flips Instance Type to the authoritative Collection value ==")
clean()
make_plane("Field", 1.0)
make_sprinkle_collection()
res = run("add_asset_modifier", asset="Scatter on Surface", host="Field",
          collection="Sprinkles", inputs={"Density": 400})
mod = bpy.data.objects["Field"].modifiers[0]
check("collection= stored the authoritative 'Collection' value on Instance Type",
      mod[ident_of("Instance Type")] == authoritative_value(mod, "Instance Type", "Collection"),
      f"stored={mod[ident_of('Instance Type')]}")
iset = res.get("inputs_set") or {}
check("collection= reports effective 'Collection' (read back, not hardcoded)",
      any(str(v).lower() == "collection" for v in iset.values()), str(iset))


# ── op=modify path resolves menus by value too, and surfaces a bad option name ──
print("== modify_modifier sets menus by value; rejects unknown option names ==")
clean()
make_plane("Field", 1.0)
run("add_asset_modifier", asset="Scatter on Surface", host="Field")
mod = bpy.data.objects["Field"].modifiers[0]
res = run("modify_modifier", target="Field", modifier_name=mod.name,
          inputs={"Instance Type": "Collection"})
check("modify_modifier stored authoritative Collection value",
      mod[ident_of("Instance Type")] == authoritative_value(mod, "Instance Type", "Collection"),
      f"stored={mod[ident_of('Instance Type')]}")
res = run("modify_modifier", target="Field", modifier_name=mod.name,
          inputs={"Instance Type": "Sphere"})   # not a real option
skipped = " ".join(str(s) for s in (res.get("skipped") or []))
check("an unknown menu option is reported, not silently accepted",
      "sphere" in skipped.lower(), str(res.get("skipped")))


print()
if failures:
    print(f"e2e_b7_menu_value :: FAILED — {len(failures)}: {failures}")
    sys.exit(1)
print("e2e_b7_menu_value :: PASSED — 0 failures")
