"""SPEC-14 / G100 — geometry fit: describe a selection as parametric form `θ = G⁻¹(P)`.

The analytic INVERSE of the field deformer (SPEC-13): that turns params → geometry; this
fits a small library of generative models (plane / sphere / cylinder / cone / ellipsoid /
torus / swept_tube) to the selected verts and hands back the best fit's type, parameters,
and — the load-bearing output — a RESIDUAL and COVERAGE that say when the math describes the
shape and when it is lying. A clean tube fits with a few-mm residual; a face fits nothing and
says so. Read-only: no vert is moved (the optional as_handle / as_curve minting is the one
explicit, opt-in side effect, like feel op=aim as_handle).
"""

import bpy
import mathutils


# ───────────────────────────── small numeric utils ─────────────────────────────

def _unit01(np, a):
    lo, hi = float(a.min()), float(a.max())
    if hi - lo < 1e-12:
        return np.zeros_like(a)
    return (a - lo) / (hi - lo)


def _grid_cov(np, a, b, na=12, nb=12):
    """Fraction of an na×nb occupancy grid (over two [0,1] params) that has ≥1 vert —
    the coverage meter. Guards the half-cylinder trap: a half tube fills ~50% of the grid."""
    if len(a) == 0:
        return 0.0
    ia = np.clip((a * na).astype(int), 0, na - 1)
    ib = np.clip((b * nb).astype(int), 0, nb - 1)
    occ = len(set(zip(ia.tolist(), ib.tolist())))
    return occ / float(na * nb)


def _rms(np, d):
    return float(np.sqrt(np.mean(d * d))) if len(d) else 0.0


def _perp_basis(np, d):
    """Two orthonormal vectors spanning the plane perpendicular to unit vector d."""
    d = d / (np.linalg.norm(d) + 1e-12)
    seed = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(d, seed); e1 /= (np.linalg.norm(e1) + 1e-12)
    e2 = np.cross(d, e1)
    return e1, e2


_AXIS_VEC = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def _axis_dir(np, P, axis):
    """Longitudinal direction: a world axis, or the first PCA principal axis for 'auto'."""
    if axis in _AXIS_VEC:
        return np.array(_AXIS_VEC[axis])
    cov = np.cov((P - P.mean(0)).T)
    w, V = np.linalg.eigh(cov)
    return V[:, np.argmax(w)]


# ───────────────────────────── rigid-primitive fits ─────────────────────────────
# Each returns a dict: {model, rank, params, residual, residual_max, coverage,
#   point, normal} (point/normal = the representative axis-line/center for as_handle),
# or None if the fit is degenerate.

def fit_plane(np, P):
    c = P.mean(0)
    cov = np.cov((P - c).T)
    w, V = np.linalg.eigh(cov)
    n = V[:, 0]
    e1, e2 = V[:, 2], V[:, 1]
    d = (P - c) @ n
    uu = (P - c) @ e1; vv = (P - c) @ e2
    return {
        "model": "plane", "rank": 0,
        "params": {"point": c.tolist(), "normal": n.tolist(),
                   "extent": [float(uu.max() - uu.min()), float(vv.max() - vv.min())]},
        "residual": _rms(np, d), "residual_max": float(np.max(np.abs(d))) if len(d) else 0.0,
        "coverage": _grid_cov(np, _unit01(np, uu), _unit01(np, vv)),
        "point": c, "normal": n,
    }


def fit_sphere(np, P):
    N = len(P)
    A = np.c_[2 * P, np.ones(N)]
    b = (P * P).sum(1)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = sol[:3]
    rr = sol[3] + c @ c
    if rr <= 0:
        return None
    r = float(np.sqrt(rr))
    dist = np.linalg.norm(P - c, axis=1)
    d = dist - r
    dirs = (P - c) / (dist[:, None] + 1e-12)
    theta = (np.arctan2(dirs[:, 1], dirs[:, 0]) / (2 * np.pi)) + 0.5
    phi = np.arccos(np.clip(dirs[:, 2], -1, 1)) / np.pi
    return {
        "model": "sphere", "rank": 1,
        "params": {"center": c.tolist(), "radius": r},
        "residual": _rms(np, d), "residual_max": float(np.max(np.abs(d))),
        "coverage": _grid_cov(np, theta, phi),
        "point": c, "normal": np.array([0.0, 0.0, 1.0]),
    }


def _project_cylinder(np, P, d):
    """Shared cylinder/cone projection: axis dir d → (e1,e2) plane basis, axial coord
    `along`, in-plane (u,v) about the least-squares circle center, radial distance, and a
    point on the axis line."""
    c0 = P.mean(0)
    e1, e2 = _perp_basis(np, d)
    rel = P - c0
    along = rel @ d
    u = rel @ e1; v = rel @ e2
    A = np.c_[2 * u, 2 * v, np.ones(len(P))]
    sol, *_ = np.linalg.lstsq(A, u * u + v * v, rcond=None)
    cu, cv = sol[0], sol[1]
    rr = sol[2] + cu * cu + cv * cv
    radius = float(np.sqrt(rr)) if rr > 0 else 0.0
    radial = np.hypot(u - cu, v - cv)
    axis_point = c0 + cu * e1 + cv * e2
    theta = (np.arctan2(v - cv, u - cu) / (2 * np.pi)) + 0.5
    return along, radial, radius, axis_point, theta


def fit_cylinder(np, P, d):
    along, radial, radius, axis_point, theta = _project_cylinder(np, P, d)
    if radius <= 0:
        return None
    dd = radial - radius
    length = float(along.max() - along.min())
    mid = axis_point + 0.5 * (along.max() + along.min()) * d
    return {
        "model": "cylinder", "rank": 2,
        "params": {"axis_point": axis_point.tolist(), "axis_dir": d.tolist(),
                   "radius": radius, "length": length},
        "residual": _rms(np, dd), "residual_max": float(np.max(np.abs(dd))),
        "coverage": _grid_cov(np, theta, _unit01(np, along)),
        "point": mid, "normal": d,
    }


def fit_cone(np, P, d):
    along, radial, _, axis_point, theta = _project_cylinder(np, P, d)
    slope, r0 = np.polyfit(along, radial, 1)
    half_angle = float(np.arctan(abs(slope)))
    expected = r0 + slope * along
    dd = (radial - expected) * np.cos(half_angle)
    length = float(along.max() - along.min())
    apex = None
    if abs(slope) > 1e-6:
        t_apex = -r0 / slope
        apex = (axis_point + t_apex * d).tolist()
    r_lo = float(r0 + slope * along.min()); r_hi = float(r0 + slope * along.max())
    mid = axis_point + 0.5 * (along.max() + along.min()) * d
    return {
        "model": "cone", "rank": 3,
        "params": {"axis_point": axis_point.tolist(), "axis_dir": d.tolist(),
                   "half_angle_deg": float(np.degrees(half_angle)),
                   "radius_lo": r_lo, "radius_hi": r_hi, "length": length, "apex": apex},
        "residual": _rms(np, dd), "residual_max": float(np.max(np.abs(dd))),
        "coverage": _grid_cov(np, theta, _unit01(np, along)),
        "point": mid, "normal": d,
    }


def fit_torus(np, P):
    c = P.mean(0)
    cov = np.cov((P - c).T)
    w, V = np.linalg.eigh(cov)
    n = V[:, 0]  # axis = least-variance eigenvector (ring lies in the other two)
    rel = P - c
    wax = rel @ n
    inplane = rel - np.outer(wax, n)
    rho = np.linalg.norm(inplane, axis=1)
    R = float(np.mean(rho))
    ring = np.sqrt((rho - R) ** 2 + wax ** 2)
    r = float(np.mean(ring))
    if R <= 0 or r <= 0:
        return None
    # a few Gauss-Newton steps on (R, r) minimising point-to-surface distance
    for _ in range(8):
        dist = np.sqrt((rho - R) ** 2 + wax ** 2)
        f = dist - r
        # ∂f/∂R = -(rho-R)/dist ; ∂f/∂r = -1
        with np.errstate(divide="ignore", invalid="ignore"):
            dfdR = np.where(dist > 1e-9, -(rho - R) / dist, 0.0)
        J = np.c_[dfdR, -np.ones(len(P))]
        try:
            step, *_ = np.linalg.lstsq(J, -f, rcond=None)
        except np.linalg.LinAlgError:
            break
        R += float(step[0]); r += float(step[1])
        if abs(step[0]) + abs(step[1]) < 1e-7:
            break
    dist = np.sqrt((rho - R) ** 2 + wax ** 2)
    dd = dist - r
    e1, e2 = _perp_basis(np, n)
    umaj = (np.arctan2(inplane @ e2, inplane @ e1) / (2 * np.pi)) + 0.5
    pmin = (np.arctan2(wax, rho - R) / (2 * np.pi)) + 0.5
    return {
        "model": "torus", "rank": 4,
        "params": {"center": c.tolist(), "axis_dir": n.tolist(),
                   "major_radius": R, "minor_radius": r},
        "residual": _rms(np, dd), "residual_max": float(np.max(np.abs(dd))),
        "coverage": _grid_cov(np, umaj, pmin),
        "point": c, "normal": n,
    }


def fit_ellipsoid(np, P):
    """Algebraic general-quadric fit (Li/Turner), constrained to an ellipsoid. Residual via
    the Taubin point-to-surface approximation |q|/‖∇q‖."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    D = np.c_[x * x, y * y, z * z, 2 * x * y, 2 * x * z, 2 * y * z, 2 * x, 2 * y, 2 * z]
    try:
        v, *_ = np.linalg.lstsq(D, np.ones(len(P)), rcond=None)
    except np.linalg.LinAlgError:
        return None
    A, B, C, Dd, E, F, G, H, I = v
    M = np.array([[A, Dd, E], [Dd, B, F], [E, F, C]])
    bvec = np.array([G, H, I])
    try:
        center = -np.linalg.solve(M, bvec)
    except np.linalg.LinAlgError:
        return None
    k = 1.0 + bvec @ np.linalg.solve(M, bvec)
    evals, evecs = np.linalg.eigh(M)
    if k <= 0 or np.any(evals <= 0):
        return None  # not an ellipsoid (hyperboloid/degenerate) — let auto skip it
    semi = np.sqrt(k / evals)
    # Taubin distance for the residual.
    q = (P * (P @ M)).sum(1) + 2 * P @ bvec - 1.0
    grad = 2 * (P @ M + bvec)
    gn = np.linalg.norm(grad, axis=1) + 1e-12
    dd = q / gn
    # coverage in the normalised (unit-sphere) frame
    loc = (P - center) @ evecs / semi
    ln = np.linalg.norm(loc, axis=1) + 1e-12
    dirs = loc / ln[:, None]
    theta = (np.arctan2(dirs[:, 1], dirs[:, 0]) / (2 * np.pi)) + 0.5
    phi = np.arccos(np.clip(dirs[:, 2], -1, 1)) / np.pi
    order = np.argsort(semi)[::-1]
    return {
        "model": "ellipsoid", "rank": 5,
        "params": {"center": center.tolist(),
                   "semi_axes": semi[order].tolist(),
                   "frame": evecs[:, order].T.tolist()},
        "residual": _rms(np, dd), "residual_max": float(np.max(np.abs(dd))),
        "coverage": _grid_cov(np, theta, phi),
        "point": center, "normal": evecs[:, order[0]],
    }


# ───────────────────────────── swept_tube ─────────────────────────────

def fit_swept_tube(np, P, d, bands):
    """Ring-sweep decomposition: bin along the axis, per-ring centroid → centerline, per-ring
    cross-plane moment-ellipse → R(s)/ab/roll, empty bins → gaps. The limb extender + the
    G100 continuity read in one decomposition."""
    e1, e2 = _perp_basis(np, d)
    c0 = P.mean(0)
    rel = P - c0
    along = rel @ d
    lo, hi = float(along.min()), float(along.max())
    span = hi - lo
    if span < 1e-9:
        return None
    nb = max(4, int(bands) if bands else 24)
    edges = np.linspace(lo, hi, nb + 1)
    idx = np.clip(((along - lo) / span * nb).astype(int), 0, nb - 1)

    rings = []          # list of dicts per NON-EMPTY bin
    gaps = []           # list of [s0,s1] normalised intervals with no verts
    resid_all = []
    cover_ring = []
    cur_gap = None
    for bi in range(nb):
        m = np.where(idx == bi)[0]
        s0 = (edges[bi] - lo) / span
        s1 = (edges[bi + 1] - lo) / span
        if len(m) < 3:
            if cur_gap is None:
                cur_gap = [s0, s1]
            else:
                cur_gap[1] = s1
            continue
        if cur_gap is not None:
            gaps.append(cur_gap); cur_gap = None
        pts = P[m]
        cen = pts.mean(0)
        rp = pts - cen
        uu = rp @ e1; vv = rp @ e2
        rad = np.hypot(uu, vv)
        R = float(np.mean(rad))
        # moment-ellipse: semi-axes from the 2D second moments
        cov2 = np.cov(np.c_[uu, vv].T)
        ev, EV = np.linalg.eigh(cov2)
        a = float(np.sqrt(2 * max(ev[1], 0.0))); bsemi = float(np.sqrt(2 * max(ev[0], 0.0)))
        roll = float(np.arctan2(EV[1, 1], EV[0, 1]))
        # per-vert residual vs the fitted ellipse radius at the vert's azimuth
        th = np.arctan2(vv, uu) - roll
        if a > 1e-9 and bsemi > 1e-9:
            er = (a * bsemi) / np.sqrt((bsemi * np.cos(th)) ** 2 + (a * np.sin(th)) ** 2 + 1e-18)
        else:
            er = np.full(len(rad), R)
        resid_all.append(rad - er)
        cover_ring.append(_grid_cov(np, (np.arctan2(vv, uu) / (2 * np.pi)) + 0.5,
                                    np.zeros(len(uu)), na=16, nb=1))
        s_mid = 0.5 * (s0 + s1)
        rings.append({"s": round(s_mid, 4), "centroid": cen.tolist(),
                      "R": R, "a": a, "b": bsemi, "roll": roll,
                      "ab_ratio": round(bsemi / a, 3) if a > 1e-9 else 1.0})
    if cur_gap is not None:
        gaps.append(cur_gap)
    if not rings:
        return None

    resid = np.concatenate(resid_all)
    axial_cov = len(rings) / float(nb)
    ang_cov = float(np.mean(cover_ring)) if cover_ring else 0.0
    coverage = axial_cov * ang_cov
    centerline = [rg["centroid"] for rg in rings]
    Rprofile = [[rg["s"], round(rg["R"], 5)] for rg in rings]
    ab = float(np.mean([rg["ab_ratio"] for rg in rings]))
    rolls = np.array([rg["roll"] for rg in rings])
    twist = float(rolls[-1] - rolls[0]) if len(rolls) >= 2 else 0.0
    return {
        "model": "swept_tube", "rank": 6,
        "params": {"axis_dir": d.tolist(), "length": span,
                   "section_ab_ratio": round(ab, 3), "twist_rad": round(twist, 4),
                   "n_rings": len(rings)},
        "residual": _rms(np, resid), "residual_max": float(np.max(np.abs(resid))),
        "coverage": coverage,
        "centerline": centerline, "radius_profile": Rprofile,
        "rings": rings, "gaps": [[round(g[0], 3), round(g[1], 3)] for g in gaps],
        "point": np.array(centerline[len(centerline) // 2]), "normal": d,
        "_span_lo": lo, "_span_hi": hi, "_axis_dir": d, "_origin": c0,
    }


# ───────────────────────────── components ─────────────────────────────

def _components(np, verts_idx, edges_pairs):
    """Union-find over the operated verts using edges with both ends in the set."""
    pos = {vi: k for k, vi in enumerate(verts_idx)}
    parent = list(range(len(verts_idx)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for (x, y) in edges_pairs:
        if x in pos and y in pos:
            ra, rb = find(pos[x]), find(pos[y])
            if ra != rb:
                parent[ra] = rb
    roots = {}
    out = []
    for k in range(len(verts_idx)):
        r = find(k)
        roots.setdefault(r, len(roots))
        out.append(roots[r])
    return np.array(out, dtype=int)


# ───────────────────────────── the op ─────────────────────────────

_RIGID = ["plane", "sphere", "cylinder", "cone", "ellipsoid", "torus", "swept_tube"]


def _fit_one(np, P, model, axis, bands):
    """Fit one group of points. Returns (chosen_fit, candidates) where candidates is the
    list of every attempted fit (for model=auto's verdict trail)."""
    d = _axis_dir(np, P, axis)
    if model == "auto":
        cands = []
        for fn in (lambda: fit_plane(np, P), lambda: fit_sphere(np, P),
                   lambda: fit_cylinder(np, P, d), lambda: fit_cone(np, P, d),
                   lambda: fit_ellipsoid(np, P), lambda: fit_torus(np, P),
                   lambda: fit_swept_tube(np, P, d, bands)):
            try:
                f = fn()
            except Exception:
                f = None
            if f:
                cands.append(f)
        if not cands:
            return None, []
        best = min(cands, key=lambda f: f["residual"])
        # simpler model wins ties: among fits within tie_tol of the best residual AND with
        # comparable coverage, pick the lowest complexity rank.
        tie_tol = max(0.0005, 0.25 * best["residual"])
        near = [f for f in cands
                if f["residual"] <= best["residual"] + tie_tol
                and f["coverage"] >= best["coverage"] - 0.15]
        chosen = min(near, key=lambda f: f["rank"]) if near else best
        return chosen, cands
    # forced single model
    if model == "plane":
        f = fit_plane(np, P)
    elif model == "sphere":
        f = fit_sphere(np, P)
    elif model == "cylinder":
        f = fit_cylinder(np, P, d)
    elif model == "cone":
        f = fit_cone(np, P, d)
    elif model == "ellipsoid":
        f = fit_ellipsoid(np, P)
    elif model == "torus":
        f = fit_torus(np, P)
    elif model == "swept_tube":
        f = fit_swept_tube(np, P, d, bands)
    else:
        return "BAD_MODEL", []
    return f, ([f] if f else [])


def _diag_mm(np, P):
    bb = P.max(0) - P.min(0)
    return float(np.linalg.norm(bb)) * 1000.0


def _verdict(np, f, tol_mm):
    res_mm = f["residual"] * 1000.0
    cov = f["coverage"]
    clean = res_mm <= tol_mm
    note = "clean fit" if clean else "no clean parametric form (organic/irregular)"
    line = f"{f['model']}, residual {res_mm:.1f}mm, coverage {cov*100:.0f}% — {note}"
    if clean and cov < 0.6:
        line += f"  ⚠ low coverage ({cov*100:.0f}%): fits the data present, but it's a patch"
    if f.get("gaps"):
        gs = ", ".join(f"s∈[{g[0]},{g[1]}]" for g in f["gaps"])
        line += f"  ⚠ gaps: {gs}"
    return line, clean


def _mint(np, f, model, as_handle, as_curve):
    """Optional opt-in minting: as_handle → a named point handle at the fit's representative
    axis/center; as_curve → the swept_tube centerline as a real Bézier curve object."""
    from . import handles
    out = {}
    if as_handle:
        pt = f.get("point")
        nrm = f.get("normal")
        if pt is not None:
            m = handles.mint_from_point([float(c) for c in pt],
                                        [float(c) for c in nrm] if nrm is not None else None,
                                        as_handle, kind="axis")
            if m.get("success"):
                out["handle"] = m["name"]
            else:
                out["handle_error"] = m.get("error")
    if as_curve:
        cl = f.get("centerline")
        if not cl:
            out["curve_error"] = f"as_curve needs a centerline (model={model} has none — use swept_tube)"
        elif bpy.data.objects.get(as_curve) is not None:
            out["curve_error"] = f"object '{as_curve}' already exists"
        else:
            cu = bpy.data.curves.new(as_curve, 'CURVE')
            cu.dimensions = '3D'
            sp = cu.splines.new('BEZIER')
            sp.bezier_points.add(len(cl) - 1)
            for bp, p in zip(sp.bezier_points, cl):
                bp.co = (float(p[0]), float(p[1]), float(p[2]))
                bp.handle_left_type = 'AUTO'; bp.handle_right_type = 'AUTO'
            obj = bpy.data.objects.new(as_curve, cu)
            bpy.context.scene.collection.objects.link(obj)
            bpy.context.view_layer.update()
            out["curve"] = obj.name
    return out


def fit_region(params):
    import numpy as np

    model = (params.get("model", "auto") or "auto").lower()
    axis = (params.get("axis", "auto") or "auto").upper()
    if axis not in ("X", "Y", "Z", "AUTO"):
        return {"error": f"axis must be X|Y|Z|auto, got {axis!r}"}
    per_component = bool(params.get("per_component", False))
    bands = int(params.get("bands", 0) or 0)
    as_handle = (params.get("as_handle", "") or "").strip()
    as_curve = (params.get("as_curve", "") or "").strip()
    target = (params.get("target", "") or "").strip()
    if model not in (_RIGID + ["auto"]):
        return {"error": f"model must be auto|{'|'.join(_RIGID)}, got {model!r}"}

    obj = bpy.data.objects.get(target) if target else bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "no mesh to fit (give target= or make a mesh active)"}

    warnings = []
    mat = obj.matrix_world
    # Read the selection if in edit mode, else the whole mesh (warned).
    if obj.mode == 'EDIT':
        import bmesh
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        sel = [v for v in bm.verts if v.select]
        if not sel:
            sel = list(bm.verts)
            warnings.append("no selection — fitting the WHOLE mesh")
        verts = sel
        P = np.array([list(mat @ v.co) for v in verts], dtype=float)
        vidx = [v.index for v in verts]
        vset = set(vidx)
        edge_pairs = [(e.verts[0].index, e.verts[1].index) for e in bm.edges
                      if e.verts[0].index in vset and e.verts[1].index in vset]
    else:
        me = obj.data
        P = np.array([list(mat @ v.co) for v in me.vertices], dtype=float)
        vidx = list(range(len(me.vertices)))
        edge_pairs = [(e.vertices[0], e.vertices[1]) for e in me.edges]
        warnings.append("object mode — fitting the WHOLE mesh (select a region in edit mode to scope)")

    if len(P) < 4:
        return {"error": f"need ≥4 verts to fit, have {len(P)}"}

    tol_param = params.get("tol")
    tol_mm = float(tol_param) if tol_param not in (None, 0, 0.0) else max(3.0, 0.01 * _diag_mm(np, P))

    def finish_one(P_):
        f, cands = _fit_one(np, P_, model, axis, bands)
        if f == "BAD_MODEL" or f is None:
            return None, cands
        f["verdict"], f["clean"] = _verdict(np, f, tol_mm)
        f["residual_mm"] = round(f["residual"] * 1000.0, 2)
        f["residual_max_mm"] = round(f["residual_max"] * 1000.0, 2)
        f["coverage"] = round(f["coverage"], 3)
        f["candidates"] = [{"model": c["model"], "residual_mm": round(c["residual"] * 1000, 2),
                            "coverage": round(c["coverage"], 3)} for c in cands]
        return f, cands

    def strip(f):
        # drop internal / non-JSON keys (numpy arrays, scratch) before it hits the wire
        for k in ("_span_lo", "_span_hi", "_axis_dir", "_origin", "point", "normal",
                  "residual", "residual_max", "rank", "clean"):
            f.pop(k, None)
        return f

    if per_component:
        comp = _components(np, vidx, edge_pairs)
        fits = []
        for c in sorted(set(comp.tolist())):
            Pc = P[comp == c]
            if len(Pc) < 4:
                continue
            f, _ = finish_one(Pc)
            if f:
                f["component"] = int(c)
                fits.append(f)
        if not fits:
            return {"error": "no component could be fit"}
        # mint only off the first component (needs point/centerline, so before strip)
        mint = _mint(np, fits[0], fits[0]["model"], as_handle, as_curve)
        result = {"success": True, "per_component": True,
                  "components": [strip(f) for f in fits],
                  "n_components": len(fits), "tol_mm": round(tol_mm, 2),
                  "verts": len(P), "warnings": warnings}
        result.update(mint)
        return result

    f, _ = finish_one(P)
    if f is None:
        return {"error": f"could not fit model={model}"}
    mint = _mint(np, f, f["model"], as_handle, as_curve)
    f.update({"success": True, "tol_mm": round(tol_mm, 2), "verts": len(P),
              "warnings": warnings})
    f.update(mint)
    return strip(f)


def coverage_region(params):
    """G100 (residual) — a MODEL-FREE continuity/coverage read for a selection that ISN'T a
    swept tube: flat sheets, doubly-curved patches, branching regions, where asserting a
    generative model (feel op=fit) is the wrong frame. Reports:
      • how many DISJOINT pieces the selection is (and where each sits),
      • a 2D occupancy grid over the patch's OWN least-squares plane (u,v) — coverage %, the
        count of INTERIOR empty cells (the surface skips this spot), and a small ASCII map.
    No model is fit first; the plane is only the natural 2D layout of a patch.

    target: mesh (empty=active). na/nb: grid resolution (default 12). Reads the live edit
    selection, else the whole mesh."""
    import numpy as np
    target = params.get("target")
    obj = bpy.data.objects.get(target) if target else bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        return {"error": "no mesh (give target= or make a mesh active)"}
    na = max(4, min(int(params.get("na", 12)), 40))
    nb = max(4, min(int(params.get("nb", 12)), 40))
    mat = obj.matrix_world

    warnings = []
    if obj.mode == 'EDIT':
        import bmesh
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        sel = [v for v in bm.verts if v.select] or list(bm.verts)
        if len(sel) == len(bm.verts):
            warnings.append("no selection — reading the WHOLE mesh")
        P = np.array([list(mat @ v.co) for v in sel], dtype=float)
        vidx = [v.index for v in sel]
        vset = set(vidx)
        edge_pairs = [(e.verts[0].index, e.verts[1].index) for e in bm.edges
                      if e.verts[0].index in vset and e.verts[1].index in vset]
    else:
        me = obj.data
        P = np.array([list(mat @ v.co) for v in me.vertices], dtype=float)
        vidx = list(range(len(me.vertices)))
        edge_pairs = [(e.vertices[0], e.vertices[1]) for e in me.edges]
        warnings.append("object mode — reading the WHOLE mesh (select a region in edit mode to scope)")

    if len(P) < 4:
        return {"error": f"need ≥4 verts, have {len(P)}"}

    # disjoint pieces
    comp = _components(np, vidx, edge_pairs)
    n_comp = len(set(comp.tolist()))

    # project onto the selection's own least-squares plane → (u, v)
    c = P.mean(0)
    cov = np.cov((P - c).T)
    w, V = np.linalg.eigh(cov)
    e1, e2 = V[:, 2], V[:, 1]      # two largest-variance directions
    u = (P - c) @ e1
    v = (P - c) @ e2
    u01 = _unit01(np, u)
    v01 = _unit01(np, v)
    iu = np.clip((u01 * na).astype(int), 0, na - 1)
    iv = np.clip((v01 * nb).astype(int), 0, nb - 1)
    occ = np.zeros((na, nb), dtype=bool)
    occ[iu, iv] = True

    # interior empties: empty cells whose row AND column fall within the occupied span
    rows_used = [a for a in range(na) if occ[a, :].any()]
    cols_used = [b for b in range(nb) if occ[:, b].any()]
    interior = 0
    if rows_used and cols_used:
        r0, r1 = min(rows_used), max(rows_used)
        c0, c1 = min(cols_used), max(cols_used)
        for a in range(r0, r1 + 1):
            for b in range(c0, c1 + 1):
                if not occ[a, b]:
                    interior += 1
    filled = int(occ.sum())
    span_cells = (len(rows_used) and len(cols_used)) and \
        (max(rows_used) - min(rows_used) + 1) * (max(cols_used) - min(cols_used) + 1) or filled
    coverage_pct = round(100.0 * filled / span_cells, 1) if span_cells else 100.0

    # compact ASCII map (rows = u, top→bottom)
    grid_map = ["".join("#" if occ[a, b] else "." for b in range(nb)) for a in range(na)]

    return {"success": True, "object": obj.name, "verts": len(P),
            "pieces": n_comp, "grid": [na, nb], "coverage_pct": coverage_pct,
            "interior_holes": interior, "filled_cells": filled,
            "map": grid_map, "warnings": warnings}


TOOLS = {
    "fit": fit_region,
    "coverage": coverage_region,
}
