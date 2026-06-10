"""E2E test for the blender-buttons extension — runs inside headless Blender.

Exercises the extension modules directly from the repo (not the installed
addon copy), so it verifies working-tree code before install.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_headless.py
       (flatpak resolves relative paths against its own sandbox — pass an absolute path)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension.common import world_bbox, world_center  # noqa: E402

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}  {detail}")


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


# Clean default scene (Cube etc.) for predictable relations
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

print("== dispatch registration ==")
for t in ("spline_tube", "bend", "scale_group"):
    check(f"{t} in dispatch", t in bb_server.TOOLS)

print("== placement: at ==")
r = run("add_box", name="t_box", width=0.2, depth=0.2, height=0.2, on={"at": [1, 2, 3]})
check("add_box at success", r.get("success"), r.get("error"))
c = world_center(bpy.data.objects["t_box"])
check("t_box center == (1,2,3)", all(abs(c[i] - (1, 2, 3)[i]) < 1e-5 for i in range(3)), c)

print("== placement: unknown key rejected ==")
r = run("add_box", name="t_bad", width=0.1, depth=0.1, height=0.1, on={"att": [0, 0, 0]})
check("unknown key errors", "error" in r and "Valid keys" in r["error"], r)
check("no object created on error", bpy.data.objects.get("t_bad") is None)

print("== add_primitives: bulk rot_y honored ==")
r = run("add_primitives", specs=[
    {"type": "cylinder", "name": "t_cyl", "radius": 0.05, "height": 0.5, "rot_y": 14},
])
check("bulk add success", r.get("success"), r.get("error"))
rot_y = math.degrees(bpy.data.objects["t_cyl"].rotation_euler.y)
check("t_cyl rot_y == 14", abs(rot_y - 14) < 1e-3, rot_y)

print("== resize: rotated-object handling (T5) ==")
# arbitrary rotation (t_cyl is rot_y=14°): refuse BEFORE mutating
before = world_bbox(bpy.data.objects["t_cyl"])
r = run("resize", targets="t_cyl", height=0.6)
check("arbitrary-rotation resize refused", "error" in r, r)
after = world_bbox(bpy.data.objects["t_cyl"])
check("refused resize left geometry untouched",
      all(abs(before[i] - after[i]) < 1e-6 for i in range(6)), (before, after))
# unrotated resize unchanged from prior behavior, no warnings
r = run("resize", targets="t_box", height=0.3)
check("unrotated resize success", r.get("success"), r.get("error"))
check("no warning on unrotated", not r.get("warnings"), r.get("warnings"))

print("== spline_tube ==")
r = run("spline_tube", name="t_tube",
        points=[{"near": "t_box", "offset": [0.2, 0, 0]}, [1.5, 2.2, 2.5], [1.7, 2.0, 2.0]],
        radius=[0.03, 0.02, 0.005], resolution=8)
check("spline_tube success", r.get("success"), r.get("error"))
tube = bpy.data.objects.get("t_tube")
check("tube exists as mesh", tube is not None and tube.type == 'MESH',
      getattr(tube, "type", None))
check("tube has verts", tube is not None and len(tube.data.vertices) > 50,
      len(tube.data.vertices) if tube else 0)
check("through-points stored", tube is not None and tube.get("bb_spline_points") is not None)
check("length reported", r.get("length", 0) > 0.5, r.get("length"))
# first anchored point = t_box center + offset
p0 = r["points"][0]
expected0 = [1.2, 2.0, 3.0]
check("anchored point resolved", all(abs(p0[i] - expected0[i]) < 1e-3 for i in range(3)), p0)

print("== spline_tube validation ==")
r = run("spline_tube", name="t_tube2", points=[[0, 0, 0]])
check("1 point rejected", "error" in r, r)
r = run("spline_tube", name="t_tube2", points=[[0, 0, 0], {"near": "missing"}])
check("missing anchor rejected", "error" in r and "not found" in r["error"], r)
r = run("spline_tube", name="t_tube2", points=[[0, 0, 0], [1, 1, 1]], radius=[0.1])
check("radius count mismatch rejected", "error" in r, r)

print("== materials introspection ==")
r = run("set_material", target="t_tube", base_color=[0.9, 0.2, 0.2], roughness=0.4)
check("set_material success", r.get("success"), r.get("error"))
r = run("describe", name="t_tube")
check("describe success", r.get("success"), r.get("error"))
mats = r.get("materials", [])
check("describe reports material", mats and mats[0].get("name") == "t_tube_mat", mats)
check("describe reports color", mats and mats[0].get("base_color", [0])[0] == 0.9, mats)
check("describe mentions spline", "spline tube through" in r.get("description", ""),
      r.get("description"))
r = run("get_object_info", name="t_tube")
check("get_object_info materials", r["info"].get("materials") is not None,
      r["info"].keys())

print("== bend ==")
before = world_bbox(bpy.data.objects["t_tube"])
r = run("bend", targets="t_tube", angle=90, axis="X")
check("bend success", r.get("success"), r.get("error"))
after = world_bbox(bpy.data.objects["t_tube"])
changed = any(abs(before[i] - after[i]) > 1e-4 for i in range(6))
check("bend changed geometry", changed, (before, after))
check("bend applied (no modifier left)", len(bpy.data.objects["t_tube"].modifiers) == 0)
r = run("bend", targets="t_box", angle=45)  # box long axis warning not expected (cube)
check("bend works on box", r.get("success"), r.get("error"))

print("== scale_group ==")
run("add_box", name="g_a", width=0.2, depth=0.2, height=0.2, on={"at": [-0.5, 0, 1.0]})
run("add_box", name="g_b", width=0.2, depth=0.2, height=0.2, on={"at": [0.5, 0, 1.0]})
r = run("scale_group", targets=["g_a", "g_b"], factor=2.0, pivot="center")
check("scale_group success", r.get("success"), r.get("error"))
ca = world_center(bpy.data.objects["g_a"])
cb = world_center(bpy.data.objects["g_b"])
check("centers spread ×2", abs(ca[0] - (-1.0)) < 1e-4 and abs(cb[0] - 1.0) < 1e-4, (ca, cb))
da = world_bbox(bpy.data.objects["g_a"])
check("parts scaled ×2", abs((da[3] - da[0]) - 0.4) < 1e-4, da)
check("z preserved at pivot", abs(ca[2] - 1.0) < 1e-4, ca)
r = run("scale_group", targets=["g_a", "g_b"], factor=0.5, pivot="bottom_center")
check("bottom_center pivot works", r.get("success"), r.get("error"))

print("== mirror_across replace ==")
run("add_box", name="arm_R", width=0.1, depth=0.1, height=0.4, on={"at": [0.3, 0, 1]})
r = run("mirror_across", targets="arm_R", plane="X", replace=["_R", "_L"])
check("mirror replace success", r.get("success"), r.get("error"))
check("arm_L created", bpy.data.objects.get("arm_L") is not None,
      r.get("mirrored_to"))
cl = world_center(bpy.data.objects["arm_L"])
check("arm_L mirrored to -X", abs(cl[0] + 0.3) < 1e-4, cl)
r = run("mirror_across", targets="t_box", plane="X", replace=["_R", "_L"])
check("no-token falls back to suffix", "t_box_mirror" in r.get("mirrored_to", []), r)

print("== T1 set_toon_material ==")
run("add_sphere", name="toon_ball", radius=0.5, on={"at": [5, 0, 0]})
r = run("set_toon_material", target="toon_ball", base_color=[0.2, 0.5, 0.9], bands=3)
check("toon success", r.get("success"), r.get("error"))
tmat = bpy.data.objects["toon_ball"].data.materials[0]
check("toon material assigned", tmat is not None and tmat.get("bb_toon") is not None)
import json as _json
stored = _json.loads(tmat["bb_toon"]) if tmat and tmat.get("bb_toon") else {}
check("bb_toon round-trips bands", stored.get("bands") == 3, stored.get("bands"))
check("bb_toon round-trips base_color", stored.get("base_color")[:3] == [0.2, 0.5, 0.9], stored.get("base_color"))
check("bb_toon graph_version", stored.get("graph_version") == 1)
nodes = tmat.node_tree.nodes
has_s2rgb = any(n.bl_idname == "ShaderNodeShaderToRGB" for n in nodes)
check("graph has ShaderToRGB", has_s2rgb)
ramp = next((n for n in nodes if n.bl_idname == "ShaderNodeValToRGB"), None)
check("graph has ColorRamp", ramp is not None)
check("ColorRamp is CONSTANT", ramp is not None and ramp.color_ramp.interpolation == "CONSTANT",
      ramp.color_ramp.interpolation if ramp else None)
check("ColorRamp has 3 stops", ramp is not None and len(ramp.color_ramp.elements) == 3,
      len(ramp.color_ramp.elements) if ramp else 0)
# idempotent reuse: second call, different shadow_color, same datablock
n_mats_before = len(bpy.data.materials)
r = run("set_toon_material", target="toon_ball", base_color=[0.2, 0.5, 0.9],
        bands=3, shadow_color=[0.1, 0.1, 0.3])
check("toon reuse success", r.get("success"), r.get("error"))
check("no .001 duplicate material", len(bpy.data.materials) == n_mats_before,
      (n_mats_before, len(bpy.data.materials)))
check("same material datablock", bpy.data.objects["toon_ball"].data.materials[0] == tmat)
r = run("describe", name="toon_ball")
check("describe mentions toon", "toon(" in r.get("description", ""), r.get("description"))

print("== T2 add_outline / remove_outline ==")
run("add_box", name="out_box", width=0.5, depth=0.5, height=0.5, on={"at": [7, 0, 0]})
r = run("add_outline", target="out_box", thickness=0.01, color=[0, 0, 0])
check("add_outline success", r.get("success"), r.get("error"))
ob = bpy.data.objects["out_box"]
omod = ob.modifiers.get("bb_outline")
check("bb_outline modifier exists", omod is not None)
check("outline normals flipped", omod is not None and omod.use_flip_normals)
check("outline material_offset=1", omod is not None and omod.material_offset == 1)
check("two material slots", len(ob.data.materials) == 2, len(ob.data.materials))
slot1 = ob.data.materials[1] if len(ob.data.materials) > 1 else None
check("slot1 backface-culled", slot1 is not None and slot1.use_backface_culling)
check("slot1 is emission", slot1 is not None and any(
    n.bl_idname == "ShaderNodeEmission" for n in slot1.node_tree.nodes))
# remove restores 1 slot, 0 outline modifiers
r = run("remove_outline", target="out_box")
check("remove_outline success", r.get("success"), r.get("error"))
check("one slot after remove", len(ob.data.materials) == 1, len(ob.data.materials))
check("no bb_outline modifier after remove", ob.modifiers.get("bb_outline") is None)
# composes with toon: slot 0 toon material untouched
r = run("add_outline", target="toon_ball", thickness=0.008)
check("outline on toon success", r.get("success"), r.get("error"))
tb = bpy.data.objects["toon_ball"]
check("toon still in slot 0", tb.data.materials[0].get("bb_toon") is not None,
      tb.data.materials[0].name if tb.data.materials[0] else None)
check("outline appended after toon", len(tb.data.materials) == 2, len(tb.data.materials))

print("== T3 undo / redo / verification ==")
for i in range(5):
    run("add_box", name=f"u_box{i}", width=0.1, depth=0.1, height=0.1, on={"at": [10 + i, 0, 0]})
present = lambda n: bpy.data.objects.get(n) is not None
check("5 undo boxes present", all(present(f"u_box{i}") for i in range(5)))
r = run("undo_steps", steps=2)
check("undo(2) success", r.get("success"), r.get("error"))
check("undo(2) reverted 2", r.get("steps") == 2, r.get("steps"))
check("u_box4 removed by undo", not present("u_box4"))
check("u_box3 removed by undo", not present("u_box3"))
check("u_box2 still present", present("u_box2"))
check("u_box0 still present", present("u_box0"))
check("undo verified against snapshot", r.get("verified") is True, r.get("warning"))
check("redo_available == 2 after undo", r.get("redo_available") == 2, r.get("redo_available"))
# redo brings one back
r = run("redo_steps", steps=1)
check("redo(1) success", r.get("success"), r.get("error"))
check("u_box3 restored by redo", present("u_box3"))
check("u_box4 still gone after redo(1)", not present("u_box4"))
check("redo verified", r.get("verified") is True, r.get("warning"))
# undo past available depth: error, scene untouched
n_before = len(bpy.data.objects)
r = run("undo_steps", steps=100000)
check("undo past depth errors", "error" in r, r)
check("scene untouched on over-undo", len(bpy.data.objects) == n_before, (n_before, len(bpy.data.objects)))
# a new mutating op clears the redo branch
run("add_box", name="u_fork", width=0.1, depth=0.1, height=0.1, on={"at": [20, 0, 0]})
r = run("get_history")
check("new op clears redo branch", r.get("redo_available") == 0, r.get("redo_available"))
# edit-mode op undo (push happens after mode restore -> must be undoable from object mode)
run("add_box", name="u_edit", width=0.4, depth=0.4, height=0.4, on={"at": [22, 0, 0]})
v0 = len(bpy.data.objects["u_edit"].data.vertices)
r = run("loop_cut", target="u_edit", axis="Z", cuts=1)
check("loop_cut success", r.get("success"), r.get("error"))
v1 = len(bpy.data.objects["u_edit"].data.vertices)
check("loop_cut added verts", v1 > v0, (v0, v1))
r = run("undo_steps", steps=1)
check("edit-mode undo success", r.get("success"), r.get("error"))
check("edit-mode undo restored verts", len(bpy.data.objects["u_edit"].data.vertices) == v0,
      (v0, len(bpy.data.objects["u_edit"].data.vertices)))

print("== T4 placement resolves before rotation ==")
run("add_box", name="floor_box", width=1.0, depth=1.0, height=0.4, on={"at": [30, 0, 0.2]})
fb = world_bbox(bpy.data.objects["floor_box"])
# rot_y=90 cylinder placed ON the floor box must rest flush, not float
r = run("add_cylinder", name="rot_cyl", radius=0.3, height=1.0, rot_y=90,
        on={"on": "floor_box"})
check("rotated on-placement success", r.get("success"), r.get("error"))
cb = world_bbox(bpy.data.objects["rot_cyl"])
check("rot_y=90 cyl rests on floor (zmin == floor zmax)", abs(cb[2] - fb[5]) < 1e-4,
      (cb[2], fb[5]))
# rot_x=90 cylinder in_front_of must be flush (its ymax == floor ymin)
r = run("add_cylinder", name="front_cyl", radius=0.2, height=0.8, rot_x=90,
        on={"in_front_of": "floor_box"})
check("rotated in_front_of success", r.get("success"), r.get("error"))
fc = world_bbox(bpy.data.objects["front_cyl"])
check("rot_x=90 cyl flush in front (ymax == floor ymin)", abs(fc[4] - fb[1]) < 1e-4,
      (fc[4], fb[1]))
# unrotated placement unchanged
run("add_box", name="plain_on", width=0.2, depth=0.2, height=0.2, on={"on": "floor_box"})
pb = world_bbox(bpy.data.objects["plain_on"])
check("unrotated on-placement still flush", abs(pb[2] - fb[5]) < 1e-4, (pb[2], fb[5]))

print("== T5 resize on axis-aligned rotation ==")
run("add_cylinder", name="r90", radius=0.3, height=1.0, rot_y=90, on={"at": [42, 0, 0]})
b0 = world_bbox(bpy.data.objects["r90"])  # world X≈1.0 (height), Y≈Z≈0.6
r = run("resize", targets="r90", width=0.5)  # request WORLD width
check("axis-aligned resize success", r.get("success"), r.get("error"))
check("axis-aligned resize no warnings", not r.get("warnings"), r.get("warnings"))
b1 = world_bbox(bpy.data.objects["r90"])
check("world width set exactly to 0.5", abs((b1[3] - b1[0]) - 0.5) < 1e-4, b1[3] - b1[0])
check("world depth unchanged", abs((b1[4] - b1[1]) - (b0[4] - b0[1])) < 1e-4,
      (b1[4] - b1[1], b0[4] - b0[1]))
check("world height unchanged", abs((b1[5] - b1[2]) - (b0[5] - b0[2])) < 1e-4,
      (b1[5] - b1[2], b0[5] - b0[2]))

print("== T6 set_textured_material (node wiring from local paths) ==")
_texdir = os.path.dirname(os.path.abspath(__file__))
def _make_img(nm, col):
    im = bpy.data.images.new(nm, 4, 4)
    im.pixels = list(col) * 16
    p = os.path.join(_texdir, f"_{nm}.png")
    im.filepath_raw = p
    im.file_format = 'PNG'
    im.save()
    return p
_dif = _make_img("texdif", [0.6, 0.3, 0.1, 1])
_nor = _make_img("texnor", [0.5, 0.5, 1.0, 1])
_rgh = _make_img("texrgh", [0.4, 0.4, 0.4, 1])
run("add_box", name="tex_box", width=0.6, depth=0.6, height=0.6, on={"at": [46, 0, 0]})
r = run("set_textured_material", target="tex_box",
        maps={"diffuse": _dif, "normal": _nor, "roughness": _rgh},
        scale=2.0, asset_id="test_asset", resolution="1k")
check("set_textured_material success", r.get("success"), r.get("error"))
txmat = bpy.data.objects["tex_box"].data.materials[0]
img_nodes = [n for n in txmat.node_tree.nodes if n.bl_idname == 'ShaderNodeTexImage']
check("3 image texture nodes", len(img_nodes) == 3, len(img_nodes))
check("all BOX projection", all(n.projection == 'BOX' for n in img_nodes),
      [n.projection for n in img_nodes])
check("projection_blend 0.2", all(abs(n.projection_blend - 0.2) < 1e-6 for n in img_nodes))
cspaces = sorted(n.image.colorspace_settings.name for n in img_nodes)
check("colorspaces: 1 sRGB + 2 Non-Color",
      cspaces.count('sRGB') == 1 and cspaces.count('Non-Color') == 2, cspaces)
check("has NormalMap node", any(n.bl_idname == 'ShaderNodeNormalMap'
                                for n in txmat.node_tree.nodes))
check("has Mapping node", any(n.bl_idname == 'ShaderNodeMapping'
                              for n in txmat.node_tree.nodes))
txstore = _json.loads(txmat["bb_texture"]) if txmat.get("bb_texture") else {}
check("bb_texture asset_id round-trips", txstore.get("asset_id") == "test_asset", txstore)
check("bb_texture scale round-trips", txstore.get("scale") == 2.0, txstore)
r = run("describe", name="tex_box")
check("describe mentions texture", "texture(" in r.get("description", ""), r.get("description"))

print("== T6b set_textured_material metal map + overrides ==")
_met = _make_img("texmet", [1.0, 1.0, 1.0, 1])
run("add_box", name="tex_box_m", width=0.6, depth=0.6, height=0.6, on={"at": [48, 0, 0]})
r = run("set_textured_material", target="tex_box_m",
        maps={"diffuse": _dif, "roughness": _rgh, "metal": _met},
        asset_id="test_metal", resolution="1k")
check("metal-map wiring success", r.get("success"), r.get("error"))
_mmat = bpy.data.objects["tex_box_m"].data.materials[0]
_mbsdf = next(n for n in _mmat.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
check("Metallic input linked to metal map", _mbsdf.inputs['Metallic'].is_linked)
check("metal map is Non-Color",
      next((n.image.colorspace_settings.name for n in _mmat.node_tree.nodes
            if n.bl_idname == 'ShaderNodeTexImage' and 'texmet' in n.image.filepath), None)
      == 'Non-Color')
run("add_box", name="tex_box_o", width=0.6, depth=0.6, height=0.6, on={"at": [50, 0, 0]})
r = run("set_textured_material", target="tex_box_o",
        maps={"diffuse": _dif, "roughness": _rgh, "metal": _met},
        base_color=[1.0, 0.55, 0.09], metallic=1.0,
        asset_id="test_gold", resolution="1k")
check("override wiring success", r.get("success"), r.get("error"))
_omat = bpy.data.objects["tex_box_o"].data.materials[0]
_obsdf = next(n for n in _omat.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
check("Base Color NOT linked (override)", not _obsdf.inputs['Base Color'].is_linked)
check("Base Color override value",
      abs(_obsdf.inputs['Base Color'].default_value[0] - 1.0) < 1e-6
      and abs(_obsdf.inputs['Base Color'].default_value[1] - 0.55) < 1e-6)
check("Metallic NOT linked (override)", not _obsdf.inputs['Metallic'].is_linked)
check("Metallic forced to 1.0", abs(_obsdf.inputs['Metallic'].default_value - 1.0) < 1e-6)
check("roughness still linked", _obsdf.inputs['Roughness'].is_linked)
_ostore = _json.loads(_omat["bb_texture"])
check("bb_texture records overrides",
      _ostore.get("metallic") == 1.0 and _ostore.get("base_color") == [1.0, 0.55, 0.09],
      _ostore)

print("== T6c set_textured_material tint + roughness override ==")
run("add_box", name="tex_box_t", width=0.6, depth=0.6, height=0.6, on={"at": [52, 0, 0]})
r = run("set_textured_material", target="tex_box_t",
        maps={"diffuse": _dif, "roughness": _rgh},
        tint=[0.5, 0.4, 0.35], roughness=1.0,
        asset_id="test_tint", resolution="1k")
check("tint wiring success", r.get("success"), r.get("error"))
_tmat = bpy.data.objects["tex_box_t"].data.materials[0]
_tbsdf = next(n for n in _tmat.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
_tmix = next((n for n in _tmat.node_tree.nodes if n.bl_idname == 'ShaderNodeMix'), None)
check("Mix(multiply) node present", _tmix is not None and _tmix.blend_type == 'MULTIPLY',
      getattr(_tmix, 'blend_type', None))
check("Base Color fed by mix", _tbsdf.inputs['Base Color'].is_linked
      and _tbsdf.inputs['Base Color'].links[0].from_node == _tmix)
check("diffuse map feeds mix A", _tmix.inputs['A'].is_linked)
check("tint value in mix B", abs(_tmix.inputs['B'].default_value[0] - 0.5) < 1e-6
      and abs(_tmix.inputs['B'].default_value[1] - 0.4) < 1e-6)
check("Roughness NOT linked (override)", not _tbsdf.inputs['Roughness'].is_linked)
check("Roughness forced to 1.0", abs(_tbsdf.inputs['Roughness'].default_value - 1.0) < 1e-6)
_tstore = _json.loads(_tmat["bb_texture"])
check("bb_texture records tint+roughness",
      _tstore.get("tint") == [0.5, 0.4, 0.35] and _tstore.get("roughness") == 1.0, _tstore)

for _p in (_dif, _nor, _rgh, _met):
    try:
        os.remove(_p)
    except OSError:
        pass

print("== T7 set_world_background HDRI ==")
# Poly Haven id resolution is server-side (no bpy); here we resolve via the same
# client, then verify the addon wires an Environment Texture node to the cached
# file — the full id→cache→env-texture path.
try:
    from server import polyhaven as _ph  # stdlib-only, safe to import in Blender
    _hres = _ph.search("studio", "hdris", 5)
    _hpath = _ph.ensure_hdri(_hres[0]["id"], "1k")
    _net = True
except Exception as _e:
    _net = False
    print(f"  skip T7 network (offline: {_e})")
if _net:
    r = run("set_world_background", hdri=_hpath, strength=1.0)
    check("hdri world success", r.get("success"), r.get("error"))
    check("world mode hdri", r.get("mode") == "hdri", r.get("mode"))
    world_nt = bpy.context.scene.world.node_tree
    env = next((n for n in world_nt.nodes if n.type == 'TEX_ENVIRONMENT'), None)
    check("environment texture node present", env is not None)
    check("env points at cached hdri file",
          env is not None and env.image is not None and str(_ph.CACHE_ROOT) in env.image.filepath,
          env.image.filepath if (env and env.image) else None)
# explicit local file path still behaves as before (regression)
_localhdri = os.path.join(_texdir, "_localenv.hdr")
_li = bpy.data.images.new("localenv", 4, 2, float_buffer=True)
_li.pixels = [0.5] * (4 * 2 * 4)
_li.filepath_raw = _localhdri
_li.file_format = 'HDR'
_li.save()
r = run("set_world_background", hdri=_localhdri, strength=0.8)
check("explicit hdri path success", r.get("success"), r.get("error"))
check("explicit hdri path used verbatim", r.get("hdri") == _localhdri, r.get("hdri"))
try:
    os.remove(_localhdri)
except OSError:
    pass

print("== E6 hex color → scene-linear ==")
from extension.shading import hex_to_linear_rgba  # noqa: E402
lin = hex_to_linear_rgba("#5C3317")
check("hex parses to 4 floats", len(lin) == 4, lin)
check("hex sRGB→linear darkens R (0.36→~0.11)", lin[0] < 0.2, lin[0])
check("hex alpha defaults to 1.0", lin[3] == 1.0, lin[3])
check("hex with alpha parses", hex_to_linear_rgba("#5C331780")[3] < 0.6,
      hex_to_linear_rgba("#5C331780")[3])
try:
    hex_to_linear_rgba("#xyz")
    check("bad hex raises", False)
except ValueError:
    check("bad hex raises", True)
run("add_box", name="hex_box", width=0.3, depth=0.3, height=0.3, on={"at": [40, 0, 0.15]})
r = run("set_material", target="hex_box", hex="#5C3317", roughness=0.6)
check("set_material hex success", r.get("success"), r.get("error"))
_mat = bpy.data.objects["hex_box"].data.materials[0]
_bsdf = next(n for n in _mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
check("base color set from hex (linear)", abs(_bsdf.inputs["Base Color"].default_value[0] - lin[0]) < 1e-4,
      list(_bsdf.inputs["Base Color"].default_value))

print("== E10 color management ==")
r = run("set_color_management", view_transform="Standard", exposure=0.5)
check("set_color_management success", r.get("success"), r.get("error"))
check("view_transform applied", bpy.context.scene.view_settings.view_transform == "Standard",
      bpy.context.scene.view_settings.view_transform)
check("exposure applied", abs(bpy.context.scene.view_settings.exposure - 0.5) < 1e-4)
r = run("set_color_management", view_transform="NopeNotReal")
check("bad view_transform errors", "error" in r, r)
# status surfaces render block
st = run("get_blender_status")["status"]
check("status has render block", "render" in st, list(st.keys()))
check("status render has view_transform", st.get("render", {}).get("view_transform") == "Standard",
      st.get("render"))

print("== E11 render quality ==")
r = run("set_render_quality", raytracing=True, ao=True, samples=32)
check("set_render_quality success", r.get("success"), r.get("error"))
_eevee = getattr(bpy.context.scene, "eevee", None)
if _eevee is not None and hasattr(_eevee, "use_raytracing"):
    check("raytracing enabled", _eevee.use_raytracing is True, _eevee.use_raytracing)
    check("status reports raytracing", st_rt := run("get_blender_status")["status"].get("render", {}).get("raytracing") is not None, None)
else:
    print("  skip raytracing assert (no use_raytracing on this build)")

print("== E7 auto-frame bounds ==")
from extension.viewport import _scene_view_bounds  # noqa: E402
run("add_box", name="af_a", width=1.0, depth=1.0, height=1.0, on={"at": [60, 0, 0.5]})
run("add_box", name="af_b", width=1.0, depth=1.0, height=1.0, on={"at": [62, 0, 0.5]})
bpy.ops.object.select_all(action='DESELECT')
bpy.data.objects["af_a"].select_set(True)
bpy.data.objects["af_b"].select_set(True)
_bounds = _scene_view_bounds()
check("scene bounds computed", _bounds is not None)
if _bounds:
    _center, _diag = _bounds
    check("auto-frame center between the two boxes", abs(_center[0] - 61.0) < 0.6, _center)
    check("auto-frame diagonal positive", _diag > 1.0, _diag)

print("== E4 boolean ==")
run("add_box", name="bool_target", width=1.0, depth=1.0, height=1.0, on={"at": [70, 0, 0.5]})
run("add_box", name="bool_cutter", width=0.4, depth=0.4, height=2.0, on={"at": [70, 0, 1.0]})
_v_before = len(bpy.data.objects["bool_target"].data.vertices)
r = run("boolean", target="bool_target", cutter="bool_cutter", op="DIFFERENCE", apply=True)
check("boolean success", r.get("success"), r.get("error"))
check("boolean applied (baked)", r.get("applied") is True, r)
check("boolean changed target geometry",
      len(bpy.data.objects["bool_target"].data.vertices) != _v_before,
      (_v_before, len(bpy.data.objects["bool_target"].data.vertices)))
check("cutter hidden from render", bpy.data.objects["bool_cutter"].hide_render is True)

print("== duplicate_mirrored ==")
run("add_box", name="mir_src", width=0.4, depth=0.2, height=0.6, on={"at": [80, 1.0, 0.3]})
r = run("duplicate_mirrored", target="mir_src", axis="Y", pivot="WORLD", new_name="mir_dst")
check("duplicate_mirrored success", r.get("success"), r.get("error"))
check("mirror object created", bpy.data.objects.get("mir_dst") is not None)
_src_c = world_center(bpy.data.objects["mir_src"])
_dst_c = world_center(bpy.data.objects["mir_dst"])
check("mirror reflected across Y=0", abs(_dst_c[1] + _src_c[1]) < 1e-3, (_src_c[1], _dst_c[1]))
check("mirror keeps clean +scale", all(s > 0 for s in bpy.data.objects["mir_dst"].scale),
      list(bpy.data.objects["mir_dst"].scale))

print("== E8 deform-after-bevel guard ==")
import bmesh as _bm  # noqa: E402
def _make_ringed(name, zs, at_x):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bm = _bm.new()
    for z in zs:
        for (x, y) in [(-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)]:
            bm.verts.new((at_x + x, y, z))
    bm.to_mesh(me)
    bm.free()
    return ob
_make_ringed("sliver_top", [0.0, 0.99, 1.0], 90)   # extreme ring 1% from neighbor
r = run("taper_end", target="sliver_top", axis="Z", end="MAX", scale=0.5)
check("taper_end on sliver succeeds", r.get("success"), r.get("error"))
check("sliver triggers bevel-guard warning", len(r.get("warnings", [])) > 0, r.get("warnings"))
_make_ringed("clean_rings", [0.0, 0.5, 1.0], 95)    # evenly spaced — no sliver
r = run("taper_end", target="clean_rings", axis="Z", end="MAX", scale=0.5)
check("clean mesh: no false warning", len(r.get("warnings", [])) == 0, r.get("warnings"))

print("== add_curve (live datablock) ==")
r = run("add_curve", name="dolly", points=[[6, -6, 3], [0, -8, 3], [-6, -6, 3]],
        type="BEZIER")
check("add_curve success", r.get("success"), r.get("error"))
_c = bpy.data.objects.get("dolly")
check("curve object created", _c is not None and _c.type == 'CURVE', _c)
if _c:
    check("datablock is a real curve", isinstance(_c.data, bpy.types.Curve))
    check("spline is bezier with 3 pts",
          _c.data.splines[0].type == 'BEZIER' and len(_c.data.splines[0].bezier_points) == 3,
          (_c.data.splines[0].type, len(_c.data.splines[0].bezier_points)))
r = run("add_curve", name="hoop", points=[[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        type="NURBS", cyclic=True, bevel_depth=0.05)
check("nurbs cyclic curve success", r.get("success"), r.get("error"))
_h = bpy.data.objects.get("hoop")
check("nurbs spline cyclic + beveled",
      _h is not None and _h.data.splines[0].use_cyclic_u and _h.data.bevel_depth > 0,
      (_h.data.splines[0].use_cyclic_u, _h.data.bevel_depth) if _h else None)
r = run("add_curve", name="bad", points=[[0, 0, 0]])
check("add_curve too-few-points errors", "error" in r, r)

print("== E5 band_around ==")
# Two boxes offset in X form a composite silhouette; a Z-band should hug both.
run("add_box", name="bnd_a", width=1.0, depth=1.0, height=2.0, on={"at": [110, 0, 1.0]})
run("add_box", name="bnd_b", width=1.0, depth=1.0, height=2.0, on={"at": [111.2, 0, 1.0]})
r = run("band_around", name="bnd_strap", targets=["bnd_a", "bnd_b"], axis="Z",
        at=1.0, width=0.2, thickness=0.05)
check("band_around success", r.get("success"), r.get("error"))
if r.get("success"):
    _b = bpy.data.objects["bnd_strap"]
    check("band is a mesh with geometry", len(_b.data.vertices) >= 12, len(_b.data.vertices))
    bx = world_bbox(_b)
    # Band spans both boxes in X (≈ from 109.5 to 111.7 plus thickness) and is
    # ~width tall in Z (0.2 + a hair). It must be wider in X than tall in Z.
    check("band wraps both boxes in X", (bx[3] - bx[0]) > 2.0, (bx[0], bx[3]))
    check("band height ≈ width param", abs((bx[5] - bx[2]) - 0.2) < 0.01, (bx[2], bx[5]))
    check("band stands proud (closed loop has faces)", len(_b.data.polygons) >= 12,
          len(_b.data.polygons))
r = run("band_around", name="bnd_bad", targets=["bnd_a"], axis="Q")
check("band bad axis errors", "error" in r, r)

print("== render_to_file ==")
run("add_box", name="rnd_box", width=1.0, depth=1.0, height=1.0, on={"at": [100, 0, 0.5]})
run("add_camera", name="rnd_cam", x=103, y=-3, z=2, target="rnd_box")
_rpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_render_test")
r = run("render_to_file", filepath=_rpath, resolution_x=64, resolution_y=48,
        engine="CYCLES", samples=1, format="PNG")
check("render_to_file success", r.get("success"), r.get("error"))
if r.get("success"):
    check("render wrote a .png", r["filepath"].endswith(".png"), r["filepath"])
    check("render file exists + non-empty",
          os.path.isfile(r["filepath"]) and os.path.getsize(r["filepath"]) > 0, r)
    check("render resolution honored", r["resolution"] == [64, 48], r["resolution"])
    try:
        os.remove(r["filepath"])
    except OSError:
        pass
r = run("render_to_file", filepath="/tmp/should_fail", format="BOGUS")
check("bad format errors", "error" in r, r)

print("== Tier C: armature + auto_weight + pose ==")
# Bone-heat weighting is well-conditioned near the world origin, so the limb
# lives at origin here (other test objects don't interfere — weighting is
# selection-scoped). auto_weight warns if weighting ever comes back empty.
BX = 0.0
run("add_box", name="limb", width=0.3, depth=0.3, height=2.0, on={"at": [BX, 0, 1.0]})
run("loop_cut", target="limb", axis="Z", cuts=8)   # segments so the joint can bend
r = run("create_armature", name="limb_rig", bones=[
    {"name": "lower", "head": [BX, 0, 0.0], "tail": [BX, 0, 1.0]},
    {"name": "upper", "head": [BX, 0, 1.0], "tail": [BX, 0, 2.0],
     "parent": "lower", "connected": True},
])
check("create_armature success", r.get("success"), r.get("error"))
check("armature has 2 bones", r.get("bone_count") == 2, r.get("bones"))
_arm = bpy.data.objects.get("limb_rig")
check("armature object is ARMATURE", _arm is not None and _arm.type == 'ARMATURE')
check("child bone parented", _arm.data.bones["upper"].parent is not None
      and _arm.data.bones["upper"].parent.name == "lower")

r = run("create_armature", name="bad_rig", bones=[
    {"name": "x", "head": [0, 0, 0], "tail": [0, 0, 0]}])  # zero-length
check("zero-length bone errors", "error" in r, r)

r = run("auto_weight", mesh="limb", armature="limb_rig")
check("auto_weight success", r.get("success"), r.get("error"))
check("auto_weight made vertex groups", r.get("vertex_groups") >= 2, r.get("vertex_groups"))
check("auto_weight actually weighted vertices", r.get("weighted_vertices", 0) > 0,
      r.get("weighted_vertices"))
check("no empty-weight warning at origin", len(r.get("warnings", [])) == 0, r.get("warnings"))
_limb = bpy.data.objects["limb"]
check("armature modifier added", any(m.type == 'ARMATURE' for m in _limb.modifiers),
      [m.type for m in _limb.modifiers])


def _top_vertex_world():
    """World position of the highest rest-vertex, read from the EVALUATED mesh
    (so armature deformation is included)."""
    rest = _limb.data.vertices
    top_idx = max(range(len(rest)), key=lambda i: rest[i].co.z)
    deps = bpy.context.evaluated_depsgraph_get()
    ev = _limb.evaluated_get(deps)
    em = ev.to_mesh()
    wco = ev.matrix_world @ em.vertices[top_idx].co
    ev.to_mesh_clear()
    return wco.copy()


_before = _top_vertex_world()
# Bend the ROOT bone about local Z (perpendicular to the bone — local Y runs
# along it and would only twist). Bending the root swings the whole chain, so
# the top vertex must move a lot. Swing direction depends on bone-local axes,
# so check horizontal (XY) displacement rather than a specific axis.
r = run("pose_bone", armature="limb_rig", bone="lower", rot=[0, 0, 60])
check("pose_bone success", r.get("success"), r.get("error"))
check("returned to object mode", bpy.context.mode == 'OBJECT', bpy.context.mode)
bpy.context.view_layer.update()
_after = _top_vertex_world()
_dh = ((_after.x - _before.x) ** 2 + (_after.y - _before.y) ** 2) ** 0.5
check("posing the root bone deforms the mesh (top vertex swings)", _dh > 0.5,
      (round(_before.x, 3), round(_before.y, 3), round(_after.x, 3), round(_after.y, 3), round(_dh, 3)))
r = run("pose_bone", armature="limb_rig", bone="nonexistent", rot=[0, 0, 0])
check("pose_bone unknown bone errors", "error" in r, r)

print()
if failures:
    print(f"E2E: {len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("E2E: ALL TESTS PASSED")
sys.exit(0)
