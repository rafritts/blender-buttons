"""band_around: a strap/hoop/belt wrapping the combined silhouette of objects.

The problem this solves: a gold strap around a treasure chest has to follow the
OUTLINE of body+lid together, bridging the gap between them — you can't get that
by stretching a box. band_around slices every target at a height band, takes the
convex hull of that cross-section (the silhouette), offsets it outward, and
sweeps a closed loop of geometry around it. Chest straps, barrel hoops, belts,
pipe clamps, crown bands.
"""

import bpy
import bmesh

from .common import resolve_targets, world_bbox


def _convex_hull_2d(points):
    """Andrew's monotone chain. points: list of (u, v). Returns CCW hull, no
    duplicate endpoint. Pure math — no bpy."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def band_around(params):
    """Build a band (strap/hoop) wrapping the combined silhouette of targets.

    name:      object name for the band (required).
    targets:   object / group / list whose combined outline the band follows.
    axis:      X | Y | Z — the band wraps around this axis (the silhouette is the
               cross-section in the perpendicular plane). Default Z (a horizontal
               belt around a standing object).
    at:        position along `axis` to wrap at (world units). Default: the
               midpoint of the targets' combined extent on that axis.
    width:     band extent ALONG the axis (how tall the strap is). Default 0.05.
    thickness: how far the band stands proud of the silhouette (radially outward).
               Default 0.02.
    """
    name = params.get("name")
    if not name:
        return {"error": "'name' is required"}
    if bpy.data.objects.get(name) is not None:
        return {"error": f"Object '{name}' already exists"}
    objs, err = resolve_targets(params.get("targets"))
    if err:
        return {"error": err}
    meshes = [o for o in objs if o.type == 'MESH']
    if not meshes:
        return {"error": "targets contain no mesh objects"}

    axis = (params.get("axis") or "Z").upper()
    if axis not in ("X", "Y", "Z"):
        return {"error": "axis must be X, Y, or Z"}
    ai = "XYZ".index(axis)
    u, v = [i for i in range(3) if i != ai]

    width = float(params.get("width", 0.05))
    thickness = float(params.get("thickness", 0.02))

    # Combined extent on the axis (to default `at` and to clamp the slab).
    lo_axis = min(world_bbox(o)[ai] for o in meshes)
    hi_axis = max(world_bbox(o)[ai + 3] for o in meshes)
    at = params.get("at")
    at = (lo_axis + hi_axis) / 2.0 if at is None else float(at)

    slab_lo = at - width / 2.0
    slab_hi = at + width / 2.0

    # Collect cross-section points: world verts within the slab, projected to (u, v).
    pts = []
    for o in meshes:
        mat = o.matrix_world
        for vert in o.data.vertices:
            wc = mat @ vert.co
            if slab_lo - 1e-6 <= wc[ai] <= slab_hi + 1e-6:
                pts.append((round(wc[u], 5), round(wc[v], 5)))
    # If the slab is too thin to catch a ring of verts, fall back to the full
    # cross-section (every vert) so a band still forms.
    if len(pts) < 3:
        pts = []
        for o in meshes:
            mat = o.matrix_world
            for vert in o.data.vertices:
                wc = mat @ vert.co
                pts.append((round(wc[u], 5), round(wc[v], 5)))

    hull = _convex_hull_2d(pts)
    if len(hull) < 3:
        return {"error": "could not form a silhouette (need a 2D cross-section of 3+ points)"}

    cu = sum(p[0] for p in hull) / len(hull)
    cv = sum(p[1] for p in hull) / len(hull)

    bm = bmesh.new()
    n = len(hull)
    rings = {"inner_lo": [], "inner_hi": [], "outer_lo": [], "outer_hi": []}
    for (pu, pv) in hull:
        # Outward (radial) direction from the silhouette centroid.
        du, dv = pu - cu, pv - cv
        mag = (du * du + dv * dv) ** 0.5 or 1.0
        du, dv = du / mag, dv / mag
        ou, ov = pu + du * thickness, pv + dv * thickness

        def mk(au, av, axisval):
            co = [0.0, 0.0, 0.0]
            co[u] = au
            co[v] = av
            co[ai] = axisval
            return bm.verts.new(co)

        rings["inner_lo"].append(mk(pu, pv, slab_lo))
        rings["inner_hi"].append(mk(pu, pv, slab_hi))
        rings["outer_lo"].append(mk(ou, ov, slab_lo))
        rings["outer_hi"].append(mk(ou, ov, slab_hi))

    il, ih = rings["inner_lo"], rings["inner_hi"]
    ol, oh = rings["outer_lo"], rings["outer_hi"]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((ol[i], ol[j], oh[j], oh[i]))   # outer wall
        bm.faces.new((ih[i], ih[j], il[j], il[i]))   # inner wall
        bm.faces.new((ih[i], oh[i], oh[j], ih[j]))   # top rim
        bm.faces.new((il[i], il[j], ol[j], ol[i]))   # bottom rim

    bm.normal_update()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)

    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    return {
        "success": True,
        "object_name": obj.name,
        "axis": axis,
        "at": round(at, 4),
        "width": width,
        "thickness": thickness,
        "hull_points": n,
        "dimensions": [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)],
    }


TOOLS = {
    "band_around": band_around,
}
