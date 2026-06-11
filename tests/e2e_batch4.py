"""E2E for batch-4 gap fixes (U1, U2, U3, U6, U9) — rig introspection. Headless.

Usage: flatpak run org.blender.Blender --background --python /abs/path/to/tests/e2e_batch4.py
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


# ───────────────────────── build a small rig ─────────────────────────
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

run("create_armature", name="rig", bones=[
    {"name": "root",    "head": [0, 0, 0],   "tail": [0, 0, 0.2], "deform": False},
    {"name": "spine",   "head": [0, 0, 0.2], "tail": [0, 0, 1.0],
     "parent": "root", "connected": True},
    {"name": "ik_hand", "head": [0.5, 0, 1.0], "tail": [0.6, 0, 1.0], "deform": False},
])
rig = bpy.data.objects["rig"]

# an empty target + a pose-bone constraint pointing at it
empt = bpy.data.objects.new("ik_target", None)
bpy.context.scene.collection.objects.link(empt)
empt.location = (0.5, 0, 1.0)
con = rig.pose.bones["spine"].constraints.new('COPY_LOCATION')
con.target = empt

# custom props: one on the object, one on a pose bone
rig["lod"] = 2
rig.pose.bones["root"]["ik_fk"] = 1.0

# ───────────────────────── U1: get_bone_tree ─────────────────────────
print("== U1: get_bone_tree (filter / deform_only) ==")
t = run("get_bone_tree", armature="rig")
check("bone tree success", t.get("success") is True, str(t))
check("counts all 3 bones", t.get("bone_count") == 3, str(t))
check("tree lists every bone",
      all(b in t["tree"] for b in ("root", "spine", "ik_hand")), t["tree"])
check("control bones marked", "(control)" in t["tree"], t["tree"])
tf = run("get_bone_tree", armature="rig", filter="spine")
check("filter keeps match + ancestor", "spine" in tf["tree"] and "root" in tf["tree"], tf["tree"])
check("filter drops non-matching sibling", "ik_hand" not in tf["tree"], tf["tree"])
td = run("get_bone_tree", armature="rig", deform_only=True)
check("deform_only keeps the deform bone", "spine" in td["tree"], td["tree"])
check("deform_only drops the control sibling", "ik_hand" not in td["tree"], td["tree"])

# ───────────────────────── U1: describe_bone ─────────────────────────
print("== U1: describe_bone ==")
db = run("describe_bone", armature="rig", bone="spine")
check("describe_bone success", db.get("success") is True, str(db))
check("reports parent", db.get("parent") == "root", str(db))
check("reports deform flag", db.get("deform") is True, str(db))
check("reports length", db.get("length_mm", 0) > 700, str(db))  # ~0.8m bone
check("lists the constraint with target",
      any(c["type"] == "COPY_LOCATION" and c.get("target") == "ik_target"
          for c in db.get("constraints", [])), str(db.get("constraints")))
check("description mentions the constraint", "COPY_LOCATION" in db["description"], db["description"])
db_missing = run("describe_bone", armature="rig", bone="nope")
check("unknown bone errors", "error" in db_missing, str(db_missing))

# ───────────────────────── U2: custom properties ─────────────────────────
print("== U2: custom property get/set (object + pose bone) ==")
gp = run("get_custom_properties", name="rig")
check("object prop listed", gp.get("properties", {}).get("lod") == 2, str(gp))
check("internal bb_/_RNA_UI excluded", all(not k.startswith("bb_") for k in gp["properties"]), str(gp))
gpb = run("get_custom_properties", name="rig", bone="root")
check("pose-bone prop listed", gpb.get("properties", {}).get("ik_fk") == 1.0, str(gpb))
sp = run("set_custom_property", name="rig", bone="root", key="ik_fk", value=0.0)
check("set existing prop success", sp.get("success") is True and sp.get("created") is False, str(sp))
check("set value reflected", rig.pose.bones["root"]["ik_fk"] == 0.0)
sp2 = run("set_custom_property", name="rig", key="export_ready", value=1)
check("set new prop reports created", sp2.get("created") is True, str(sp2))
check("new prop actually created", rig.get("export_ready") == 1)
sp_bad = run("set_custom_property", name="rig", bone="missing", key="x", value=1)
check("set on missing bone errors", "error" in sp_bad, str(sp_bad))

# ───────────────────────── U3: pose_bone loc + additive ─────────────────────────
print("== U3: pose_bone translate + additive ==")
pl = run("pose_bone", armature="rig", bone="ik_hand", loc=[0, 0.2, 0])
check("pose by loc success", pl.get("success") is True, str(pl))
check("loc reflected", abs(rig.pose.bones["ik_hand"].location.y - 0.2) < 1e-4, str(pl))
pa = run("pose_bone", armature="rig", bone="ik_hand", loc=[0, 0.05, 0], additive=True)
check("additive loc accumulates", abs(rig.pose.bones["ik_hand"].location.y - 0.25) < 1e-4,
      str(rig.pose.bones["ik_hand"].location.y))
pr = run("pose_bone", armature="rig", bone="ik_hand", rot=[10, 0, 0])  # rot still works
check("rot-only still works", pr.get("success") is True, str(pr))
pn = run("pose_bone", armature="rig", bone="ik_hand")
check("neither rot nor loc errors", "error" in pn, str(pn))

# ───────────────────────── U9: list_constraints ─────────────────────────
print("== U9: list_constraints ==")
lc = run("list_constraints", name="rig", bone="spine")
check("list_constraints success", lc.get("success") is True, str(lc))
check("constraint reported with type+target",
      any(c["type"] == "COPY_LOCATION" and c.get("target") == "ik_target"
          for c in lc.get("constraints", [])), str(lc))

# ───────────────────────── U6: describe non-mesh types ─────────────────────────
print("== U6: describe armature / empty / lattice ==")
da = run("describe", name="rig")
check("armature describe has bone summary", "armature: 3 bones" in da["description"], da["description"])
check("armature describe drops 'no material'", "no material" not in da["description"], da["description"])
de = run("describe", name="ik_target")
check("empty describe says empty", "empty" in de["description"], de["description"])
check("empty describe drops 'no material'", "no material" not in de["description"], de["description"])
# lattice deforming a mesh
lat_data = bpy.data.lattices.new("lat_data")
lat = bpy.data.objects.new("lat", lat_data)
bpy.context.scene.collection.objects.link(lat)
run("add_box", name="latmesh", width=1.0, depth=1.0, height=1.0)
lm = bpy.data.objects["latmesh"].modifiers.new("L", 'LATTICE')
lm.object = lat
dl = run("describe", name="lat")
check("lattice describe names what it deforms",
      "lattice" in dl["description"] and "latmesh" in dl["description"], dl["description"])

print()
if failures:
    print(f"BATCH4 E2E: {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("BATCH4 E2E: ALL TESTS PASSED")
