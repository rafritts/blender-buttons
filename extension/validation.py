"""SPEC-16 — the always-on correctness floor (`validate`) + forced perception (`feel`).

Two forced senses, neither opt-out (see docs/SPEC-16-agent-feedback.md):

  • validate — "what's broken." An always-on predicate that runs after every geometry
    op, scoped to the TOUCHED DELTA and its relations. Intent-free defects (z-fight,
    non-manifold, flipped normals, degenerate faces) are UNSUPPRESSABLE. Intent-laden
    checks (clipping/penetration) are governed by DECLARED intent — a positive
    assertion (`validate op=expect`), never an `ignore` — keyed on the (check,
    counterpart) RELATIONSHIP, suppressed-to-a-count (never silenced), and enforced as
    a BIDIRECTIONAL invariant (a declared-intended clip that VANISHES is also a finding).

  • feel — "what exists." A cheap perceptual delta of the touched object, no verdict.

This module owns: the validate aggregator (a thin layer over the existing detectors in
lint.py / introspect.py — it adds NO new detection logic), the declared-intent registry
(scene-scoped, module-global like collab's queue; cleared on scene load), the human
override state (global + per-mesh exclusion FROM COMPUTATION), and the cross-session
telemetry that tunes the bundles from data. The panel surface (registry view / revoke /
add / override toggles) lives in ui.py + collab.py; the agent verb in server/verbs.

DISCIPLINE: every function here runs on Blender's MAIN THREAD (the dispatch + panel
operators), so the module globals need no locking.
"""

import json
import os

import bpy

# Spatial epsilons, shared with the detectors so findings reconcile (gaps.md G107).
_EPS = 1e-4        # coplanar / below-floor (0.1 mm)
_CLIP_FLOOR_MM = 0.3   # ignore sub-0.3mm grazes (matches auto_proximity_note)

# Intent-free defect checks — there is NO suppression path for any of these.
# `non_manifold` now means 3+/0-face edges ONLY (open 1-face rims are NOT here — G129);
# `inconsistent_topology` is the χ-vs-boundary-loop invariant break (G118).
_INTENT_FREE = ("z_fight", "below_floor", "degenerate", "inverted_normals",
                "non_manifold", "self_intersection", "inconsistent_topology")
# Intent-laden checks — suppressible only by a DECLARED intent (expect).
_CLIPPING = "clipping"
# G129: an open boundary loop (plane, cup mouth, cloth) is legit geometry, not a defect.
# Declarable via expect — which arms a SEAL tripwire (a declared-open part that later
# closes is a finding). Undeclared boundaries are a quiet count, never a hard defect.
_OPEN_BOUNDARY = "open_boundary"
_ALL_CHECKS = _INTENT_FREE + (_CLIPPING, _OPEN_BOUNDARY)


# ── scene-scoped declared-intent registry (module global, like collab._pending) ──
# Each entry: {"check": "clipping", "a": str, "b": str, "reason": str,
#              "status": "holding"|"vanished", "source": "agent"|"human"}
# Keyed on the (check, {a,b}) RELATIONSHIP, never the bare mesh — so declaring
# Hair↔Body intended does NOT also blind a later Hair↔Hat clip.
_intents = []

# G218: declarations are SCENE facts, not process facts. G125 already writes the registry
# into the .blend (scene["bb_intents"]) and clear_intents() re-grounds on scene LOAD — but
# an addon reinstall/reload resets this module (fresh _intents = []) with no scene load, so
# every declaration vanished and the tripwires silently disarmed. This flag makes grounding
# LAZY: the first registry access after a module (re)load pulls the scene's stored registry
# back in. Registration-time loading is impossible (bpy.context is restricted there).
_grounded = False


def _ensure_grounded():
    global _grounded
    if _grounded:
        return
    _grounded = True
    try:
        sc = bpy.context.scene
        raw = sc.get("bb_intents") if sc is not None else None
        if raw and not _intents:
            data = json.loads(raw)
            if isinstance(data, list):
                _intents.extend(data)
    except Exception:
        pass


def _pair_key(check, a, b):
    return (check, frozenset((a, b)))


def _find_intent(check, a, b):
    """Exact (a,b) lookup — for add/revoke dedup."""
    key = _pair_key(check, a, b)
    for e in _intents:
        if _pair_key(e["check"], e["a"], e["b"]) == key:
            return e
    return None


def _token_matches(token, objname):
    """A declaration token matches an object either by exact name OR — so a single
    `expect Sprinkles↔Icing` covers a whole scatter — by COLLECTION membership when the
    token names a collection (feedback P1.5)."""
    if token == objname:
        return True
    coll = bpy.data.collections.get(token)
    if coll is not None:
        return objname in coll.all_objects
    return False


def _intent_for_pair(check, x, y):
    """Fuzzy match a live penetrating pair (x,y) against the registry, honouring the
    collection-membership tokens above. Used when classifying findings (not for dedup)."""
    _ensure_grounded()
    for e in _intents:
        if e["check"] != check:
            continue
        if (_token_matches(e["a"], x) and _token_matches(e["b"], y)) or \
           (_token_matches(e["a"], y) and _token_matches(e["b"], x)):
            return e
    return None


def _boundary_intent(objname):
    """A declared OPEN-BOUNDARY intent covering objname (G129) — exact name or a
    collection token. Single-object: stored with a==b==the part/collection."""
    _ensure_grounded()
    for e in _intents:
        if e["check"] == _OPEN_BOUNDARY and _token_matches(e["a"], objname):
            return e
    return None


def _prune_dead_intents():
    """Auto-GC declarations whose object (or collection) no longer exists, so deleting a
    declared part never leaves a permanent un-clearable VANISHED tripwire (feedback P1.5)."""
    _ensure_grounded()
    changed = False
    for e in list(_intents):
        for tok in (e["a"], e["b"]):
            if bpy.data.objects.get(tok) is None and bpy.data.collections.get(tok) is None:
                _intents.remove(e)
                changed = True
                break
    if changed:
        _persist_intents()


def add_intent(a, b, reason, check=_CLIPPING, source="agent", max_depth=None):
    """Declare a clip/penetration INTENDED — a positive, falsifiable assertion carrying
    its reason verbatim. Re-declaring a pair updates its reason. Returns the entry.

    For check=open_boundary (G129) it's a SINGLE part/collection — b defaults to a — and
    declaring it intended arms a SEAL tripwire (if the part later closes, that's a finding)."""
    _ensure_grounded()
    if check == _OPEN_BOUNDARY and not b:
        b = a
    if not a or not b:
        return {"error": "expect needs both objects (a, b) of the intended pair"}
    if not (reason or "").strip():
        return {"error": "expect needs a reason — 'I intend X to clip Y because …'. "
                         "An assertion you can't justify is a bug you're hiding."}
    e = _find_intent(check, a, b)
    if e is None:
        e = {"check": check, "a": a, "b": b, "reason": reason.strip(),
             "status": "holding", "source": source}
        _intents.append(e)
    else:
        e["reason"] = reason.strip()
        e["source"] = source
    # G119: a clipping declaration may carry a DEPTH ENVELOPE — it blesses the overlap only
    # up to max_depth (mm); anything deeper is still a finding, so a broad 'coffee↔mug
    # intended' can't also hide an 11mm base poke-through. Record the depth AT DECLARATION
    # too, so a later 'this pair is now Nx deeper than when you blessed it' tripwire can fire.
    if check == _CLIPPING:
        e["max_depth"] = max_depth
        try:
            e["depth_at_decl"] = _true_penetration_mm(a, b)
        except Exception:
            e["depth_at_decl"] = None
    record_intend(check)
    _persist_intents()
    _tag_redraw()
    return {"success": True, "intent": dict(e)}


def revoke_intent(a, b, check=_CLIPPING):
    """Drop a declared intent — re-arming the finding (the human overruling: 'that clip
    is a bug, fix it'). Honest no-op error if it wasn't declared."""
    _ensure_grounded()
    e = _find_intent(check, a, b)
    if e is None:
        return {"error": f"no declared {check} intent for {a}↔{b}"}
    _intents.remove(e)
    _persist_intents()
    _tag_redraw()
    return {"success": True, "revoked": {"check": check, "a": a, "b": b}}


def list_intents():
    """The live registry — every declared assertion with its current status."""
    _ensure_grounded()
    return [dict(e) for e in _intents]


def _persist_intents():
    """G125: write the declared-intent registry INTO the .blend (a scene custom prop) so a
    re-open doesn't drop every declaration and resurrect the noise wall it suppressed."""
    try:
        sc = bpy.context.scene
        if sc is not None:
            sc["bb_intents"] = json.dumps(_intents)
    except Exception:
        pass


def clear_intents():
    """Called on scene load (state.reset_history_state). The declarations describe a scene,
    so RE-GROUND from the loaded .blend's own stored registry (G125 — survive a reopen)
    rather than always dropping them; a fresh/empty scene just starts clean."""
    global _drift, _grounded
    _drift = 0.0
    _grounded = True
    _intents.clear()
    try:
        sc = bpy.context.scene
        raw = sc.get("bb_intents") if sc is not None else None
        if raw:
            data = json.loads(raw)
            if isinstance(data, list):
                _intents.extend(data)
    except Exception:
        pass


# ── epistemic-drift re-grounding checkpoint (SPEC-16, feedback P1.6) ──────────
# Per-op feedback is the spine; this is a periodic RE-ANCHOR on top of it. Each geometry
# op accrues "drift" weighted by how much it can invalidate the agent's mental model — a
# boolean rearranges everything, a nudge barely anything. When the accrued drift crosses a
# threshold, the next result carries a whole-scene recap (object map + the intent/tripwire
# registry) so a stale mental model re-grounds on a long build. It does NOT replace the
# act→read loop, and it never windows the hard-defect validate floor.
_drift = 0.0
_DRIFT_THRESHOLD = 100.0
_DRIFT_HIGH = {            # structural rearrangers — a lot can shift unseen
    "boolean", "apply_modifiers", "remesh", "join_objects", "noise_displace", "bend",
    "bake_shape_keys_to_basis", "separate_selection",
}
_DRIFT_MED = {             # local topology edits
    "extrude", "spin", "extrude_along_curve", "inset_faces", "loop_cut", "subdivide_selection",
    "poke_faces", "grid_fill", "bridge_handles", "delete_geometry", "field", "flute",
    "taper_end", "taper_section", "shape_profile", "relax_selection", "slide_selection",
    "merge_by_distance", "bevel", "round_corners", "smooth_edges",
}


def accrue_drift(tool):
    """Add this op's drift weight; return a re-ground recap dict (and reset) when the
    accrued drift crosses the threshold, else None."""
    global _drift
    w = 25.0 if tool in _DRIFT_HIGH else 8.0 if tool in _DRIFT_MED else 2.0
    _drift += w
    if _drift < _DRIFT_THRESHOLD:
        return None
    _drift = 0.0
    return _reground_recap()


def _reground_recap():
    """A compact whole-scene re-anchor: object map + the live intent/tripwire registry."""
    from .common import scene_mesh_objects
    objs = scene_mesh_objects()
    listed = ", ".join(o.name for o in objs[:24])
    if len(objs) > 24:
        listed += f", … (+{len(objs) - 24})"
    intents = [e for e in _intents if e["check"] == _CLIPPING]
    holding = [f"{e['a']}↔{e['b']}" for e in intents if e.get("status") == "holding"]
    vanished = [f"{e['a']}↔{e['b']}" for e in intents if e.get("status") != "holding"]
    return {
        "object_count": len(objs),
        "objects": listed,
        "declared_clips_holding": holding,
        "declared_clips_vanished": vanished,
    }


# ── human override state ──────────────────────────────────────────────────────

def is_global_off():
    """Human pulled the global floor down (a WindowManager toggle). Session-scoped."""
    wm = bpy.context.window_manager
    return bool(getattr(wm, "bb_validate_off", False)) if wm else False


def mesh_excluded(name):
    """A human per-mesh / per-collection override. EXCLUSION FROM COMPUTATION — the
    object is taken out of scope entirely (the check never runs on it), not merely
    suppressed in output, because on an 80M-quad import the cost is the CHECKING."""
    obj = bpy.data.objects.get(name)
    if obj is None:
        return False
    if obj.get("bb_no_validate"):
        return True
    # A collection-level override covers its members.
    for coll in obj.users_collection:
        if coll.get("bb_no_validate"):
            return True
    return False


# ── the validate aggregator ─────────────────────────────────────────────────

def run_validate(touched_names=None, scene_wide=False, verbose=False):
    """Run the floor over the touched delta (or the whole scene, for op=run). Returns a
    structured dict plus a pre-rendered one-line `line` for the status block. Reports BY
    EXCEPTION: clean checks collapse to counts. Adds no detection logic — it composes
    lint.check_mesh / introspect.check_contacts (+ a true-depth recompute). verbose=True
    (op=run) lists every finding instead of capping the line."""
    if is_global_off():
        return {"off": True, "scope": "global", "passed": None,
                "line": "validate: OFF (human override) — floor is down"}
    _prune_dead_intents()

    from . import lint, introspect
    from .common import scene_mesh_objects, world_bbox, eval_world_bmesh

    scene = [o for o in scene_mesh_objects()]
    excluded = [o.name for o in scene if mesh_excluded(o.name)]
    live = [o for o in scene if o.name not in excluded]
    live_names = {o.name for o in live}

    if scene_wide or not touched_names:
        scope = list(live)
    else:
        want = {n for n in touched_names if n in live_names}
        scope = [o for o in live if o.name in want]
    scope_names = {o.name for o in scope}

    if not scope:
        # All-excluded, or the op touched nothing validatable (e.g. a delete). Honest
        # empty result; surface any human exclusion so silence is never mistaken for clean.
        line = (f"validate: {len(excluded)} mesh(es) excluded (human override)"
                if excluded else "")
        return {"off": False, "passed": True, "excluded": excluded,
                "intent_free": [], "clipping": _empty_clip(),
                "open_boundary": {"declared": 0, "undeclared": [], "intended": 0, "sealed": []},
                "line": line}

    intent_free = []

    # z-fight — scoped: pairs between a touched object and ANY live mesh (so a new part
    # coplanar with an existing neighbour is caught, not just touched-vs-touched).
    for pair in lint._coplanar_pairs(live, _EPS):
        if pair["a"] in scope_names or pair["b"] in scope_names:
            intent_free.append({"check": "z_fight",
                                "message": (f"{pair['a']}↔{pair['b']} coplanar at "
                                            f"{pair['axis']}={pair['coord']} "
                                            f"({pair['overlap_mm'][0]}×{pair['overlap_mm'][1]}mm)")})
    _bump("z_fight", any(f["check"] == "z_fight" for f in intent_free))

    # per-object intent-free defects (below-floor / normals / degenerate / non-manifold /
    # self-intersection) — reuse the tested per-mesh detectors.
    cm = lint.check_mesh({"targets": list(scope_names)})
    reports = {r["object"]: r for r in cm.get("reports", [])} if cm.get("success") else {}
    for o in scope:
        xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(o)
        below = zmin < -_EPS
        _bump("below_floor", below)
        if below:
            intent_free.append({"check": "below_floor",
                                "message": f"{o.name} dips {round(-zmin * 1000, 1)}mm below z=0"})
        bm = eval_world_bmesh(o)
        inv = bm is not None and len(bm.faces) >= 8 and lint._normals_inward_fraction(bm) > 0.7
        if bm is not None:
            bm.free()
        _bump("inverted_normals", inv)
        if inv:
            intent_free.append({"check": "inverted_normals",
                                "message": f"{o.name} normals appear inverted (most face inward)"})
        r = reports.get(o.name, {})
        deg = r.get("zero_area_faces", 0)
        _bump("degenerate", bool(deg))
        if deg:
            intent_free.append({"check": "degenerate",
                                "message": f"{o.name} has {deg} zero-area face(s)"})
        nm = r.get("non_manifold_edges", 0)
        _bump("non_manifold", bool(nm))
        if nm:
            intent_free.append({"check": "non_manifold",
                                "message": f"{o.name} has {nm} non-manifold edge(s)"})
        sx = r.get("self_intersections", 0)
        _bump("self_intersection", bool(sx))
        if sx:
            intent_free.append({"check": "self_intersection",
                                "message": f"{o.name} has {sx} self-intersection(s)"})
        # G118: an impossible Euler characteristic (χ vs boundary-loop count) — the cheap,
        # decisive tell of a hollow built inside-out / a boolean gone wrong. Always a defect.
        euler_ok = r.get("euler_ok", True)
        _bump("inconsistent_topology", not euler_ok)
        if not euler_ok:
            intent_free.append({"check": "inconsistent_topology",
                                "message": (f"{o.name} has impossible topology "
                                            f"(χ={r.get('euler_characteristic')}, "
                                            f"{r.get('boundary_loops')} boundary loop(s)) — a "
                                            f"hollow/boolean likely did the opposite of intent")})

    # clipping / penetration — intent-laden, DELTA-SCOPED to what this op touched.
    clip = _clipping_findings(introspect, scope, scope_names, live_names)
    # open boundaries — G129: legit for planes/rims/cloth (quiet count), declarable, with
    # a SEAL tripwire on declared-open parts.
    ob = _open_boundary_findings(scope, reports)

    passed = (not intent_free and not clip["new"] and not clip["vanished"]
              and not clip.get("deeper") and not ob["sealed"])
    line = _render_line(intent_free, clip, ob, excluded, verbose)
    return {"off": False, "passed": passed, "excluded": excluded,
            "intent_free": intent_free, "clipping": clip, "open_boundary": ob, "line": line}


def _open_boundary_findings(scope, reports):
    """G129 — open boundary loops are NOT defects (a tabletop plane, a cup mouth, cloth).
    Report them as a quiet count, declarable via expect (check=open_boundary). A declared-
    open part that has since CLOSED is a 'sealed' finding (the bidirectional tripwire — an
    intended mouth must not silently seal)."""
    undeclared, intended, sealed = [], 0, []
    scope_names = {o.name for o in scope}
    for o in scope:
        b = reports.get(o.name, {}).get("boundary_loops", 0)
        if b <= 0:
            continue
        decl = _boundary_intent(o.name)
        if decl is not None:
            decl["status"] = "holding"
            intended += 1
        else:
            undeclared.append({"object": o.name, "loops": b})
        _bump(_OPEN_BOUNDARY, decl is None)
    # seal tripwire: a declared-open part this op touched that now has NO boundary.
    for e in _intents:
        if e["check"] != _OPEN_BOUNDARY:
            continue
        name = e["a"]
        if name in scope_names and reports.get(name, {}).get("boundary_loops", None) == 0:
            e["status"] = "vanished"
            sealed.append({"object": name, "reason": e.get("reason", "")})
    return {"declared": len([e for e in _intents if e["check"] == _OPEN_BOUNDARY]),
            "undeclared": undeclared, "intended": intended, "sealed": sealed}


def _empty_clip():
    return {"declared": len([e for e in _intents if e["check"] == _CLIPPING]),
            "new": [], "vanished": [], "deeper": [], "intended_in_scope": 0}


def _true_penetration_mm(a_name, b_name):
    """The REAL max vertex-penetration depth between two meshes, recomputed every report,
    built on introspect._signed_distance — the SAME signed nearest-surface primitive
    `feel op=clearance` uses (a bbox gate, then RAY-PARITY inside-test for a closed solid),
    so the always-on floor and clearance can never disagree (G204). The old local
    normal-sign test (a single nearest-face dot) misclassified grazes against curved /
    non-convex shells as deep crossings — it could report a penetration deeper than the
    whole mesh is thick (a 174mm 'clip' on a ~10mm hair root). Parity is robust there.
    Returns mm (0 = no real crossing)."""
    from . import introspect
    a = bpy.data.objects.get(a_name)
    b = bpy.data.objects.get(b_name)
    if a is None or b is None:
        return 0.0
    pa = introspect._prepare(a)
    pb = introspect._prepare(b)
    if pa is None or pb is None:
        return 0.0
    worst = 0.0
    for src, dst in ((pa, pb), (pb, pa)):
        for v in src["verts"]:
            sd = introspect._signed_distance(v, dst)
            if sd is not None and sd < 0.0 and -sd > worst:   # v is inside dst
                worst = -sd
    return round(worst * 1000, 1)


def _min_bbox_overlap_mm(a_name, b_name):
    """Smallest per-axis world-bbox overlap (mm), 0 if separated on any axis — the cheap
    fallback magnitude when vertex sampling can't measure a matched-footprint overlap."""
    from .common import world_bbox
    a = bpy.data.objects.get(a_name)
    b = bpy.data.objects.get(b_name)
    if a is None or b is None:
        return 0.0
    ax = world_bbox(a)
    bx = world_bbox(b)
    m = min((min(ax[i + 3], bx[i + 3]) - max(ax[i], bx[i])) for i in range(3))
    return round(m * 1000, 1) if m > 0 else 0.0


def _is_open_shell(name, cache):
    """G124 — does this mesh have any open boundary edge (1 linked face)? If so its
    inside/outside is ill-defined and BVH penetration depth against it is meaningless.
    Cached per validate run (the same pair is tested from both directions)."""
    if name in cache:
        return cache[name]
    from .common import eval_world_bmesh
    obj = bpy.data.objects.get(name)
    val = False
    if obj is not None and obj.type == 'MESH':
        bm = eval_world_bmesh(obj)
        if bm is not None:
            val = any(len(e.link_faces) == 1 for e in bm.edges)
            bm.free()
    cache[name] = val
    return val


def _clipping_findings(introspect, scope, scope_names, live_names):
    """Penetration findings, DELTA-SCOPED. check_contacts (robust bbox+gate) finds the
    candidate pairs touching this op's scope; each candidate's TRUE depth is recomputed
    and sub-graze pairs dropped. Declared pairs collapse to a count (never re-listed);
    undeclared pairs are NEW; a declared pair that this op TOUCHED and that no longer
    crosses is VANISHED (the bidirectional invariant — only for pairs we actually read)."""
    res = introspect.check_contacts({"targets": list(scope_names)})
    candidates = set()
    for c in res.get("contacts", []):
        for p in c.get("penetrating", []):
            candidates.add(frozenset((c["object"], p["other"])))

    shell_cache = {}
    depths, open_shell = {}, set()
    for key in candidates:
        a, b = tuple(key)
        # G124: the signed inside/outside test that drives penetration DEPTH is undefined
        # against a non-watertight shell (open boundary → ill-defined normals), so it
        # returns garbage magnitudes (an 84mm "clip" on a 6mm sprinkle). When either party
        # is an open shell, flag CONTACT without a fabricated number and point at clearance.
        if _is_open_shell(a, shell_cache) or _is_open_shell(b, shell_cache):
            depths[key] = None
            open_shell.add(key)
            continue
        d = _true_penetration_mm(a, b)
        if d >= _CLIP_FLOOR_MM:
            depths[key] = d                          # precise true depth
        elif _min_bbox_overlap_mm(a, b) >= 1.0:
            # A real overlap the vertex sampling can't measure (matched footprints — every
            # vert sits on a coincident face). Flag it WITHOUT a number rather than drop it
            # (no false-negative) or print a wrong one (feedback P0.2): hint at clearance.
            depths[key] = None
        # else: a sub-graze the proxy used to over-report — correctly dropped.

    intended_in_scope, new, deeper = 0, [], []
    for key, depth in depths.items():
        a, b = tuple(key)
        e = _intent_for_pair(_CLIPPING, a, b)
        if e is not None:
            # G119: a depth envelope means the declaration only covers up to max_depth — a
            # deeper clip is STILL a finding (an ignore-by-the-back-door otherwise).
            max_d = e.get("max_depth")
            if max_d is not None and depth is not None and depth > max_d + _CLIP_FLOOR_MM:
                new.append({"a": a, "b": b, "depth_mm": depth,
                            "message": f"{a}↔{b} {depth}mm EXCEEDS declared max {max_d}mm "
                                       f"(deeper than intended — fix or raise max_depth)"})
                continue
            e["status"] = "holding"
            intended_in_scope += 1
            # change tripwire: blessed once, but it's now markedly deeper than at declaration.
            d0 = e.get("depth_at_decl")
            if depth is not None and d0 and depth > 2 * d0 + 0.5:
                deeper.append({"a": a, "b": b, "now": depth, "then": d0})
        else:
            if depth is not None:
                msg = f"{a}↔{b} {depth}mm"
            elif key in open_shell:
                msg = f"{a}↔{b} (contact, depth N/A — open shell; `feel op=clearance` to measure)"
            else:
                msg = f"{a}↔{b} (overlap — `feel op=clearance` to measure)"
            new.append({"a": a, "b": b, "depth_mm": depth, "message": msg})

    # Bidirectional invariant — but ONLY for declared OBJECT pairs this op touched (in
    # scope). A pair the op never read tells us nothing, so it must NOT print VANISHED
    # (feedback P0.1). Collection-scoped declarations don't vanish (too broad).
    vanished = []
    for e in _intents:
        if e["check"] != _CLIPPING:
            continue
        a, b = e["a"], e["b"]
        is_obj_pair = (bpy.data.objects.get(a) is not None and
                       bpy.data.objects.get(b) is not None)
        touched = a in scope_names or b in scope_names
        if (is_obj_pair and touched and a in live_names and b in live_names
                and frozenset((a, b)) not in depths):
            e["status"] = "vanished"
            vanished.append({"a": a, "b": b, "reason": e["reason"]})

    # G125: when many NEW clips all hit ONE surface, it's almost always a settled scatter
    # (N instances resting on one substrate). Offer the collection-level declaration that
    # collapses the whole class, instead of leaving the agent to declare them one by one.
    hint = None
    if len(new) >= 6:
        counts = {}
        for n in new:
            counts[n["a"]] = counts.get(n["a"], 0) + 1
            counts[n["b"]] = counts.get(n["b"], 0) + 1
        common, c = max(counts.items(), key=lambda kv: kv[1])
        if c >= 6:
            hint = (f"{c} of these clips involve '{common}' — if it's a settled scatter, "
                    f"group the instances and validate op=expect <collection>↔{common} "
                    f"(or *↔{common}) to declare the whole class at once")

    _bump(_CLIPPING, len(new) > 0)
    return {"declared": len([e for e in _intents if e["check"] == _CLIPPING]),
            "new": new, "vanished": vanished, "deeper": deeper,
            "intended_in_scope": intended_in_scope, "hint": hint}


def _render_line(intent_free, clip, ob, excluded, verbose=False):
    """Compact, report-by-exception status line. Clean ⇒ a short reassurance (so
    silence-because-clean is explicit, never absent). Clips collapse to a COUNT by
    default; only the NEW delta is listed. verbose lists everything (op=run)."""
    cap = 999 if verbose else 4
    segs = []
    by_check = {}
    for f in intent_free:
        by_check.setdefault(f["check"], []).append(f["message"])
    for check in _INTENT_FREE:
        msgs = by_check.get(check)
        if msgs:
            shown = "; ".join(msgs[:cap])
            more = "" if verbose or len(msgs) <= cap else f" …(+{len(msgs) - cap})"
            segs.append(f"{check} {len(msgs)}: {shown}{more}")
    # clipping: declared collapses to a count; only the NEW delta is listed.
    cl = []
    if clip["declared"]:
        cl.append(f"{clip['declared']} intended")
    if clip["new"]:
        shown = ", ".join(n["message"] for n in clip["new"][:cap])
        more = "" if verbose or len(clip["new"]) <= cap else \
            f" …(+{len(clip['new']) - cap}; validate op=run verbose to list)"
        cl.append(f"{len(clip['new'])} new: {shown}{more}")
    for v in clip["vanished"][:cap]:
        cl.append(f"VANISHED {v['a']}↔{v['b']} (declared intended — confirm or clear)")
    for d in clip.get("deeper", [])[:cap]:
        cl.append(f"DEEPER {d['a']}↔{d['b']} {d['now']}mm now vs {d['then']}mm at declaration "
                  f"(intended pair changed — re-confirm)")
    if cl:
        segs.append("clipping " + " · ".join(cl))
    if clip.get("hint"):
        segs.append("↳ " + clip["hint"])
    # G129: open boundaries — a quiet count (NOT a defect; doesn't fail the floor), plus
    # the loud SEAL tripwire on declared-open parts that have closed.
    if ob:
        for s in ob.get("sealed", [])[:cap]:
            segs.append(f"SEALED {s['object']} (declared open — now CLOSED; confirm or clear)")
        und = ob.get("undeclared", [])
        if und:
            shown = ", ".join(f"{u['object']}({u['loops']})" for u in und[:cap])
            more = "" if verbose or len(und) <= cap else f" …(+{len(und) - cap})"
            note = (f"open_boundary {len(und)}: {shown}{more} — intended for a plane/rim/"
                    f"cloth? validate op=expect check=open_boundary to declare")
            segs.append(note)
        if ob.get("declared"):
            segs.append(f"{ob['declared']} boundary intended")
    excl = f"  [{len(excluded)} excluded]" if excluded else ""
    if not segs:
        return f"validate: clean{excl}"
    return "validate: " + " | ".join(segs) + excl


# ── ambient feel delta ─────────────────────────────────────────────────────

def feel_delta(focus_name):
    """A cheap perceptual note on the object the op just touched — counts + world dims.
    No verdict; it is the floor of perception (the agent can't opt out of seeing its own
    work). Delta-scoped: only the touched object, never the untouched scene."""
    obj = bpy.data.objects.get(focus_name) if focus_name else None
    if obj is None or obj.type != 'MESH' or obj.data is None:
        return None
    me = obj.data
    from .common import world_bbox
    xmin, ymin, zmin, xmax, ymax, zmax = world_bbox(obj)
    dims = f"{round(xmax - xmin, 3)}×{round(ymax - ymin, 3)}×{round(zmax - zmin, 3)}m"
    return (f"feel: {obj.name} — {len(me.vertices)}v {len(me.edges)}e "
            f"{len(me.polygons)}f · dims {dims}")


# ── telemetry (cross-session, tunes the bundles from data) ──────────────────

_telemetry = {
    # validate: per check, runs / findings (yield) + intend declarations.
    "validate": {},
    # feel: per perceptual op, how often the agent excluded it / it auto-skipped.
    "feel": {},
}
_tele_dirty = 0


def _vt(check):
    return _telemetry["validate"].setdefault(check, {"runs": 0, "findings": 0, "intend": 0})


def _bump(check, found):
    rec = _vt(check)
    rec["runs"] += 1
    if found:
        rec["findings"] += 1
    _mark_dirty()


def record_intend(check):
    _vt(check)["intend"] += 1
    _save()   # an explicit declaration is rare + worth persisting immediately


def record_feel(excluded=(), auto_skipped=()):
    fe = _telemetry["feel"]
    for op in excluded:
        fe.setdefault(op, {"excluded": 0, "auto_skipped": 0})["excluded"] += 1
    for op in auto_skipped:
        fe.setdefault(op, {"excluded": 0, "auto_skipped": 0})["auto_skipped"] += 1
    _mark_dirty()


def stats():
    """Ranked telemetry for tuning the bundles. validate ⇒ finding-yield (the strong
    signal: a check that has surfaced ZERO findings across many runs is pure cost) +
    intend-rate. feel ⇒ exclusion-rate. Persisted across sessions."""
    _save()
    val = []
    for check, r in _telemetry["validate"].items():
        runs = r["runs"] or 0
        val.append({"check": check, "runs": runs, "findings": r["findings"],
                    "yield": round(r["findings"] / runs, 4) if runs else None,
                    "intend": r["intend"]})
    val.sort(key=lambda d: (d["yield"] if d["yield"] is not None else -1), reverse=True)
    feel = []
    for op, r in _telemetry["feel"].items():
        feel.append({"op": op, "excluded": r["excluded"], "auto_skipped": r["auto_skipped"]})
    feel.sort(key=lambda d: d["excluded"], reverse=True)
    return {"success": True, "validate": val, "feel": feel}


# ── persistence (cross-session telemetry; the ~/-rooted idiom, cf. designs.py) ──

def _state_path():
    d = os.path.expanduser("~/.blender-buttons")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "spec16_telemetry.json")


def _mark_dirty():
    global _tele_dirty
    _tele_dirty += 1
    if _tele_dirty >= 20:     # throttle disk writes; flush on read (stats) regardless
        _save()


def _save():
    global _tele_dirty
    try:
        with open(_state_path(), "w") as fh:
            json.dump(_telemetry, fh)
        _tele_dirty = 0
    except OSError:
        pass


def load():
    """Load persisted telemetry at addon register. Best-effort: a missing/corrupt file
    just starts fresh."""
    global _telemetry
    try:
        with open(_state_path()) as fh:
            data = json.load(fh)
        if isinstance(data, dict) and "validate" in data and "feel" in data:
            _telemetry = data
    except (OSError, ValueError):
        pass


def _tag_redraw():
    try:
        from .collab import tag_redraw
        tag_redraw()
    except Exception:
        pass


# ── socket-addressable ops (the agent verb routes here) ─────────────────────

def validate_run(params):
    """op=run — the on-demand full sweep (scene-wide, not delta-scoped). verbose lists
    every finding (no cap)."""
    touched = params.get("targets")
    if isinstance(touched, str) and touched:
        touched = [s.strip() for s in touched.split(",")]
    elif isinstance(touched, str):
        touched = None
    return {"success": True, **run_validate(touched, scene_wide=not touched,
                                            verbose=bool(params.get("verbose")))}


def validate_expect(params):
    """op=expect / intend — declare a clip intended (a or b may name a COLLECTION), OR an
    open boundary intended (check=open_boundary, a single part/collection — G129)."""
    check = (params.get("check") or _CLIPPING).strip()
    md = params.get("max_depth")
    return add_intent(params.get("a", ""), params.get("b", ""),
                      params.get("reason", ""), check=check, source="agent",
                      max_depth=(float(md) if md not in (None, "", 0) else None))


def validate_forget(params):
    """op=forget — retire a declaration (clears a stale tripwire)."""
    check = (params.get("check") or _CLIPPING).strip()
    return revoke_intent(params.get("a", ""), params.get("b", ""), check=check)


def validate_intended(params):
    """op=intended — list the live registry."""
    return {"success": True, "intents": list_intents(),
            "global_off": is_global_off()}


def validate_stats(params):
    return stats()


def feel_telemetry(params):
    """op (feel side) — record which perceptual reads a `feel op=all` call excluded /
    auto-skipped, so the bundle defaults can be tuned from data."""
    record_feel(excluded=params.get("excluded") or (),
                auto_skipped=params.get("auto_skipped") or ())
    return {"success": True}


TOOLS = {
    "validate_run": validate_run,
    "validate_expect": validate_expect,
    "validate_forget": validate_forget,
    "validate_intended": validate_intended,
    "validate_stats": validate_stats,
    "feel_telemetry": feel_telemetry,
}
