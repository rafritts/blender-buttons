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


# ───────────────────────────── analytic patch: quadric (SPEC-19 Phase 1) ─────────────────────────────

def _quadric_shape(k1, k2):
    """Name the form from the two principal curvatures (1/m). The legible verdict §1.1."""
    flat = 0.5  # |curvature| below this (1/m, ≈ 2mm sag over a 10cm patch) reads as flat
    s1 = 0 if abs(k1) < flat else (1 if k1 > 0 else -1)
    s2 = 0 if abs(k2) < flat else (1 if k2 > 0 else -1)
    if s1 == 0 and s2 == 0:
        return "flat (planar)"
    if s1 >= 0 and s2 >= 0 and (s1 or s2):
        return "bowl (concave, both curve up)"
    if s1 <= 0 and s2 <= 0 and (s1 or s2):
        return "dome (convex, both curve down)"
    if s1 * s2 < 0:
        return "saddle (opposing curvatures)"
    return "trough (curved one way, straight the other)"


def _quadric_expr(a, b, c, d, e, f):
    """The executable round-trip: a `field` expr that SETS height. In the shared AUTO frame
    the in-plane coords are field `z` (along L) and `x` (along U), and height is field `y`
    (along V=normal). Displacing along V by (target_height − current_height) lands each vert
    on the fitted surface — apply via channel=axis:v field_mode=add (§3.2)."""
    poly = (f"{a:.6g}*z*z {b:+.6g}*x*x {c:+.6g}*z*x "
            f"{d:+.6g}*z {e:+.6g}*x {f:+.6g}")
    return f"({poly}) - y"


def _quadric_formula(a, b, c, d, e, f):
    """The legible face: h(u,v) the model reads and reasons over (u along axis_u, v along
    axis_v, both in metres from the patch centroid; coefficients in 1/m, 1/m, 1/m, —, —, m)."""
    terms = [f"{a:+.4g}u²", f"{b:+.4g}v²", f"{c:+.4g}uv", f"{d:+.4g}u", f"{e:+.4g}v", f"{f:+.4g}"]
    return "h(u,v) = " + " ".join(terms).lstrip("+ ")


def fit_quadric(np, P):
    """SPEC-19 Phase 1 — the first ANALYTIC basis: a height-field quadric
    h(u,v) = a·u² + b·v² + c·u·v + d·u + e·v + f over the best-fit plane, by linear least
    squares (closed-form, exact residual). A region of quads becomes an editable formula the
    model reads in coefficient-space.

    The frame is the field deformer's OWN AUTO frame (shared `_group_frame`) so the emitted
    `expr` round-trips byte-for-byte through `edit op=field`: u along L (field `z`), v along U
    (field `x`), height along V = the minor/normal axis (field `y`)."""
    from .fields import _group_frame
    O, L, U, V = _group_frame(np, P, "AUTO")
    rel = P - O
    u = rel @ L            # in-plane axis 1  (field `z`)
    v = rel @ U            # in-plane axis 2  (field `x`)
    h = rel @ V            # height along the minor axis = normal  (field `y`)
    A = np.c_[u * u, v * v, u * v, u, v, np.ones(len(P))]
    try:
        sol, *_ = np.linalg.lstsq(A, h, rcond=None)
    except np.linalg.LinAlgError:
        return None
    a, b, c, d, e, f = (float(x) for x in sol)
    dd = h - A @ sol
    hv = float(np.var(h))
    captured = (1.0 - float(np.var(dd)) / hv) if hv > 1e-18 else 1.0
    # principal curvatures from the Hessian [[2a, c], [c, 2b]]
    tr, det = 2 * a + 2 * b, (2 * a) * (2 * b) - c * c
    disc = float(np.sqrt(max(tr * tr / 4 - det, 0.0)))
    k1, k2 = tr / 2 + disc, tr / 2 - disc
    # height-field minting scaffold (as_surface §1.4): the frame, the patch's own (u,v)
    # extent, and the closure that evaluates h over a sample grid in that frame.
    uvext = (float(u.min()), float(u.max()), float(v.min()), float(v.max()))

    def _h(uc, vc, _a=a, _b=b, _c=c, _d=d, _e=e, _f=f):
        return _a * uc * uc + _b * vc * vc + _c * uc * vc + _d * uc + _e * vc + _f

    return {
        "model": "quadric", "rank": 7,
        "params": {"a": round(a, 6), "b": round(b, 6), "c": round(c, 6),
                   "d": round(d, 6), "e": round(e, 6), "f": round(f, 6),
                   "k_max": round(k1, 4), "k_min": round(k2, 4),
                   "shape": _quadric_shape(k1, k2),
                   "frame_origin": [round(x, 5) for x in O.tolist()],
                   "axis_u": [round(x, 4) for x in L.tolist()],
                   "axis_v": [round(x, 4) for x in U.tolist()],
                   "normal": [round(x, 4) for x in V.tolist()]},
        "residual": _rms(np, dd), "residual_max": float(np.max(np.abs(dd))) if len(dd) else 0.0,
        "coverage": _grid_cov(np, _unit01(np, u), _unit01(np, v)),
        "captured": round(captured, 4),
        "formula": _quadric_formula(a, b, c, d, e, f),
        "expr": _quadric_expr(a, b, c, d, e, f),
        "apply_channel": "axis:v",
        "point": O, "normal": V,
        "_frame": (O, L, U, V), "_uv_extent": uvext, "_height": _h,
        "_curv": (abs(k1), abs(k2)), "_coeffs": (a, b, c, d, e, f), "_uvh": (u, v, h),
    }


# ───────────── analytic patch: rbf bumps + progressive layering (Phase 2) ─────────────

def _bump_expr(bumps):
    """The bump sum in the `field` grammar (u along L = `z`, v along U = `x`). Each term is a
    localized Gaussian — exp is in the field sandbox, so the whole thing round-trips."""
    terms = []
    for bp in bumps:
        cu, cv, w, amp = bp["cu"], bp["cv"], bp["w"], bp["amp"]
        terms.append(f"{amp:+.6g}*exp(-((z-({cu:.6g}))*(z-({cu:.6g}))"
                     f"+(x-({cv:.6g}))*(x-({cv:.6g})))/{w*w:.6g})")
    return " ".join(terms)


def _bump_formula(bumps):
    """The legible face: each bump as amp·exp(−((u−cu)²+(v−cv)²)/w²), one local feature each."""
    return " ".join(
        f"{bp['amp']:+.4g}·exp(−((u{-bp['cu']:+.3g})²+(v{-bp['cv']:+.3g})²)/{bp['w']**2:.3g})"
        for bp in bumps)


def _gaussian_layer(np, u, v, target, n_terms, w_candidates, tol_m):
    """Matching-pursuit fit of localized Gaussian bumps to the `target` heights (the leftover a
    gross fit missed). Each round: seed a center at the largest residual, choose its WIDTH by a
    small sweep over `w_candidates` (the feature's scale isn't known a priori), then jointly
    refit ALL amplitudes by linear LSQ. Repeat until n_terms placed or RMS residual < tol.
    Centers come from the data (peaks), widths from the sweep — each term stays LOCAL +
    INTERPRETABLE (§1.1). Returns (bumps, residual_array)."""
    centers = []                                   # (cu, cv, w)
    resid = np.asarray(target, dtype=float).copy()
    amps = np.zeros(0)

    def design(cs):
        return np.column_stack([np.exp(-((u - cu) ** 2 + (v - cv) ** 2) / (w ** 2))
                                for (cu, cv, w) in cs])

    for _ in range(max(1, int(n_terms))):
        if _rms(np, resid) <= tol_m:
            break
        k = int(np.argmax(np.abs(resid)))
        cu, cv = float(u[k]), float(v[k])
        best = None                                # (rms, w, amps, resid)
        for w in w_candidates:
            cs = centers + [(cu, cv, float(w))]
            amps_try, *_ = np.linalg.lstsq(design(cs), target, rcond=None)
            r = target - design(cs) @ amps_try
            rms = _rms(np, r)
            if best is None or rms < best[0]:
                best = (rms, float(w), amps_try, r)
        centers.append((cu, cv, best[1]))
        amps, resid = best[2], best[3]
    bumps = [{"cu": round(cu, 5), "cv": round(cv, 5), "w": round(w, 5),
              "amp": round(float(amps[i]), 6)}
             for i, (cu, cv, w) in enumerate(centers)]
    return bumps, resid


def fit_heightfield(np, P, model, n_terms, progressive, tol_m):
    """SPEC-19 Phase 2 — the layered height field: a quadric GROSS form + a sum of localized
    Gaussian bumps fit to what the gross form missed (matching-pursuit, §2 progressive). One
    honest layer at a time — read `base dome + cheekbone bump + brow ridge`, never fifty
    coupled coefficients. model=rbf/gaussians always layers; model=quadric progressive=true
    auto-layers until the residual clears tol. Emits the combined formula + a round-tripping
    `expr` (the bumps are exp terms the field sandbox already speaks)."""
    base = fit_quadric(np, P)
    if base is None:
        return None
    if model == "quadric" and not progressive:
        return base
    u, v, h = base["_uvh"]
    a, b, c, d, e, f = base["_coeffs"]
    O, L, U, V = base["_frame"]
    umin, umax, vmin, vmax = base["_uv_extent"]
    quad_h = a * u * u + b * v * v + c * u * v + d * u + e * v + f
    # width sweep candidates: grid-cell spacing × {…}, capped at 60% of the patch — narrow
    # tubercles to broad lobes, the scale the feature actually sits at.
    eu, ev = (umax - umin), (vmax - vmin)
    spacing = float(np.sqrt(max(eu * ev, 1e-9) / max(len(u), 1)))
    cap = 0.6 * min(eu, ev)
    w_candidates = sorted({min(spacing * m, cap)
                           for m in (1.2, 1.7, 2.4, 3.4, 4.7, 6.6, 9.2, 13.0)})
    nt = n_terms if n_terms else 4
    # 1. matching-pursuit on the base residual → WHERE the bumps go + each one's width.
    bumps0, _ = _gaussian_layer(np, u, v, h - quad_h, nt, w_candidates, tol_m)
    # 2. JOINT re-solve: fit the quadric base AND the bump amplitudes together, so the base
    #    no longer competes with the bumps for the gross curvature (otherwise the quadric LSQ
    #    steals part of each bump, inflating the residual the bumps then chase).
    cols = [u * u, v * v, u * v, u, v, np.ones(len(u))]
    for bp in bumps0:
        cols.append(np.exp(-((u - bp["cu"]) ** 2 + (v - bp["cv"]) ** 2) / (bp["w"] ** 2)))
    A = np.column_stack(cols)
    sol, *_ = np.linalg.lstsq(A, h, rcond=None)
    a, b, c, d, e, f = (float(x) for x in sol[:6])
    amps = sol[6:]
    bumps = [{**bp, "amp": round(float(amps[i]), 6)} for i, bp in enumerate(bumps0)]
    dd = h - A @ sol

    def _h2(uc, vc, _bumps=bumps, _a=a, _b=b, _c=c, _d=d, _e=e, _f=f):
        out = _a * uc * uc + _b * vc * vc + _c * uc * vc + _d * uc + _e * vc + _f
        for bp in _bumps:
            out = out + bp["amp"] * np.exp(
                -((uc - bp["cu"]) ** 2 + (vc - bp["cv"]) ** 2) / (bp["w"] ** 2))
        return out

    hv = float(np.var(h))
    captured = (1.0 - float(np.var(dd)) / hv) if hv > 1e-18 else 1.0
    formula = base["formula"] + (("  +  " + _bump_formula(bumps)) if bumps else "")
    bexpr = _bump_expr(bumps)
    quad_poly = (f"{a:.6g}*z*z {b:+.6g}*x*x {c:+.6g}*z*x {d:+.6g}*z {e:+.6g}*x {f:+.6g}")
    expr = f"({quad_poly}{(' + ' + bexpr) if bexpr else ''}) - y"
    return {
        "model": model, "rank": 8,
        "params": {"a": round(a, 6), "b": round(b, 6), "c": round(c, 6),
                   "d": round(d, 6), "e": round(e, 6), "f": round(f, 6),
                   "shape": base["params"]["shape"], "n_bumps": len(bumps), "bumps": bumps,
                   "frame_origin": base["params"]["frame_origin"],
                   "axis_u": base["params"]["axis_u"], "axis_v": base["params"]["axis_v"],
                   "normal": base["params"]["normal"]},
        "residual": _rms(np, dd), "residual_max": float(np.max(np.abs(dd))) if len(dd) else 0.0,
        "coverage": base["coverage"], "captured": round(captured, 4),
        "formula": formula, "expr": expr, "apply_channel": "axis:v",
        "point": O, "normal": V,
        "_frame": (O, L, U, V), "_uv_extent": base["_uv_extent"], "_height": _h2,
        "_curv": base["_curv"],
    }


# ───────────── analytic patch: bspline control grid (Phase 2) ─────────────

_BSPLINE_DEG = 3


def _bspline_knots(np, n_ctrl, deg=_BSPLINE_DEG):
    """Clamped open-uniform knot vector: deg+1 zeros, uniform interior, deg+1 ones."""
    n_int = max(n_ctrl - deg - 1, 0)
    interior = [(i + 1) / (n_int + 1) for i in range(n_int)]
    return np.array([0.0] * (deg + 1) + interior + [1.0] * (deg + 1))


def _bspline_basis(np, t, knots, n_ctrl, deg=_BSPLINE_DEG):
    """Cox-de-Boor recursion → (len(t), n_ctrl) basis matrix at params t∈[0,1]. The basis is a
    partition of unity and non-negative, so the surface stays inside the control hull (no
    overshoot) — the §1.1 legibility guarantee for a B-spline."""
    t = np.clip(np.asarray(t, float), 0.0, 1.0 - 1e-9)
    N = np.zeros((len(t), len(knots) - 1))
    for i in range(len(knots) - 1):
        N[:, i] = np.where((t >= knots[i]) & (t < knots[i + 1]), 1.0, 0.0)
    for d in range(1, deg + 1):
        Nn = np.zeros((len(t), len(knots) - 1 - d))
        for i in range(len(knots) - 1 - d):
            den1, den2 = knots[i + d] - knots[i], knots[i + d + 1] - knots[i + 1]
            a = ((t - knots[i]) / den1 * N[:, i]) if den1 > 1e-12 else 0.0
            b = ((knots[i + d + 1] - t) / den2 * N[:, i + 1]) if den2 > 1e-12 else 0.0
            Nn[:, i] = a + b
        N = Nn
    return N[:, :n_ctrl]


def fit_bspline(np, P, n_ctrl):
    """SPEC-19 Phase 2 — the workhorse stitchable surface: a tensor-product cubic B-spline
    height field over an m×m control grid, control points by LINEAR least squares given the
    clamped knot vector. Each control point pulls LOCALLY and the surface is convex-hull
    bounded (no overshoot) — admitted by §1.1. Round-trips via as_surface (the B-spline basis
    isn't in the field-expr grammar), not a field expr."""
    from .fields import _group_frame
    O, L, U, V = _group_frame(np, P, "AUTO")
    rel = P - O
    u, v, h = rel @ L, rel @ U, rel @ V
    umin, umax, vmin, vmax = float(u.min()), float(u.max()), float(v.min()), float(v.max())
    deg = _BSPLINE_DEG
    # control count: requested (basis_terms) or 5; never below deg+1, and keep m*m ≤ verts.
    m = max(deg + 1, int(n_ctrl) if n_ctrl else 5)
    while m > deg + 1 and m * m > len(P):
        m -= 1

    def _n01(a, lo, hi):
        return (a - lo) / (hi - lo) if hi - lo > 1e-12 else np.zeros_like(a)

    ku, kv = _bspline_knots(np, m), _bspline_knots(np, m)
    Bu = _bspline_basis(np, _n01(u, umin, umax), ku, m)
    Bv = _bspline_basis(np, _n01(v, vmin, vmax), kv, m)
    A = (Bu[:, :, None] * Bv[:, None, :]).reshape(len(P), m * m)
    try:
        sol, *_ = np.linalg.lstsq(A, h, rcond=None)
    except np.linalg.LinAlgError:
        return None
    dd = h - A @ sol
    C = sol.reshape(m, m)
    hv = float(np.var(h))
    captured = (1.0 - float(np.var(dd)) / hv) if hv > 1e-18 else 1.0

    def _height(uc, vc, _C=C, _ku=ku, _kv=kv, _m=m,
                _ub=(umin, umax), _vb=(vmin, vmax)):
        shp = np.shape(uc)
        uf = np.asarray(uc, float).ravel()
        vf = np.asarray(vc, float).ravel()
        bu = _bspline_basis(np, (uf - _ub[0]) / (_ub[1] - _ub[0]) if _ub[1] - _ub[0] > 1e-12
                            else np.zeros_like(uf), _ku, _m)
        bv = _bspline_basis(np, (vf - _vb[0]) / (_vb[1] - _vb[0]) if _vb[1] - _vb[0] > 1e-12
                            else np.zeros_like(vf), _kv, _m)
        return np.einsum("ni,nj,ij->n", bu, bv, _C).reshape(shp)

    eu, ev = (umax - umin), (vmax - vmin)
    hspan = float(h.max() - h.min())
    k = 4.0 * hspan / max(min(eu, ev) ** 2, 1e-6)        # rough curvature for tessellation
    return {
        "model": "bspline", "rank": 9,
        "params": {"control_grid": f"{m}×{m}", "n_ctrl": m * m,
                   "ctrl_height_range": [round(float(C.min()), 5), round(float(C.max()), 5)],
                   "frame_origin": [round(x, 5) for x in O.tolist()],
                   "axis_u": [round(x, 4) for x in L.tolist()],
                   "axis_v": [round(x, 4) for x in U.tolist()],
                   "normal": [round(x, 4) for x in V.tolist()]},
        "residual": _rms(np, dd), "residual_max": float(np.max(np.abs(dd))) if len(dd) else 0.0,
        "coverage": _grid_cov(np, _unit01(np, u), _unit01(np, v)),
        "captured": round(captured, 4),
        "formula": f"B-spline surface · {m}×{m} control grid "
                   f"(each control point pulls locally, convex-hull bounded — no overshoot)",
        "point": O, "normal": V,
        "_frame": (O, L, U, V), "_uv_extent": (umin, umax, vmin, vmax), "_height": _height,
        "_curv": (k, k),
    }


# ───────────── analytic mass: superquadric (Phase 2) ─────────────

def _superq_io(np, q, A, B, C, e1, e2):
    """Superellipsoid inside-outside function F (Solina form). F=1 on the surface, <1 inside."""
    qx = np.abs(q[:, 0] / A) ** (2.0 / e2)
    qy = np.abs(q[:, 1] / B) ** (2.0 / e2)
    qz = np.abs(q[:, 2] / C) ** (2.0 / e1)
    return np.nan_to_num((qx + qy) ** (e2 / e1) + qz, nan=1e6, posinf=1e6)


def _superq_resid(np, q, p):
    A, B, C, e1, e2 = p
    F = _superq_io(np, q, A, B, C, e1, e2)
    return np.sqrt(max(A * B * C, 1e-9)) * (F ** e1 - 1.0)


def _superq_radial(np, q, p):
    """Gross-Boult radial point-to-surface distance — the honest residual (the algebraic F-1 is
    biased by distance; this projects each point radially onto the surface)."""
    A, B, C, e1, e2 = p
    F = _superq_io(np, q, A, B, C, e1, e2)
    qn = np.linalg.norm(q, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rad = qn * np.abs(1.0 - F ** (-e1 / 2.0))
    return np.nan_to_num(rad, nan=0.0, posinf=0.0)


def _superq_lm(np, q):
    """Self-rolled Levenberg-Marquardt on the Solina residual (no scipy in Blender). Center +
    rotation are fixed (PCA, by the caller); this optimizes (A,B,C,e1,e2) only."""
    ext = np.abs(q).max(0)
    p = np.array([max(ext[0], 1e-3), max(ext[1], 1e-3), max(ext[2], 1e-3), 1.0, 1.0])
    lo = np.array([1e-3, 1e-3, 1e-3, 0.1, 0.1])
    hi = np.array([1e4, 1e4, 1e4, 2.0, 2.0])
    lam = 1e-3
    for _ in range(60):
        r0 = _superq_resid(np, q, p)
        cost0 = float(np.sum(r0 ** 2))
        J = np.zeros((len(r0), 5))
        for k in range(5):
            dp = np.zeros(5); dp[k] = max(1e-6, abs(p[k]) * 1e-5)
            J[:, k] = (_superq_resid(np, q, p + dp) - r0) / dp[k]
        H = J.T @ J
        g = J.T @ r0
        for _try in range(8):
            try:
                step = np.linalg.solve(H + lam * np.diag(np.diag(H) + 1e-12), -g)
            except np.linalg.LinAlgError:
                break
            pn = np.clip(p + step, lo, hi)
            if float(np.sum(_superq_resid(np, q, pn) ** 2)) < cost0:
                p = pn; lam = max(lam * 0.5, 1e-9); break
            lam *= 3.0
        else:
            break
    rad = _superq_radial(np, q, p)
    return p, _rms(np, rad), rad


def _superq_shape(e1, e2):
    """Name the mass from the two squareness exponents (≈1 round, →0 boxy, →2 pinched)."""
    def lab(e):
        return "boxy" if e < 0.6 else ("round" if e < 1.4 else "pinched")
    z, xy = lab(e1), lab(e2)
    if z == xy == "round":
        return "ellipsoid (rounded mass)"
    if z == xy == "boxy":
        return "box (rounded cuboid)"
    if z == xy == "pinched":
        return "octahedron/diamond"
    return f"{xy} cross-section, {z} profile"


def fit_superquadric(np, P):
    """SPEC-19 Phase 2 — the gross MASS of a closed blob (thumb, torso, pebble): a
    superellipsoid |·|-power surface fit by nonlinear least squares. Legible knobs: A,B,C
    radii (size) + e1,e2 exponents (boxiness/pinch). Center+orientation come from PCA; because
    the superquadric has a DISTINGUISHED z-axis, each principal axis is tried as z and the best
    fit kept. Native SDF → composes by smooth-min (Phase 3 graft). Mints via as_surface (a
    closed parametric mesh), not a field expr."""
    c = P.mean(0)
    Q0 = P - c
    cov = np.cov(Q0.T)
    w, Vv = np.linalg.eigh(cov)
    base = Vv[:, np.argsort(w)[::-1]]
    best = None
    for zk in range(3):
        cols = [j for j in range(3) if j != zk] + [zk]
        R = base[:, cols]
        p, rms, rad = _superq_lm(np, Q0 @ R)
        if best is None or rms < best[1]:
            best = (p, rms, rad, R)
    p, rms, rad, R = best
    A, B, C, e1, e2 = (float(x) for x in p)
    Ax, Ay, Az = R[:, 0], R[:, 1], R[:, 2]

    def _surface_mesh(resolution, _p=(A, B, C, e1, e2), _R=R, _c=c):
        return _superq_build(np, _p, _R, _c, resolution)

    def _sdf(pts, _p=(A, B, C, e1, e2), _R=R, _c=c):
        q = (np.asarray(pts, float) - _c) @ _R
        return _superq_radial_signed(np, q, _p)

    return {
        "model": "superquadric", "rank": 10,
        "params": {"center": [round(x, 5) for x in c.tolist()],
                   "size_xy": [round(A, 5), round(B, 5)], "size_z": round(C, 5),
                   "e1_profile": round(e1, 3), "e2_section": round(e2, 3),
                   "shape": _superq_shape(e1, e2),
                   "axis_x": [round(x, 4) for x in Ax.tolist()],
                   "axis_y": [round(x, 4) for x in Ay.tolist()],
                   "axis_z": [round(x, 4) for x in Az.tolist()]},
        "residual": float(rms), "residual_max": float(np.max(rad)) if len(rad) else 0.0,
        "coverage": _superq_coverage(np, Q0 @ R, A, B, C),
        "captured": round(1.0 - min(float(rms) / (max(A, B, C) + 1e-9), 1.0), 4),
        "formula": (f"superellipsoid · A={A:.3g} B={B:.3g} C={C:.3g} (radii), "
                    f"e1={e1:.2g} (profile) e2={e2:.2g} (section)"),
        "point": c, "normal": Az,
        "_surface_mesh": _surface_mesh, "_sdf": _sdf,
    }


def _superq_coverage(np, q, A, B, C):
    """Occupancy over the (azimuth, elevation) angular grid — a full blob covers ~all of it; a
    fitted cap covers a fraction (guards the half-shell trap, like the rigid fits)."""
    qn = q / (np.array([A, B, C]) + 1e-12)
    nrm = np.linalg.norm(qn, axis=1) + 1e-12
    d = qn / nrm[:, None]
    az = (np.arctan2(d[:, 1], d[:, 0]) / (2 * np.pi)) + 0.5
    el = np.arccos(np.clip(d[:, 2], -1, 1)) / np.pi
    return _grid_cov(np, az, el)


def _superq_radial_signed(np, q, p):
    A, B, C, e1, e2 = p
    F = _superq_io(np, q, A, B, C, e1, e2)
    qn = np.linalg.norm(q, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = qn * (1.0 - F ** (-e1 / 2.0))          # <0 inside, >0 outside
    return np.nan_to_num(d, nan=0.0, posinf=0.0, neginf=-min(A, B, C))


def _superq_build(np, p, R, c, resolution):
    """A closed UV-superellipsoid mesh: rings of 2n verts over the elevation eta, plus two
    poles. Returns (world_verts, faces). The §1.4 instantiation of a superquadric fit."""
    A, B, C, e1, e2 = p
    try:
        n = max(6, int((resolution or "16x16").lower().split("x")[0]))
    except Exception:
        n = 16
    nom = 2 * n

    def sg(ang, e):
        return np.sign(np.sin(ang)) * (np.abs(np.sin(ang)) ** e)

    def cg(ang, e):
        return np.sign(np.cos(ang)) * (np.abs(np.cos(ang)) ** e)

    etas = np.linspace(-np.pi / 2, np.pi / 2, n + 2)[1:-1]   # interior rings (skip poles)
    oms = np.linspace(-np.pi, np.pi, nom + 1)[:-1]
    verts = []
    ring_idx = []
    for et in etas:
        row = []
        for om in oms:
            x = A * cg(et, e1) * cg(om, e2)
            y = B * cg(et, e1) * sg(om, e2)
            z = C * sg(et, e1)
            row.append(len(verts))
            verts.append((x, y, z))
        ring_idx.append(row)
    south = len(verts); verts.append((0.0, 0.0, -C))
    north = len(verts); verts.append((0.0, 0.0, C))
    faces = []
    for i in range(len(ring_idx) - 1):
        a, b = ring_idx[i], ring_idx[i + 1]
        for j in range(nom):
            jn = (j + 1) % nom
            faces.append((a[j], a[jn], b[jn], b[j]))
    for j in range(nom):                                     # pole fans
        jn = (j + 1) % nom
        faces.append((south, ring_idx[0][jn], ring_idx[0][j]))
        faces.append((north, ring_idx[-1][j], ring_idx[-1][jn]))
    Vloc = np.array(verts, dtype=float)
    Wv = c[None, :] + Vloc @ R.T                             # local → world
    return [tuple(float(x) for x in p_) for p_ in Wv.tolist()], faces


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
_ANALYTIC = ["quadric", "rbf", "gaussians", "bspline", "superquadric"]   # SPEC-19 Phase 1 + 2
_PLANNED = ["thin_plate"]                                 # SPEC-19 Phase 2 (remaining)


def _fit_one(np, P, model, axis, bands, progressive=False, n_terms=0, tol_m=0.003):
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
    elif model == "quadric":
        f = fit_heightfield(np, P, "quadric", n_terms, True, tol_m) if progressive \
            else fit_quadric(np, P)
    elif model in ("rbf", "gaussians"):
        f = fit_heightfield(np, P, model, n_terms, True, tol_m)
    elif model == "bspline":
        f = fit_bspline(np, P, n_terms)
    elif model == "superquadric":
        f = fit_superquadric(np, P)
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


def _resolution(np, f, resolution, tol_mm):
    """The §1.4 'suggested, then chosen' tessellation count. If `resolution`='UxV' the model
    chose; else propose from curvature + the faceting tolerance: a quad chord of cell `c`
    deviates from a surface of curvature k by ~k·c²/8, so cell ≈ √(8·tol/|k|) keeps facet
    error under tol. Clamp [4,64]."""
    umin, umax, vmin, vmax = f["_uv_extent"]
    if resolution:
        try:
            su, sv = (resolution or "").lower().split("x")
            return max(2, int(su)), max(2, int(sv))
        except Exception:
            pass
    ku, kv = f.get("_curv", (0.0, 0.0))
    tol_m = (tol_mm or 1.0) / 1000.0
    eu, ev = umax - umin, vmax - vmin

    def n_for(extent, k):
        if k < 1e-6:
            return 12                      # near-flat → a modest default grid
        cell = float(np.sqrt(8.0 * tol_m / k))
        return int(np.clip(np.ceil(extent / max(cell, 1e-6)) + 1, 4, 64))
    return n_for(eu, ku), n_for(ev, kv)


def _mint_surface(np, f, name, resolution, tol_mm):
    """Instantiate a height-field fit as a real quad-grid mesh patch (the as_surface path,
    §1.4): sample h(u,v) on a UxV grid in the fit's own frame, place every vert at
    O + u·L + v·U + h·V, stitch a uniform quad quilt. The formula is the intent; this is one
    sampling of it. Mirrors the as_curve minting idiom (read-time, opt-in side effect)."""
    if bpy.data.objects.get(name) is not None:
        return {"surface_error": f"object '{name}' already exists"}
    if "_surface_mesh" in f:                              # closed parametric (superquadric)
        verts, faces = f["_surface_mesh"](resolution)
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.update()
        obj = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return {"surface": obj.name, "surface_res": [len(faces)], "surface_verts": len(verts)}
    if "_frame" not in f or "_height" not in f or "_uv_extent" not in f:
        return {"surface_error": f"as_surface needs a height-field or superquadric fit; "
                                 f"model={f['model']} mints no patch"}
    O, L, U, V = f["_frame"]
    umin, umax, vmin, vmax = f["_uv_extent"]
    nu, nv = _resolution(np, f, resolution, tol_mm)
    us = np.linspace(umin, umax, nu)
    vs = np.linspace(vmin, vmax, nv)
    UU, VV = np.meshgrid(us, vs, indexing="ij")          # (nu, nv)
    H = np.asarray(f["_height"](UU, VV), dtype=float)
    W = (O[None, None, :] + UU[..., None] * L[None, None, :]
         + VV[..., None] * U[None, None, :] + H[..., None] * V[None, None, :])
    verts = [tuple(float(c) for c in p) for p in W.reshape(-1, 3).tolist()]
    faces = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            a0 = i * nv + j
            faces.append((a0, a0 + 1, a0 + nv + 1, a0 + nv))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return {"surface": obj.name, "surface_res": [nu, nv], "surface_verts": len(verts)}


def fit_region(params):
    import numpy as np

    model = (params.get("model", "auto") or "auto").lower()
    axis = (params.get("axis", "auto") or "auto").upper()
    if axis not in ("X", "Y", "Z", "AUTO"):
        return {"error": f"axis must be X|Y|Z|auto, got {axis!r}"}
    per_component = bool(params.get("per_component", False))
    bands = int(params.get("bands", 0) or 0)
    progressive = bool(params.get("progressive", False))
    n_terms = int(params.get("basis_terms", 0) or 0)
    as_handle = (params.get("as_handle", "") or "").strip()
    as_curve = (params.get("as_curve", "") or "").strip()
    as_surface = (params.get("as_surface", "") or "").strip()
    resolution = (params.get("resolution", "") or "").strip()
    target = (params.get("target", "") or "").strip()
    if model in _PLANNED:
        return {"error": f"model={model!r} is SPEC-19 Phase 2 (not built yet). Height-field "
                         f"analytic patches available now: {'|'.join(_ANALYTIC)} "
                         f"(add progressive=true to layer bumps onto a quadric). "
                         f"Rigid primitives: {'|'.join(_RIGID)}."}
    if model not in (_RIGID + _ANALYTIC + ["auto"]):
        return {"error": f"model must be auto|{'|'.join(_RIGID + _ANALYTIC)}, got {model!r}"}

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
        f, cands = _fit_one(np, P_, model, axis, bands, progressive, n_terms, tol_mm / 1000.0)
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
        # drop internal / non-JSON keys (numpy arrays, scratch) before it hits the wire:
        # the named scratch + every "_"-prefixed key (frame/extent/closures for minting)
        for k in ("point", "normal", "residual", "residual_max", "rank", "clean"):
            f.pop(k, None)
        for k in [k for k in f if k.startswith("_")]:
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
        # mint only off the first component (needs point/centerline/frame, so before strip)
        mint = _mint(np, fits[0], fits[0]["model"], as_handle, as_curve)
        if as_surface:
            mint.update(_mint_surface(np, fits[0], as_surface, resolution, tol_mm))
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
    if as_surface:
        mint.update(_mint_surface(np, f, as_surface, resolution, tol_mm))
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
