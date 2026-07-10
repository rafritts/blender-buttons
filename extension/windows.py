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
# Offer curation (§6.3): how many candidates a window offers before the coverage
# line reports the rest as segmented-but-not-offered. Anti-flooding, not silence.
_MAX_CANDIDATES = 12
_KIND_CAPS = {"region": 8, "loop": 4, "material": 4, "vgroup": 4}
# Crease threshold for the region segmenter — matches flood_to_crease's default,
# so an offered region IS what a flood from inside it would grab.
_CREASE_DEG = 25.0


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


def _fmt_delta(m):
    """Signed length for local-frame offsets; sub-report-precision reads as 0."""
    if abs(m) < 5e-5:
        return "0"
    return ("+" if m > 0 else "−") + _fmt_len(abs(m))


def _normal_token(n):
    """A face normal as a world-axis word ('+Z', '−X leaning +Y') — which way
    the face points, without shipping the vector."""
    axes = "XYZ"
    order = sorted(range(3), key=lambda i: -abs(n[i]))
    a = order[0]
    tok = ("+" if n[a] >= 0 else "−") + axes[a]
    if abs(n[a]) >= 0.92:
        return tok
    b = order[1]
    return f"{tok} leaning {'+' if n[b] >= 0 else '−'}{axes[b]}"


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


def _pair_twins(items, kind_key, win_ext):
    """Mark mirror twins across the object's X: same kind, centroids mirrored
    within 5% of the window extent, off the midline. Pairing is EXCLUSIVE and
    mutual — an already-twinned item never re-pairs, so no A→C / B→C chains."""
    for i, a in enumerate(items):
        if a.get("twin"):
            continue
        for b_ in items[i + 1:]:
            if b_.get("twin") or a[kind_key] != b_[kind_key]:
                continue
            ca, cb = a["centroid"], b_["centroid"]
            if (abs(ca.x + cb.x) < 0.05 * win_ext
                    and abs(ca.y - cb.y) < 0.05 * win_ext
                    and abs(ca.z - cb.z) < 0.05 * win_ext
                    and abs(ca.x) > 0.02 * win_ext):
                a["twin"] = b_["id"]
                b_["twin"] = a["id"]
                break


# ── candidate generation: selections offer themselves (§6.3) ─────────────────

def _crease_regions(bm, face_set, angle_deg=_CREASE_DEG):
    """Crease-bounded flood regions: partition the window's faces into patches
    whose interior edges are all smooth (dihedral < angle) and manifold. Each
    region is exactly what flood_to_crease would grab from a seed inside it —
    the offer pre-runs the segmenter so the agent picks from a list instead of
    hunting seeds."""
    thresh = math.radians(angle_deg)
    parent = {fi: fi for fi in face_set}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2:            # boundary / non-manifold = barrier
            continue
        a, b = lf[0].index, lf[1].index
        if a not in parent or b not in parent:
            continue
        try:
            if e.calc_face_angle() >= thresh:   # crease = barrier
                continue
        except ValueError:
            continue                # degenerate edge = barrier
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    comps = {}
    for fi in face_set:
        comps.setdefault(find(fi), []).append(fi)
    return sorted(comps.values(), key=lambda fs: (-len(fs), fs[0]))


def _make_candidates(obj, bm, face_set, fdata, bbox, comps, landmarks):
    """Pre-run the cheap segmenters over the window and offer the results as
    claimable candidates (§6.3): islands (saturating grow per shell), crease-
    bounded flood regions, protrusion cuts, boundary loops, material/vgroup
    patches. Ephemeral — they live on the window, discarded with it. Returns
    (offered candidate dicts, coverage dict). Verts are the claim payload;
    faces feed the coverage-honesty line."""
    win_ext = math.sqrt((bbox[3] - bbox[0]) ** 2 + (bbox[4] - bbox[1]) ** 2
                        + (bbox[5] - bbox[2]) ** 2) or 1e-9
    total_area = sum(a for _, a in fdata.values()) or 1e-12
    whole = len(face_set)
    raw = []

    # islands — one candidate per shell (the autorun "click + Ctrl+Numpad+ to
    # saturation"). A single-shell window offers nothing here: the window itself
    # is that region.
    if len(comps) > 1:
        for fs in comps:
            raw.append({"kind": "island", "faces": fs})

    # crease-bounded flood regions — skip a lone region (== the whole window).
    # Facet shards: when a mesh's faceting angle exceeds the crease threshold,
    # every facet reads as its own "region" — honest, but offering single faces
    # among real multi-face regions is anchoring noise. 1-face regions survive
    # only when the segmentation is ALL single faces (a plain cube's six sides
    # are 1-face regions, and they ARE the offer).
    regions = _crease_regions(bm, face_set)
    if len(regions) > 1:
        if len(regions[0]) > 1:
            regions = [fs for fs in regions if len(fs) > 1]
        for fs in regions[:_KIND_CAPS["region"]]:
            raw.append({"kind": "region", "faces": fs})

    # protrusion cuts — the landmark pass already clustered them
    for lm in landmarks:
        if lm["channel"] == "protrusion":
            raw.append({"kind": "protrusion", "faces": list(lm["faces"])})

    # boundary loops — the claim payload is the LOOP VERTS (a ring, ready for
    # bridge/extrude); the adjacent faces stand in for coverage accounting. The
    # centroid is the RING's, not its faces' — a one-quad-tall tube's wall faces
    # touch both rims, which would smear both loops onto the same centre.
    mw = obj.matrix_world
    for lp in _boundary_loops_in(bm, face_set)[:_KIND_CAPS["loop"]]:
        raw.append({"kind": "loop", "faces": lp["faces"],
                    "verts": sorted(lp["verts"]), "perimeter": lp["perimeter"],
                    "centroid_w": mw @ lp["centroid"]})

    # material patches — the faces of each slot present in the window. For fused
    # garments the material IS the part's handle (select op=material rationale).
    if len(obj.material_slots) > 1:
        by_mat = {}
        for fi in face_set:
            by_mat.setdefault(bm.faces[fi].material_index, []).append(fi)
        if len(by_mat) > 1:
            for mi, fs in sorted(by_mat.items(),
                                 key=lambda kv: (-len(kv[1]), kv[0]))[:_KIND_CAPS["material"]]:
                slot = obj.material_slots[mi] if mi < len(obj.material_slots) else None
                label = slot.material.name if (slot and slot.material) else f"slot {mi}"
                raw.append({"kind": "material", "faces": fs, "label": label})

    # vgroup patches — non-handle vertex groups with whole faces in the window
    # (vert-only smears stay reachable via select op=group; a patch offer means
    # "this is a coherent face region"). HANDLE_ groups are already claimed.
    from .handles import VGROUP_PREFIX
    real_groups = {vg.index: vg.name for vg in obj.vertex_groups
                   if not vg.name.startswith(VGROUP_PREFIX)}
    if real_groups:
        try:
            deform = bm.verts.layers.deform.active
        except Exception:
            deform = None
        if deform is not None:
            vert_groups = {}                       # vert index -> {group indices}
            group_verts = {}                       # group index -> {vert indices}
            for fi in face_set:
                for v in bm.faces[fi].verts:
                    if v.index in vert_groups:
                        continue
                    gis = {gi for gi, w in v[deform].items()
                           if w > 0.0 and gi in real_groups}
                    vert_groups[v.index] = gis
                    for gi in gis:
                        group_verts.setdefault(gi, set()).add(v.index)
            faces_by_group = {}
            for fi in face_set:
                vs = bm.faces[fi].verts
                common = set(vert_groups.get(vs[0].index, ()))
                for v in vs[1:]:
                    if not common:
                        break
                    common &= vert_groups.get(v.index, set())
                for gi in common:
                    faces_by_group.setdefault(gi, []).append(fi)
            for gi, fs in sorted(faces_by_group.items(),
                                 key=lambda kv: (-len(kv[1]), kv[0]))[:_KIND_CAPS["vgroup"]]:
                raw.append({"kind": "vgroup", "faces": fs,
                            "label": real_groups[gi],
                            "verts": sorted(group_verts.get(gi, ()))})

    # drop whole-window echoes; fill verts; measure
    kept = []
    for c in raw:
        if len(c["faces"]) >= whole:
            continue
        if not c["faces"]:
            continue
        if "verts" not in c:
            vs = set()
            for fi in c["faces"]:
                vs.update(v.index for v in bm.faces[fi].verts)
            c["verts"] = sorted(vs)
        ext, ctr, area = _extent_of(fdata, c["faces"])
        if "centroid_w" in c:
            ctr = c.pop("centroid_w")
            ext = c["perimeter"] / math.pi     # ≈ diameter — the rim's own scale
        c.update(extent=ext, centroid=ctr, area=area)
        kept.append(c)

    # dedup near-identical face sets across generators, keeping the higher-
    # priority kind (an island that is also one flood region, a material patch
    # that is exactly a side): both ways ≥90% overlap = the same patch offered
    # twice. Loops always survive — their claim payload (the ring) is different
    # even when their faces match a region's.
    prio = {"island": 0, "protrusion": 1, "region": 2, "loop": 3,
            "material": 4, "vgroup": 5}
    kept.sort(key=lambda c: (prio[c["kind"]], -c["area"], c["faces"][0]))
    offered = []
    for c in kept:
        fs = set(c["faces"])
        if c["kind"] != "loop" and any(
                k["kind"] != "loop"
                and len(fs & k["_fs"]) >= 0.9 * len(fs)
                and len(fs & k["_fs"]) >= 0.9 * len(k["_fs"])
                for k in offered):
            continue
        c["_fs"] = fs
        offered.append(c)
    dropped = max(0, len(offered) - _MAX_CANDIDATES)
    offered = offered[:_MAX_CANDIDATES]
    for c in offered:
        del c["_fs"]

    # ids + position tokens (deduped like landmarks') + mirror twins
    used = {}
    for k, c in enumerate(offered, 1):
        c["id"] = f"c{k}"
        tok = region_words(bbox, c["centroid"])
        if tok in used:
            used[tok] += 1
            tok = f"{tok}·{used[tok]}"
        else:
            used[tok] = 1
        c["token"] = tok
    _pair_twins(offered, "kind", win_ext)

    # coverage honesty (anti-anchoring): what fraction of the window the offer
    # actually reaches — by face count AND by area (a big flat floor and a dense
    # detail patch weigh differently; report both, anchor to neither).
    covered = set()
    for c in offered:
        covered.update(c["faces"])
    covered &= face_set
    coverage = {
        "n": len(offered),
        "face_pct": round(100.0 * len(covered) / whole) if whole else 0,
        "area_pct": round(100.0 * sum(fdata[fi][1] for fi in covered) / total_area),
        "dropped": dropped,
    }
    return offered, coverage


# ── landmark generation: one algorithm, every scale ──────────────────────────

def _make_landmarks(obj, bm, face_set, fdata, bbox, vert_ids, comps):
    """The salience pass (§6.1). Channels: island / protrusion / dense / pole /
    rim. Returns (ranked landmark dicts, tail description, tail_face_ids,
    shells_in_window)."""
    win_ext = math.sqrt((bbox[3] - bbox[0]) ** 2 + (bbox[4] - bbox[1]) ** 2
                        + (bbox[5] - bbox[2]) ** 2) or 1e-9
    total_area = sum(a for _, a in fdata.values()) or 1e-12
    raw = []

    # islands — a separate piece is the loudest possible fact about a window
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
    _pair_twins(named, "channel", win_ext)

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


# ── coordinate starvation: faces as the currency (§6.2) ─────────────────────

def _face_rings(bm, face_set, fdata):
    """Bottom-level face enumeration: BFS rings out from the window-centre face
    (the face nearest the area-weighted centroid) — the order grow walks and an
    eye scans. Non-disk patches need nothing special (BFS distance is defined
    on any face-adjacency graph); a multi-shell window restarts BFS per shell
    at the unvisited face nearest the window centre, rings renumbering with it.
    Returns shells → rings → [(face id, area)]."""
    total_area = sum(a for _, a in fdata.values()) or 1e-12
    ctr = Vector((0, 0, 0))
    for c, a in fdata.values():
        ctr += c * a
    ctr /= total_area
    unvisited = set(face_set)
    shells = []
    while unvisited:
        seed = min(unvisited, key=lambda fi: (fdata[fi][0] - ctr).length)
        unvisited.discard(seed)
        cur = {seed}
        rings = []
        while cur:
            rings.append([(fi, fdata[fi][1]) for fi in sorted(cur)])
            nxt = set()
            for fi in cur:
                for e in bm.faces[fi].edges:
                    for nf in e.link_faces:
                        if nf.index in unvisited:
                            unvisited.discard(nf.index)
                            nxt.add(nf.index)
            cur = nxt
        shells.append(rings)
    return shells


def _face_view_data(obj, bm, fi):
    """The single-face vert view (§6.2) — the ONLY place vert coordinates
    appear, and only in the face's local frame: origin = face centre, axes =
    world. Each vert carries its face-incidence count (the whole mesh's, not
    the window's) — a pole announces itself as 'shares 8 faces'. Edges come
    as lengths, in loop order. Returns (view dict, world bbox)."""
    f = bm.faces[fi]
    mw = obj.matrix_world
    scale = mw.median_scale
    ctr_w = mw @ f.calc_center_median()
    nrm = mw.to_3x3() @ f.normal
    if nrm.length > 1e-12:
        nrm.normalize()
    inf = float("inf")
    bb = [inf, inf, inf, -inf, -inf, -inf]
    verts = []
    edges = []
    for l in f.loops:
        v = l.vert
        co = mw @ v.co
        for k in range(3):
            if co[k] < bb[k]: bb[k] = co[k]
            if co[k] > bb[k + 3]: bb[k + 3] = co[k]
        d = co - ctr_w
        verts.append({"i": v.index, "d": (d.x, d.y, d.z),
                      "shares": len(v.link_faces)})
        nv = l.link_loop_next.vert
        edges.append((v.index, nv.index,
                      ((mw @ v.co) - (mw @ nv.co)).length))
    return ({"face": fi, "area": f.calc_area() * scale * scale,
             "normal": (nrm.x, nrm.y, nrm.z), "verts": verts, "edges": edges},
            tuple(bb))


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
        comps = _face_components(bm, face_set)
        named, tail_desc, tail_faces, n_comps = _make_landmarks(
            obj, bm, face_set, fdata, bbox, verts, comps)
        candidates, coverage = _make_candidates(
            obj, bm, face_set, fdata, bbox, comps, named)
        face_rings = (_face_rings(bm, face_set, fdata)
                      if len(face_set) <= _FACE_LIST_CAP else None)
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
            "candidates": candidates, "coverage": coverage,
            "face_rings": face_rings,
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
    tokens, extents, areas, counts — no XYZ, except the single-face vert view
    (§6.2), where coords appear in the face's LOCAL frame only."""
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
    cands = []
    for c in win.get("candidates", ()):
        d = {"id": c["id"], "kind": c["kind"], "token": c["token"],
             "n_faces": len(c["faces"]), "n_verts": len(c["verts"]),
             "extent": _fmt_len(c["extent"])}
        if c.get("label"):
            d["label"] = c["label"]
        if c.get("perimeter"):
            d["perimeter"] = _fmt_len(c["perimeter"])
        if c.get("twin"):
            d["twin"] = c["twin"]
        cands.append(d)
    out = {
        "id": win["id"], "label": win["label"], "object": win["object"],
        "n_faces": win["n_faces"], "n_verts": win["n_verts"],
        "size": [_fmt_len(x1 - x0), _fmt_len(y1 - y0), _fmt_len(z1 - z0)],
        "shells_in_window": win["shells_in_window"],
        "landmarks": lms, "tail": win["tail"], "root": win["root"],
        "candidates": cands,
        "stack": stack,
        "bottom_level": win["n_faces"] <= _FACE_LIST_CAP,
    }
    cov = win.get("coverage")
    if cands and cov:
        line = (f"{cov['n']} candidate{'s cover' if cov['n'] != 1 else ' covers'} "
                f"{cov['face_pct']}% of this window's faces ({cov['area_pct']}% "
                f"of its area) — {100 - cov['face_pct']}% unoffered")
        if cov.get("dropped"):
            line += (f"; {cov['dropped']} more segmented but not offered "
                     f"(cap {_MAX_CANDIDATES})")
        out["coverage"] = line
    elif cov is not None:
        out["coverage"] = ("no candidates — the window segments into nothing at "
                           "this scale; select by hand (op=flood / by_axis / "
                           "pick + grow)")
    fv = win.get("face_view")
    if fv:
        out["face_view"] = {
            "face": f"f{fv['face']}",
            "area": _fmt_area(fv["area"]),
            "normal": _normal_token(fv["normal"]),
            "verts": [{"id": f"v{v['i']}",
                       "d": [round(x, 5) for x in v["d"]],
                       "at": f"Δ({_fmt_delta(v['d'][0])}, {_fmt_delta(v['d'][1])}, "
                             f"{_fmt_delta(v['d'][2])})",
                       "shares": v["shares"]} for v in fv["verts"]],
            "edges": [f"v{a}–v{b} {_fmt_len(ln)}" for a, b, ln in fv["edges"]],
        }
    fr = win.get("face_rings")
    if fr and not fv:
        # pre-composed ring lines: a ring of near-uniform areas (within 10% of
        # the mean) compresses to "f8 f11 f13 f17  ≈2.1mm² each"
        ring_lines = []
        multi = len(fr) > 1
        for si, rings in enumerate(fr, 1):
            for ri, faces in enumerate(rings):
                prefix = f"shell {si} · " if multi else ""
                if len(faces) > 1:
                    areas = [a for _, a in faces]
                    mean = sum(areas) / len(areas)
                    if all(abs(a - mean) <= 0.1 * mean for a in areas):
                        ids = " ".join(f"f{fid}" for fid, _ in faces)
                        body = f"{ids}  ≈{_fmt_area(mean)} each"
                    else:
                        body = " · ".join(f"f{fid} {_fmt_area(a)}"
                                          for fid, a in faces)
                else:
                    fid, a = faces[0]
                    body = f"f{fid} {_fmt_area(a)}"
                ring_lines.append(f"{prefix}ring {ri}: {body}")
        out["face_rings"] = ring_lines
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

    # descend: f<id> / L# / position token / the grouped tail / spatial fallback
    bm, owned = _get_bm(obj)
    try:
        bm.faces.ensure_lookup_table()
        parent_faces = set(cur["face_ids"])
        chosen = None
        label = None
        atl = at.lower()
        # single-face vert view (§6.2): f<id> from the ring enumeration
        if atl.startswith("f") and atl[1:].isdigit():
            fi = int(atl[1:])
            if fi not in parent_faces:
                return {"error": f"f{fi} is not a face of window {cur['id']} "
                                 f"({cur['n_faces']} faces). Face ids come from "
                                 f"the window's ring enumeration — bottom-level "
                                 f"windows (≤{_FACE_LIST_CAP} faces) list them; "
                                 f"descend until the rings appear."}
            face_view, fv_bbox = _face_view_data(obj, bm, fi)
            _COUNTER[0] += 1
            wid = f"w{_COUNTER[0]}"
            win = {
                "id": wid, "object": obj.name,
                "label": f"{cur['label']} ▸ f{fi}",
                "face_ids": [fi], "sig": _sig(obj),
                "parent": cur["id"], "bbox": fv_bbox,
                "n_faces": 1, "n_verts": len(face_view["verts"]),
                "shells_in_window": 1,
                "landmarks": [], "tail": None, "tail_face_ids": [],
                "candidates": [], "coverage": None, "face_rings": None,
                "root": False, "face_view": face_view,
            }
            _WINDOWS[wid] = win
            _STACK.append(wid)
            return {"success": True, "window": _present(win), "moved": "down"}
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


# ── claiming: where semantics enters the system (§6.3) ───────────────────────

def _candidate_by_id(win, cid):
    if win is None:
        return None
    return next((c for c in win.get("candidates", ()) if c["id"] == cid), None)


def _offer_menu(win):
    ids = ", ".join(f"{c['id']}({c['kind']})" for c in win.get("candidates", ()))
    return ids or "(none — this window segments into nothing; select by hand)"


def _operand_verts(win, obj, name):
    """Resolve an add=/subtract= operand to a vert-index set: a candidate id of
    the CURRENT window (c3), else a handle / vertex-group name substring (the
    same matching pick's within= uses — minted handles' backing vgroups match).
    Returns (verts, error)."""
    nm = name.strip()
    if len(nm) > 1 and nm[0] in "cC" and nm[1:].isdigit():
        cand = _candidate_by_id(win, nm.lower())
        if cand is not None:
            return set(cand["verts"]), None
        if win is not None:
            return None, (f"'{nm}' names no candidate of window {win['id']}. "
                          f"Offered: {_offer_menu(win)}")
        return None, (f"'{nm}' looks like a candidate id but no window is open "
                      f"— look target=<obj> first, or name a handle/vgroup")
    needle = nm.lower()
    matched = [vg for vg in obj.vertex_groups if needle in vg.name.lower()]
    if not matched:
        return None, (f"'{nm}' matches no candidate id, handle, or vertex group "
                      f"on {obj.name}. Groups ({len(obj.vertex_groups)}): "
                      f"{[vg.name for vg in obj.vertex_groups]}")
    gidx = {vg.index for vg in matched}
    verts = {v.index for v in obj.data.vertices
             if any(g.group in gidx and g.weight > 0.0 for g in v.groups)}
    if not verts:
        return None, (f"'{nm}' matched group(s) "
                      f"{[vg.name for vg in matched]} but they hold no verts")
    return verts, None


def claim_candidate(params):
    """§6.3 — claim an offered candidate (and/or do region algebra), selecting
    the result; `as=<name>` mints it as a vgroup-backed handle — THE moment the
    agent's semantics ("that protrusion is the left arm") enters the scene as a
    durable fact. Omitting `as` selects without minting; `as` naming an existing
    handle re-points it (regions assemble across windows). add=/subtract= union
    or remove candidate ids / handle / vgroup names from the working set."""
    import bmesh
    from . import handles as _handles
    from . import perception
    from .state import push_undo

    cid = (params.get("candidate") or "").strip().lower()
    name = (params.get("as") or "").strip()
    adds = [s.strip() for s in (params.get("add") or "").split(",") if s.strip()]
    subs = [s.strip() for s in (params.get("subtract") or "").split(",") if s.strip()]

    win, werr = current_window()
    if cid and win is None:
        return {"error": f"claim candidate={cid} needs an open window — {werr}. "
                         f"look target=<obj> first (the look reply offers the "
                         f"candidates)."}
    if not cid and not (adds or subs):
        return {"error": "claim needs candidate=<id> and/or add=/subtract= — "
                         "a bare claim has nothing to work from. look at the "
                         "current window's offer, or select first and use "
                         "add=/subtract= for algebra."}

    if win is not None:
        obj = bpy.data.objects.get(win["object"])
        if obj is None:
            return {"error": f"window {win['id']}'s object '{win['object']}' "
                             f"no longer exists — look target=<obj> to re-open"}
    else:
        obj = bpy.context.active_object
        if obj is None or obj.type != 'MESH':
            return {"error": f"no window open ({werr}) and no active mesh to "
                             f"run algebra on — look target=<obj> first"}

    cand = None
    if cid:
        cand = _candidate_by_id(win, cid)
        if cand is None:
            return {"error": f"'{cid}' names no candidate of window {win['id']}. "
                             f"Offered: {_offer_menu(win)}"}
        base = set(cand["verts"])
        base_desc = f"{cand['id']} ({cand['kind']}, {len(base)} verts)"
    else:
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            base = {v.index for v in bm.verts if v.select}
        else:
            base = {v.index for v in obj.data.vertices if v.select}
        base_desc = f"the current selection ({len(base)} verts)"

    algebra = []
    for nm in adds:
        vs, e2 = _operand_verts(win, obj, nm)
        if e2:
            return {"error": e2}
        base |= vs
        algebra.append(f"+ {nm} ({len(vs)} verts)")
    for nm in subs:
        vs, e2 = _operand_verts(win, obj, nm)
        if e2:
            return {"error": e2}
        base -= vs
        algebra.append(f"− {nm} ({len(vs)} verts)")
    if not base:
        alg = " ".join(algebra)
        return {"error": f"the result is empty — {base_desc}{' ' + alg if alg else ''} "
                         f"left no verts, so there is nothing to select or claim"}

    # Select the result on the window's object: enter edit mode there (so the
    # G220 narration can read it), write the verts, flush up, exit. Selects
    # persist on the mesh data after the exit, same as every select op.
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    for f in bm.faces:
        f.select = False
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = v.index in base
    bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)
    rep = perception.describe_selection(obj)
    bpy.ops.object.mode_set(mode='OBJECT')

    result = {"success": True, "selected": len(base), "source": base_desc}
    if algebra:
        result["algebra"] = " ".join(algebra)
    if rep:
        result["selection_report"] = rep["line"]

    if name:
        if _handles._find_handle(name) is not None:
            minted = _handles.update_handle_verts(obj, sorted(base), name)
        else:
            minted = _handles.mint_from_vert_indices(obj, sorted(base), name,
                                                     kind="claim")
        if minted.get("error"):
            result["handle_error"] = minted["error"]
        else:
            result["handle"] = minted["name"]
            result["vgroup"] = minted["vgroup"]
            result["handle_updated"] = bool(minted.get("updated"))

    # mirror-twin prompt (§6.3): claiming one of a twinned pair reminds you the
    # other half exists — left_arm usually wants a right_arm
    if cand is not None and cand.get("twin"):
        twin = _candidate_by_id(win, cand["twin"])
        if twin is not None:
            prompt = (f"mirror twin exists: {twin['id']} ({twin['kind']}, "
                      f"{len(twin['verts'])} verts at {twin['token']})")
            if name:
                prompt += (f" — claim it too: select op=claim "
                           f"candidate={twin['id']} name=<its name>")
            result["twin_prompt"] = prompt

    push_undo(f"claim {cid or 'selection'}" + (f" as {name}" if name else ""))
    return result


TOOLS = {
    "look_window": look_window,
    "claim_candidate": claim_candidate,
}
