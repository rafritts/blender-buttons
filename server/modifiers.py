from server._core import mcp, call_blender, _status


@mcp.tool()
def add_modifier(type: str, name: str = "", levels: int = 2, render_levels: int = 2,
                 width: float = 0.1, segments: int = 1,
                 target: str = "", offset: float = None,
                 wrap_method: str = "NEAREST_SURFACEPOINT",
                 axis: str = "X", merge_threshold: float = None,
                 mirror_object: str = "", precision: int = None,
                 rest_source: str = "", factor: float = None, iterations: int = None,
                 label: str = "") -> str:
    """
    Add a modifier to the active object.
    type: SUBSURF | BEVEL | SOLIDIFY | MIRROR | ARRAY | SCREW | SHRINKWRAP
          | MESH_DEFORM | ARMATURE | LATTICE | CORRECTIVE_SMOOTH
    levels: subdivision levels (SUBSURF)  |  width/segments: bevel params
    target: the partner object. Required for —
      SHRINKWRAP  : the surface to wrap onto.
      MESH_DEFORM : the cage mesh that drives the deform (added UNBOUND — then
                    call bind_mesh_deform to bind it; the recovery path for a
                    production cloth/skin deform stack).
      ARMATURE    : the armature that deforms this mesh (needs vertex groups /
                    weights — see auto_weight / weight_to_bone).
      LATTICE     : the lattice cage that deforms this mesh.
    offset: SHRINKWRAP only — surface offset in meters (skin distance).
    wrap_method: SHRINKWRAP only —
                 NEAREST_SURFACEPOINT (default) | PROJECT | NEAREST_VERTEX | TARGET_PROJECT.
    axis: MIRROR only — any combination of X, Y, Z (default "X"). E.g. "XY" mirrors on both.
    merge_threshold: MIRROR only — weld coincident verts at the mirror plane (typical 0.001).
    mirror_object: MIRROR only — use this object's local axes as the mirror plane (defaults to self).
    precision: MESH_DEFORM only — bind precision 2–10 (higher = sharper, slower bind).
    CORRECTIVE_SMOOTH — fixes skinning collapse on bends (a deform-stack staple):
      rest_source: BIND (default — smooth toward a captured pose, vertex-keyed;
                   added UNBOUND, then call rebind_deform to capture) |
                   ORCO (smooth toward the base mesh, no bind).
      factor: smoothing strength 0..1. iterations: smoothing passes.
    """
    params = {
        "type": type, "name": name or type.capitalize(),
        "levels": levels, "render_levels": render_levels,
        "width": width, "segments": segments,
        "wrap_method": wrap_method,
        "axis": axis,
    }
    if target:
        params["target"] = target
    if offset is not None:
        params["offset"] = offset
    if merge_threshold is not None:
        params["merge_threshold"] = merge_threshold
    if mirror_object:
        params["mirror_object"] = mirror_object
    if precision is not None:
        params["precision"] = precision
    if rest_source:
        params["rest_source"] = rest_source
    if factor is not None:
        params["factor"] = factor
    if iterations is not None:
        params["iterations"] = iterations
    result = call_blender("add_modifier", params, label=label)
    if result.get("success"):
        main = f"{result['modifier']} [{result.get('op_id','')}]"
        if result.get("note"):
            main += f"\n  {result['note']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def bind_mesh_deform(mesh: str, cage: str = "", action: str = "bind",
                     modifier: str = "", precision: int = None,
                     label: str = "") -> str:
    """
    Bind / unbind / rebind a Mesh Deform modifier — the recovery path for a
    production cloth/skin deform stack (gaps.md V1).

    MESH_DEFORM drives a high-res mesh from a low-res cage (better cloth/skin
    deformation than direct armature skinning). The bind is computed once and is
    keyed to the mesh's vertex count — so ANY topology edit silently invalidates
    it (the modifier stops deforming with no error), and rebinding is the fix.

    mesh:      the mesh carrying (or to carry) the MESH_DEFORM modifier.
    cage:      the cage object that drives the deform. If the mesh has no
               MESH_DEFORM modifier yet, one is created against this cage; if it
               already has one, cage is optional (re-points it when given).
    action:    bind (default — bind if currently unbound) | unbind | rebind
               (unbind then bind, after a cage edit or topology change).
    modifier:  name of a specific MESH_DEFORM modifier (when several exist).
    precision: bind precision 2–10 (higher = sharper, slower bind).

    The cage must fully ENCLOSE the mesh or the bind silently refuses — this
    reports that as an error rather than a false success.
    """
    params = {"mesh": mesh, "action": action}
    if cage:
        params["cage"] = cage
    if modifier:
        params["modifier"] = modifier
    if precision is not None:
        params["precision"] = precision
    result = call_blender("bind_mesh_deform", params, label=label)
    if result.get("success"):
        state = "bound" if result.get("bound") else "unbound"
        main = (f"mesh-deform {result['action']}: '{result['modifier']}' on "
                f"'{result['mesh']}' (cage '{result['cage']}') → {state} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def rebind_deform(mesh: str, modifier: str = "", label: str = "") -> str:
    """
    Rebind stale deform binds after a topology edit or a stack-order move — the
    recovery verb the "DEFORM BIND INVALIDATED" warning points at (gaps.md W3).

    MESH_DEFORM, SURFACE_DEFORM, and CORRECTIVE_SMOOTH(rest_source=BIND) each store
    bind data keyed to the mesh's vertex count + order. A topology edit (vert-count
    change) or a move_modifier that changes the modifier's evaluated input leaves
    the bind flag reading True while the bind is silently DEAD. This rebinds it
    (unbind → bind) against the current geometry. RE-BINDS existing modifiers only
    — it never creates one (use add_modifier / bind_mesh_deform for setup).

    mesh:     the mesh carrying the bound deform modifier(s).
    modifier: name of ONE specific modifier; omit to rebind EVERY bindable deform
              modifier on the mesh.

    A CORRECTIVE_SMOOTH set to rest_source=ORCO has no stored bind (it smooths
    toward Original Coordinates) and is reported as skipped, not toggled blind.
    """
    params = {"mesh": mesh}
    if modifier:
        params["modifier"] = modifier
    result = call_blender("rebind_deform", params, label=label)
    if result.get("success"):
        rebound = ", ".join(f"{r['modifier']}({r['type']})" for r in result.get("rebound", []))
        main = f"rebound on '{result['mesh']}': {rebound} [{result.get('op_id','')}]"
        for s in result.get("skipped", []):
            main += f"\n  skipped {s['modifier']} ({s['type']}): {s['reason']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def move_modifier(target: str, modifier: str, index: int = None,
                  before: str = "", after: str = "", label: str = "") -> str:
    """
    Reorder a modifier in the object's stack (gaps.md W1). Stack ORDER is
    semantics: a deform modifier ABOVE a Subsurf binds against the base mesh;
    below it, against the denser subdivided result. add_modifier / bind_mesh_deform
    append to the BOTTOM and nothing could move them before this.

    target:   object name.
    modifier: name of the modifier to move.
    Pass exactly ONE destination:
      index:  absolute target index (0 = top of the stack).
      before: move it directly ABOVE this modifier (by name).
      after:  move it directly BELOW this modifier (by name).

    TRAP (handled): moving a BOUND deform modifier changes its evaluated input, so
    the bind dies — silently and WITHOUT a vert-count change, so the topology guard
    can't see it. This returns a DEFORM BIND INVALIDATED warning when it moves a
    bound deform modifier; the recipe is move → rebind_deform.
    """
    params = {"target": target, "modifier": modifier}
    if index is not None:
        params["index"] = index
    if before:
        params["before"] = before
    if after:
        params["after"] = after
    result = call_blender("move_modifier", params, label=label)
    if result.get("success"):
        main = (f"moved '{result['modifier']}' on '{result['target']}': "
                f"index {result['from_index']} → {result['to_index']} "
                f"[{result.get('op_id','')}]")
        if result.get("bind_warning"):
            main += f"\n{result['bind_warning']}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def modify_modifier(target: str, modifier_name: str,
                    levels: int = None, render_levels: int = None,
                    width: float = None, segments: int = None,
                    thickness: float = None, offset: float = None,
                    angle_limit: float = None, count: int = None,
                    wrap_method: str = "", target_object: str = "",
                    label: str = "") -> str:
    """
    Tweak properties on an existing modifier without rebuilding it.
    Use this to dial in shrinkwrap offset, bevel width, subsurf levels, etc.

    target: object name. modifier_name: name of the modifier on that object.
    Each numeric param is optional — pass only the ones you want to change.
    angle_limit is in degrees (BEVEL). target_object re-points SHRINKWRAP/ARRAY to a different object.
    wrap_method (SHRINKWRAP): NEAREST_SURFACEPOINT | PROJECT | NEAREST_VERTEX | TARGET_PROJECT.
    """
    params = {"target": target, "modifier_name": modifier_name}
    for key, val in (("levels", levels), ("render_levels", render_levels),
                     ("width", width), ("segments", segments),
                     ("thickness", thickness), ("offset", offset),
                     ("angle_limit", angle_limit), ("count", count)):
        if val is not None:
            params[key] = val
    if wrap_method:
        params["wrap_method"] = wrap_method
    if target_object:
        params["target_object"] = target_object
    result = call_blender("modify_modifier", params, label=label)
    if result.get("success"):
        applied = result.get("applied", [])
        skipped = result.get("skipped", [])
        tail = f" (skipped: {skipped})" if skipped else ""
        main = f"{result['modifier']} ({result['type']}): {applied}{tail} [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def remove_modifier(target: str, modifier_name: str, label: str = "") -> str:
    """
    Remove a modifier from an object by name. Pass modifier_name='ALL' to clear them all.
    Use list_modifiers first to see what's on the object.
    """
    result = call_blender("remove_modifier",
                          {"target": target, "modifier_name": modifier_name}, label=label)
    if result.get("success"):
        main = f"removed {result['removed']} from '{result['target']}' [{result.get('op_id','')}]"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def list_modifiers(target: str) -> str:
    """
    List the modifier stack on an object (top → bottom = evaluation order).
    Each entry shows type, name, and the relevant numeric props.
    """
    result = call_blender("list_modifiers", {"target": target})
    if not result.get("success"):
        return result.get("error", "failed") + _status(result)
    mods = result["modifiers"]
    if not mods:
        return f"'{result['target']}': no modifiers" + _status(result)
    lines = [f"'{result['target']}' modifier stack ({len(mods)}):"]
    for i, m in enumerate(mods):
        extras = " ".join(f"{k}={v}" for k, v in m.items() if k not in ("name", "type"))
        lines.append(f"  {i}. {m['type']:12} '{m['name']}'  {extras}")
    return "\n".join(lines) + _status(result)


@mcp.tool()
def boolean(target: str, cutter: str, op: str = "DIFFERENCE",
            solver: str = "EXACT", apply: bool = False, hide_cutter: bool = True,
            label: str = "") -> str:
    """
    Cut, fuse, or intersect two meshes via a Boolean modifier. The general verb
    for keyholes, mortises, split-lid chests, half-barrels, drilled holes, etc.
    — position a cutter mesh where you want the operation, then call this.

    target:      the mesh that is modified and kept.
    cutter:      the mesh used as the operand (hidden afterward by default).
    op:          DIFFERENCE (default — subtract cutter from target) |
                 UNION (fuse) | INTERSECT (keep only the overlap).
    solver:      EXACT (default — robust) | FAST (legacy, brittle).
    apply:       True bakes the result into target's mesh immediately; False
                 (default) leaves the modifier live so you can move the cutter
                 and watch it update, then apply_modifiers later.
    hide_cutter: hide the cutter in viewport + render after the op (default True).

    To make a half-cylinder / arch (classic chest lid): add a cylinder, add a box
    spanning the lower half, then boolean(lid, box, op="DIFFERENCE").

    FRAGILITY: booleans dislike non-manifold meshes, coplanar overlapping faces,
    and un-applied non-uniform scale. If apply fails, run
    apply_transform(targets="<target>,<cutter>", scale=True) and retry, or
    solver="FAST". On apply failure the modifier is left in place to inspect.
    """
    result = call_blender("boolean", {
        "target": target, "cutter": cutter, "op": op, "solver": solver,
        "apply": apply, "hide_cutter": hide_cutter,
    }, label=label)
    if result.get("success"):
        state = "applied (baked)" if result.get("applied") else f"live modifier '{result.get('modifier')}'"
        main = (f"boolean {result['op']} '{result['cutter']}' → '{result['target']}' "
                f"[{result['solver']}]: {state} [{result.get('op_id','')}]")
        if result.get("apply_error"):
            main += f"\n⚠ apply failed: {result['apply_error']}\n  {result.get('hint','')}"
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def apply_modifiers(name: str = "") -> str:
    """
    Apply all modifiers on an object, collapsing them into the base mesh.
    name: object name — if omitted, applies to the active object.
    Required before export, boolean operations, or manual mesh editing on a modified object.
    Must be in Object Mode.
    """
    result = call_blender("apply_modifiers", {"name": name})
    if result.get("success"):
        applied = result.get("applied", [])
        main = (f"Applied {len(applied)} modifier(s) on '{result['object']}': {applied}"
                if applied else f"No modifiers on '{result['object']}'")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def convert_to_mesh(name: str = "") -> str:
    """
    Bake a non-mesh object (curve, text, metaball) into a real mesh — Object >
    Convert > Mesh. Evaluates the full result: modifiers, the curve's bevel, and
    any hooks all get baked into actual geometry.

    The delivery step for an R4 following rope/cable: it's a LIVE curve so it can
    stretch with the rig, but a curve isn't export geometry and can't take a
    textured material cleanly. Pose the rig, then convert_to_mesh("rope") bakes
    the posed, beveled, hook-deformed tube into a game-ready, texturable mesh in
    one call. Already-mesh objects are a no-op.

    name: object name — if omitted, the active object. Must be in Object Mode.
    """
    result = call_blender("convert_to_mesh", {"name": name})
    if not result.get("success"):
        return result.get("error", "failed")
    if not result.get("converted"):
        return f"'{result['object']}' is already a mesh — nothing to convert" + _status(result)
    return (f"Converted '{result['object']}' from {result['from_type']} → mesh "
            f"({result['vertices']} verts, {result['faces']} faces)" + _status(result))
