"""UV unwrap — the server half of SPEC-18 Phase 1 (closes gaps.md G152).

Flat helper(s) the `uv` verb dispatches to. Box-projection texturing (no UVs) stays
the default; reach for an unwrap only when texture grain must follow a curved surface.
This phase exposes the no-seam projections (smart / cube / cylinder / sphere); seam
marking + seam-driven methods and the deterministic `uv op=check` verdict are later.
"""

from server._core import mcp, call_blender, _status, _targets


@mcp.tool()
def uv_unwrap(target: str, method: str = "smart", angle_limit: float = 66.0,
              island_margin: float = 0.02, scale_to_bounds: bool = False,
              label: str = "") -> str:
    """Flatten a mesh's UVs with a parametric / auto projection — no seams needed.

    Box projection (`material` without space=uv) needs none of this and is the default;
    unwrap only when grain must follow a curved surface (a mug belly, a plate rim, wood
    edge grain). After unwrapping, feed the UV layer to a UV-projected material node graph.

    target:          object, group/collection, or 'a,b,c' — each mesh unwrapped
                     INDEPENDENTLY (UVs are per-mesh).
    method:          smart (default, hard-surface "just give me sane UVs") | cube (boxy
                     props) | cylinder (mugs, bottles, columns) | sphere (balls, domes).
    angle_limit:     [smart] degrees; split islands where faces bend past this (66 default).
    island_margin:   [smart] gap packed between islands, UV units (0.02 default).
    scale_to_bounds: stretch the result to fill the whole [0,1] square (default False).

    The unwrap is mechanical — it flattens; it does not judge where the seams land or
    whether the grain reads right (taste → render a checker for the human, SPEC-18 §6).
    """
    result = call_blender("uv_unwrap", {
        "target": _targets(target), "method": method, "angle_limit": angle_limit,
        "island_margin": island_margin, "scale_to_bounds": scale_to_bounds,
    }, label=label)
    if result.get("success"):
        parts = ", ".join(f"{u['name']} ({u['uv_layer']}, {u['faces']}f)"
                          for u in result.get("unwrapped", []))
        main = (f"unwrapped {result['count']} mesh(es) via {result['method']}: {parts} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)
