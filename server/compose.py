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
    body = (f"grafted '{a}' + '{b}' → '{result['object']}' "
            f"(smooth-min k={result.get('blend')}m, {result.get('resolution')}³ voxels): "
            f"{result.get('verts')} verts, {result.get('faces')} faces — {wt}")
    if result.get("removed"):
        body += f"\n  removed sources: {', '.join(result['removed'])}"
    for w in result.get("warnings", []):
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
