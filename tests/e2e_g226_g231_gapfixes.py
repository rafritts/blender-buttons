"""E2E for G226–G231 (the 2026-08 gap batch). Headless, working-tree extension.

  G226 — collection scatter with Pick Instance off gets a teaching advisory
  G227 — validate op=expect check=self_intersection quiets intended crossings
  G228 — look op=guide / serve_guide is the resource-less teaching channel
  G229 — add type=text at ~2 mm cap height does not emit zero-area faces
  G230 — material bind_image wires a packed image to Principled
  G231 — script abort ignores pre-existing intent-free leftovers

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_g226_g231_gapfixes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy        # noqa: E402
import bmesh      # noqa: E402

from extension import server as bb_server   # noqa: E402
from extension import state                 # noqa: E402
from extension import validation            # noqa: E402
from extension import finishes              # noqa: E402
from extension import lint                  # noqa: E402
from server.guidance import serve_guide     # noqa: E402

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
        if c != bpy.context.scene.collection:
            try:
                bpy.data.collections.remove(c)
            except Exception:
                pass
    for img in list(bpy.data.images):
        if img.name not in ("Render Result", "Viewer Node"):
            bpy.data.images.remove(img)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    validation.clear_intents()
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


def make_multi_sprinkles(n=3):
    coll = bpy.data.collections.new("Sprinkles")
    bpy.context.scene.collection.children.link(coll)
    for i in range(n):
        me = bpy.data.meshes.new(f"Bit{i}")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.01)
        bm.to_mesh(me)
        bm.free()
        bit = bpy.data.objects.new(f"Bit{i}", me)
        coll.objects.link(bit)
    return coll


def make_degenerate(name="Leftover"):
    me = bpy.data.meshes.new(name)
    # a zero-area triangle (collinear verts)
    me.from_pydata([(0, 0, 0.1), (0.01, 0, 0.1), (0.005, 0, 0.1)], [], [(0, 1, 2)])
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


# ───────────────────────── G228: guide without resources ─────────────────────────
print("== G228: serve_guide (resource-less teaching channel) ==")
manual = serve_guide("")
check("empty topic returns the field manual", "look → descend → claim → modify" in manual
      or "THE ONE RULE" in manual or "derive" in manual.lower(),
      f"len={len(manual)}")
check("topic=llms is the same manual", serve_guide("llms") == manual)
idx = serve_guide("techniques")
check("topic=techniques is the index", "form-blockout" in idx and "shell" in idx, idx[:200])
shell = serve_guide("shell")
check("topic=shell is the technique", len(shell) > 80 and "shell" in shell.lower(),
      shell[:160])
unk = serve_guide("not-a-technique")
check("unknown topic is a teaching error, not a throw",
      "unknown guide topic" in unk and "form-blockout" in unk, unk)


# ───────────────────────── G226: Pick Instance advisory ─────────────────────────
print("== G226: Pick Instance advisory on multi-prototype collection ==")
ng, err = finishes._find_asset_node_group("Scatter on Surface")
if err:
    print(f"  SKIP G226 — Scatter on Surface unavailable: {err}")
else:
    clean()
    make_plane("Field", 1.0)
    make_multi_sprinkles(3)
    res = run("add_asset_modifier", asset="Scatter on Surface", host="Field",
              collection="Sprinkles", inputs={"Density": 200})
    notes = " ".join(res.get("notes") or [])
    check("add_asset succeeded", res.get("success"), str(res)[:200])
    check("advisory fires when Pick Instance is off",
          "Pick Instance" in notes and "stack" in notes.lower(), notes)
    # Flip the socket and re-add — advisory must go quiet.
    clean()
    make_plane("Field", 1.0)
    make_multi_sprinkles(3)
    res2 = run("add_asset_modifier", asset="Scatter on Surface", host="Field",
               collection="Sprinkles",
               inputs={"Density": 200, "Pick Instance": True})
    notes2 = " ".join(res2.get("notes") or [])
    check("advisory silent when Pick Instance=True",
          "stack" not in notes2.lower(), notes2)


# ───────────────────────── G227: expect self_intersection ─────────────────────────
print("== G227: expect check=self_intersection ==")
clean()
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.5))
a = bpy.context.active_object
a.name = "Knot"
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.4, 0, 0.5))
b = bpy.context.active_object
b.select_set(True)
a.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
a.name = "Knot"
v = validation.run_validate(["Knot"])
has_sx = any(f["check"] == "self_intersection" for f in v["intent_free"])
check("joined overlapping cubes report self_intersection", has_sx, v["line"])
check("undeclared self_intersection fails the floor", not v["passed"], v["line"])
bad = validation.add_intent("Knot", "", "not a reason that matters", check="degenerate")
check("expect check=degenerate is refused", bool(bad.get("error")), bad)
ok = validation.add_intent("Knot", "", "realized scatter seated into the substrate",
                           check="self_intersection")
check("expect check=self_intersection accepted", ok.get("success"), ok)
v2 = validation.run_validate(["Knot"])
check("declared self_intersection is not intent-free",
      not any(f["check"] == "self_intersection" for f in v2["intent_free"]),
      v2["line"])
check("declared self_intersection does not fail the floor", v2["passed"], v2["line"])
check("intended count is visible",
      (v2.get("self_intersection") or {}).get("intended", 0) >= 1,
      v2.get("self_intersection"))
check("line mentions intended", "self_intersection intended" in (v2.get("line") or ""),
      v2.get("line"))


# ───────────────────────── G229: small-scale text is clean ─────────────────────────
print("== G229: add type=text at 2 mm does not emit degenerates ==")
clean()
glyphs = [("Lbl_shft", "shft"), ("Lbl_caps", "caps"), ("Lbl_semi", ";"),
          ("Lbl_comma", ","), ("Lbl_dot", "."), ("Lbl_f2", "F2"), ("Lbl_a", "a")]
for name, body in glyphs:
    res = run("add_text", name=name, body=body, size=0.002, depth=0.0004)
    check(f"{name} add succeeded", res.get("success"), str(res)[:200])
    if not res.get("success"):
        continue
    obj = bpy.data.objects.get(name)
    check(f"{name} has faces", obj is not None and obj.type == 'MESH'
          and obj.data and len(obj.data.polygons) > 0, obj)
    if obj is None:
        continue
    rep = lint.check_mesh({"target": name})["reports"][0]
    check(f"{name} has 0 zero-area faces",
          rep.get("zero_area_faces", 1) == 0,
          f"zero_area={rep.get('zero_area_faces')} {rep}")
    v = validation.run_validate([name])
    deg = [f for f in v["intent_free"] if f["check"] == "degenerate"]
    check(f"{name} floor has no degenerate finding", not deg, v["line"])


# ───────────────────────── G230: bind a packed image ─────────────────────────
print("== G230: bind_image wires a packed image ==")
clean()
check("bind_image registered", "bind_image" in bb_server.TOOLS)
probe = bpy.data.images.new("ProbeTex", 8, 8)
probe.generated_type = 'UV_GRID'
probe.pack()
make_plane("Screen", 0.2)
# box projection — no UV required
res = run("bind_image", target="Screen", image="ProbeTex", bind="both",
          space="box", emission_strength=2.5, material_name="ScreenMat")
check("bind_image succeeded", res.get("success"), str(res)[:240])
check("generated image is in the blend", res.get("packed") is True, res)
# path provenance: write a real PNG and bind it — that path must pack
png = os.path.join("/tmp", "bb_g230_probe.png")
probe.filepath_raw = png
probe.file_format = 'PNG'
try:
    probe.save()
except Exception as e:
    check("probe.save for path test", False, str(e))
else:
    res_path = run("bind_image", target="Screen", image=png, bind="base",
                   space="box", material_name="ScreenMatPath")
    check("bind from filesystem path succeeded", res_path.get("success"),
          str(res_path)[:200])
    check("file-backed image packed into the blend",
          res_path.get("packed") is True, res_path)
    try:
        os.remove(png)
    except OSError:
        pass
check("bind=both recorded", res.get("bind") == "both", res)
mat = bpy.data.materials.get("ScreenMat")
check("material exists", mat is not None)
if mat and mat.node_tree:
    nt = mat.node_tree
    tex = next((n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image == probe), None)
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    check("Image Texture node present", tex is not None)
    check("projection is BOX", tex is not None and tex.projection == 'BOX',
          getattr(tex, "projection", None))
    if tex and bsdf:
        base_from = [l.from_node for l in bsdf.inputs['Base Color'].links]
        check("Base Color driven by the image", tex in base_from, base_from)
        em_sock = bsdf.inputs.get('Emission Color') or bsdf.inputs.get('Emission')
        em_from = [l.from_node for l in em_sock.links] if em_sock else []
        check("Emission driven by the image", tex in em_from, em_from)
# space=uv without UVs must teach, not silently box
res_uv = run("bind_image", target="Screen", image="ProbeTex", space="uv")
check("space=uv with no UV map is a teaching error",
      not res_uv.get("success") and "uv op=unwrap" in (res_uv.get("error") or ""),
      res_uv.get("error"))


# ───────────────────────── G231: abort only on introduced defects ─────────────────────────
print("== G231: script abort ignores pre-existing leftovers ==")
clean()
make_degenerate("Lbl_bad")
v0 = validation.run_validate(["Lbl_bad"])
check("leftover is a real degenerate",
      any(f["check"] == "degenerate" for f in v0["intent_free"]), v0["line"])
# Unrelated add must succeed (not abort+restore) despite the leftover.
r = run("script_batch", label="g231-leftover", on_error="abort", steps=[
    {"verb": "add", "params": {
        "type": "box", "name": "ok_box", "width": 0.05, "depth": 0.05, "height": 0.05,
        "on": {"on_floor": True},
    }},
])
check("batch with leftover degenerate did NOT abort",
      r.get("result") in ("ok", "completed_with_warnings"),
      f"result={r.get('result')} err={r.get('error')}")
check("ok_box survived (no transactional restore)",
      bpy.data.objects.get("ok_box") is not None,
      [o.name for o in bpy.context.scene.objects])
check("leftover still present", bpy.data.objects.get("Lbl_bad") is not None)
fv = r.get("final_validate") or {}
check("final validate still surfaces the leftover",
      any(f.get("check") == "degenerate" for f in (fv.get("intent_free") or []))
      or "degenerate" in (fv.get("line") or ""),
      fv.get("line"))

# A step that INTRODUCES an intent-free defect still aborts.
clean()
# two overlapping coplanar slabs → z-fight on the second add
r2 = run("script_batch", label="g231-introduced", on_error="abort", steps=[
    {"verb": "add", "params": {
        "type": "box", "name": "slab_a", "width": 0.2, "depth": 0.2, "height": 0.02,
        "on": {"on_floor": True},
    }},
    {"verb": "add", "params": {
        "type": "box", "name": "slab_b", "width": 0.2, "depth": 0.2, "height": 0.02,
        "on": {"on_floor": True},
    }},
])
check("introduced z-fight still aborts",
      r2.get("result") == "aborted",
      f"result={r2.get('result')} err={r2.get('error')}")
check("introduced abort restored both slabs",
      bpy.data.objects.get("slab_a") is None and bpy.data.objects.get("slab_b") is None,
      [o.name for o in bpy.context.scene.objects])


print()
if failures:
    print(f"e2e_g226_g231_gapfixes :: FAILED — {len(failures)}: {failures}")
    sys.exit(1)
print("e2e_g226_g231_gapfixes :: PASSED — 0 failures")
