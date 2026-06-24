"""UV unwrap — SPEC-18 Phase 1 (closes gaps.md G152 for the no-seam case).

Box-projection texturing (textures.py) needs no UVs and stays the default; reach
here only when texture grain must follow a curved surface — a mug belly, a plate
rim, wood edge grain. This phase exposes the parametric / auto projections that need
no seams: smart / cube / cylinder / sphere. Seam marking + the seam-driven methods
(angle / conformal) and the deterministic `uv op=check` verdict are later phases.

Each projection is a mechanical setter — it flattens the mesh, it never judges where
the seams land or whether the grain reads right (that's taste → the human, SPEC-18 §6).
"""

import math

import bpy

from .common import resolve_targets, linked_guard

# The no-seam methods this phase supports. angle/conformal (which consume marked
# seams) are SPEC-18 Phase 2.
METHODS = ("smart", "cube", "cylinder", "sphere")


def _ensure_uv_layer(me):
    """Active UV layer for a mesh, creating one named 'UVMap' when absent. The
    projection operators create a layer themselves if none exists, but doing it up
    front guarantees a named layer to report and keeps behaviour identical whether or
    not the mesh was unwrapped before."""
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    return me.uv_layers.active


def _project_active(method, angle_limit, island_margin, scale_to_bounds):
    """Run the chosen projection on the active object — assumed already in EDIT mode
    with all faces selected. Returns None on success or an error string."""
    try:
        if method == "smart":
            # angle_limit is an ANGLE property (radians at the API, degrees in the UI).
            bpy.ops.uv.smart_project(angle_limit=math.radians(angle_limit),
                                     island_margin=island_margin,
                                     scale_to_bounds=scale_to_bounds)
        elif method == "cube":
            bpy.ops.uv.cube_project(scale_to_bounds=scale_to_bounds)
        elif method == "cylinder":
            # ALIGN_TO_OBJECT, not the default VIEW_ON_EQUATOR: wrap around the
            # object's OWN local axis so the unwrap is deterministic and independent
            # of viewport orientation (a mug belly follows its local Z, not the camera).
            bpy.ops.uv.cylinder_project(direction='ALIGN_TO_OBJECT',
                                        scale_to_bounds=scale_to_bounds)
        elif method == "sphere":
            bpy.ops.uv.sphere_project(direction='ALIGN_TO_OBJECT',
                                      scale_to_bounds=scale_to_bounds)
    except RuntimeError as e:
        return str(e)
    return None


def uv_unwrap(params):
    """Flatten one or more meshes' UVs with a parametric / auto projection (no seams).

    target:          object, group/collection, or 'a,b,c' — each mesh unwrapped
                     INDEPENDENTLY (UVs are per-mesh).
    method:          smart (default) | cube | cylinder | sphere.
    angle_limit:     [smart] degrees; islands split where faces bend past this (66 default).
    island_margin:   [smart] gap packed between islands in UV units (0.02 default).
    scale_to_bounds: stretch the result to fill the whole [0,1] square (default False).

    Manages its own Edit-Mode entry/exit per mesh and restores the mode it found
    (G157). Box projection (material without space=uv) needs none of this.
    """
    target = params.get("target")
    if target is None or target == "":
        return {"error": "uv op=unwrap needs target=<object/group/'a,b,c'>"}
    method = (params.get("method") or "smart").lower().strip()
    if method not in METHODS:
        return {"error": f"unknown method '{method}' — use one of {', '.join(METHODS)} "
                         f"(angle/conformal need marked seams — SPEC-18 Phase 2, not built)"}
    angle_limit = float(params.get("angle_limit", 66.0))
    island_margin = float(params.get("island_margin", 0.02))
    scale_to_bounds = bool(params.get("scale_to_bounds", False))

    objs, err = resolve_targets(target)
    if err:
        return {"error": err}
    meshes = [o for o in objs if o.type == 'MESH']
    if not meshes:
        return {"error": f"'{target}' contains no mesh to unwrap"}
    for o in meshes:
        blocked = linked_guard(o)
        if blocked:
            return {"error": blocked}

    # Remember what to put back (G157 hygiene). Switching the active object requires
    # OBJECT mode, so drop out of any edit session first; we restore it at the end.
    start_active = bpy.context.view_layer.objects.active
    start_mode = start_active.mode if start_active is not None else 'OBJECT'
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    unwrapped = []
    for o in meshes:
        _ensure_uv_layer(o.data)
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        perr = _project_active(method, angle_limit, island_margin, scale_to_bounds)
        bpy.ops.object.mode_set(mode='OBJECT')
        if perr:
            return {"error": f"{method} unwrap failed on '{o.name}': {perr}"}
        layer = o.data.uv_layers.active
        unwrapped.append({"name": o.name,
                          "uv_layer": layer.name if layer else "UVMap",
                          "faces": len(o.data.polygons)})

    # Restore the original active object + its mode so a unwrap mid edit-session
    # leaves the agent where it was (the mode is echoed in the status block).
    bpy.ops.object.select_all(action='DESELECT')
    if start_active is not None and start_active.name in bpy.data.objects:
        start_active.select_set(True)
        bpy.context.view_layer.objects.active = start_active
        if start_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

    return {"success": True, "method": method, "unwrapped": unwrapped,
            "count": len(unwrapped),
            "status_focus": unwrapped[0]["name"] if unwrapped else None}


TOOLS = {
    "uv_unwrap": uv_unwrap,
}
