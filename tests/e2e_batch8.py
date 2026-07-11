"""E2E for batch-8 gap fixes (W1, W2, W3) — modifier stack order, manual-path bind
guard, and the type-agnostic deform rebind. Headless.

Usage: flatpak run --filesystem=home org.blender.Blender --background \
         --python /abs/path/to/tests/e2e_batch8.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from extension import server as bb_server   # noqa: E402

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


def mods(name):
    return [m.name for m in bpy.data.objects[name].modifiers]


def mod(name, mod_name):
    return {m.name: m for m in bpy.data.objects[name].modifiers}.get(mod_name)


# ───────── W1: move_modifier reorders the stack ─────────
print("== W1: move_modifier ==")
clean()
run("add_box", name="block", width=1, depth=1, height=1)
run("select_object", name="block")
run("add_modifier", type="SUBSURF", name="Subsurf")
run("add_modifier", type="BEVEL", name="Bevel")
run("add_modifier", type="SOLIDIFY", name="Solidify")
check("stack built top→bottom", mods("block") == ["Subsurf", "Bevel", "Solidify"], mods("block"))

r = run("move_modifier", target="block", modifier="Solidify", index=0)
check("move by index=0 success", r.get("success") is True, str(r))
check("reports from/to index", r.get("from_index") == 2 and r.get("to_index") == 0, str(r))
check("Solidify now on top", mods("block") == ["Solidify", "Subsurf", "Bevel"], mods("block"))

r = run("move_modifier", target="block", modifier="Solidify", after="Subsurf")
check("move after=Subsurf success", r.get("success") is True, str(r))
check("Solidify directly below Subsurf", mods("block") == ["Subsurf", "Solidify", "Bevel"], mods("block"))

r = run("move_modifier", target="block", modifier="Bevel", before="Subsurf")
check("move before=Subsurf success", r.get("success") is True, str(r))
check("Bevel directly above Subsurf", mods("block") == ["Bevel", "Subsurf", "Solidify"], mods("block"))

# Guard rails.
check("out-of-range index errors", "error" in run("move_modifier", target="block", modifier="Bevel", index=9))
check("two destinations errors", "error" in run("move_modifier", target="block", modifier="Bevel", index=0, before="Subsurf"))
check("no destination errors", "error" in run("move_modifier", target="block", modifier="Bevel"))
check("unknown modifier errors", "error" in run("move_modifier", target="block", modifier="Nope", index=0))
check("unknown reference errors", "error" in run("move_modifier", target="block", modifier="Bevel", before="Nope"))

# CORRECTIVE_SMOOTH is now creatable via add_modifier.
print("== W1: add_modifier CORRECTIVE_SMOOTH ==")
clean()
run("add_sphere", name="cs", radius=1.0, segments=16, rings=12)
run("select_object", name="cs")
r = run("add_modifier", type="CORRECTIVE_SMOOTH", name="CS")
check("CORRECTIVE_SMOOTH added", r.get("success") is True, str(r))
cs = mod("cs", "CS")
check("modifier exists + typed", cs is not None and cs.type == 'CORRECTIVE_SMOOTH')
check("defaults rest_source=BIND", cs is not None and cs.rest_source == 'BIND', getattr(cs, "rest_source", None))
check("added unbound", cs is not None and cs.is_bind is False)
r = run("add_modifier", type="CORRECTIVE_SMOOTH", name="CSorco", rest_source="ORCO")
check("rest_source=ORCO honored", mod("cs", "CSorco").rest_source == 'ORCO')


# ───────── W3: rebind_deform (umbrella, rebind-only) ─────────
# CORRECTIVE_SMOOTH(rest_source=BIND): rebind_deform captures the bind.
print("== W3: rebind_deform binds a CORRECTIVE_SMOOTH(BIND) ==")
clean()
run("add_sphere", name="cs", radius=1.0, segments=16, rings=12)
run("select_object", name="cs")
run("add_modifier", type="CORRECTIVE_SMOOTH", name="CS")  # rest_source=BIND, unbound
r = run("rebind_deform", mesh="cs", modifier="CS")
check("corrective-smooth rebind success", r.get("success") is True, str(r))
check("corrective-smooth now bound", mod("cs", "CS").is_bind is True, str(r))

# CORRECTIVE_SMOOTH(rest_source=ORCO): nothing to rebind — reported, not toggled.
print("== W3: ORCO corrective-smooth has no bind to recompute ==")
clean()
run("add_sphere", name="cs2", radius=1.0, segments=16, rings=12)
run("select_object", name="cs2")
run("add_modifier", type="CORRECTIVE_SMOOTH", name="CSorco", rest_source="ORCO")
r = run("rebind_deform", mesh="cs2", modifier="CSorco")
check("ORCO corrective-smooth rebind errors clearly", "error" in r
      and "Original Coords" in r["error"], str(r))
check("ORCO modifier left unbound", mod("cs2", "CSorco").is_bind is False)

# SURFACE_DEFORM dispatch (headless-only — not in Spring's stack). Construct one by
# hand (no add_modifier creation path for it) and confirm rebind_deform binds it.
print("== W3: rebind_deform dispatches to surfacedeform_bind ==")
clean()
run("add_plane", name="target_surf", size=4)
run("add_plane", name="skin", size=1)
bpy.data.objects["skin"].location = (0, 0, 0.1)
bpy.context.view_layer.update()
sd = bpy.data.objects["skin"].modifiers.new(name="SD", type='SURFACE_DEFORM')
sd.target = bpy.data.objects["target_surf"]
r = run("rebind_deform", mesh="skin", modifier="SD")
check("surface-deform rebind success", r.get("success") is True, str(r))
check("surface-deform now bound", mod("skin", "SD").is_bound is True, str(r))

# Rebind-only contract: non-bindable modifier and bindless mesh both error.
print("== W3: rebind-only contract ==")
clean()
run("add_box", name="b", width=1, depth=1, height=1)
run("select_object", name="b")
run("add_modifier", type="SUBSURF", name="Sub")
check("rebind a non-bindable modifier errors", "error" in run("rebind_deform", mesh="b", modifier="Sub"))
check("rebind a mesh with no bindable modifier errors", "error" in run("rebind_deform", mesh="b"))
check("rebind missing modifier errors", "error" in run("rebind_deform", mesh="b", modifier="Ghost"))


print()
if failures:
    print(f"BATCH8 E2E: {len(failures)} FAILED → {failures}")
    sys.exit(1)
else:
    print("BATCH8 E2E: ALL TESTS PASSED")
