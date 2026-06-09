"""Placement DSL — resolves `on=...` specs into world-space centers.

A placement spec is a dict combining one or more of these constraints. The
resolver computes the world-space CENTER for a new object whose local bounds
extend ±(w/2, d/2, h/2) from its origin.

Axis convention: +X right, +Y back (away from front view), +Z up.
So "front" = -Y, "back" = +Y, "left" = -X, "right" = +X.

Whole-object placements (set all three axes):
  {"on": "name"}            -- rests on top of target, centered XY
  {"under": "name"}         -- rests under target, centered XY
  {"centered_on": "name"}   -- match XYZ centers of target
  {"between": ["a", "b"]}   -- centered on midpoint of two object centers
  {"at_corner": {"of": "name", "corner": "front_left"|"front_right"|"back_left"|"back_right"}}
                            -- bottom-{corner} of new aligns with bottom-{corner} of target
  {"at": [x, y, z]}         -- center at the literal world coordinate (full ripcord;
                               prefer relational keys when an anchor object exists)

Adjacency placements (set 1 axis + center the other 2 on target):
  {"left_of": "name"}       -- flush to target's -X side, Y/Z centered on target
  {"right_of": "name"}      -- flush to target's +X side
  {"in_front_of": "name"}   -- flush to target's -Y side
  {"behind": "name"}        -- flush to target's +Y side

Mirror placement (sets cx from another object's center, flipping the chosen axis):
  {"mirror_of": "name", "axis": "X"}   -- center = (-cx_of_name, cy, cz) when axis=X
                                          (axis Y or Z analogous)

Absolute axis overrides (applied AFTER relational resolution; always win):
  {"x": value}              -- center X = value
  {"y": value}              -- center Y = value
  (use "raise_to"/"on_floor" for Z — they set Z_MIN, not Z_CENTER)

Z overrides (always applied last, win conflicts):
  {"on_floor": True}        -- Z_MIN of new = 0
  {"raise_to": value}       -- Z_MIN of new = value
  {"z": value}              -- center Z = value (alternative to raise_to)

Modifiers:
  {"gap": 0.02}             -- spacing for on/under/left_of/right_of/in_front_of/behind
                              (positive = farther apart; negative = overlap)
"""

import bpy

from .common import world_bbox

# Every key resolve_placement understands. Anything else in a spec is a typo or
# an unsupported idea — reject loudly instead of silently ignoring it.
VALID_SPEC_KEYS = {
    "on", "under", "between", "centered_on", "at_corner", "at",
    "left_of", "right_of", "in_front_of", "behind",
    "mirror_of", "axis",
    "on_floor", "raise_to", "x", "y", "z", "gap",
}


def resolve_placement(spec, dims):
    """Compute world-space center (cx, cy, cz) for a new object with given dims.
    spec is None or a dict (see vocabulary above). dims is (w, d, h)."""
    w, d, h = dims
    cx, cy, cz = 0.0, 0.0, 0.0

    if not spec:
        return (cx, cy, cz)

    if not isinstance(spec, dict):
        raise ValueError(f"Placement spec must be a dict, got {type(spec).__name__}")

    unknown = set(spec) - VALID_SPEC_KEYS
    if unknown:
        raise ValueError(
            f"Unknown placement key(s) {sorted(unknown)}. "
            f"Valid keys: {sorted(VALID_SPEC_KEYS)}"
        )

    gap = spec.get("gap", 0.0)

    def bbox(name):
        o = bpy.data.objects.get(name)
        if o is None:
            raise ValueError(f"Placement target '{name}' not found")
        return world_bbox(o)

    def center(name):
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(name)
        return ((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2)

    # Whole-object placements
    if "at" in spec:
        at = spec["at"]
        if not (isinstance(at, (list, tuple)) and len(at) == 3):
            raise ValueError("'at' requires [x, y, z] — three world coordinates for the center")
        cx, cy, cz = float(at[0]), float(at[1]), float(at[2])
    elif "on" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["on"])
        cx = (xmin + xmax) / 2
        cy = (ymin + ymax) / 2
        cz = zmax + h / 2 + gap
    elif "under" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["under"])
        cx = (xmin + xmax) / 2
        cy = (ymin + ymax) / 2
        cz = zmin - h / 2 - gap
    elif "between" in spec:
        names = spec["between"]
        if not (isinstance(names, list) and len(names) == 2):
            raise ValueError("'between' requires a list of exactly 2 object names")
        c1, c2 = center(names[0]), center(names[1])
        cx = (c1[0] + c2[0]) / 2
        cy = (c1[1] + c2[1]) / 2
        cz = (c1[2] + c2[2]) / 2
    elif "centered_on" in spec:
        cx, cy, cz = center(spec["centered_on"])
    elif "at_corner" in spec:
        ac = spec["at_corner"]
        if not isinstance(ac, dict) or "of" not in ac:
            raise ValueError("'at_corner' must be {'of': name, 'corner': 'front_left'|...}")
        corner = ac.get("corner", "front_left")
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(ac["of"])
        parts = corner.lower().split("_")
        if "front" in parts:
            cy = ymin + d / 2
        elif "back" in parts:
            cy = ymax - d / 2
        else:
            cy = (ymin + ymax) / 2
        if "left" in parts:
            cx = xmin + w / 2
        elif "right" in parts:
            cx = xmax - w / 2
        else:
            cx = (xmin + xmax) / 2
        cz = zmin + h / 2

    # Adjacency placements (override the above if present)
    if "left_of" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["left_of"])
        cx = xmin - w / 2 - gap
        cy = (ymin + ymax) / 2
        cz = (zmin + zmax) / 2
    elif "right_of" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["right_of"])
        cx = xmax + w / 2 + gap
        cy = (ymin + ymax) / 2
        cz = (zmin + zmax) / 2
    elif "in_front_of" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["in_front_of"])
        cx = (xmin + xmax) / 2
        cy = ymin - d / 2 - gap
        cz = (zmin + zmax) / 2
    elif "behind" in spec:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox(spec["behind"])
        cx = (xmin + xmax) / 2
        cy = ymax + d / 2 + gap
        cz = (zmin + zmax) / 2

    # Mirror placement — sets center from another object, flipping the chosen axis
    if "mirror_of" in spec:
        src_cx, src_cy, src_cz = center(spec["mirror_of"])
        axis = spec.get("axis", "X").upper()
        cx, cy, cz = src_cx, src_cy, src_cz
        if axis == "X":
            cx = -src_cx
        elif axis == "Y":
            cy = -src_cy
        elif axis == "Z":
            cz = -src_cz
        else:
            raise ValueError(f"mirror_of axis must be X, Y, or Z (got {axis!r})")

    # Z overrides (last word)
    if spec.get("on_floor"):
        cz = h / 2
    if "raise_to" in spec:
        cz = spec["raise_to"] + h / 2

    # Absolute X/Y/Z overrides — always last word for that axis.
    if "x" in spec:
        cx = float(spec["x"])
    if "y" in spec:
        cy = float(spec["y"])
    if "z" in spec:
        cz = float(spec["z"])

    return (cx, cy, cz)


def describe_placement(obj):
    """Describe an object's position in relational terms — no raw coordinates.
    Walks the scene to find the nearest meaningful anchor (floor, another object's face)."""
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    w, d, h = xmax - xmin, ymax - ymin, zmax - zmin

    parts = []
    if abs(zmin) < 1e-4:
        parts.append("standing on floor")
    elif zmin > 0:
        for o in bpy.context.scene.objects:
            if o == obj or o.type != 'MESH':
                continue
            o_xmin, o_ymin, o_zmin, o_xmax, o_ymax, o_zmax = world_bbox(o)
            if abs(zmin - o_zmax) < 1e-3 and o_xmin <= (xmin + xmax) / 2 <= o_xmax:
                parts.append(f"resting on '{o.name}'")
                break
        else:
            parts.append(f"floating {round(zmin, 3)}m above floor")

    parts.append(f"size {round(w, 3)}x{round(d, 3)}x{round(h, 3)}m (W×D×H)")
    return "; ".join(parts)
