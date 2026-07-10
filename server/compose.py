"""SPEC-19 Phase 3 — server facade for the algebraic compose ops (extension/compose.py).

graft: SDF smooth-min union (the fillet radius is one number) → marching-tetrahedra mesh.
stitch: weld two boundary-sharing patches into one watertight quilt (matched sampling)."""

from server._core import call_blender


def graft(a="", b="", mode="smin", blend=0.0, resolution=0, name="", keep=False, label=""):
    """Merge two parts by smooth-min of their signed-distance fields — the filleted union the
    bridge/connect family can't do (supersedes gaps.md G153). The blend radius `k` is the ONE
    legible knob: the merge monster reduced to arithmetic. Marching-tetrahedra meshed (always
    watertight). a/b are two CLOSED mesh objects; the graft replaces them (keep=True to retain)."""
    m = (mode or "").strip().lower()
    if m in ("", "vert"):                         # `mode` shares the delete-op default; map it
        m = "smin"
    result = call_blender("graft", {
        "a": a, "b": b, "mode": m, "blend": blend,
        "resolution": resolution, "name": name, "keep": keep,
    })
    if not result.get("success"):
        return result.get("error", "graft failed")
    wt = "watertight ✓" if result.get("watertight") else "⚠ has open edges at the seam"
    grid = result.get("grid")
    grid_str = ("×".join(str(g) for g in grid) if grid else f"{result.get('resolution')}³")
    cell = result.get("cell_size")
    cell_str = f" @ {cell}m cells" if cell else ""
    body = (f"grafted '{a}' + '{b}' → '{result['object']}' "
            f"(smooth-min k={result.get('blend')}m, {grid_str} voxels{cell_str}): "
            f"{result.get('verts')} verts, {result.get('faces')} faces — {wt}")
    if result.get("removed"):
        body += f"\n  removed sources: {', '.join(result['removed'])}"
    for w in result.get("warnings", []):
        body += f"\n  ⚠ {w}"
    return body


def bud(host="", at=None, handle="", diameter=0.01, hang=None, neck=None,
        direction="down", solver="EXACT", label=""):
    """Grow a CLOSED teardrop mass fused to `host` at a point, preserving the host's
    identity (name, materials, modifiers) — the volume author graft can't be (new object,
    dropped materials/modifiers). A bead of icing dripping from a rim, a rivet, a drop."""
    params = {"host": host, "diameter": diameter, "direction": direction, "solver": solver}
    if isinstance(at, (list, tuple)) and len(at) == 3:
        params["at"] = list(at)
    if handle:
        params["handle"] = handle
    if hang is not None:
        params["hang"] = hang
    if neck is not None:
        params["neck"] = neck
    result = call_blender("bud", params, label=label)
    if not result.get("success"):
        return result.get("error", "bud failed")
    keep_id = ("identity kept ✓" if result.get("materials_preserved")
               and result.get("modifiers_preserved") else "⚠ identity changed")
    body = (f"budded a {result['diameter']}m bead (hang {result['hang']}m, neck "
            f"{result['neck']}m) onto '{result['host']}' — {keep_id}, host dims now "
            f"{result.get('dims_after')}, welded {result.get('welded_verts', 0)} verts")
    for w in result.get("notes", []):
        body += f"\n  ⚠ {w}"
    return body


def stitch(a="", b="", name="", keep=False, label=""):
    """Weld two surface patches that share a boundary into one watertight quilt: match the
    boundary sampling, then merge the shared rim → a C0 seam with no crack/T-junction (the
    discrete-connector gap §2). a/b are two mesh patches; result replaces them (keep=True)."""
    result = call_blender("stitch", {"a": a, "b": b, "name": name, "keep": keep})
    if not result.get("success"):
        return result.get("error", "stitch failed")
    wt = "watertight seam ✓" if result.get("seam_closed") else "⚠ seam still open"
    body = (f"stitched '{a}' + '{b}' → '{result['object']}' "
            f"({result.get('seam_verts')} seam verts welded, gap {result.get('seam_gap_mm')}mm): "
            f"{result.get('verts')} verts — {wt}")
    if result.get("removed"):
        body += f"\n  removed sources: {', '.join(result['removed'])}"
    for w in result.get("warnings", []):
        body += f"\n  ⚠ {w}"
    return body
