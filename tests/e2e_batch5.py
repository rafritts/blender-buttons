"""E2E for batch-5 gap fixes (U4, U7, U8, U10) — production-asset access. Headless.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_batch5.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


# ───────────────────────── U4: get_scene_tree scaling ─────────────────────────
print("== U4: get_scene_tree filter / type / summarize ==")
clean()
widgets = bpy.data.collections.new("widgets")
bpy.context.scene.collection.children.link(widgets)
for i in range(25):
    me = bpy.data.meshes.new(f"wdata_{i}")
    o = bpy.data.objects.new(f"widget_{i}", me)
    widgets.objects.link(o)
run("add_box", name="hero", width=1.0, depth=1.0, height=1.0)

full = run("get_scene_tree")
check("big collection summarized by default",
      "25 objects" in full["tree"] and "widget_0" not in full["tree"], full["tree"])
check("summarized count reported", full.get("summarized") == 25, str(full.get("summarized")))

expanded = run("get_scene_tree", summarize=0)
check("summarize=0 expands the collection", "widget_0" in expanded["tree"], "(truncated)")

filt = run("get_scene_tree", filter="widget_7")
check("filter lists matches, not a summary",
      "widget_7" in filt["tree"] and "25 objects" not in filt["tree"], filt["tree"])
check("filter drops non-matches", "hero" not in filt["tree"], filt["tree"])

typed = run("get_scene_tree", type="MESH")
check("type filter keeps meshes", "hero" in typed["tree"], typed["tree"])

# ───────────────────────── U7: particle systems ─────────────────────────
print("== U7: particle visibility + describe line ==")
clean()
run("add_box", name="furry", width=1.0, depth=1.0, height=1.0)
furry = bpy.data.objects["furry"]
furry.modifiers.new("hair", 'PARTICLE_SYSTEM')
psys = furry.particle_systems[0]
psys.settings.type = 'HAIR'
psys.settings.count = 500
pv = run("set_particle_visibility", name="furry", show=False)
check("set_particle_visibility success", pv.get("success") is True, str(pv))
check("particle modifier hidden in viewport",
      furry.modifiers["hair"].show_viewport is False)
d = run("describe", name="furry")
check("describe reports the particle system",
      "particle system" in d["description"] and "500" in d["description"], d["description"])
pv_none = run("set_particle_visibility", name="hero_missing", show=True)
check("missing object errors", "error" in pv_none, str(pv_none))

# ───────────────────────── U8: shape keys ─────────────────────────
print("== U8: shape key list / get / set ==")
clean()
run("add_box", name="morph", width=1.0, depth=1.0, height=1.0)
morph = bpy.data.objects["morph"]
morph.shape_key_add(name="Basis")
morph.shape_key_add(name="bulge")
lk = run("list_shape_keys", name="morph")
check("list_shape_keys counts keys", lk.get("count") == 2, str(lk))
check("shape key names listed",
      {k["name"] for k in lk["shape_keys"]} == {"Basis", "bulge"}, str(lk))
sk = run("set_shape_key", name="morph", key="bulge", value=0.7)
check("set_shape_key success", sk.get("success") is True, str(sk))
check("shape key value applied",
      abs(morph.data.shape_keys.key_blocks["bulge"].value - 0.7) < 1e-4)
sk_bad = run("set_shape_key", name="morph", key="nope", value=1.0)
check("unknown shape key errors", "error" in sk_bad, str(sk_bad))
lk_none = run("list_shape_keys", name="morph_missing")
check("missing object errors", "error" in lk_none, str(lk_none))

# ───────────────────────── U10: linked library data ─────────────────────────
print("== U10: linked data surfaced + mutation blocked ==")
clean()
libpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_linked_lib.blend")
bpy.ops.mesh.primitive_cube_add()
cube = bpy.context.active_object
cube.name = "LinkedCube"
bpy.data.libraries.write(libpath, {cube}, fake_user=True)
bpy.data.objects.remove(cube, do_unlink=True)
with bpy.data.libraries.load(libpath, link=True) as (df, dt):
    dt.objects = ["LinkedCube"]
for o in dt.objects:
    if o:
        bpy.context.scene.collection.objects.link(o)
linked = bpy.data.objects.get("LinkedCube")
check("linked object present", linked is not None and linked.library is not None, str(linked))

dl = run("describe", name="LinkedCube")
check("describe surfaces linked status", "lib:" in dl["description"], dl["description"])

tree = run("get_scene_tree")
check("scene tree tags linked data", "[lib:" in tree["tree"], tree["tree"])

mat = run("set_material", target="LinkedCube", base_color=[1, 0, 0])
check("set_material on linked data blocked loudly",
      "error" in mat and "linked library data" in mat["error"], str(mat))

edit = run("select_all", target="LinkedCube", action="SELECT")
check("geometry-edit on linked data blocked loudly",
      "error" in edit and "linked library data" in edit["error"], str(edit))

# A normal local object is NOT blocked (no false positive).
run("add_box", name="local_box", width=1.0, depth=1.0, height=1.0)
ok_mat = run("set_material", target="local_box", base_color=[0, 1, 0])
check("local object still accepts material", ok_mat.get("success") is True, str(ok_mat))

if os.path.exists(libpath):
    os.remove(libpath)

print()
if failures:
    print(f"BATCH5 E2E: {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("BATCH5 E2E: ALL TESTS PASSED")
