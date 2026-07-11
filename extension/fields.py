"""SPEC-13 / G99 — the field deformer: apply an explicit p' = F(vars(p)) over a selection.

One general engine. For every selected vertex we build a clean, geometry-derived variable
namespace (`vars`), evaluate a function `F` (preset / control points / sandboxed expression)
over those vars as vectorized numpy arrays, and write the result back through a chosen
application channel (radial / normal / axis / twist / vector).

The hard, valuable 80% is the parameterization: every var is derived from the SELECTION's own
verts (its centroid, its extent, its connected components) — never the global mesh ring index.
That is what makes the field work on one sub-shell of a fused, many-shell mesh, where
some ops silently key off the whole mesh and break.
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

# Presets whose rest value is 0, not the multiply-identity 1 (G222). Composed with
# a multiply channel they scale every radius by ≈0 and collapse the form, so on
# `radial` these DEFAULT to `add` (amp = absolute depth); taper/power/smoothstep
# rest at 1 and keep the multiply default (amp = relative scale).
_ZERO_BASED_PRESETS = {"lobes", "sine", "bell"}


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


# interp modes shared by BOTH axes of a loft (the cross-section profiles AND the
# row-to-row blend down the line-axis) — G201. `pchip`/`bicubic_monotone` alias to
# `monotone` (Fritsch–Carlson): passes every key smoothly with NO overshoot, the
# standard cure for the cubic-undershoot rings the drape path used to print.
_INTERP_MODES = {"linear", "smooth", "cubic", "monotone"}


def _resolve_interp(raw):
    """Normalise an interp name (with aliases). Returns (mode, error)."""
    interp = (raw or "smooth").lower()
    if interp in ("pchip", "bicubic_monotone", "monotone_cubic"):
        interp = "monotone"
    if interp not in _INTERP_MODES:
        return None, f"interp must be one of {sorted(_INTERP_MODES)}, got {interp!r}"
    return interp, None


def _fc_tangents(np, xs, ys):
    """Fritsch–Carlson monotone tangents at each key. ys is (K,) OR (N,K) — one curve
    per row. Guarantees a monotone Hermite between keys: no over/undershoot."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    dx = np.diff(xs)
    if ys.ndim == 2:
        d = np.diff(ys, axis=1) / dx[None, :]
        m = np.empty_like(ys)
        m[:, 0] = d[:, 0]; m[:, -1] = d[:, -1]
        if ys.shape[1] > 2:
            m[:, 1:-1] = 0.5 * (d[:, :-1] + d[:, 1:])
        for k in range(d.shape[1]):
            dk = d[:, k]
            zero = np.abs(dk) < 1e-12
            m[:, k] = np.where(zero, 0.0, m[:, k])
            m[:, k + 1] = np.where(zero, 0.0, m[:, k + 1])
            safe = np.where(zero, 1.0, dk)
            a = np.where(zero, 0.0, m[:, k] / safe)
            b = np.where(zero, 0.0, m[:, k + 1] / safe)
            s = a * a + b * b
            over = s > 9.0
            tau = np.where(over, 3.0 / np.sqrt(np.where(over, s, 1.0)), 1.0)
            m[:, k] = np.where(over, tau * a * dk, m[:, k])
            m[:, k + 1] = np.where(over, tau * b * dk, m[:, k + 1])
        return m
    d = np.diff(ys) / dx
    m = np.empty_like(ys)
    m[0] = d[0]; m[-1] = d[-1]
    if len(ys) > 2:
        m[1:-1] = 0.5 * (d[:-1] + d[1:])
    for k in range(len(d)):
        if abs(d[k]) < 1e-12:
            m[k] = 0.0; m[k + 1] = 0.0
            continue
        a = m[k] / d[k]; b = m[k + 1] / d[k]
        s = a * a + b * b
        if s > 9.0:
            tau = 3.0 / np.sqrt(s)
            m[k] = tau * a * d[k]; m[k + 1] = tau * b * d[k]
    return m


def _interp_curve(np, xs, ys, q, interp):
    """1-D interpolation of values ys sampled at sorted keys xs, evaluated at queries q.

    ys may be (K,) — one shared curve (a cross-section profile) — or (N,K) — a separate
    curve per query row (the loft v-blend: each vert carries its own K profile samples).
    q is (N,). One code path serves BOTH axes of a loft so the surface is interpolated the
    same way across and down (G201). interp: linear | smooth | cubic | monotone."""
    xs = np.asarray(xs, dtype=float)
    K = len(xs)
    q = np.asarray(q, dtype=float)
    n = len(q)
    ys = np.asarray(ys, dtype=float)
    per_row = (ys.ndim == 2)
    if K == 1:
        return ys[:, 0].copy() if per_row else np.full(n, float(ys[0]))
    rows = np.arange(n)
    idx = np.clip(np.searchsorted(xs, q) - 1, 0, K - 2)

    def gy(i):
        i = np.clip(i, 0, K - 1)
        return ys[rows, i] if per_row else ys[i]

    x0 = xs[idx]; x1 = xs[idx + 1]
    seg = np.where(x1 - x0 > 1e-12, x1 - x0, 1.0)
    lt = np.clip((q - x0) / seg, 0.0, 1.0)
    p1 = gy(idx); p2 = gy(idx + 1)
    if interp == "linear":
        return p1 + (p2 - p1) * lt
    if interp == "smooth":
        e = lt * lt * (3.0 - 2.0 * lt)
        return p1 + (p2 - p1) * e
    lt2 = lt * lt; lt3 = lt2 * lt
    if interp == "cubic":
        p0 = gy(idx - 1); p3 = gy(idx + 2)
        return 0.5 * ((2 * p1) + (-p0 + p2) * lt +
                      (2 * p0 - 5 * p1 + 4 * p2 - p3) * lt2 +
                      (-p0 + 3 * p1 - 3 * p2 + p3) * lt3)
    # monotone Hermite (Fritsch–Carlson)
    m = _fc_tangents(np, xs, ys)
    m1 = m[rows, idx] if per_row else m[idx]
    m2 = m[rows, idx + 1] if per_row else m[idx + 1]
    h00 = 2 * lt3 - 3 * lt2 + 1
    h10 = lt3 - 2 * lt2 + lt
    h01 = -2 * lt3 + 3 * lt2
    h11 = lt3 - lt2
    return h00 * p1 + h10 * seg * m1 + h01 * p2 + h11 * seg * m2


def _eval_points(np, points, params, t):
    """Control-point curve in normalized t. interp = linear | smooth | cubic | monotone."""
    interp, err = _resolve_interp(params.get("interp", "smooth"))
    if err:
        return None, err
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
    return _interp_curve(np, ts, vs, t, interp), None


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

    # blend the keyed profiles ALONG v with the SAME interp used across u (G201) — a
    # loft is one surface; interpolating u cubically but v with eased-linear is what
    # printed a terrace band at every mould row. One code path, both axes.
    interp, err = _resolve_interp(params.get("interp", "smooth"))
    if err:
        return None, err, False
    if K == 1:
        F = M[:, 0]
    else:
        F = _interp_curve(np, vpos, M, v, interp)

    # ribbon detection: does the cross-section SHAPE actually change down the array, or
    # do the profiles only translate (identical shape + a rigid offset — still a
    # developable ribbon)? Compare each profile to the first AFTER removing its mean, so
    # a pure vertical offset doesn't read as real second-curvature (G195).
    span = float(M.max() - M.min())
    Mc = M - M.mean(axis=0, keepdims=True)          # remove each column's offset
    maxdiff = 0.0
    for j in range(1, K):
        maxdiff = max(maxdiff, float(np.max(np.abs(Mc[:, j] - Mc[:, 0]))))
    ribbon = (K < 2) or (maxdiff <= 1e-6 + 1e-3 * max(span, 1e-9))
    return F, None, ribbon


TOOLS = {
}
