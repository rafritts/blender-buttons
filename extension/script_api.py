"""SPEC-23 — Script runner (experimental v0).

Transport over the existing verb/tool surface: ordered multi-step runs that call
the same `execute_command` path as MCP (placement DSL, auto-feel, auto-validate).

Gears:
  • batch  — ordered list of verb/tool steps (primary bulk path)
  • exec   — short Python body with a `buttons` DSL in scope
  • dry_run — resolve/bind/budget only, no mutation

Hard step cap: 25. Progressive bulk is the point — see docs/SPEC-23-script-runner.md.
"""

from __future__ import annotations

import time
import traceback

import bpy

from . import history as history_mod
from . import state
from . import validation

# ── product constants (SPEC-23 §6.4) ─────────────────────────────────────────
HARD_STEP_CAP = 25
MAX_CODE_BYTES = 64 * 1024

# Intent-free defects abort by default; undeclared clips warn (strict promotes).
# G231: abort only on findings INTRODUCED by a step, not pre-existing leftovers.
_INTENT_FREE_CHECKS = frozenset(validation._INTENT_FREE)


def _intent_free_keys(vres):
    """Stable (check, message) keys for a validate result's intent-free list."""
    if not isinstance(vres, dict):
        return set()
    return {(f.get("check"), f.get("message") or f.get("check"))
            for f in (vres.get("intent_free") or [])}

# Tools that must not nest (the runner itself).
_SCRIPT_TOOLS = frozenset({"script_batch", "script_exec", "script_dry_run"})

# Module-global: True while a batch/exec is on the stack (nested refuse).
_in_script = False


class Abort(Exception):
    """Script-authored stop — raised from buttons.Abort(msg) or the runner."""

    def __init__(self, message="aborted"):
        super().__init__(message)
        self.message = str(message)


class Handle:
    """Structured return from a mutating DSL call. `.name` is the object handle."""

    __slots__ = ("ok", "name", "names", "bounds", "dims", "validate", "warnings",
                 "flag", "raw", "result")

    def __init__(self, raw, focus=None, flag="ok"):
        self.raw = raw if isinstance(raw, dict) else {"error": str(raw)}
        self.result = self.raw
        self.ok = bool(self.raw.get("success")) and "error" not in self.raw
        self.flag = flag
        self.name = focus or _focus_from_result(self.raw) or ""
        names = _names_from_result(self.raw)
        self.names = names
        if not self.name and names:
            self.name = names[0]
        st = self.raw.get("blender_status") or {}
        self.bounds = st.get("world_bounds") or self.raw.get("world_bounds")
        self.dims = st.get("dimensions") or self.raw.get("dimensions")
        self.validate = self.raw.get("validate")
        warns = list(self.raw.get("warnings") or [])
        if self.raw.get("no_op_warning"):
            warns.append(self.raw["no_op_warning"])
        if self.raw.get("topology_delta_warning"):
            warns.append(self.raw["topology_delta_warning"])
        if self.raw.get("bind_warning"):
            warns.append(self.raw["bind_warning"])
        self.warnings = warns

    def __repr__(self):
        return f"Handle(name={self.name!r}, ok={self.ok}, flag={self.flag})"

    def get(self, key, default=None):
        """Dict-like access for feel/validate-shaped returns."""
        return self.raw.get(key, default)


# ── verb → tool thin map (SPEC-23: full surface via tool= escape; verbs for house style)

_ADD_TYPE_TO_TOOL = {
    "box": "add_box",
    "plane": "add_plane",
    "cylinder": "add_cylinder",
    "sphere": "add_sphere",
    "cone": "add_cone",
    "torus": "add_torus",
    "icosphere": "add_icosphere",
    "circle": "add_circle",
    "grid": "add_grid",
    "lattice": "add_lattice",
    "text": "add_text",
    "curve": "add_curve",
    "light": "add_light",
    "camera": "add_camera",
}

# transform op → (tool, optional param renames)
_TRANSFORM_OP_TO_TOOL = {
    "nudge": "nudge",
    "place": "place",
    "move_to": "move_to",
    "rotate_to": "rotate_to",
    "aim_axis": "aim_axis",
    "rest_on": "rest_on",
    "seat": "seat_into",
    "resize": "resize",
    "scale": "scale_group",
    "rotate": "rotate_object",
    "apply": "apply_transform",
    "snap": "snap_to",
    "snap_grid": "snap_to_grid",
}

_MATERIAL_OP_TO_TOOL = {
    "set": "set_material",
    "assign": "assign_material",
    "image": "bind_image",
    "shade_smooth": "shade_smooth",
    "shade_flat": "shade_flat",
}

_VALIDATE_OP_TO_TOOL = {
    "run": "validate_run",
    "expect": "validate_expect",
    "intend": "validate_expect",
    "forget": "validate_forget",
    "intended": "validate_intended",
    "stats": "validate_stats",
}

# Common edit ops that map 1:1 to tool names (experimental subset; use tool= for rest)
_EDIT_OP_TO_TOOL = {
    "bevel": "bevel",
    "extrude": "extrude",
    "boolean": "boolean",
    "loop_cut": "loop_cut",
    "subdivide": "subdivide_selection",
    "delete": "delete_geometry",
    "separate": "separate_selection",
    "merge": "merge_by_distance",
    "symmetrize": "symmetrize",
    "mark_sharp": "mark_sharp",
    "bend": "bend",
    "spin": "spin",
    "bridge": "bridge_handles",
    "grab": "move_vertices",
    "scale": "scale_vertices",
    "shrink_fatten": "shrink_fatten",
    "randomize": "jitter_vertices",
    "recalc_normals": "recalc_normals",
    "inset": "inset",
    "poke": "poke",
    "smooth": "smooth_vertices",
    "bisect": "bisect",
    "to_sphere": "to_sphere",
    "triangulate": "triangulate",
    "tris_to_quads": "tris_to_quads",
}


def resolve_step(step):
    """Turn a batch step dict into (tool, params, verb, op, error).

    Accepted shapes:
      {"tool": "add_box", "params": {...}}
      {"verb": "add", "params": {"type": "box", ...}}
      {"verb": "transform", "op": "snap", "params": {...}}
      {"verb": "add", "type": "box", "name": "...", ...}  # flat params
    """
    if not isinstance(step, dict):
        return None, None, None, None, "step must be a dict"

    # Direct tool path — full surface escape.
    if step.get("tool"):
        tool = str(step["tool"]).strip()
        params = dict(step.get("params") or {})
        # Allow flat keys alongside params=
        for k, v in step.items():
            if k not in ("tool", "params", "verb", "op", "type") and k not in params:
                params[k] = v
        return tool, params, None, None, None

    verb = (step.get("verb") or "").strip().lower()
    if not verb:
        return None, None, None, None, "step needs verb= or tool="

    # Params: explicit params= wins; remaining keys (minus meta) are merged in.
    params = dict(step.get("params") or {})
    for k, v in step.items():
        if k not in ("verb", "op", "type", "params", "tool") and k not in params:
            params[k] = v

    op = (step.get("op") or params.pop("op", None) or "").strip().lower() if (
        step.get("op") or params.get("op")
    ) else ""
    # type for add may live at top level or in params
    if "type" in step and "type" not in params:
        params["type"] = step["type"]

    if verb == "add":
        ptype = str(params.pop("type", "") or "").strip().lower()
        if not ptype:
            return None, None, verb, None, "add needs type= (box|cylinder|…)"
        tool = _ADD_TYPE_TO_TOOL.get(ptype)
        if not tool:
            return None, None, verb, ptype, (
                f"add type={ptype!r} unknown. Valid: {sorted(_ADD_TYPE_TO_TOOL)}"
            )
        # rot_x/y/z → rotation list some tools accept as separate fields already
        return tool, params, verb, ptype, None

    if verb == "transform":
        if not op:
            return None, None, verb, None, "transform needs op="
        tool = _TRANSFORM_OP_TO_TOOL.get(op)
        if not tool:
            return None, None, verb, op, (
                f"transform op={op!r} not in v0 map "
                f"({sorted(_TRANSFORM_OP_TO_TOOL)}); use tool=<name> for others"
            )
        # rotate_to: deg_x/y/z → x/y/z
        if op == "rotate_to":
            for src, dst in (("deg_x", "x"), ("deg_y", "y"), ("deg_z", "z")):
                if src in params and dst not in params:
                    params[dst] = params.pop(src)
                elif src in params:
                    params.pop(src)
        return tool, params, verb, op, None

    if verb == "material":
        if not op:
            return None, None, verb, None, "material needs op="
        tool = _MATERIAL_OP_TO_TOOL.get(op)
        if not tool:
            return None, None, verb, op, (
                f"material op={op!r} not in v0 map "
                f"({sorted(_MATERIAL_OP_TO_TOOL)}); use tool=<name>"
            )
        return tool, params, verb, op, None

    if verb == "validate":
        if not op:
            op = "run"
        tool = _VALIDATE_OP_TO_TOOL.get(op)
        if not tool:
            return None, None, verb, op, (
                f"validate op={op!r} unknown. Valid: {sorted(_VALIDATE_OP_TO_TOOL)}"
            )
        return tool, params, verb, op, None

    if verb == "edit":
        if not op:
            return None, None, verb, None, "edit needs op="
        tool = _EDIT_OP_TO_TOOL.get(op)
        if not tool:
            return None, None, verb, op, (
                f"edit op={op!r} not in v0 map "
                f"({sorted(_EDIT_OP_TO_TOOL)}); use tool=<name> for full surface"
            )
        return tool, params, verb, op, None

    if verb == "feel":
        # v0: only a few high-value feels; rest via tool=
        if not op:
            op = "resting"
        feel_map = {
            "resting": "check_resting",
            "contacts": "check_contacts",
            "clearance": "check_clearance",
            "distance": "distance_between",
            "gap": "gap_between",
            "mesh": "check_mesh",
            "topology": "get_topology",
        }
        tool = feel_map.get(op)
        if not tool:
            return None, None, verb, op, (
                f"feel op={op!r} not in v0 map ({sorted(feel_map)}); use tool=<name>"
            )
        return tool, params, verb, op, None

    if verb == "object":
        # thin: rename / delete / duplicate common
        obj_map = {
            "rename": "rename_object",
            "delete": "delete_object",
            "duplicate": "duplicate_object",
            "join": "join_objects",
        }
        if not op:
            return None, None, verb, None, "object needs op="
        tool = obj_map.get(op)
        if not tool:
            return None, None, verb, op, (
                f"object op={op!r} not in v0 map ({sorted(obj_map)}); use tool=<name>"
            )
        return tool, params, verb, op, None

    return None, None, verb, op or None, (
        f"verb={verb!r} not in v0 map "
        f"(add|transform|edit|material|validate|feel|object). "
        f"Use tool=<extension_tool_name> for full surface."
    )


def _focus_from_result(result):
    if not isinstance(result, dict):
        return None
    explicit = result.get("status_focus")
    if isinstance(explicit, str) and explicit:
        return explicit
    for key in ("moved", "rotated", "resized", "scaled", "aimed", "applied_to",
                "assigned_to", "placed", "rested", "object_name", "objects",
                "renamed", "created"):
        v = result.get(key)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, str) and first:
                return first
            if isinstance(first, dict) and isinstance(first.get("name"), str):
                return first["name"]
    st = result.get("blender_status") or {}
    if st.get("active_object"):
        return st["active_object"]
    return None


def _names_from_result(result):
    if not isinstance(result, dict):
        return []
    out = []
    for key in ("object_name", "created", "moved", "objects", "assigned_to",
                "placed", "resized", "rotated"):
        v = result.get(key)
        if isinstance(v, str) and v:
            out.append(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict) and item.get("name"):
                    out.append(item["name"])
    # dedupe preserve order
    seen = set()
    uniq = []
    for n in out:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def _placement_echo(params):
    if not isinstance(params, dict):
        return None
    on = params.get("on")
    if isinstance(on, dict):
        return on
    return None


def _absolute_placement(params):
    on = _placement_echo(params)
    if not isinstance(on, dict):
        return False
    return "at" in on


def _classify_step(tool, result, strict=False, baseline_if=None):
    """Return (flag, findings_list, should_abort, abort_reason).

    flag: ok | warn | fail

    G231 / SPEC-23 §5.6: abort on intent-free defects INTRODUCED by the step.
    Pre-existing scene leftovers (same check+message as the pre-script baseline)
    stay visible on the final validate line, not fatal to an unrelated batch.
    """
    findings = []
    baseline_if = baseline_if or set()
    if not isinstance(result, dict):
        return "fail", [{"kind": "error", "message": str(result)}], True, str(result)

    if result.get("error") or result.get("success") is False:
        err = result.get("error") or "tool returned success=false"
        return "fail", [{"kind": "error", "message": err}], True, err

    v = result.get("validate")
    if isinstance(v, dict) and not v.get("off"):
        for f in (v.get("intent_free") or []):
            key = (f.get("check"), f.get("message") or f.get("check"))
            if key in baseline_if:
                continue
            findings.append({
                "kind": "intent_free",
                "check": f.get("check"),
                "message": f.get("message") or f.get("check"),
            })
        clip = v.get("clipping") or {}
        for f in (clip.get("new") or []):
            findings.append({
                "kind": "undeclared_clip",
                "message": f.get("message") or str(f),
                "pair": [f.get("a"), f.get("b")],
            })
        for f in (clip.get("vanished") or []):
            findings.append({
                "kind": "clip_vanished",
                "message": f.get("message") or str(f),
            })

    intent_free = [f for f in findings if f["kind"] == "intent_free"]
    clips = [f for f in findings if f["kind"] == "undeclared_clip"]

    if intent_free:
        msg = intent_free[0]["message"]
        return "fail", findings, True, f"intent-free defect: {msg}"

    if clips and strict:
        msg = clips[0]["message"]
        return "fail", findings, True, f"undeclared clip (strict): {msg}"

    if findings:
        return "warn", findings, False, None

    return "ok", findings, False, None


def _journal_line(entry):
    """Compact one-line journal entry for pretty-print."""
    i = entry["i"]
    vo = entry.get("verb_op") or entry.get("tool") or "?"
    focus = entry.get("focus") or "—"
    flag = entry.get("flag") or "?"
    dims = entry.get("dims")
    bounds = entry.get("bounds") or {}
    note_parts = []
    if entry.get("placement"):
        pl = entry["placement"]
        # short echo
        bits = []
        for k in ("on", "under", "left_of", "right_of", "in_front_of", "behind",
                  "centered_on", "on_floor", "align", "gap"):
            if k in pl:
                bits.append(f"{k}={pl[k]}")
        if bits:
            note_parts.append(" ".join(str(b) for b in bits))
    if entry.get("absolute_placement"):
        note_parts.append("absolute_placement")
    if entry.get("via_bpy"):
        note_parts.append("via=bpy")
    if entry.get("note"):
        note_parts.append(entry["note"])
    if flag in ("fail", "warn") and entry.get("findings"):
        note_parts.append(entry["findings"][0].get("message", "")[:60])

    dim_s = "—"
    if dims:
        dim_s = f"[{dims[0]:.3f}, {dims[1]:.3f}, {dims[2]:.3f}]"
    elif bounds.get("z"):
        z = bounds["z"]
        dim_s = f"z=[{z[0]:.3f}, {z[1]:.3f}]"

    note = "   " + " ".join(note_parts) if note_parts else ""
    return f"  {i:2d}  {vo:<18}  {focus:<12}  {flag:<4}  {dim_s}{note}"


def _scene_names():
    return set(o.name for o in bpy.context.scene.objects)


class _Runner:
    """Shared execution state for one batch/exec run."""

    def __init__(self, label, on_error="abort", validate_scope="touched",
                 verbose=False, strict=False, mode="batch"):
        self.label = label or mode
        self.on_error = on_error if on_error in ("abort", "continue") else "abort"
        self.validate_scope = validate_scope if validate_scope in ("touched", "scene") else "touched"
        self.verbose = bool(verbose)
        self.strict = bool(strict)
        self.mode = mode
        self.journal = []
        self.findings = []
        self.created = []
        self.touched = []
        self.deleted = []
        self.via_bpy = False
        self.step_count = 0
        self.first_failure = None
        self.ok_n = 0
        self.warn_n = 0
        self.fail_n = 0
        self.checkpoints = []
        self._names_before = _scene_names()
        self._hist_before = len(state._history)
        self._t0 = time.monotonic()
        # G231: snapshot intent-free findings already in the scene so a leftover
        # degenerate / z-fight cannot abort an unrelated later phase.
        try:
            self._baseline_if = _intent_free_keys(
                validation.run_validate(None, scene_wide=True))
        except Exception:
            self._baseline_if = set()

    def check_budget(self, upcoming=1):
        if self.step_count + upcoming > HARD_STEP_CAP:
            return (
                f"rejected_budget: hard step cap is {HARD_STEP_CAP} "
                f"(would be {self.step_count + upcoming}). "
                f"Split into phase-sized batches and read the receipt between them."
            )
        return None

    def run_tool(self, tool, params, verb=None, op=None, via_bpy=False):
        """Execute one tool via nested execute_command. Returns Handle."""
        # Late import avoids circular import at module load.
        from . import server as bb_server

        if tool in _SCRIPT_TOOLS:
            raise Abort(f"nested script tools are not allowed ({tool})")

        budget_err = self.check_budget(1)
        if budget_err:
            raise Abort(budget_err)

        self.step_count += 1
        params = dict(params or {})
        # Drop None values so tools see "unset"
        params = {k: v for k, v in params.items() if v is not None}

        result = bb_server.execute_command({
            "tool": tool,
            "params": params,
            "label": f"script:{self.label}#{self.step_count}",
        })
        if not isinstance(result, dict):
            result = {"error": str(result), "success": False}

        flag, findings, should_abort, abort_reason = _classify_step(
            tool, result, strict=self.strict, baseline_if=self._baseline_if
        )
        focus = _focus_from_result(result)
        names = _names_from_result(result)
        st = result.get("blender_status") or {}
        dims = st.get("dimensions") or result.get("dimensions")
        bounds = st.get("world_bounds") or result.get("world_bounds")
        placement = _placement_echo(params)

        # Track created/touched/deleted by scene delta + result names
        names_now = _scene_names()
        new = sorted(names_now - self._names_before - set(self.created))
        gone = sorted((self._names_before | set(self.created)) - names_now)
        for n in new:
            if n not in self.created:
                self.created.append(n)
        for n in gone:
            if n not in self.deleted:
                self.deleted.append(n)
        for n in names + new + ([focus] if focus else []):
            if n and n not in self.touched and n not in self.deleted:
                self.touched.append(n)

        if via_bpy:
            self.via_bpy = True

        verb_op = None
        if verb and op:
            verb_op = f"{verb}/{op}"
        elif verb:
            verb_op = verb
        else:
            verb_op = tool

        entry = {
            "i": self.step_count,
            "tool": tool,
            "verb": verb,
            "op": op,
            "verb_op": verb_op,
            "focus": focus,
            "flag": flag,
            "dims": dims,
            "bounds": bounds,
            "placement": placement,
            "absolute_placement": _absolute_placement(params),
            "validate": result.get("validate"),
            "findings": findings,
            "via_bpy": via_bpy,
            "note": None,
        }
        if flag == "fail" and abort_reason:
            entry["note"] = abort_reason
        if self.verbose:
            entry["raw"] = result

        self.journal.append(entry)
        self.findings.extend(findings)

        if flag == "ok":
            self.ok_n += 1
        elif flag == "warn":
            self.warn_n += 1
        else:
            self.fail_n += 1

        if flag == "fail" and self.first_failure is None:
            self.first_failure = {
                "i": self.step_count,
                "tool": tool,
                "verb_op": verb_op,
                "focus": focus,
                "error": abort_reason or (findings[0]["message"] if findings else "fail"),
                "bounds": bounds,
                "dims": dims,
            }

        handle = Handle(result, focus=focus, flag=flag)

        if should_abort and self.on_error == "abort":
            raise Abort(abort_reason or "step failed")

        return handle

    def checkpoint(self, label, focus=None):
        """Force a full status + validate into the receipt."""
        from . import status as status_mod

        sp = {"focus": focus} if focus else {}
        st = status_mod.get_blender_status(sp).get("status")
        touched = list(self.touched) if self.validate_scope == "touched" else None
        if self.validate_scope == "scene":
            vres = validation.run_validate(None, scene_wide=True)
        else:
            vres = validation.run_validate(touched)
        cp = {
            "label": label,
            "focus": focus or (st or {}).get("active_object"),
            "status": st,
            "validate": vres,
        }
        self.checkpoints.append(cp)
        return cp

    def transactional_restore(self):
        """Undo every history step pushed during this run."""
        n = len(state._history) - self._hist_before
        if n <= 0:
            return {"restored": False, "steps": 0, "note": "nothing to undo"}
        r = history_mod.undo_steps({"steps": n})
        return {
            "restored": bool(r.get("success")),
            "steps": n,
            "verified": r.get("verified"),
            "warning": r.get("warning") or r.get("error"),
        }

    def final_validate(self):
        # G231: the phase recap is scene-wide so pre-existing leftovers stay
        # visible on the receipt even when per-step abort was touched-scoped.
        # `validate=touched` still scopes the per-step floor / abort decision.
        return validation.run_validate(None, scene_wide=True)

    def final_status(self, focus=None):
        from . import status as status_mod
        if not focus and self.touched:
            focus = self.touched[-1]
        elif not focus and self.created:
            focus = self.created[-1]
        sp = {"focus": focus} if focus else {}
        return status_mod.get_blender_status(sp).get("status")

    def build_receipt(self, result_kind, extra=None, restored=None):
        duration = round(time.monotonic() - self._t0, 3)
        final_v = None
        final_s = None
        # On rejected_budget before any step, skip final reads.
        if result_kind != "rejected_budget" or self.step_count > 0:
            try:
                final_v = self.final_validate()
            except Exception as e:
                final_v = {"passed": False, "line": f"validate error: {e}"}
            try:
                final_s = self.final_status()
            except Exception:
                final_s = None

        # Rollup finding counts
        counts = {}
        for f in self.findings:
            k = f.get("check") or f.get("kind") or "other"
            counts[k] = counts.get(k, 0) + 1

        hist_delta = len(state._history) - self._hist_before
        receipt = {
            "success": result_kind in ("ok", "completed_with_warnings"),
            "result": result_kind,
            "label": self.label,
            "mode": self.mode,
            "steps": {
                "total": self.step_count,
                "ok": self.ok_n,
                "warn": self.warn_n,
                "fail": self.fail_n,
            },
            "created": list(self.created),
            "touched": list(self.touched),
            "deleted": list(self.deleted),
            "via_bpy": self.via_bpy,
            "on_error": self.on_error,
            "strict": self.strict,
            "duration": duration,
            "journal": self.journal,
            "findings": self.findings,
            "findings_counts": counts,
            "first_failure": self.first_failure,
            "final_validate": final_v,
            "final_status": final_s,
            "checkpoints": self.checkpoints,
            "undo": {
                "unit": f"script:{self.label}",
                "policy": "transactional",
                "steps": max(0, hist_delta),
                "note": (
                    "v0: each mutator is one Blender undo step; "
                    "abort restores all steps from this run"
                ),
            },
            "cap": HARD_STEP_CAP,
        }
        if restored is not None:
            receipt["undo"]["restore"] = restored
        if extra:
            receipt.update(extra)
        return receipt


def _buttons_module(runner: _Runner):
    """Build the injected `buttons` namespace for exec."""

    class Buttons:
        Abort = Abort

        def call(self, tool, **params):
            return runner.run_tool(tool, params)

        def add(self, type=None, **params):
            if type is not None:
                params = dict(params, type=type)
            tool, p, verb, op, err = resolve_step({"verb": "add", "params": params})
            if err:
                raise Abort(err)
            return runner.run_tool(tool, p, verb=verb, op=op)

        def transform(self, op=None, **params):
            step = {"verb": "transform", "params": params}
            if op is not None:
                step["op"] = op
            tool, p, verb, op_r, err = resolve_step(step)
            if err:
                raise Abort(err)
            return runner.run_tool(tool, p, verb=verb, op=op_r)

        def edit(self, op=None, **params):
            step = {"verb": "edit", "params": params}
            if op is not None:
                step["op"] = op
            tool, p, verb, op_r, err = resolve_step(step)
            if err:
                raise Abort(err)
            return runner.run_tool(tool, p, verb=verb, op=op_r)

        def material(self, op=None, **params):
            step = {"verb": "material", "params": params}
            if op is not None:
                step["op"] = op
            tool, p, verb, op_r, err = resolve_step(step)
            if err:
                raise Abort(err)
            return runner.run_tool(tool, p, verb=verb, op=op_r)

        def validate(self, op="run", **params):
            step = {"verb": "validate", "op": op, "params": params}
            tool, p, verb, op_r, err = resolve_step(step)
            if err:
                raise Abort(err)
            return runner.run_tool(tool, p, verb=verb, op=op_r)

        def feel(self, op="resting", **params):
            step = {"verb": "feel", "op": op, "params": params}
            tool, p, verb, op_r, err = resolve_step(step)
            if err:
                raise Abort(err)
            return runner.run_tool(tool, p, verb=verb, op=op_r)

        def object(self, op=None, **params):
            # B13: bind the object verb under this name so exec `object(op=...)`
            # is not builtins.object. Shadowing the builtin in script globals is
            # the contract (SPEC-23 thin-map already includes object).
            step = {"verb": "object", "params": params}
            if op is not None:
                step["op"] = op
            tool, p, verb, op_r, err = resolve_step(step)
            if err:
                raise Abort(err)
            return runner.run_tool(tool, p, verb=verb, op=op_r)

        def checkpoint(self, label, focus=None):
            return runner.checkpoint(label, focus=focus)

        def focus(self, name):
            """Set final-focus preference for the receipt."""
            runner._focus_override = name
            return name

    return Buttons()


# ── public tool handlers ─────────────────────────────────────────────────────

def _guard_reentry():
    global _in_script
    if _in_script:
        return {"error": "script: already inside a script run — nested script is refused",
                "success": False, "result": "aborted"}
    return None


def script_batch(params):
    """Run an ordered list of verb/tool steps. Hard cap 25."""
    global _in_script
    err = _guard_reentry()
    if err:
        return err

    steps = params.get("steps")
    if not isinstance(steps, list):
        return {"error": "script batch needs steps=[...]", "success": False,
                "result": "aborted"}

    label = params.get("label") or "batch"
    on_error = params.get("on_error") or "abort"
    validate_scope = params.get("validate") or "touched"
    verbose = bool(params.get("verbose"))
    strict = bool(params.get("strict"))

    # Budget gate BEFORE mutation
    if len(steps) > HARD_STEP_CAP:
        return {
            "success": False,
            "result": "rejected_budget",
            "label": label,
            "mode": "batch",
            "error": (
                f"rejected_budget: {len(steps)} steps > hard cap {HARD_STEP_CAP}. "
                f"Split into phase-sized batches (≤{HARD_STEP_CAP}) and read each receipt."
            ),
            "steps": {"total": 0, "ok": 0, "warn": 0, "fail": 0},
            "created": [],
            "touched": [],
            "deleted": [],
            "journal": [],
            "findings": [],
            "cap": HARD_STEP_CAP,
            "undo": {"unit": f"script:{label}", "policy": "transactional", "steps": 0},
        }

    # Resolve all steps first (bind errors before any mutation when possible)
    resolved = []
    for i, step in enumerate(steps):
        tool, p, verb, op, rerr = resolve_step(step)
        if rerr:
            return {
                "success": False,
                "result": "aborted",
                "label": label,
                "mode": "batch",
                "error": f"step {i + 1}: {rerr}",
                "steps": {"total": 0, "ok": 0, "warn": 0, "fail": 0},
                "created": [],
                "touched": [],
                "journal": [],
                "first_failure": {
                    "i": i + 1,
                    "error": rerr,
                    "verb_op": f"{verb}/{op}" if verb else None,
                },
                "cap": HARD_STEP_CAP,
            }
        if tool in _SCRIPT_TOOLS:
            return {
                "success": False,
                "result": "aborted",
                "error": f"step {i + 1}: nested script tools refused",
                "label": label,
            }
        # Existence check against live TOOLS (import server late)
        from . import server as bb_server
        if tool not in bb_server.TOOLS:
            return {
                "success": False,
                "result": "aborted",
                "label": label,
                "error": f"step {i + 1}: unknown tool {tool!r}",
                "first_failure": {"i": i + 1, "error": f"unknown tool {tool!r}",
                                  "tool": tool},
            }
        resolved.append((tool, p, verb, op))

    runner = _Runner(label, on_error=on_error, validate_scope=validate_scope,
                     verbose=verbose, strict=strict, mode="batch")
    _in_script = True
    aborted = False
    abort_msg = None
    try:
        for tool, p, verb, op in resolved:
            runner.run_tool(tool, p, verb=verb, op=op)
    except Abort as e:
        aborted = True
        abort_msg = e.message
    except Exception as e:
        aborted = True
        abort_msg = f"{type(e).__name__}: {e}"
        if runner.first_failure is None:
            runner.first_failure = {
                "i": runner.step_count,
                "error": abort_msg,
                "traceback": traceback.format_exc()[-800:],
            }
    finally:
        _in_script = False

    restored = None
    if aborted and on_error == "abort":
        restored = runner.transactional_restore()
        # After restore, created list is historical (for journal); live scene is clean
        result_kind = "aborted"
    elif runner.fail_n or runner.warn_n:
        result_kind = "completed_with_warnings" if not aborted else "aborted"
    else:
        result_kind = "ok"

    if aborted and on_error == "abort":
        result_kind = "aborted"

    receipt = runner.build_receipt(result_kind, restored=restored)
    if abort_msg:
        receipt["error"] = abort_msg
    return receipt


def script_exec(params):
    """Run a Python body with `buttons` (and optional `bpy`) in scope."""
    global _in_script
    err = _guard_reentry()
    if err:
        return err

    code = params.get("code")
    path = params.get("path")
    if path and not code:
        try:
            with open(path, "r", encoding="utf-8") as f:
                code = f.read()
        except OSError as e:
            return {"success": False, "result": "aborted",
                    "error": f"cannot read path={path!r}: {e}"}
    if not isinstance(code, str) or not code.strip():
        return {"success": False, "result": "aborted",
                "error": "script exec needs code= or path="}

    raw = code.encode("utf-8")
    if len(raw) > MAX_CODE_BYTES:
        return {
            "success": False,
            "result": "rejected_budget",
            "error": (
                f"rejected_budget: code is {len(raw)} bytes > {MAX_CODE_BYTES}. "
                f"Split phases; hard step cap is still {HARD_STEP_CAP}."
            ),
            "cap": HARD_STEP_CAP,
        }

    label = params.get("label") or "exec"
    on_error = params.get("on_error") or "abort"
    validate_scope = params.get("validate") or "touched"
    verbose = bool(params.get("verbose"))
    strict = bool(params.get("strict"))

    runner = _Runner(label, on_error=on_error, validate_scope=validate_scope,
                     verbose=verbose, strict=strict, mode="exec")
    buttons = _buttons_module(runner)

    # Restricted-ish globals: full Python (documented), buttons + bpy in scope.
    g = {
        "__builtins__": __builtins__,
        "buttons": buttons,
        "Abort": Abort,
        "bpy": bpy,
    }
    # Also expose common names at top level for ergonomics.
    # `object` shadows builtins.object inside the script — that is the contract
    # (B13 / SPEC-23 thin-map). Use type / __builtins__['object'] if a script
    # needs the builtin.
    for name in ("add", "transform", "edit", "material", "validate", "feel",
                 "checkpoint", "call", "object"):
        g[name] = getattr(buttons, name)
    g["obj"] = buttons.object

    _in_script = True
    aborted = False
    abort_msg = None
    try:
        compiled = compile(code, path or f"<script:{label}>", "exec")
        exec(compiled, g, g)  # noqa: S102 — intentional agent script surface
    except Abort as e:
        aborted = True
        abort_msg = e.message
        if runner.first_failure is None:
            runner.first_failure = {
                "i": runner.step_count or 1,
                "error": abort_msg,
                "verb_op": "(script)",
            }
    except Exception as e:
        aborted = True
        abort_msg = f"{type(e).__name__}: {e}"
        if runner.first_failure is None:
            runner.first_failure = {
                "i": runner.step_count or 1,
                "error": abort_msg,
                "traceback": traceback.format_exc()[-800:],
            }
    finally:
        _in_script = False

    # Detect raw bpy use heuristically if code mentions bpy.ops / data writes
    if "bpy." in code:
        # Tag receipt; individual via_bpy only when buttons isn't used for a step
        runner.via_bpy = runner.via_bpy or ("bpy.ops" in code or "bpy.data" in code)

    restored = None
    if aborted and on_error == "abort":
        restored = runner.transactional_restore()
        result_kind = "aborted"
    elif runner.fail_n or runner.warn_n:
        result_kind = "completed_with_warnings"
    else:
        result_kind = "ok"

    if aborted and on_error == "abort":
        result_kind = "aborted"

    receipt = runner.build_receipt(result_kind, restored=restored)
    if abort_msg:
        receipt["error"] = abort_msg
    return receipt


def script_dry_run(params):
    """Parse / bind / budget only — no mutation."""
    mode = (params.get("mode") or "batch").strip().lower()
    label = params.get("label") or "dry_run"

    if mode == "exec":
        code = params.get("code") or ""
        path = params.get("path")
        if path and not code:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    code = f.read()
            except OSError as e:
                return {"success": False, "result": "aborted",
                        "error": f"cannot read path={path!r}: {e}", "dry_run": True}
        if not code.strip():
            return {"success": False, "error": "dry_run exec needs code= or path=",
                    "dry_run": True}
        nbytes = len(code.encode("utf-8"))
        if nbytes > MAX_CODE_BYTES:
            return {
                "success": False,
                "result": "rejected_budget",
                "error": f"code {nbytes} bytes > {MAX_CODE_BYTES}",
                "dry_run": True,
                "cap": HARD_STEP_CAP,
            }
        try:
            compile(code, path or f"<script:{label}>", "exec")
        except SyntaxError as e:
            return {"success": False, "result": "aborted", "dry_run": True,
                    "error": f"syntax: {e}"}
        return {
            "success": True,
            "result": "ok",
            "dry_run": True,
            "mode": "exec",
            "label": label,
            "code_bytes": nbytes,
            "note": (
                f"syntax ok; runtime step count still enforced at {HARD_STEP_CAP} "
                f"(loops count)."
            ),
            "cap": HARD_STEP_CAP,
        }

    # batch dry_run
    steps = params.get("steps")
    if not isinstance(steps, list):
        return {"success": False, "error": "dry_run batch needs steps=[...]",
                "dry_run": True}

    if len(steps) > HARD_STEP_CAP:
        return {
            "success": False,
            "result": "rejected_budget",
            "dry_run": True,
            "error": f"{len(steps)} steps > hard cap {HARD_STEP_CAP}",
            "cap": HARD_STEP_CAP,
        }

    from . import server as bb_server
    resolved = []
    errors = []
    for i, step in enumerate(steps):
        tool, p, verb, op, rerr = resolve_step(step)
        if rerr:
            errors.append({"i": i + 1, "error": rerr})
            continue
        if tool not in bb_server.TOOLS:
            errors.append({"i": i + 1, "error": f"unknown tool {tool!r}", "tool": tool})
            continue
        resolved.append({
            "i": i + 1,
            "tool": tool,
            "verb": verb,
            "op": op,
            "params": p,
        })

    if errors:
        return {
            "success": False,
            "result": "aborted",
            "dry_run": True,
            "label": label,
            "errors": errors,
            "resolved": resolved,
            "first_failure": errors[0],
            "cap": HARD_STEP_CAP,
        }

    return {
        "success": True,
        "result": "ok",
        "dry_run": True,
        "mode": "batch",
        "label": label,
        "steps": len(resolved),
        "resolved": resolved,
        "cap": HARD_STEP_CAP,
    }


TOOLS = {
    "script_batch": script_batch,
    "script_exec": script_exec,
    "script_dry_run": script_dry_run,
}
