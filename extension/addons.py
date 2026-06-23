"""Generic addon / operator bridge — drive ANY installed Blender addon by name.

The server deliberately exposes capabilities as explicit named handlers, but this is
the one general-purpose escape hatch: list the enabled addons, introspect an operator's
parameters, and run `bpy.ops.<namespace>.<operator>(**args)`. It rides the normal
dispatch spine, so addon_run is logged + undoable + status-reported like any mutator,
and is blocked while the external-mutation lock is set (it is NOT lock-exempt).

Used to drive e.g. the Poliigon addon's online download/login when wanted — but note
material BUILDING from local files is handled vendor-neutrally by `material op=pbr`,
which has zero dependency on this bridge or on any addon's API.
"""

import addon_utils
import bpy


def addon_list(params):
    """List the ENABLED addons (the set that can actually be driven). `filter` is an
    optional name substring."""
    filter_str = (params.get("filter") or "").lower()
    infos = {}
    for m in addon_utils.modules():
        infos[m.__name__] = getattr(m, "bl_info", {}) or {}
    out = []
    for key in bpy.context.preferences.addons.keys():
        info = infos.get(key, {})
        label = info.get("name", key)
        if filter_str and filter_str not in label.lower() and filter_str not in key.lower():
            continue
        out.append({
            "module": key,
            "name": label,
            "version": ".".join(str(x) for x in info.get("version", ())) or None,
            "category": info.get("category", ""),
        })
    out.sort(key=lambda a: a["name"].lower())
    return {"success": True, "addons": out, "count": len(out)}


def _ops_in(ns):
    cat = getattr(bpy.ops, ns, None)
    if cat is None:
        return None
    return sorted(o for o in dir(cat) if not o.startswith("__"))


def addon_inspect(params):
    """Introspect an operator. `operator` is either a namespace ('poliigon' → list its
    operators) or a full id ('poliigon.poliigon_material' → list its parameters with
    types, defaults, and enum choices)."""
    operator = (params.get("operator") or "").strip()
    if not operator:
        return {"error": "'operator' is required — a namespace like 'poliigon', or a full "
                         "id like 'poliigon.poliigon_material'"}
    ns = operator.split(".")[0]
    ops = _ops_in(ns)
    if ops is None:
        return {"error": f"no operator namespace '{ns}'. Run addon op=list to see drivable addons."}
    if "." not in operator:
        return {"success": True, "namespace": ns, "count": len(ops),
                "operators": [f"{ns}.{o}" for o in ops]}

    opname = operator.split(".", 1)[1]
    fn = getattr(getattr(bpy.ops, ns), opname, None)
    if fn is None:
        return {"error": f"no operator '{operator}'. Operators in '{ns}': "
                         f"{[ns + '.' + o for o in ops][:50]}"}
    try:
        rna = fn.get_rna_type()
    except Exception as e:
        return {"error": f"could not introspect '{operator}': {e}"}

    props = []
    for p in rna.properties:
        if p.identifier == "rna_type":
            continue
        entry = {"name": p.identifier, "type": p.type, "description": p.description or ""}
        if p.type == "ENUM":
            try:
                entry["values"] = [it.identifier for it in p.enum_items]
            except Exception:
                pass
        if not getattr(p, "is_array", False):
            try:
                entry["default"] = p.default
            except Exception:
                pass
        props.append(entry)
    return {"success": True, "operator": operator, "label": rna.name,
            "description": rna.description or "", "params": props}


def _best_area_override():
    """A best-effort context override for operators that fail a context poll. None in
    --background (no window)."""
    win = getattr(bpy.context, "window", None)
    if not win or not getattr(win, "screen", None):
        return None
    screen = win.screen
    if not screen.areas:
        return None
    area = next((a for a in screen.areas if a.type == 'VIEW_3D'), screen.areas[0])
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    ov = {"window": win, "screen": screen, "area": area}
    if region:
        ov["region"] = region
    return ov


def addon_run(params):
    """Run bpy.ops.<namespace>.<operator>(**args). Returns the operator's result set.
    On a context-poll RuntimeError, retries once under a best-effort VIEW_3D override."""
    operator = (params.get("operator") or "").strip()
    if "." not in operator:
        return {"error": "'operator' must be '<namespace>.<operator>', e.g. 'object.shade_smooth'"}
    ns, opname = operator.split(".", 1)
    # bpy.ops is LAZY — getattr returns a wrapper for ANY name, even nonexistent ones,
    # so a None check can't catch a typo (it would blow up only at call time, uncaught).
    # Validate against the real operator list (dir() of the namespace) instead.
    ops = _ops_in(ns)
    if not ops or opname not in ops:
        return {"error": f"no operator '{operator}'. Use addon op=inspect operator={ns} to list "
                         f"its operators, or addon op=list for drivable addons."}
    fn = getattr(getattr(bpy.ops, ns), opname)
    args = params.get("args") or {}
    if not isinstance(args, dict):
        return {"error": "'args' must be an object of operator properties"}
    exec_ctx = (params.get("exec_context") or "EXEC_DEFAULT").upper()
    if exec_ctx not in {"EXEC_DEFAULT", "INVOKE_DEFAULT", "EXEC_REGION_WIN", "INVOKE_REGION_WIN"}:
        return {"error": f"exec_context '{exec_ctx}' not recognised (EXEC_DEFAULT | INVOKE_DEFAULT | "
                         f"EXEC_REGION_WIN | INVOKE_REGION_WIN)"}

    try:
        result = fn(exec_ctx, **args)
    except TypeError as e:
        return {"error": f"{operator} rejected args {sorted(args)}: {e}. "
                         f"Run addon op=inspect operator={operator} for valid parameters."}
    except RuntimeError as e:
        ov = _best_area_override()
        if ov is None:
            return {"error": f"{operator} failed: {e}"}
        try:
            with bpy.context.temp_override(**ov):
                result = fn(exec_ctx, **args)
        except Exception as e2:
            return {"error": f"{operator} failed: {e} (retry under VIEW_3D override: {e2})"}
    except Exception as e:
        return {"error": f"{operator} failed: {type(e).__name__}: {e}"}

    rset = list(result)
    return {"success": ("FINISHED" in rset or "RUNNING_MODAL" in rset),
            "operator": operator, "result": rset, "args": args}


TOOLS = {
    "addon_list": addon_list,
    "addon_inspect": addon_inspect,
    "addon_run": addon_run,
}
