"""SPEC-13 / G99 — the field deformer: apply an explicit p' = F(vars(p)) over a selection.

One general engine. For every selected vertex we build a clean, geometry-derived variable
namespace (`vars`), evaluate a function `F` (preset / control points / sandboxed expression)
over those vars as vectorized numpy arrays, and write the result back through a chosen
application channel (radial / normal / axis / twist / vector).

The hard, valuable 80% is the parameterization: every var is derived from the SELECTION's own
verts (its centroid, its extent, its connected components) — never the global mesh ring index.
That is what makes the field work on one sub-shell of a fused, many-shell mesh, where
taper_end/shape_profile silently key off the whole mesh and break.
"""

import bpy
import mathutils

from .state import push_undo


# ───────────────────────────── expression sandbox ─────────────────────────────

_ALLOWED_FUNCS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "exp", "log", "sqrt",
    "abs", "floor", "ceil", "sign", "hypot", "min", "max", "pow", "mod",
    "clamp", "smoothstep", "step", "noise",
}
_CONSTS = {"pi", "tau", "e"}


def _validate_expr_ast(node, allowed_names):
    """Walk an expression AST, rejecting anything outside a tight whitelist.

    Permitted: numeric literals, the namespace/const names, the math function set (called
    positionally only), and the arithmetic operators. Everything else — attribute access,
    subscripting, comprehensions, lambdas, comparisons, names we don't recognise — is
    refused. `custom` is a code-exec surface; this is the gate."""
    import ast
    if isinstance(node, ast.Expression):
        return _validate_expr_ast(node.body, allowed_names)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return None
        return f"literal {node.value!r} is not a number"
    if isinstance(node, ast.Name):
        if node.id in allowed_names or node.id in _CONSTS:
            return None
        return (f"name '{node.id}' is not allowed — use a field variable "
                f"(t,u,v,r,theta,s,L,nx..,x..,X..,i,ci,ring,rnd,crnd), a const "
                f"(pi,tau,e), or a math function ({', '.join(sorted(_ALLOWED_FUNCS))})")
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                    ast.Pow, ast.Mod, ast.FloorDiv)):
            return f"operator {type(node.op).__name__} is not allowed"
        return _validate_expr_ast(node.left, allowed_names) or \
            _validate_expr_ast(node.right, allowed_names)
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.UAdd, ast.USub)):
            return f"unary {type(node.op).__name__} is not allowed"
        return _validate_expr_ast(node.operand, allowed_names)
    if isinstance(node, ast.Call):
        if node.keywords:
            return "keyword arguments are not allowed in a field expression"
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            fname = getattr(node.func, "id", type(node.func).__name__)
            return f"function '{fname}' is not in the allowed set {sorted(_ALLOWED_FUNCS)}"
        for arg in node.args:
            err = _validate_expr_ast(arg, allowed_names)
            if err:
                return err
        return None
    return f"syntax element {type(node).__name__} is not allowed in a field expression"


def _expr_funcs(np, seed):
    """The numpy-backed math callables exposed to a field expression (and to `noise`)."""
    def _clamp(x, lo, hi):
        return np.clip(x, lo, hi)

    def _smoothstep(e0, e1, x):
        t = np.clip((np.asarray(x, dtype=float) - e0) / (np.asarray(e1 - e0) + 1e-12), 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    def _step(edge, x):
        return np.where(np.asarray(x, dtype=float) < edge, 0.0, 1.0)

    def _noise(*args):
        # Deterministic hash-noise in [0,1), seeded. Vectorized over the coord arrays.
        if not args:
            return float((seed * 2654435761) & 0xFFFF) / 0x10000
        h = np.zeros_like(np.asarray(args[0], dtype=float)) + float(seed) * 0.1731
        for j, a in enumerate(args):
            h = h + np.asarray(a, dtype=float) * (12.9898 + j * 7.137)
        val = np.sin(h) * 43758.5453
        return val - np.floor(val)

    return {
        "sin": np.sin, "cos": np.cos, "tan": np.tan,
        "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan, "atan2": np.arctan2,
        "exp": np.exp, "log": np.log, "sqrt": np.sqrt, "abs": np.abs,
        "floor": np.floor, "ceil": np.ceil, "sign": np.sign, "hypot": np.hypot,
        "min": np.minimum, "max": np.maximum, "pow": np.power, "mod": np.mod,
        "clamp": _clamp, "smoothstep": _smoothstep, "step": _step, "noise": _noise,
    }


def _eval_expr(np, src, namespace, seed):
    """Validate then evaluate a field expression against the numpy var arrays. Returns
    (array, error). On any validation failure returns (None, message) and never executes."""
    import ast
    import math
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        return None, f"could not parse expression: {e}"
    err = _validate_expr_ast(tree, set(namespace.keys()))
    if err:
        return None, err
    env = dict(namespace)
    env.update(_expr_funcs(np, seed))
    env.update({"pi": math.pi, "tau": math.tau, "e": math.e})
    try:
        code = compile(tree, "<field-expr>", "eval")
        out = eval(code, {"__builtins__": {}}, env)  # noqa: S307 — AST whitelisted above
    except Exception as e:
        return None, f"expression evaluation failed: {e}"
    n = len(namespace["t"])
    out = np.asarray(out, dtype=float)
    if out.ndim == 0:                       # a constant expression → broadcast
        out = np.full(n, float(out))
    if out.shape != (n,):
        return None, f"expression produced shape {out.shape}, expected ({n},)"
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0), None


# ───────────────────────────── components / hashes ─────────────────────────────

def _components(verts, vset):
    """Union-find connected components over the operated verts, using only edges whose
    BOTH endpoints are in the operated set. Returns an int array (one component id per
    operated vert, in `verts` order)."""
    idx_of = {v.index: k for k, v in enumerate(verts)}
    parent = list(range(len(verts)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for v in verts:
        for e in v.link_edges:
            o = e.other_vert(v)
            if o.index in idx_of and o.index in vset:
                ra, rb = find(idx_of[v.index]), find(idx_of[o.index])
                if ra != rb:
                    parent[ra] = rb
    roots = {}
    out = []
    for k in range(len(verts)):
        r = find(k)
        if r not in roots:
            roots[r] = len(roots)
        out.append(roots[r])
    return out


def _hash01(np, ints, seed):
    a = (np.asarray(ints, dtype=np.int64) * 2654435761 + seed * 40503) & 0xFFFFFFFF
    a = ((a ^ (a >> 13)) * 1274126177) & 0xFFFFFFFF
    a = (a ^ (a >> 16)) & 0xFFFFFFFF
    return (a & 0xFFFFFF).astype(float) / float(0x1000000)


# ───────────────────────────── frame derivation ─────────────────────────────

_AXIS_VEC = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
_OTHER = {"X": ("Y", "Z"), "Y": ("X", "Z"), "Z": ("X", "Y")}


def _group_frame(np, P, axis):
    """Return (origin, L, U, V) for a group of world points P (M,3). origin = centroid;
    L = longitudinal axis (a world axis, or the first PCA principal axis for axis='auto');
    U,V = the two orthonormal cross-plane axes."""
    origin = P.mean(axis=0)
    if axis == "AUTO":
        cov = np.cov((P - origin).T)
        evals, evecs = np.linalg.eigh(cov)
        order = np.argsort(evals)[::-1]
        L = evecs[:, order[0]]
        U = evecs[:, order[1]]
        V = evecs[:, order[2]]
    else:
        L = np.array(_AXIS_VEC[axis])
        ua, va = _OTHER[axis]
        U = np.array(_AXIS_VEC[ua])
        V = np.array(_AXIS_VEC[va])
    return origin, L, U, V


def _normalize01(np, a):
    lo, hi = float(a.min()), float(a.max())
    if hi - lo < 1e-12:
        return np.zeros_like(a)
    return (a - lo) / (hi - lo)


def _arc_length(np, ca, world, comp):
    """Per-component arc-length s and total L, walking each component's ordered spine.

    The spine is the sequence of cross-section ring centroids ordered by longitudinal
    projection `ca`; s accumulates world distance between consecutive ring centroids and
    is assigned to every vert of that ring. Resets per component (so a field of separate
    strands gets an independent root-to-tip parameter on each)."""
    s = np.zeros(len(ca))
    Ltot = np.zeros(len(ca))
    for c in np.unique(comp):
        m = np.where(comp == c)[0]
        cav = ca[m]
        # bin into rings by rounded longitudinal projection
        keyf = np.round(cav, 4)
        order = np.argsort(keyf, kind="stable")
        ring_s = {}
        prev_centroid = None
        acc = 0.0
        cur_key = None
        bucket = []

        def flush(bucket, acc, prev):
            cen = world[m[bucket]].mean(axis=0)
            if prev is not None:
                acc = acc + float(np.linalg.norm(cen - prev))
            for b in bucket:
                ring_s[m[b]] = acc
            return acc, cen

        for oi in order:
            k = keyf[oi]
            if cur_key is None:
                cur_key = k
            if k != cur_key:
                acc, prev_centroid = flush(bucket, acc, prev_centroid)
                bucket = []
                cur_key = k
            bucket.append(oi)
        if bucket:
            acc, prev_centroid = flush(bucket, acc, prev_centroid)
        total = acc if acc > 0 else 1.0
        for gi in m:
            s[gi] = ring_s.get(gi, 0.0)
            Ltot[gi] = total
    return s, Ltot


# ───────────────────────────── the op ─────────────────────────────

def field(params):
    import numpy as np
    import bmesh

    obj = bpy.context.active_object
    if obj is None or obj.mode != 'EDIT':
        return {"error": "Must be in edit mode"}

    axis = (params.get("axis", "Z") or "Z").upper()
    if axis not in ("X", "Y", "Z", "AUTO"):
        return {"error": f"axis must be X|Y|Z|auto, got {axis!r}"}
    about = (params.get("about", "axis") or "axis").lower()
    if about == "spine":
        return {"error": "about=spine is not shipped yet (v1 ships about=axis); "
                         "use about=axis. Curved-part radial fields are a later phase."}
    channel = (params.get("channel", "radial") or "radial").lower()
    field_mode = (params.get("field_mode", "") or "").lower()
    per_component = bool(params.get("per_component", False))
    seed = int(params.get("seed", 0))

    # ── function source: exactly one of preset / points / expr ──
    preset = (params.get("preset", "") or "").strip().lower()
    points = params.get("points") or []
    expr = (params.get("expr", "") or "").strip()
    expr_x = (params.get("expr_x", "") or "").strip()
    expr_y = (params.get("expr_y", "") or "").strip()
    expr_z = (params.get("expr_z", "") or "").strip()
    has_vec_expr = bool(expr_x or expr_y or expr_z)
    moulds = params.get("moulds") or []
    sources = [bool(preset), bool(points), bool(expr) or has_vec_expr, bool(moulds)]
    if sum(sources) != 1:
        return {"error": "supply EXACTLY one function source: preset=<name>, "
                         "points=[[t,val],...], expr=\"...\" "
                         "(expr_x/y/z for channel=vector), or "
                         "moulds=[{at,points},...] (the drape/loft array)"}

    # ── gather operated verts (stable order) ──
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    selected = [v for v in bm.verts if v.select]
    scoped = bool(selected)
    verts = selected if scoped else list(bm.verts)
    warnings = []
    if not verts:
        return {"error": "mesh has no vertices"}
    if not scoped:
        warnings.append("no selection — field applied to the WHOLE mesh")

    mat = obj.matrix_world
    mat_inv = mat.inverted()
    nmat = mat.to_3x3().inverted().transposed()
    P = np.array([list(mat @ v.co) for v in verts], dtype=float)
    Nrm = np.array([list((nmat @ v.normal).normalized()) for v in verts], dtype=float)
    vidx = np.array([v.index for v in verts], dtype=np.int64)
    n = len(verts)

    vset = {v.index for v in verts}
    comp = np.array(_components(verts, vset), dtype=np.int64)

    # ── per-vertex frame + local coords (per-group if per_component, else one frame) ──
    O = np.zeros((n, 3)); U = np.zeros((n, 3)); V = np.zeros((n, 3)); Lax = np.zeros((n, 3))
    if per_component:
        groups = [np.where(comp == c)[0] for c in np.unique(comp)]
    else:
        groups = [np.arange(n)]
    t = np.zeros(n); uu = np.zeros(n); vv = np.zeros(n)
    for g in groups:
        origin, Lv, Uv, Vv = _group_frame(np, P[g], axis)
        O[g] = origin; Lax[g] = Lv; U[g] = Uv; V[g] = Vv

    d = P - O
    ca = np.einsum("ij,ij->i", d, Lax)   # longitudinal projection
    cu = np.einsum("ij,ij->i", d, U)
    cv = np.einsum("ij,ij->i", d, V)
    for g in groups:
        t[g] = _normalize01(np, ca[g])
        uu[g] = _normalize01(np, cu[g])
        vv[g] = _normalize01(np, cv[g])
    r = np.hypot(cu, cv)
    theta = np.arctan2(cv, cu)

    s, Larc = _arc_length(np, ca, P, comp)
    # axis-bin index (ring): rank of the rounded longitudinal projection, per group
    ring = np.zeros(n, dtype=np.int64)
    for g in groups:
        keys = np.round(ca[g], 4)
        uniq = {k: i for i, k in enumerate(sorted(set(keys.tolist())))}
        ring[g] = [uniq[k] for k in keys.tolist()]

    rnd = _hash01(np, vidx, seed)
    crnd_by_c = {int(c): _hash01(np, np.array([int(c)]), seed)[0] for c in np.unique(comp)}
    crnd = np.array([crnd_by_c[int(c)] for c in comp])

    namespace = {
        "t": t, "u": uu, "v": vv, "us": 2 * uu - 1, "vs": 2 * vv - 1,
        "r": r, "theta": theta, "s": s, "L": Larc,
        "nx": Nrm[:, 0], "ny": Nrm[:, 1], "nz": Nrm[:, 2],
        "x": cu, "y": cv, "z": ca, "X": P[:, 0], "Y": P[:, 1], "Z": P[:, 2],
        "i": vidx.astype(float), "ci": comp.astype(float), "ring": ring.astype(float),
        "rnd": rnd, "crnd": crnd,
    }

    # ── evaluate F ──
    def eval_scalar(src):
        return _eval_expr(np, src, namespace, seed)

    if channel == "vector" or has_vec_expr:
        # vector channel: up to three component expressions (any omitted = 0)
        comps = []
        for src in (expr_x, expr_y, expr_z):
            if src:
                arr, err = eval_scalar(src)
                if err:
                    return {"error": f"expr error: {err}"}
                comps.append(arr)
            else:
                comps.append(np.zeros(n))
        Fx, Fy, Fz = comps
        Fvec = np.stack([Fx, Fy, Fz], axis=1)
        f_range = [float(np.min(Fvec)), float(np.max(Fvec))]
    else:
        if preset:
            F, err = _eval_preset(np, preset, params, namespace)
            if err:
                return {"error": err}
        elif points:
            F, err = _eval_points(np, points, params, t)
            if err:
                return {"error": err}
        elif moulds:
            F, err, ribbon = _eval_moulds(np, moulds, params, uu, vv)
            if err:
                return {"error": err}
            if ribbon:
                warnings.append(
                    "uniform moulds → this drapes as a RIBBON (single curvature), "
                    "not a shell; vary the moulds down the sheet for the second curvature")
        else:
            F, err = eval_scalar(expr)
            if err:
                return {"error": f"expr error: {err}"}
        cmin = params.get("clamp_min"); cmax = params.get("clamp_max")
        if cmin is not None:
            F = np.maximum(F, float(cmin))
        if cmax is not None:
            F = np.minimum(F, float(cmax))
        f_range = [float(np.min(F)), float(np.max(F))]

    # ── map F → world displacement through the channel ──
    eff_mode = field_mode or ("multiply" if channel == "radial" else "add")
    sx = float(params.get("sigma_x", 1.0) or 1.0)
    sy = float(params.get("sigma_y", 1.0) or 1.0)
    Pnew = P.copy()

    if channel == "radial":
        live = r > 1e-9
        if eff_mode == "multiply":
            cun = cu * F * sx
            cvn = cv * F * sy
        else:
            if eff_mode == "set":
                rr = F
            elif eff_mode == "add":
                rr = r + F
            else:
                return {"error": f"radial mode must be add|multiply|set, got {eff_mode}"}
            scale = np.where(live, rr / np.where(live, r, 1.0), 1.0)
            cun = cu * scale * sx
            cvn = cv * scale * sy
        Pnew = O + cun[:, None] * U + cvn[:, None] * V + ca[:, None] * Lax
        Pnew[~live] = P[~live]
    elif channel == "normal":
        Pnew = P + F[:, None] * Nrm
    elif channel.startswith("axis"):
        spec = channel.split(":", 1)[1] if ":" in channel else "long"
        spec = spec.upper()
        if spec in ("X", "Y", "Z"):
            dir_v = np.array(_AXIS_VEC[spec])[None, :]
        elif spec == "LONG":
            dir_v = Lax
        elif spec == "U":
            dir_v = U
        elif spec == "V":
            dir_v = V
        else:
            return {"error": f"axis channel dir must be X|Y|Z|long|u|v, got {spec}"}
        Pnew = P + F[:, None] * dir_v
    elif channel == "twist":
        ca_ = np.cos(F); sa_ = np.sin(F)
        cun = cu * ca_ - cv * sa_
        cvn = cu * sa_ + cv * ca_
        Pnew = O + cun[:, None] * U + cvn[:, None] * V + ca[:, None] * Lax
    elif channel == "vector":
        frame = (params.get("frame", "world") or "world").lower()
        if frame == "world":
            delta = Fvec
        elif frame == "local":
            delta = Fvec[:, 0:1] * U + Fvec[:, 1:2] * V + Fvec[:, 2:3] * Lax
        elif frame == "tangent_normal":
            nrm = Nrm
            tan = Lax - np.einsum("ij,ij->i", Lax, nrm)[:, None] * nrm
            tl = np.linalg.norm(tan, axis=1, keepdims=True)
            tan = np.where(tl > 1e-9, tan / np.where(tl > 1e-9, tl, 1.0), U)
            bit = np.cross(nrm, tan)
            delta = Fvec[:, 0:1] * tan + Fvec[:, 1:2] * bit + Fvec[:, 2:3] * nrm
        else:
            return {"error": f"frame must be world|local|tangent_normal, got {frame}"}
        Pnew = P + delta
    else:
        return {"error": f"unknown channel {channel!r} — use radial|normal|axis:<dir>|twist|vector"}

    # ── write back ──
    moved = 0
    for k, v in enumerate(verts):
        nc = mat_inv @ mathutils.Vector((Pnew[k, 0], Pnew[k, 1], Pnew[k, 2]))
        if (nc - v.co).length > 1e-9:
            moved += 1
        v.co = nc

    bm.normal_update()
    bm.select_flush_mode()                 # G87: flush before the editmesh→mesh sync
    bmesh.update_edit_mesh(obj.data)
    push_undo(f"field {channel} {eff_mode} ({'preset:'+preset if preset else 'points' if points else 'expr'})")

    sel_w = Pnew
    bbox = {
        "x": [round(float(sel_w[:, 0].min()), 4), round(float(sel_w[:, 0].max()), 4)],
        "y": [round(float(sel_w[:, 1].min()), 4), round(float(sel_w[:, 1].max()), 4)],
        "z": [round(float(sel_w[:, 2].min()), 4), round(float(sel_w[:, 2].max()), 4)],
    }
    return {
        "success": True,
        "channel": channel,
        "mode": eff_mode,
        "axis": axis,
        "scope": "selection" if scoped else "whole_mesh",
        "components": int(len(np.unique(comp))),
        "verts_total": n,
        "verts_moved": moved,
        "f_range": [round(f_range[0], 5), round(f_range[1], 5)],
        "sel_bbox": bbox,
        "warnings": warnings,
    }


def _eval_preset(np, preset, params, ns):
    """Closed-form preset families over the var arrays. Returns (array, error)."""
    a = float(params.get("preset_a", 1.0))
    b = float(params.get("preset_b", 1.0))
    k = float(params.get("k", 1.0))
    amp = float(params.get("amp", 1.0))
    freq = float(params.get("freq", 1.0))
    phase = float(params.get("phase", 0.0))
    center = float(params.get("center", 0.5))
    width = float(params.get("bell_width", 0.2)) or 0.2
    t = ns["t"]; theta = ns["theta"]
    import math
    tau = math.tau
    if preset == "taper":
        return a + (b - a) * t, None
    if preset == "power":
        return a + (b - a) * np.power(np.clip(t, 0.0, 1.0), k), None
    if preset == "smoothstep":
        e = t * t * (3.0 - 2.0 * t)
        return a + (b - a) * e, None
    if preset == "bell":
        return amp * np.exp(-(((t - center) / width) ** 2)), None
    if preset == "sine":
        return amp * np.sin(tau * freq * t + phase), None
    if preset == "lobes":
        return amp * np.cos(freq * theta + phase), None
    return None, (f"unknown preset {preset!r} — use taper|power|smoothstep|bell|sine|lobes")


def _eval_points(np, points, params, t):
    """Control-point curve in normalized t. interp = linear | smooth | cubic."""
    interp = (params.get("interp", "smooth") or "smooth").lower()
    cps = []
    for p in points:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            cps.append((float(p[0]), float(p[1])))
        elif isinstance(p, dict):
            cps.append((float(p.get("t", p.get("x"))), float(p.get("val", p.get("v")))))
        else:
            return None, f"bad point {p!r}; want [t, val]"
    cps.sort(key=lambda c: c[0])
    ts = np.array([c[0] for c in cps]); vs = np.array([c[1] for c in cps])
    if len(cps) < 2:
        return np.full(len(t), vs[0] if len(vs) else 0.0), None
    if interp == "linear":
        return np.interp(t, ts, vs), None
    if interp == "smooth":
        # piecewise: locate segment, ease the local parameter with smoothstep
        idx = np.clip(np.searchsorted(ts, t) - 1, 0, len(ts) - 2)
        t0 = ts[idx]; t1 = ts[idx + 1]; v0 = vs[idx]; v1 = vs[idx + 1]
        lt = np.clip((t - t0) / np.where(t1 - t0 > 1e-12, t1 - t0, 1.0), 0.0, 1.0)
        e = lt * lt * (3.0 - 2.0 * lt)
        return v0 + (v1 - v0) * e, None
    if interp == "cubic":
        # Catmull-Rom through the control points (clamped ends)
        out = np.empty(len(t))
        for j, tv in enumerate(t):
            i = int(np.clip(np.searchsorted(ts, tv) - 1, 0, len(ts) - 2))
            p1, p2 = vs[i], vs[i + 1]
            p0 = vs[i - 1] if i - 1 >= 0 else p1
            p3 = vs[i + 2] if i + 2 < len(vs) else p2
            seg = ts[i + 1] - ts[i]
            lt = 0.0 if seg < 1e-12 else (tv - ts[i]) / seg
            lt2 = lt * lt; lt3 = lt2 * lt
            out[j] = 0.5 * ((2 * p1) + (-p0 + p2) * lt +
                            (2 * p0 - 5 * p1 + 4 * p2 - p3) * lt2 +
                            (-p0 + 3 * p1 - 3 * p2 + p3) * lt3)
        return out, None
    return None, f"interp must be linear|smooth|cubic, got {interp!r}"


def _eval_moulds(np, moulds, params, u, v):
    """The DRAPE / LOFT source — vacuum-form onto an ARRAY of cross-section moulds.

    Each mould is a control-point profile over the cross-axis `u`, keyed at a position
    `at` (0..1) down the line-axis `v`. We sample every key's profile at each vert's u,
    then blend the keyed values along v (smoothstep between neighbours). The variation of
    the moulds DOWN v is what gives the sheet its second curvature — a real shell. If the
    keyed profiles don't actually differ, the result is a single-curvature ribbon, which
    we flag (third return value) so the caller can warn without blocking.

    Returns (F, error, ribbon)."""
    keys = []
    for m in moulds:
        if not isinstance(m, dict) or "points" not in m:
            return None, "each mould wants {\"at\": <0..1>, \"points\": [[u,val],...]}", False
        keys.append([m.get("at"), m["points"]])
    K = len(keys)
    if K == 0:
        return None, "moulds is empty — give at least one {at, points}", False
    # position each key down v: explicit `at`, else spread evenly across 0..1
    if any(k[0] is None for k in keys):
        for i, k in enumerate(keys):
            if k[0] is None:
                k[0] = (i / (K - 1)) if K > 1 else 0.0
    keys.sort(key=lambda k: float(k[0]))
    vpos = np.array([float(k[0]) for k in keys])

    # sample every key's profile at each vert's u → (n, K)
    cols = []
    for _, pts in keys:
        pv, err = _eval_points(np, pts, params, u)
        if err:
            return None, err, False
        cols.append(pv)
    M = np.stack(cols, axis=1)

    # blend the keyed profiles along v (smoothstep between bracketing keys)
    n = len(u)
    if K == 1:
        F = M[:, 0]
    else:
        idx = np.clip(np.searchsorted(vpos, v) - 1, 0, K - 2)
        v0 = vpos[idx]; v1 = vpos[idx + 1]
        lt = np.clip((v - v0) / np.where(v1 - v0 > 1e-12, v1 - v0, 1.0), 0.0, 1.0)
        e = lt * lt * (3.0 - 2.0 * lt)
        rows = np.arange(n)
        f0 = M[rows, idx]; f1 = M[rows, idx + 1]
        F = f0 + (f1 - f0) * e

    # ribbon detection: do the keyed profiles actually vary across the array?
    span = float(M.max() - M.min())
    maxdiff = 0.0
    for j in range(1, K):
        maxdiff = max(maxdiff, float(np.max(np.abs(M[:, j] - M[:, 0]))))
    ribbon = (K < 2) or (maxdiff <= 1e-6 + 1e-3 * max(span, 1e-9))
    return F, None, ribbon


TOOLS = {
    "field": field,
}
