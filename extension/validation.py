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
_INTENT_FREE = ("z_fight", "below_floor", "degenerate", "inverted_normals",
                "non_manifold", "self_intersection")
# The one intent-laden check — suppressible only by a DECLARED intent.
_CLIPPING = "clipping"
_ALL_CHECKS = _INTENT_FREE + (_CLIPPING,)


# ── scene-scoped declared-intent registry (module global, like collab._pending) ──
# Each entry: {"check": "clipping", "a": str, "b": str, "reason": str,
#              "status": "holding"|"vanished", "source": "agent"|"human"}
# Keyed on the (check, {a,b}) RELATIONSHIP, never the bare mesh — so declaring
# Hair↔Body intended does NOT also blind a later Hair↔Hat clip.
_intents = []


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
    for e in _intents:
        if e["check"] != check:
            continue
        if (_token_matches(e["a"], x) and _token_matches(e["b"], y)) or \
           (_token_matches(e["a"], y) and _token_matches(e["b"], x)):
            return e
    return None


def _prune_dead_intents():
    """Auto-GC declarations whose object (or collection) no longer exists, so deleting a
    declared part never leaves a permanent un-clearable VANISHED tripwire (feedback P1.5)."""
    for e in list(_intents):
        for tok in (e["a"], e["b"]):
            if bpy.data.objects.get(tok) is None and bpy.data.collections.get(tok) is None:
                _intents.remove(e)
                break


def add_intent(a, b, reason, check=_CLIPPING, source="agent"):
    """Declare a clip/penetration INTENDED — a positive, falsifiable assertion carrying
    its reason verbatim. Re-declaring a pair updates its reason. Returns the entry."""
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
    record_intend(check)
    _tag_redraw()
    return {"success": True, "intent": dict(e)}


def revoke_intent(a, b, check=_CLIPPING):
    """Drop a declared intent — re-arming the finding (the human overruling: 'that clip
    is a bug, fix it'). Honest no-op error if it wasn't declared."""
    e = _find_intent(check, a, b)
    if e is None:
        return {"error": f"no declared {check} intent for {a}↔{b}"}
    _intents.remove(e)
    _tag_redraw()
    return {"success": True, "revoked": {"check": check, "a": a, "b": b}}


def list_intents():
    """The live registry — every declared assertion with its current status."""
    return [dict(e) for e in _intents]


def clear_intents():
    """Scene load wiped the world the assertions described — drop them (called from
    state.reset_history_state)."""
    _intents.clear()


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
                "intent_free": [], "clipping": _empty_clip(), "line": line}

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

    # clipping / penetration — intent-laden, DELTA-SCOPED to what this op touched.
    clip = _clipping_findings(introspect, scope, scope_names, live_names)

    passed = not intent_free and not clip["new"] and not clip["vanished"]
    line = _render_line(intent_free, clip, excluded, verbose)
    return {"off": False, "passed": passed, "excluded": excluded,
            "intent_free": intent_free, "clipping": clip, "line": line}


def _empty_clip():
    return {"declared": len([e for e in _intents if e["check"] == _CLIPPING]),
            "new": [], "vanished": [], "intended_in_scope": 0}


def _true_penetration_mm(a_name, b_name):
    """The REAL max vertex-penetration depth between two meshes, recomputed every report:
    for each sampled vert of one inside the other (signed by the nearest-face normal, the
    method `feel op=clearance` uses), the distance to that surface. This replaces
    check_contacts' interior-sample proxy, which over-reported grazes as tens of mm and
    didn't track a lift (feedback P0.2). Returns mm (0 = no real crossing)."""
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
        bvh = dst["bvh"]
        for v in src["verts"]:
            loc, normal, _idx, dist = bvh.find_nearest(v)
            if loc is None:
                continue
            if (v - loc).dot(normal) < 0.0 and dist > worst:   # v is inside dst
                worst = dist
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

    depths = {}
    for key in candidates:
        a, b = tuple(key)
        d = _true_penetration_mm(a, b)
        if d >= _CLIP_FLOOR_MM:
            depths[key] = d                          # precise true depth
        elif _min_bbox_overlap_mm(a, b) >= 1.0:
            # A real overlap the vertex sampling can't measure (matched footprints — every
            # vert sits on a coincident face). Flag it WITHOUT a number rather than drop it
            # (no false-negative) or print a wrong one (feedback P0.2): hint at clearance.
            depths[key] = None
        # else: a sub-graze the proxy used to over-report — correctly dropped.

    intended_in_scope, new = 0, []
    for key, depth in depths.items():
        a, b = tuple(key)
        e = _intent_for_pair(_CLIPPING, a, b)
        if e is not None:
            e["status"] = "holding"
            intended_in_scope += 1
        else:
            msg = f"{a}↔{b} {depth}mm" if depth is not None else \
                f"{a}↔{b} (overlap — `feel op=clearance` to measure)"
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

    _bump(_CLIPPING, len(new) > 0)
    return {"declared": len([e for e in _intents if e["check"] == _CLIPPING]),
            "new": new, "vanished": vanished, "intended_in_scope": intended_in_scope}


def _render_line(intent_free, clip, excluded, verbose=False):
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
    if cl:
        segs.append("clipping " + " · ".join(cl))
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
    """op=expect / intend — declare a clip intended (a or b may name a COLLECTION)."""
    return add_intent(params.get("a", ""), params.get("b", ""),
                      params.get("reason", ""), source="agent")


def validate_forget(params):
    """op=forget — retire a declaration (clears a stale tripwire)."""
    return revoke_intent(params.get("a", ""), params.get("b", ""))


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
