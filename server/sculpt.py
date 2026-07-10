from typing import Optional

from server._core import mcp, call_blender, _status


# All sculpt_* tools accept a world-space brush center (at_x/y/z) and radius in
# meters, plus a falloff curve. They work on the named target object whether or
# not it's currently active — no need to be in edit mode. If the mesh is too
# coarse to register the brush, pass subdivide=True to add density first.


def _sculpt_result(brush: str, result: dict) -> str:
    if result.get("success"):
        sub = result.get("subdivided_edges", 0)
        sub_note = f" (+{sub} edges subdivided)" if sub else ""
        verts = result.get("verts_affected", result.get("verts_per_pass", "?"))
        if "iterations" in result and "verts_per_pass" in result:
            head = f"{brush}: {result['iterations']} iterations × {verts} verts{sub_note}"
        else:
            head = f"{brush}: affected {verts} verts{sub_note}"
        if result.get("frame"):
            head += f" ({result['frame']})"
        if result.get("max_drop") is not None:
            head += f"  [{result.get('region', '')} drape, max drop {result['max_drop']}m, pin {result.get('pin')}]"
        warn = result.get("warning")
        if warn:
            head += f"\n  ⚠ {warn}"
        return head
    return result.get("error", "failed")


@mcp.tool()
def sculpt_grab(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                to_x: Optional[float] = None, to_y: Optional[float] = None,
                to_z: Optional[float] = None,
                out: float = 0.0, inward: float = 0.0,
                up: float = 0.0, down: float = 0.0, left: float = 0.0, right: float = 0.0,
                forward: float = 0.0, back: float = 0.0,
                falloff: str = "SMOOTH", subdivide: bool = False,
                detail: Optional[float] = None, connected: bool = False,
                label: str = "") -> str:
    """Pull a region of `target` by an offset. Verts at the brush center
    (at_x, at_y, at_z) move the full offset; verts at the radius edge don't move;
    everything between interpolates by falloff. Drag clay from one spot to another —
    bulge a cheekbone, pull a handle outward, lift a brow.

    Give the offset ONE of two ways:
      to_x/to_y/to_z          — a world-space destination point; offset = (to - at).
                                The coordinate ripcord (hand-compute the point).
      direction words (F3)    — the offset in METERS, which is the part that wants to
                                be local: out/inward (along the brushed region's average
                                normal), up/down/left/right/forward/back (world axes).
                                Composable, e.g. sculpt_grab(..., out=0.02, up=0.01).
    The result names the resolved 'out' direction in world-semantic words.

    falloff: SMOOTH | LINEAR | SPHERE | SHARP | ROOT | CONSTANT.
    subdivide: if the mesh is too coarse in the brush region, set True to locally
               subdivide edges before sculpting.
    """
    params = {
        "target": target, "at": [at_x, at_y, at_z],
        "radius": radius, "falloff": falloff, "subdivide": subdivide,
        "out": out, "inward": inward, "up": up, "down": down, "left": left,
        "right": right, "forward": forward, "back": back,
        "detail": detail, "connected": connected,
    }
    if to_x is not None and to_y is not None and to_z is not None:
        params["to"] = [to_x, to_y, to_z]
    result = call_blender("sculpt_grab", params, label=label)
    return _sculpt_result("grab", result) + _status(result)


@mcp.tool()
def sculpt_gravity(target: str, at_x: Optional[float] = None, at_y: Optional[float] = None,
                   at_z: Optional[float] = None, radius: Optional[float] = None,
                   strength: float = 0.02, pin: float = 0.25,
                   falloff: str = "SMOOTH", subdivide: bool = False,
                   detail: Optional[float] = None, connected: bool = False,
                   label: str = "") -> str:
    """Drape a region of `target` under GRAVITY — the lead region-parametric deformer.

    Pins the TOP of the region and lets the lower mass fall along world -Z, ramped by
    height (top frozen → bottom falls fully). The fullest point sinks and the lower
    pole elongates → a hanging / teardrop form by construction, not by a seeing hand.
    Use this instead of hand-grabbing a soft form into shape.

    Scope: pass at_x/at_y/at_z + radius to drape just a sphere (e.g. one breast);
    omit them to drape the WHOLE mesh.

    strength: metres the free (bottom) end falls (try 0.02).
    pin:      0..1 top fraction frozen as the attachment (default 0.25). pin=0 is a
              rigid slide (no sag); higher pin freezes more of the top.
    falloff:  radial falloff at the sphere edge (scoped mode). SMOOTH|LINEAR|…
    """
    params = {"target": target, "strength": strength, "pin": pin,
              "falloff": falloff, "subdivide": subdivide,
              "detail": detail, "connected": connected}
    if at_x is not None and at_y is not None and at_z is not None:
        params["at"] = [at_x, at_y, at_z]
        if radius is not None:
            params["radius"] = radius
    result = call_blender("sculpt_gravity", params, label=label)
    return _sculpt_result("gravity", result) + _status(result)


@mcp.tool()
def sculpt_inflate(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                   amount: float, falloff: str = "SMOOTH", subdivide: bool = False,
                   detail: Optional[float] = None, connected: bool = False,
                   label: str = "") -> str:
    """Push verts along their OWN normals — organic bulge or deflate.

    amount: meters along each vert's normal. Positive = outward (bulge),
            negative = inward (deflate). Differs from sculpt_draw because each
            vert moves along its own surface normal, so curved areas bulge
            outward in their natural direction. Over 2× the radius is refused
            before mutating (wrong-magnitude guard, G208).
    detail: target edge length (m) the footprint is densified to before the stroke
            (default radius/4) so the falloff can actually appear (G213).
    connected: scope geodesically along the surface, not a euclidean sphere — on a
            thin shell this walks ONE wall instead of grabbing both (G215).
    """
    result = call_blender("sculpt_inflate", {
        "target": target, "at": [at_x, at_y, at_z], "radius": radius,
        "amount": amount, "falloff": falloff, "subdivide": subdivide,
        "detail": detail, "connected": connected,
    }, label=label)
    return _sculpt_result("inflate", result) + _status(result)


@mcp.tool()
def sculpt_draw(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                amount: float, normal_x: float = 0.0, normal_y: float = 0.0,
                normal_z: float = 0.0, falloff: str = "SMOOTH",
                subdivide: bool = False, detail: Optional[float] = None,
                connected: bool = False, label: str = "") -> str:
    """Push verts along a SINGLE averaged normal — uniform-direction ridge or dent.

    amount: meters along the averaged normal. Signed.
    normal_x/y/z: optional world-space normal override. If all three are 0, the
                  average of vert normals in the region is used. Override when
                  the surface is curved enough that the average is unstable, or
                  when you want a specific direction (e.g. [0, 0, 1] to push up).
    """
    normal = [normal_x, normal_y, normal_z] if any([normal_x, normal_y, normal_z]) else None
    params = {"target": target, "at": [at_x, at_y, at_z], "radius": radius,
              "amount": amount, "falloff": falloff, "subdivide": subdivide,
              "detail": detail, "connected": connected}
    if normal is not None:
        params["normal"] = normal
    result = call_blender("sculpt_draw", params, label=label)
    return _sculpt_result("draw", result) + _status(result)


@mcp.tool()
def sculpt_smooth(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                  iterations: int = 1, falloff: str = "SMOOTH",
                  subdivide: bool = False, detail: Optional[float] = None,
                  connected: bool = False, label: str = "") -> str:
    """Laplacian relax — pull each vert toward the centroid of its neighbors.

    iterations: how many smoothing passes. More iterations = more relaxation.
                There's no `amount` parameter — strength is iterations × falloff.
    detail/connected: densify to a target edge length (G213) / scope geodesically (G215).
    """
    result = call_blender("sculpt_smooth", {
        "target": target, "at": [at_x, at_y, at_z], "radius": radius,
        "iterations": iterations, "falloff": falloff, "subdivide": subdivide,
        "detail": detail, "connected": connected,
    }, label=label)
    return _sculpt_result("smooth", result) + _status(result)


@mcp.tool()
def sculpt_crease(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                  amount: float, falloff: str = "SHARP", subdivide: bool = False,
                  detail: Optional[float] = None, connected: bool = False,
                  label: str = "") -> str:
    """Pull verts toward the brush center — sharp folds, valleys, seams.

    Default falloff is SHARP because the whole point is a tight fold; pass
    falloff='SMOOTH' for a softer crease.

    amount: meters of pull toward center. Positive = pull in (valley),
            negative = push out (ridge).
    """
    result = call_blender("sculpt_crease", {
        "target": target, "at": [at_x, at_y, at_z], "radius": radius,
        "amount": amount, "falloff": falloff, "subdivide": subdivide,
        "detail": detail, "connected": connected,
    }, label=label)
    return _sculpt_result("crease", result) + _status(result)


@mcp.tool()
def sculpt_pinch(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                 amount: float, falloff: str = "SMOOTH", subdivide: bool = False,
                 detail: Optional[float] = None, connected: bool = False,
                 label: str = "") -> str:
    """Pull verts radially inward in their TANGENT PLANE — tightens without raising.

    Unlike crease (which moves verts toward the center directly), pinch projects
    the toward-center direction onto each vert's tangent plane. The surface
    puckers without changing its average height — good for tightening features
    like lip corners, fabric folds, or pinching a sphere into a teardrop.

    amount: meters of in-plane pull. Positive = inward, negative = outward.
    """
    result = call_blender("sculpt_pinch", {
        "target": target, "at": [at_x, at_y, at_z], "radius": radius,
        "amount": amount, "falloff": falloff, "subdivide": subdivide,
        "detail": detail, "connected": connected,
    }, label=label)
    return _sculpt_result("pinch", result) + _status(result)


@mcp.tool()
def sculpt_flatten(target: str, at_x: float, at_y: float, at_z: float, radius: float,
                   amount: float = 1.0,
                   plane_normal_x: float = 0.0, plane_normal_y: float = 0.0,
                   plane_normal_z: float = 0.0,
                   falloff: str = "SMOOTH", subdivide: bool = False,
                   detail: Optional[float] = None, connected: bool = False,
                   label: str = "") -> str:
    """Project verts toward an average plane through the brush center — smooth out bumps.

    amount: 0..1 blend toward the plane (default 1.0 = fully flatten).
            Negative values push AWAY from the plane (amplify bumps).
    plane_normal_x/y/z: optional world-space plane normal override. If all three
                        are 0, the average of vert normals in the region is used.
                        Pass an override for "flatten against THIS plane"
                        (e.g. [0, 0, 1] to flatten against the ground plane).
    """
    plane = [plane_normal_x, plane_normal_y, plane_normal_z] \
        if any([plane_normal_x, plane_normal_y, plane_normal_z]) else None
    params = {"target": target, "at": [at_x, at_y, at_z], "radius": radius,
              "amount": amount, "falloff": falloff, "subdivide": subdivide,
              "detail": detail, "connected": connected}
    if plane is not None:
        params["plane_normal"] = plane
    result = call_blender("sculpt_flatten", params, label=label)
    return _sculpt_result("flatten", result) + _status(result)
