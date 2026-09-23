"""SPEC-21 — shared perception plumbing: shells, patches, and the one-line
"what got grabbed" narration behind every mutating select (G219/G220).

The principle (SPEC-21 §6.3): a count is a checksum with no reference value.
Every selection answers with legible ground truth — how many connected patches,
how big, where on the object, whether it is (or spans) a separate island/shell,
whether it touches an open rim. Component identity ("you grabbed exactly shell
#41 of 65") is the single most decision-relevant property a selection has on
real game meshes (nails, teeth, eyes, buttons) — its absence is what let a
correct grow no-op on a fingernail island get committed as a tool bug (G219).

Deliberately bpy-light: pure topology/geometry over a bmesh. No mode handling,
no ops — callers hand in an edit-mode object; later SPEC-21 phases (the `look`
verb's landmark windows) build on the same helpers.
"""

import bpy
from mathutils import Vector

from .common import region_words

# Above this vert count the whole-mesh shell scan is skipped (identity omitted)
# so narration can never become the slow path; counts/extent stay O(V) single-pass.
_SHELL_SCAN_CAP = 400_000
# Object-mode status repeats the live component selection (G237). Building a
# bmesh of a huge mesh on every status call is not worth the line.
_OBJECT_SEL_CAP = 100_000


def shells(bm):
    """The mesh's connected components ("shells"), deterministically ordered:
    largest first, ties broken by smallest contained vert index. Returns
    (ordered, vert_to_shell): `ordered` is a list of vert-index lists;
    `vert_to_shell` maps vert index → 1-based shell ordinal (so "#1" is always
    the biggest shell). O(V+E) union-find over all edges; loose verts are their
    own singleton shells (honest: a stray vert IS an island)."""
    bm.verts.ensure_lookup_table()
    n = len(bm.verts)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in bm.edges:
        a, b = e.verts[0].index, e.verts[1].index
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    comps = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    ordered = sorted(comps.values(), key=lambda vs: (-len(vs), vs[0]))
    v2s = {}
    for k, vs in enumerate(ordered, 1):
        for i in vs:
            v2s[i] = k
    return ordered, v2s


def _selection_patches(bm, sel_set):
    """Number of connected components WITHIN the selection (edges with both ends
    selected). '1 patch' = a coherent region; '4 patches' = the selection is
    scattered — the shape fact a bare count hides."""
    parent = {i: i for i in sel_set}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in bm.edges:
        a, b = e.verts[0].index, e.verts[1].index
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    return len({find(i) for i in sel_set})


def _fmt_len(m):
    """Compact length: mm below 1cm, cm below 1m, m above."""
    if m < 0.01:
        return f"{m * 1000:.1f}mm"
    if m < 1.0:
        return f"{m * 100:.1f}cm"
    return f"{m:.2f}m"


def _shell_identity(bm, sel_set, total):
    """The component-identity clause (G219): which shell(s) the selection lives
    on, and whether it saturates them. Returns (clause | None, saturated: bool).
    Single-shell meshes stay silent (the clause would be noise on every cube)."""
    if total > _SHELL_SCAN_CAP:
        return None, False
    ordered, v2s = shells(bm)
    n_shells = len(ordered)
    if n_shells <= 1:
        return None, len(sel_set) == total
    touched = sorted({v2s[i] for i in sel_set})
    saturated = all(all(i in sel_set for i in ordered[k - 1]) for k in touched)
    if len(touched) == 1:
        k = touched[0]
        size = len(ordered[k - 1])
        if saturated:
            return (f"= exactly shell #{k} of {n_shells} — its own island, "
                    f"all {size} verts"), True
        return f"within shell #{k} of {n_shells} ({len(sel_set)} of {size} verts)", False
    ks = ", ".join(f"#{k}" for k in touched[:4]) + ("…" if len(touched) > 4 else "")
    sat = " — all saturated" if saturated else ""
    return f"spans {len(touched)} of {n_shells} shells ({ks}){sat}", saturated


def describe_selection(obj):
    """The G220 narration: one line of legible ground truth about the live
    component selection. Returns a dict with `line` (the sentence) plus the
    structured fields, or None when obj isn't a mesh (or, in object mode, the
    mesh is too large to narrate on the status path).

    Edit mode reads the edit bmesh. Object mode reads the selection stored on
    the mesh — select ops exit edit mode before the status block is built, and
    that selection is still what the next grab will move (G237)."""
    import bmesh
    if obj is None or getattr(obj, "type", None) != 'MESH' or obj.data is None:
        return None
    owned = False
    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
    else:
        if len(obj.data.vertices) > _OBJECT_SEL_CAP:
            return None
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        owned = True
    try:
        return _narrate_selection(obj, bm)
    finally:
        if owned:
            bm.free()


def _narrate_selection(obj, bm):
    bm.verts.ensure_lookup_table()
    mw = obj.matrix_world
    total = len(bm.verts)
    if total == 0:
        return {"line": "sel: (mesh has no verts)", "selected": 0, "total": 0}

    # One pass over all verts: world coords for the object bbox (fresh — the
    # cached bound_box can lag an edit) and the selected subset's coords.
    sel_cos = []
    sel_set = set()
    inf = float("inf")
    ox0 = oy0 = oz0 = inf
    ox1 = oy1 = oz1 = -inf
    for v in bm.verts:
        co = mw @ v.co
        if co.x < ox0: ox0 = co.x
        if co.x > ox1: ox1 = co.x
        if co.y < oy0: oy0 = co.y
        if co.y > oy1: oy1 = co.y
        if co.z < oz0: oz0 = co.z
        if co.z > oz1: oz1 = co.z
        if v.select:
            sel_set.add(v.index)
            sel_cos.append(co)

    n = len(sel_set)
    if n == 0:
        return {"line": f"sel: EMPTY — 0 of {total} verts", "selected": 0,
                "total": total}
    if n == total:
        line = f"sel: ALL {total} verts — the whole mesh"
        return {"line": line, "selected": n, "total": total, "whole_mesh": True}

    n_faces = sum(1 for f in bm.faces if f.select)
    patches = _selection_patches(bm, sel_set)

    xs = [c.x for c in sel_cos]
    ys = [c.y for c in sel_cos]
    zs = [c.z for c in sel_cos]
    ext = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    centroid = Vector((sum(xs) / n, sum(ys) / n, sum(zs) / n))
    where = region_words((ox0, oy0, oz0, ox1, oy1, oz1), centroid)

    # An open rim under the selection changes what grow/extrude/bridge will do.
    on_rim = any(len(e.link_faces) == 1
                 and (e.verts[0].index in sel_set or e.verts[1].index in sel_set)
                 for e in bm.edges)

    identity, saturated = _shell_identity(bm, sel_set, total)

    patch_word = "1 patch" if patches == 1 else f"{patches} patches"
    size = "×".join(_fmt_len(e) for e in ext)
    bits = [f"sel: {n} verts"]
    if n_faces:
        bits[0] += f" / {n_faces} faces"
    bits.append(f"— {patch_word}, {size} at {where} of {obj.name}")
    if identity:
        bits.append(f"; {identity}")
    if on_rim:
        bits.append("; touches an open rim")
    return {"line": " ".join(bits[:2]) + "".join(bits[2:]),
            "selected": n, "total": total, "faces": n_faces, "patches": patches,
            "extent_m": [round(e, 5) for e in ext], "position": where,
            "identity": identity, "saturated": saturated, "open_rim": on_rim}


def expansion_noop_reason(bm, direction="GROW"):
    """G219 — WHY an expansion op (grow/shrink/flood) added or removed nothing.
    A correct no-op, a real malfunction, and a wrong-store fantasy must never
    read identically; this names the mechanical reason when there is one."""
    bm.verts.ensure_lookup_table()
    sel = {v.index for v in bm.verts if v.select}
    total = len(bm.verts)
    if not sel:
        return "nothing is selected — the op needs a seed selection"
    if len(sel) == total:
        return "the whole mesh is already selected"
    if total <= _SHELL_SCAN_CAP:
        ordered, v2s = shells(bm)
        n_shells = len(ordered)
        touched = sorted({v2s[i] for i in sel})
        if all(all(i in sel for i in ordered[k - 1]) for k in touched):
            ks = ", ".join(f"#{k}" for k in touched[:4]) + ("…" if len(touched) > 4 else "")
            size = sum(len(ordered[k - 1]) for k in touched)
            if direction == "SHRINK":
                return (f"the selection is {len(touched)} complete island(s) "
                        f"({ks} of {n_shells} shells, {size} verts) — there is no "
                        f"selection rim to peel, so Select Less removes nothing")
            return (f"the selection is saturated: it already fills {len(touched)} "
                    f"whole island(s) ({ks} of this mesh's {n_shells} separate "
                    f"shells, {size} verts) and expansion cannot cross between "
                    f"shells. Correct no-op, not a malfunction — to reach other "
                    f"geometry, seed on another shell (select op=pick / in_sphere "
                    f"/ by_axis)")
    return ("no reachable neighbours changed state — if this is surprising, "
            "check the component mode and whether the region is walled off")
