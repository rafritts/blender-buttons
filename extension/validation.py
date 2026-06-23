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
    key = _pair_key(check, a, b)
    for e in _intents:
        if _pair_key(e["check"], e["a"], e["b"]) == key:
            return e
    return None


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

def run_validate(touched_names=None, scene_wide=False):
    """Run the floor over the touched delta (or the whole scene, for op=run). Returns a
    structured dict plus a pre-rendered one-line `line` for the status block. Reports BY
    EXCEPTION: clean checks collapse to counts. Adds no detection logic — it composes
    lint.validate_scene / lint.check_mesh / introspect.check_contacts."""
    if is_global_off():
        return {"off": True, "scope": "global", "passed": None,
                "line": "validate: OFF (human override) — floor is down"}

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

    # clipping / penetration — intent-laden. Run check_contacts on the scope; each
    # penetrating pair is checked against the declared-intent registry.
    clip = _clipping_findings(introspect, scope, live_names)

    passed = not intent_free and not clip["new"] and not clip["vanished"]
    line = _render_line(intent_free, clip, excluded)
    return {"off": False, "passed": passed, "excluded": excluded,
            "intent_free": intent_free, "clipping": clip, "line": line}


def _empty_clip():
    return {"intended": 0, "new": [], "vanished": [], "clean": 0, "intended_pairs": []}


def _clipping_findings(introspect, scope, live_names):
    """Penetration findings split by the declared-intent registry: intended pairs
    collapse to a count; undeclared pairs are NEW findings; declared-intended pairs
    that are no longer penetrating are VANISHED findings (the bidirectional invariant)."""
    scope_names = [o.name for o in scope]
    res = introspect.check_contacts({"targets": scope_names})
    # Current penetrating pairs (normalised, deduped) involving the scope.
    current = {}   # frozenset({a,b}) -> depth_mm
    for c in res.get("contacts", []):
        a = c["object"]
        for p in c.get("penetrating", []):
            key = frozenset((a, p["other"]))
            current[key] = max(current.get(key, 0.0), p["depth_mm"])

    intended_now, new = [], []
    for key, depth in current.items():
        a, b = tuple(key) if len(key) == 2 else (next(iter(key)), next(iter(key)))
        e = _find_intent(_CLIPPING, a, b)
        if e is not None:
            e["status"] = "holding"
            intended_now.append({"a": a, "b": b, "depth_mm": depth})
        else:
            new.append({"a": a, "b": b, "depth_mm": depth, "message": f"{a}↔{b} {depth}mm"})

    # Bidirectional: a declared-intended pair that is NOT currently penetrating — but only
    # when BOTH its objects are still live (a deleted/excluded object isn't a vanished clip).
    vanished = []
    for e in _intents:
        if e["check"] != _CLIPPING:
            continue
        key = frozenset((e["a"], e["b"]))
        if e["a"] in live_names and e["b"] in live_names and key not in current:
            e["status"] = "vanished"
            vanished.append({"a": e["a"], "b": e["b"], "reason": e["reason"]})

    found = len(new) > 0
    _bump(_CLIPPING, found)
    clean = max(0, len(scope_names) - len({n for k in current for n in k}))
    return {"intended": len(intended_now), "intended_pairs": intended_now,
            "new": new, "vanished": vanished, "clean": clean}


def _render_line(intent_free, clip, excluded):
    """Compact, report-by-exception status line. Clean ⇒ a short reassurance (so
    silence-because-clean is explicit, never absent)."""
    segs = []
    # intent-free, grouped by check with a count.
    by_check = {}
    for f in intent_free:
        by_check.setdefault(f["check"], []).append(f["message"])
    for check in _INTENT_FREE:
        msgs = by_check.get(check)
        if msgs:
            segs.append(f"{check} {len(msgs)}: " + "; ".join(msgs[:3]))
    # clipping: intended collapses to a count; NEW + VANISHED surface.
    cl = []
    if clip["intended"]:
        pairs = ", ".join(f"{p['a']}↔{p['b']}" for p in clip["intended_pairs"][:4])
        cl.append(f"{clip['intended']} intended ({pairs})")
    for n in clip["new"][:4]:
        cl.append(f"NEW {n['message']}")
    for v in clip["vanished"][:4]:
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
    """op=run — the on-demand full sweep (scene-wide, not delta-scoped)."""
    touched = params.get("targets")
    if isinstance(touched, str) and touched:
        touched = [s.strip() for s in touched.split(",")]
    elif isinstance(touched, str):
        touched = None
    return {"success": True, **run_validate(touched, scene_wide=not touched)}


def validate_expect(params):
    """op=expect / intend — declare a clip intended."""
    return add_intent(params.get("a", ""), params.get("b", ""),
                      params.get("reason", ""), source="agent")


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
    "validate_intended": validate_intended,
    "validate_stats": validate_stats,
    "feel_telemetry": feel_telemetry,
}
