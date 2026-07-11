"""G23 move 3 — teaching errors for valid ops missing a structural param.

Pure native test: each guarded call is missing its required param, so the verb
short-circuits with a teaching string BEFORE call_blender — no Blender needed and
the live scene is never touched. Run from the repo root:  uv run python tests/g23_teaching.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.verbs.transform import transform
from server.verbs.edit import edit
from server.verbs.add import add

failures = []


def check(label, text, must_contain):
    ok = all(s in text for s in must_contain)
    if ok:
        print(f"  ok    {label}")
    else:
        failures.append(label)
        print(f"  FAIL  {label}\n        got: {text!r}")


print("== transform teaching errors ==")
check("move_to with no destination", transform(op="move_to"),
      ["transform op=move_to: needs", "to_x/to_y/to_z", "e.g."])
check("rotate_to with no angle", transform(op="rotate_to"),
      ["op=rotate_to: needs", "deg_x/deg_y/deg_z"])
check("aim_axis with no segment", transform(op="aim_axis", targets="bolt"),
      ["op=aim_axis: needs", "aim_from+aim_to"])
check("rest_on with no target", transform(op="rest_on", targets="crate"),
      ["op=rest_on: needs", "target="])
check("resize with no dims", transform(op="resize", targets="box"),
      ["op=resize: needs", "width/depth/height"])
check("snap with no target", transform(op="snap", targets="lid"),
      ["op=snap: needs", "target="])
check("match_dim missing reference", transform(op="match_dim", target="shelf"),
      ["op=match_dim: needs", "reference"])
check("distribute missing endpoints", transform(op="distribute", targets="a,b,c"),
      ["op=distribute: needs", "between=[a,b]"])
check("distribute with only one endpoint", transform(op="distribute", targets="a,b", between=["x"]),
      ["op=distribute: needs"])
check("array_radial missing center", transform(op="array_radial", prototype="spoke", count=8),
      ["op=array_radial: needs", "center"])
check("scatter missing source", transform(op="scatter", target="rock"),
      ["op=scatter: needs", "source="])
check("snap_loop missing handle", transform(op="snap_loop"),
      ["op=snap_loop: needs", "handle="])

print("== edit teaching errors ==")
check("bridge missing handles", edit(op="bridge"),
      ["edit op=bridge: needs", "a and b"])
check("bridge with only one handle", edit(op="bridge", a="torso.neck"),
      ["edit op=bridge: needs"])
check("boolean missing cutter", edit(op="boolean", target="block"),
      ["op=boolean: needs", "cutter="])
check("extrude_along_curve missing curve", edit(op="extrude_along_curve", target="ring"),
      ["op=extrude_along_curve: needs", "curve="])

print("== add teaching errors ==")
check("box missing name", add(type="box"),
      ["add type=box: needs name", "e.g."])
check("cylinder missing name", add(type="cylinder"),
      ["add type=cylinder: needs name"])
check("curve missing points", add(type="curve", name="path"),
      ["add type=curve: needs", "points="])

print("== negative: a satisfied guard must NOT fire (still routes; unknown op caught) ==")
check("unknown op still falls through to unknown()", transform(op="floomp"),
      ["unknown op", "floomp"])
check("unknown type still falls through to unknown()", add(type="blorb"),
      ["unknown type", "blorb"])

print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("G23-TEACHING PASSED")
