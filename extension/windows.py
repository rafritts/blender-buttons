"""SPEC-21 §6 — landmark LOD windows: the loop's eyes.

The server can never know what a mesh IS; it reports SALIENCE — islands,
protrusions, density anomalies, poles, open rims — as landmarks inside a
window, and the agent brings the semantics ("a humanoid's two top protrusions
are arms") and records them at claim time. One algorithm, one output shape,
applied recursively: the root window is the whole object; descending into a
landmark (or a bare position token) re-runs the same breakdown at that finer
scale. Zoom IS the scale picker — a body-scale scan can't see a nose; the
face-front window scans at its own scale and the nose is simply there.

The window stack lives HERE, server-side: it is the attention state that the
old stateless one-shot verbs forced the agent to re-serialize into coordinate
bands on every call (§6.0 root cause 1). Windows are invalidated lazily by a
topology signature; a stale window errors legibly and says how to re-open
(§6.6). Everything reported is coordinate-starved (§6.2): extents, areas,
counts, position-in-window tokens — world XYZ never crosses the wire.
"""

import math

import bpy
import mathutils
from mathutils import Vector

from .common import region_words

# ── module state: the attention ──────────────────────────────────────────────
_WINDOWS = {}       # id -> window dict
_STACK = []         # window ids, root first; last = current window
_COUNTER = [0]

# Curation: how many landmarks a window names before grouping the tail (§6.1:
# "5–9, salience-ranked; the tail is grouped, never dropped silently").
_MAX_LANDMARKS = 7
# Bottom-level threshold: at or below this many faces a window enumerates its
# faces (BFS rings, areas only — §6.2), and single-face descent unlocks verts.
_FACE_LIST_CAP = 40


def reset():
    """Drop all windows (used by tests / new_scene)."""
    _WINDOWS.clear()
    _STACK.clear()


def _sig(obj):
    me = obj.data
    return (len(me.vertices), len(me.polygons))


def _get_bm(obj):
    """A bmesh for reading. Returns (bm, owned) — free only when owned."""
    import bmesh
    if obj.mode == 'EDIT':
        return bmesh.from_edit_mesh(obj.data), False
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    return bm, True


def _fmt_len(m):
    if m < 0.01:
        return f"{m * 1000:.1f}mm"
    if m < 1.0:
        return f"{m * 100:.1f}cm"
    return f"{m:.2f}m"


def _fmt_area(m2):
    if m2 < 1e-4:
        return f"{m2 * 1e6:.1f}mm²"
    if m2 < 1.0:
        return f"{m2 * 1e4:.1f}cm²"
    return f"{m2:.2f}m²"


# ── geometry passes (all world-space, all O(window)) ─────────────────────────

def _face_data(obj, bm, face_ids):
    """Per-face world centroid + area for the window's faces, plus the window's
    world bbox and vert set. One pass; everything downstream reads from this."""
    mw = obj.matrix_world
    scale = mw.median_scale
    data = {}
    inf = float("inf")
    bb = [inf, inf, inf, -inf, -inf, -inf]
    verts = set()
    for fi in face_ids:
        f = bm.faces[fi]
        c = mw @ f.calc_center_median()
        data[fi] = (c, f.calc_area() * scale * scale)
        for v in f.verts:
            verts.add(v.index)
            co = mw @ v.co
            if co.x < bb[0]: bb[0] = co.x
            if co.y < bb[1]: bb[1] = co.y
            if co.z < bb[2]: bb[2] = co.z
            if co.x > bb[3]: bb[3] = co.x
            if co.y > bb[4]: bb[4] = co.y
            if co.z > bb[5]: bb[5] = co.z
    return data, tuple(bb), verts


def _face_components(bm, face_set):
    """Connected components of the window's faces (adjacency = shared edge)."""
    parent = {fi: fi for fi in face_set}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in bm.edges:
        prev = None
        for f in e.link_faces:
            if f.index in parent:
                if prev is not None:
                    ra, rb = find(prev), find(f.index)
                    if ra != rb:
                        parent[ra] = rb
                prev = f.index
    comps = {}
    for fi in face_set:
        comps.setdefault(find(fi), []).append(fi)
    return sorted(comps.values(), key=lambda fs: (-len(fs), fs[0]))


def _cluster(bm, seed_faces, face_set):
    """Group a face subset into adjacency clusters (within the window)."""
    seeds = set(seed_faces)
    clusters = []
    while seeds:
        fi = seeds.pop()
        blob = {fi}
        frontier = [fi]
        while frontier:
            cur = frontier.pop()
            for e in bm.faces[cur].edges:
                for nf in e.link_faces:
                    if nf.index in seeds:
                        seeds.discard(nf.index)
                        blob.add(nf.index)
                        frontier.append(nf.index)
        clusters.append(sorted(blob))
    return clusters


def _extent_of(fdata, faces):
    """World bbox diagonal + centroid of a face cluster (from _face_data)."""
    inf = float("inf")
    lo = [inf, inf, inf]
    hi = [-inf, -inf, -inf]
    acc = Vector((0, 0, 0))
    area = 0.0
    for fi in faces:
        c, a = fdata[fi]
        acc += c * a
        area += a
        for k in range(3):
            if c[k] < lo[k]: lo[k] = c[k]
            if c[k] > hi[k]: hi[k] = c[k]
    ext = math.sqrt(sum((hi[k] - lo[k]) ** 2 for k in range(3)))
    ctr = acc / area if area > 0 else Vector((0, 0, 0))
    return ext, ctr, area


def _boundary_loops_in(bm, face_set):
    """TRUE open-boundary loops (mesh edges with one face) touching the window.
    Returns a list of {verts, edges, faces, perimeter, centroid} dicts."""
    mw_edges = [e for e in bm.edges
                if len(e.link_faces) == 1 and e.link_faces[0].index in face_set]
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in mw_edges:
        a, b = e.verts[0].index, e.verts[1].index
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    loops = {}
    for e in mw_edges:
        loops.setdefault(find(e.verts[0].index), []).append(e)
    out = []
    for edges in loops.values():
        peri = sum(e.calc_length() for e in edges)
        ctr = Vector((0, 0, 0))
        vs = set()
        faces = set()
        for e in edges:
            for v in e.verts:
                if v.index not in vs:
                    vs.add(v.index)
                    ctr += v.co
            faces.add(e.link_faces[0].index)
        ctr /= max(1, len(vs))
        out.append({"verts": vs, "n_edges": len(edges), "perimeter": peri,
                    "centroid": ctr, "faces": sorted(faces)})
    return sorted(out, key=lambda d: -d["perimeter"])


def _symmetric_x(obj, bm):
    """Cheap bilateral check across the object's world X=0: sample verts, mirror,
    nearest-match. Root-window orientation info only."""
    mw = obj.matrix_world
    verts = bm.verts
    n = len(verts)
    if n < 8:
        return False
    kd = mathutils.kdtree.KDTree(n)
    xs = []
    for i, v in enumerate(verts):
        co = mw @ v.co
        kd.insert(co, i)
        xs.append(co.x)
    kd.balance()
    span = (max(xs) - min(xs)) or 1e-9
    tol = 0.01 * span
    step = max(1, n // 300)
    checked = matched = 0
    for i in range(0, n, step):
        co = mw @ verts[i].co
        if abs(co.x) < tol:
            continue
        checked += 1
        _, _, d = kd.find(Vector((-co.x, co.y, co.z)))
        if d is not None and d <= tol:
            matched += 1
    return checked >= 10 and matched / checked >= 0.95


# ── landmark generation: one algorithm, every scale ──────────────────────────

def _make_landmarks(obj, bm, face_set, fdata, bbox, vert_ids):
    """The salience pass (§6.1). Channels: island / protrusion / dense / pole /
    rim. Returns (ranked landmark dicts, tail description, tail_face_ids,
    shells_in_window)."""
    win_ext = math.sqrt((bbox[3] - bbox[0]) ** 2 + (bbox[4] - bbox[1]) ** 2
                        + (bbox[5] - bbox[2]) ** 2) or 1e-9
    total_area = sum(a for _, a in fdata.values()) or 1e-12
    raw = []

    # islands — a separate piece is the loudest possible fact about a window
    comps = _face_components(bm, face_set)
    if len(comps) > 1:
        for fs in comps:
            ext, ctr, area = _extent_of(fdata, fs)
            raw.append({"channel": "island", "faces": fs, "extent": ext,
                        "centroid": ctr, "area": area,
                        "score": 3.0 * math.sqrt(area / total_area)})

    # protrusions — radius outliers from the window's area-weighted centre
    if len(fdata) >= 12:
        ctr_all = Vector((0, 0, 0))
        for c, a in fdata.values():
            ctr_all += c * a
        ctr_all /= total_area
        radii = {fi: (c - ctr_all).length for fi, (c, a) in fdata.items()}
        vals = list(radii.values())
        mean = sum(vals) / len(vals)
        var = sum((r - mean) ** 2 for r in vals) / len(vals)
        thresh = mean + 1.3 * math.sqrt(var)
        outliers = [fi for fi, r in radii.items() if r > thresh]
        for cl in _cluster(bm, outliers, face_set):
            if len(cl) < 3:
                continue
            ext, ctr, area = _extent_of(fdata, cl)
            if ext < 0.06 * win_ext:
                continue
            raw.append({"channel": "protrusion", "faces": cl, "extent": ext,
                        "centroid": ctr, "area": area,
                        "score": 2.5 * math.sqrt(ext / win_ext)})

    # dense patches — face-area anomalies (concentration)
    areas = sorted(a for _, a in fdata.values())
    if len(areas) >= 20:
        median = areas[len(areas) // 2]
        small = [fi for fi, (_, a) in fdata.items() if a < 0.2 * median]
        for cl in _cluster(bm, small, face_set):
            if len(cl) < 5:
                continue
            ext, ctr, area = _extent_of(fdata, cl)
            raw.append({"channel": "dense", "faces": cl, "extent": ext,
                        "centroid": ctr, "area": area,
                        "score": 1.5 * math.sqrt(len(cl) / len(fdata))})

    # poles — anomalously-high-valence verts (a radial fan announces itself:
    # "shares 8 faces"). The threshold adapts to the mesh's REGULAR valence —
    # quads are regular at 4, triangulated meshes at 6 — so a tri mesh's grid
    # doesn't read as wall-to-wall poles while its true fans still do.
    valences = sorted(len(bm.verts[vi].link_edges)
                      for vi in list(vert_ids)[:2000])
    median_val = valences[len(valences) // 2] if valences else 4
    pole_min = max(6, median_val + 2)
    pole_faces = {}
    for vi in vert_ids:
        v = bm.verts[vi]
        val = len(v.link_edges)
        if val >= pole_min:
            fs = [f.index for f in v.link_faces if f.index in face_set]
            if len(fs) >= val - 1:
                pole_faces[vi] = (val, fs)
    for vi, (val, fs) in sorted(pole_faces.items())[:24]:
        ext, ctr, area = _extent_of(fdata, fs)
        raw.append({"channel": "pole", "faces": sorted(fs), "extent": ext,
                    "centroid": ctr, "area": area, "valence": val,
                    "score": 1.1 + 0.06 * val})

    # rims — true open-boundary loops
    rims = _boundary_loops_in(bm, face_set)
    for lp in rims[:16]:
        ctr_w = obj.matrix_world @ lp["centroid"]
        ext = lp["perimeter"] / math.pi          # ≈ diameter, an honest scale
        raw.append({"channel": "rim", "faces": lp["faces"], "extent": ext,
                    "centroid": ctr_w, "area": 0.0, "perimeter": lp["perimeter"],
                    "score": 1.6 * math.sqrt(min(1.0, ext / win_ext))})

    # cross-channel dedup, greedy by salience: a lower-scored landmark that mostly
    # overlaps an already-kept one of similar size is the same patch re-announced
    # through another lens (a pole's fan is also a dense cluster; a small island is
    # also a radius outlier). A SUB-feature of a much bigger landmark survives —
    # the 3× size guard keeps an arm inside the torso island reportable.
    raw.sort(key=lambda lm: -lm["score"])
    kept = []
    for lm in raw:
        fs = set(lm["faces"])
        if any(len(fs & k["_fs"]) >= 0.7 * len(fs) and len(k["_fs"]) <= 3 * len(fs)
               for k in kept):
            continue
        lm["_fs"] = fs
        kept.append(lm)
    for lm in kept:
        del lm["_fs"]

    named = kept[:_MAX_LANDMARKS]
    tail = kept[_MAX_LANDMARKS:]

    # position tokens, deduped within the window
    used = {}
    for k, lm in enumerate(named, 1):
        lm["id"] = f"L{k}"
        tok = region_words(bbox, lm["centroid"])
        if tok in used:
            used[tok] += 1
            tok = f"{tok}·{used[tok]}"
        else:
            used[tok] = 1
        lm["token"] = tok

    # mirror twins (only meaningful when the object is bilateral — root caches it)
    for i, a in enumerate(named):
        for b_ in named[i + 1:]:
            if a["channel"] != b_["channel"]:
                continue
            ca, cb = a["centroid"], b_["centroid"]
            if (abs(ca.x + cb.x) < 0.05 * win_ext
                    and abs(ca.y - cb.y) < 0.05 * win_ext
                    and abs(ca.z - cb.z) < 0.05 * win_ext
                    and abs(ca.x) > 0.02 * win_ext):
                a.setdefault("twin", b_["id"])
                b_.setdefault("twin", a["id"])

    # tail: grouped, never dropped silently — and still addressable as one unit
    tail_desc = None
    tail_faces = set()
    if tail:
        by_ch = {}
        for lm in tail:
            by_ch.setdefault(lm["channel"], []).append(lm)
            tail_faces.update(lm["faces"])
        bits = []
        for ch, lms in sorted(by_ch.items(), key=lambda kv: -len(kv[1])):
            sizes = sorted(len(lm["faces"]) for lm in lms)
            bits.append(f"{len(lms)} {ch}{'s' if len(lms) > 1 else ''} "
                        f"({sizes[0]}–{sizes[-1]} faces)")
        tail_desc = " · ".join(bits)

    return named, tail_desc, tail_faces, len(comps)


# ── window construction / bookkeeping ────────────────────────────────────────

def _new_window(obj, face_ids, parent_id, label):
    bm, owned = _get_bm(obj)
    try:
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        if face_ids is None:
            face_set = set(range(len(bm.faces)))
        else:
            face_set = set(face_ids)
        if not face_set:
            return None, "window would be empty (no faces in scope)"
        fdata, bbox, verts = _face_data(obj, bm, face_set)
        named, tail_desc, tail_faces, n_comps = _make_landmarks(
            obj, bm, face_set, fdata, bbox, verts)
        _COUNTER[0] += 1
        wid = f"w{_COUNTER[0]}"
        win = {
            "id": wid, "object": obj.name, "label": label,
            "face_ids": sorted(face_set), "sig": _sig(obj),
            "parent": parent_id, "bbox": bbox,
            "n_faces": len(face_set), "n_verts": len(verts),
            "shells_in_window": n_comps,
            "landmarks": named, "tail": tail_desc,
            "tail_face_ids": sorted(tail_faces),
            "root": face_ids is None,
        }
        if face_ids is None:
            win["symmetric_x"] = _symmetric_x(obj, bm)
        _WINDOWS[wid] = win
        return win, None
    finally:
        if owned:
            bm.free()


def _check_fresh(win):
    """§6.6 — lazy invalidation: a topology edit invalidates the window; the
    error is legible and says how to recover."""
    obj = bpy.data.objects.get(win["object"])
    if obj is None:
        return None, (f"window {win['id']} is stale — object '{win['object']}' "
                      f"no longer exists. look target=<obj> to open a new window.")
    if _sig(obj) != tuple(win["sig"]):
        v0, f0 = win["sig"]
        v1, f1 = _sig(obj)
        return None, (f"window {win['id']} is stale — topology changed since it was "
                      f"opened ({v0}→{v1} verts, {f0}→{f1} faces). Not your error: "
                      f"windows invalidate on topology edits. look target="
                      f"{win['object']} to re-open, then descend again.")
    return obj, None


def _grow_faces(bm, faces, within, rings=1):
    """Grow a face set by N adjacency rings, contained within the parent window."""
    cur = set(faces)
    for _ in range(rings):
        add = set()
        for fi in cur:
            for e in bm.faces[fi].edges:
                for nf in e.link_faces:
                    if nf.index in within and nf.index not in cur:
                        add.add(nf.index)
        if not add:
            break
        cur |= add
    return cur


_POS_WORDS = {"top", "bottom", "left", "right", "front", "back", "center"}


def _faces_in_region(fdata, bbox, token):
    """Spatial descent fallback: 'show me top right' with no landmark there —
    the window's faces whose centroid sits in that third of the window bbox."""
    words = [w for w in token.replace("·", "-").split("-") if w]
    if not words or not all(w in _POS_WORDS for w in words):
        return None
    x0, y0, z0, x1, y1, z1 = bbox
    dx, dy, dz = (x1 - x0) or 1e-9, (y1 - y0) or 1e-9, (z1 - z0) or 1e-9
    out = []
    for fi, (c, _a) in fdata.items():
        fx, fy, fz = (c.x - x0) / dx, (c.y - y0) / dy, (c.z - z0) / dz
        ok = True
        for w in words:
            if w == "top" and fz <= 0.66: ok = False
            elif w == "bottom" and fz >= 0.33: ok = False
            elif w == "right" and fx <= 0.66: ok = False
            elif w == "left" and fx >= 0.33: ok = False
            elif w == "back" and fy <= 0.66: ok = False
            elif w == "front" and fy >= 0.33: ok = False
            elif w == "center" and not (0.33 < fx < 0.66 and 0.33 < fy < 0.66
                                        and 0.33 < fz < 0.66): ok = False
            if not ok:
                break
        if ok:
            out.append(fi)
    return out


# ── presentation ─────────────────────────────────────────────────────────────

def _present(win):
    """The structured reply the server-side verb formats. Coordinate-starved:
    tokens, extents, areas, counts — no XYZ."""
    x0, y0, z0, x1, y1, z1 = win["bbox"]
    lms = []
    for lm in win["landmarks"]:
        d = {"id": lm["id"], "token": lm["token"], "channel": lm["channel"],
             "n_faces": len(lm["faces"]), "extent": _fmt_len(lm["extent"])}
        if lm["channel"] == "rim":
            d["perimeter"] = _fmt_len(lm["perimeter"])
        if lm["channel"] == "pole":
            d["valence"] = lm["valence"]
        if lm.get("twin"):
            d["twin"] = lm["twin"]
        lms.append(d)
    stack = []
    for wid in _STACK:
        w = _WINDOWS.get(wid)
        if w:
            stack.append(f"{wid}:{w['label']}")
    out = {
        "id": win["id"], "label": win["label"], "object": win["object"],
        "n_faces": win["n_faces"], "n_verts": win["n_verts"],
        "size": [_fmt_len(x1 - x0), _fmt_len(y1 - y0), _fmt_len(z1 - z0)],
        "shells_in_window": win["shells_in_window"],
        "landmarks": lms, "tail": win["tail"], "root": win["root"],
        "stack": stack,
        "bottom_level": win["n_faces"] <= _FACE_LIST_CAP,
    }
    if win["root"]:
        out["symmetric_x"] = win.get("symmetric_x", False)
    return out


# ── the tool ─────────────────────────────────────────────────────────────────

def look_window(params):
    """The look verb's engine. Modes:
      target=<obj>            → open the ROOT window (replaces the stack)
      at=<L#|token|tail>      → DESCEND within the current window (pushes)
      up=True                 → pop back to the parent window
      (nothing)               → re-describe the current window
    """
    target = (params.get("target") or "").strip()
    at = (params.get("at") or "").strip()
    up = bool(params.get("up"))

    if up:
        if len(_STACK) <= 1:
            return {"error": "already at the root window — look target=<obj> "
                             "opens a new root" if _STACK else
                             "no window open — look target=<obj> first"}
        _STACK.pop()
        win = _WINDOWS[_STACK[-1]]
        obj, err = _check_fresh(win)
        if err:
            return {"error": err}
        return {"success": True, "window": _present(win), "moved": "up"}

    if target and not at:
        obj = bpy.data.objects.get(target)
        if obj is None:
            meshes = [o.name for o in bpy.data.objects if o.type == 'MESH']
            return {"error": f"'{target}' not found. Meshes: {meshes}"}
        if obj.type != 'MESH':
            return {"error": f"'{target}' is a {obj.type}, not a mesh"}
        win, err = _new_window(obj, None, None, obj.name)
        if err:
            return {"error": err}
        _STACK.clear()
        _STACK.append(win["id"])
        return {"success": True, "window": _present(win), "moved": "root"}

    if not _STACK:
        return {"error": "no window open — look target=<obj> opens the root window"}
    cur = _WINDOWS[_STACK[-1]]
    obj, err = _check_fresh(cur)
    if err:
        return {"error": err}

    if not at:
        return {"success": True, "window": _present(cur), "moved": "none"}

    # descend: L# / position token / the grouped tail / spatial fallback
    bm, owned = _get_bm(obj)
    try:
        bm.faces.ensure_lookup_table()
        parent_faces = set(cur["face_ids"])
        chosen = None
        label = None
        atl = at.lower()
        for lm in cur["landmarks"]:
            if lm["id"].lower() == atl or lm["token"] == atl:
                chosen = set(lm["faces"])
                label = f"{cur['label']} ▸ {lm['id']}({lm['token']})"
                # one ring of context, contained in the parent window
                chosen = _grow_faces(bm, chosen, parent_faces, rings=1)
                break
        if chosen is None and atl in ("tail", "minor-islands") and cur["tail_face_ids"]:
            chosen = set(cur["tail_face_ids"])
            label = f"{cur['label']} ▸ tail"
        if chosen is None:
            fdata, _, _ = _face_data(obj, bm, parent_faces)
            region = _faces_in_region(fdata, cur["bbox"], atl)
            if region:
                chosen = set(region)
                label = f"{cur['label']} ▸ {atl}"
            elif region is not None:
                return {"error": f"no faces of window {cur['id']} sit in '{at}' — "
                                 f"try another region or a landmark id"}
        if chosen is None:
            opts = [f"{lm['id']}({lm['token']})" for lm in cur["landmarks"]]
            return {"error": f"'{at}' names no landmark or region of window "
                             f"{cur['id']}. Landmarks: {', '.join(opts) or '(none)'}; "
                             f"position words like 'top-right' also work"}
    finally:
        if owned:
            bm.free()

    win, err = _new_window(obj, sorted(chosen), cur["id"], label)
    if err:
        return {"error": err}
    _STACK.append(win["id"])
    return {"success": True, "window": _present(win), "moved": "down"}


def current_window():
    """The live window (fresh-checked), or (None, why). Phase-3 claiming reads
    the attention state through this."""
    if not _STACK:
        return None, "no window open"
    win = _WINDOWS[_STACK[-1]]
    _, err = _check_fresh(win)
    if err:
        return None, err
    return win, None


TOOLS = {
    "look_window": look_window,
}
