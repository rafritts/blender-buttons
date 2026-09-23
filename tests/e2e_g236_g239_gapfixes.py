"""E2E for G236–G239. Headless, working-tree extension via execute_command.

  G236 — below_floor is declareable; a script may add a centered primitive and
         seat or declare it before the run ends
  G237 — status names the modifier stack, whether dims are evaluated, and repeats
         a live component selection after edit mode has been left
  G238 — material set writes subsurface and coat, and reports a missing socket
  G239 — apply_texture wires diffuse, roughness, and normal with box projection

Usage: flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
         --python /abs/path/to/tests/e2e_g236_g239_gapfixes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server  # noqa: E402
from extension import state, validation  # noqa: E402
from extension.common import world_bbox  # noqa: E402
from extension.shading import _write_aliased  # noqa: E402


def _load_status_formatter():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server", "_core.py")
    src = open(path, encoding="utf-8").read()
    start = src.index("def _status")
    end = src.index("\ndef fmt_provenance")
    ns = {}
    exec(src[start:end], ns, ns)  # noqa: S102 — the shipped formatter
    return ns["_status"]


_status = _load_status_formatter()

failures = []


def check(label, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FAIL '} {label}" + ("" if cond else f"   {detail}"))
    if not cond:
        failures.append(label)


def run(tool, **params):
    return bb_server.execute_command({"tool": tool, "params": params})


def clean():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    state.reset_history_state()
    validation._intents.clear()
    sc = bpy.context.scene
    if sc is not None and "bb_intents" in sc:
        del sc["bb_intents"]


def zmin(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        return None
    bpy.context.view_layer.update()
    return world_bbox(obj)[2]


def sock(bsdf, names):
    for name in names:
        if name in bsdf.inputs:
            return name, bsdf.inputs[name].default_value
    return None, None


# ───────────────────────── G236: declare below_floor ─────────────────────────
print("== G236: expect check=below_floor ==")
clean()
run("add_box", name="Table", width=0.4, depth=0.3, height=0.022)
table = bpy.data.objects["Table"]
table.location.z = -0.011
bpy.context.view_layer.update()
v = validation.run_validate(["Table"])
check("ground slab is below_floor",
      any(f["check"] == "below_floor" and f.get("object") == "Table"
          for f in v["intent_free"]), v["line"])
check("undeclared below_floor fails the floor", not v["passed"], v["line"])
bad = validation.add_intent("Table", "", "not a declarable check", check="degenerate")
check("expect check=degenerate is still refused", bool(bad.get("error")), bad)
ok = validation.add_intent("Table", "", "the tabletop is the ground", check="below_floor")
check("expect check=below_floor accepted", ok.get("success"), ok)
v2 = validation.run_validate(["Table"])
check("declared below_floor is not intent-free",
      not any(f["check"] == "below_floor" for f in v2["intent_free"]), v2["line"])
check("declared below_floor does not fail the floor", v2["passed"], v2["line"])
check("intended count is on the line",
      "below_floor intended" in (v2.get("line") or ""), v2.get("line"))

table.location.z = 0.05
bpy.context.view_layer.update()
v3 = validation.run_validate(["Table"])
check("lifted ground body trips VANISHED",
      any(x.get("object") == "Table" for x in (v3.get("below_floor") or {}).get("vanished") or []),
      v3.get("line"))
check("VANISHED below_floor fails the floor", not v3["passed"], v3["line"])
gone = validation.revoke_intent("Table", "", check="below_floor")
check("forget below_floor with only a= works", gone.get("success"), gone)

# A dip on a mesh the script did not create still aborts that step.
print("== G236: existing mesh pushed through the floor still aborts ==")
clean()
run("add_box", name="Mug", width=0.05, depth=0.05, height=0.08, on={"on_floor": True})
before = zmin("Mug")
r = run("script_exec", label="g236-existing", code=(
    'transform(op="nudge", targets="Mug", down=0.02)\n'
))
check("nudge of an existing mesh through z=0 aborts",
      r.get("result") == "aborted", f"result={r.get('result')} err={r.get('error')}")
check("abort names below_floor", "below" in (r.get("error") or ""), r.get("error"))
check("transaction restored the mug",
      bpy.data.objects.get("Mug") is not None and zmin("Mug") >= -1e-4,
      f"before={before} after={zmin('Mug')}")

# Centered add, then a later line seats it: the add must not abort the script.
print("== G236: add then place is legal ==")
clean()
r = run("script_exec", label="g236-place", code=(
    'add(type="cylinder", name="Bit", radius=0.004, height=0.01)\n'
    'transform(op="nudge", targets="Bit", up=0.02)\n'
))
check("add-then-place succeeds", r.get("success"),
      f"result={r.get('result')} err={r.get('error')}")
check("placed cylinder survived", bpy.data.objects.get("Bit") is not None,
      r.get("created"))
check("placed cylinder is on or above z=0",
      bpy.data.objects.get("Bit") is not None and zmin("Bit") >= -1e-4, zmin("Bit"))
journal = r.get("journal") or []
check("the centered add itself was not a hard fail",
      journal and journal[0].get("flag") != "fail", journal[0] if journal else None)

# Left under the floor with no declaration: the script aborts and restores.
print("== G236: add and leave below aborts at the end ==")
clean()
r = run("script_exec", label="g236-leave", code=(
    'add(type="cylinder", name="LeftBit", radius=0.004, height=0.01)\n'
))
check("unplaced centered add aborts", r.get("result") == "aborted",
      f"result={r.get('result')} err={r.get('error')} undo={r.get('undo')}")
check("unplaced abort restored the add", bpy.data.objects.get("LeftBit") is None,
      [o.name for o in bpy.context.scene.objects])

# Declare the dip in the same script and it may stay under the floor.
print("== G236: add then declare below_floor ==")
clean()
r = run("script_exec", label="g236-declare", code=(
    'add(type="cylinder", name="Scrap", radius=0.004, height=0.01)\n'
    'validate(op="expect", a="Scrap", check="below_floor", reason="parked scrap")\n'
))
check("add-then-declare succeeds", r.get("success"),
      f"result={r.get('result')} err={r.get('error')}")
check("declared scrap survived", bpy.data.objects.get("Scrap") is not None)
v = validation.run_validate(["Scrap"])
check("declared scrap is not an intent-free dip",
      not any(f["check"] == "below_floor" for f in v["intent_free"]), v["line"])


# ───────────────────────── G237: stack, basis, selection ─────────────────────────
print("== G237: status names the stack and the evaluated mesh ==")
clean()
res = run("add_box", name="Block", width=0.2, depth=0.2, height=0.2, on={"on_floor": True})
st = res.get("blender_status") or {}
check("a bare mesh is the cage", st.get("dims_basis") == "cage", st.get("dims_basis"))
check("bare mesh has no modifier list", not st.get("modifiers"), st.get("modifiers"))
run("add_modifier", target="Block", type="SOLIDIFY", thickness=0.05, offset=1)
res = run("get_blender_status", focus="Block")
st = res.get("status") or {}
check("solidify dims are evaluated", st.get("dims_basis") == "evaluated", st.get("dims_basis"))
mods = st.get("modifiers") or []
check("stack lists SOLIDIFY",
      any(m.get("type") == "SOLIDIFY" for m in mods), mods)
obj = bpy.data.objects["Block"]
xs = [(obj.matrix_world @ v.co).x for v in obj.data.vertices]
cage_w = max(xs) - min(xs)
dims = st.get("dimensions") or [0, 0, 0]
check("evaluated dims are larger than the cage",
      dims[0] > cage_w + 0.04, f"dims={dims} cage_w={cage_w}")
block = _status({"blender_status": st})
check("status block says evaluated and names the modifier",
      "evaluated" in block and "SOLIDIFY" in block, block)

print("== G237: component selection survives into the next status ==")
res = run("select_by_axis", target="Block", axis="Z", factor=0.6, comparison="GREATER")
st = res.get("blender_status") or {}
line = st.get("selection_line") or ""
check("select leaves OBJECT mode", st.get("mode") == "OBJECT", st.get("mode"))
check("status repeats sel: after leaving edit mode", line.startswith("sel:"), line)
check("the selection is not the whole mesh", "whole mesh" not in line, line)
res2 = run("get_blender_status", focus="Block")
line2 = (res2.get("status") or {}).get("selection_line") or ""
check("the next call still repeats sel:", line2.startswith("sel:"), line2)
block2 = _status({"blender_status": res2.get("status") or {}})
check("rendered block contains the sel line", "sel:" in block2, block2)


# ───────────────────────── G238: subsurface and coat ─────────────────────────
print("== G238: set writes subsurface and coat ==")
clean()
run("add_box", name="Dough", width=0.05, depth=0.05, height=0.02, on={"on_floor": True})
res = run("set_material", target="Dough", material_name="DoughMat", roughness=0.55,
          subsurface_weight=0.42, subsurface_radius=[1.0, 0.45, 0.2],
          subsurface_scale=0.006, coat_weight=0.35, coat_roughness=0.08)
check("set_material succeeded", res.get("success"), str(res)[:300])
check("nothing was skipped on this build", not res.get("skipped"), res.get("skipped"))
mat = bpy.data.materials.get("DoughMat")
bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if mat else None
check("principled exists", bsdf is not None)
if bsdf is not None:
    name, val = sock(bsdf, ("Subsurface Weight", "Subsurface"))
    check("subsurface weight landed",
          name is not None and abs(float(val) - 0.42) < 1e-4, (name, val))
    name, val = sock(bsdf, ("Subsurface Radius",))
    comps = list(val)[:3] if val is not None else []
    check("subsurface radius landed",
          name is not None and len(comps) == 3
          and all(abs(comps[i] - e) < 1e-4 for i, e in enumerate((1.0, 0.45, 0.2))),
          (name, comps))
    name, val = sock(bsdf, ("Subsurface Scale",))
    check("subsurface scale landed",
          name is not None and abs(float(val) - 0.006) < 1e-5, (name, val))
    name, val = sock(bsdf, ("Coat Weight", "Coat", "Clearcoat"))
    check("coat weight landed",
          name is not None and abs(float(val) - 0.35) < 1e-4, (name, val))
    name, val = sock(bsdf, ("Coat Roughness", "Clearcoat Roughness"))
    check("coat roughness landed",
          name is not None and abs(float(val) - 0.08) < 1e-4, (name, val))
    applied, skipped, written = [], [], []
    _write_aliased(bsdf, ("Not A Real Socket",), 1.0, applied, skipped, written, "nope")
    check("a missing socket is reported, not applied",
          skipped and not applied and not written, (applied, skipped))

res_bad = run("set_material", target="Dough", material_name="DoughMat",
              subsurface_radius="nope")
check("a bad radius is an error", not res_bad.get("success") and "subsurface_radius" in (
    res_bad.get("error") or ""), res_bad.get("error"))


# ───────────────────────── G239: wire a texture ─────────────────────────
print("== G239: apply_texture wires three maps ==")
clean()
run("add_box", name="Top", width=0.2, depth=0.2, height=0.02, on={"on_floor": True})
paths = {}
try:
    for key in ("diffuse", "roughness", "normal"):
        img = bpy.data.images.new(f"g239_{key}", 4, 4, alpha=False)
        path = f"/tmp/bb_g239_{key}.png"
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        paths[key] = path
    res = run("apply_texture", target="Top", material_name="Wood",
              maps=paths, scale=2.5, id="wood_table_worn")
    check("apply_texture succeeded", res.get("success"), str(res)[:300])
    check("wired diffuse, roughness, normal",
          res.get("wired") == ["diffuse", "roughness", "normal"], res.get("wired"))
    mat = bpy.data.materials.get("Wood")
    nt = mat.node_tree if mat else None
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None) if nt else None
    slots = list(bpy.data.objects["Top"].data.materials)
    check("material assigned to Top",
          mat is not None and slots and slots[0] == mat, slots)
    if nt and bsdf:
        diff = next(n for n in nt.nodes if n.label == "bb_tex_diffuse")
        rough = next(n for n in nt.nodes if n.label == "bb_tex_roughness")
        check("diffuse is box projection into Base Color",
              diff.projection == "BOX"
              and bsdf.inputs["Base Color"].links
              and bsdf.inputs["Base Color"].links[0].from_node == diff,
              diff.projection)
        check("roughness drives Roughness",
              bsdf.inputs["Roughness"].links
              and bsdf.inputs["Roughness"].links[0].from_node == rough)
        nm = next(n for n in nt.nodes if n.label == "bb_tex_normalmap")
        check("normal goes through a normal map",
              bsdf.inputs["Normal"].links and bsdf.inputs["Normal"].links[0].from_node == nm)
        mapping = next(n for n in nt.nodes if n.label == "bb_tex_map")
        scale = list(mapping.inputs["Scale"].default_value)[:3]
        check("scale dial is uniform",
              all(abs(v - 2.5) < 1e-4 for v in scale), scale)
        cs = res.get("colorspaces") or {}
        check("roughness is non-color",
              cs.get("roughness") in ("Non-Color", "Non-Colour", "Utility - Raw", "Raw"), cs)
        n_before = len([n for n in nt.nodes if (n.label or "").startswith("bb_tex_")])
        res2 = run("apply_texture", target="Top", material_name="Wood",
                   maps=paths, scale=1.0)
        n_after = len([n for n in nt.nodes if (n.label or "").startswith("bb_tex_")])
        check("re-apply does not stack a second graph",
              res2.get("success") and n_after == n_before, f"{n_before} → {n_after}")
finally:
    for path in paths.values():
        try:
            os.remove(path)
        except OSError:
            pass

res = run("apply_texture", target="Top")
check("texture with no id and no maps errors",
      not res.get("success") and "id" in (res.get("error") or ""), res.get("error"))


print()
if failures:
    print(f"e2e_g236_g239_gapfixes :: FAILED — {len(failures)}: {failures}")
    sys.exit(1)
print("e2e_g236_g239_gapfixes :: PASSED — 0 failures")
