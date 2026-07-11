"""addon — drive any installed Blender addon/extension by name.

The one general-purpose escape hatch over the named-handler surface: `op` selects:

  list    — the enabled addons that can be driven                    (filter)
  inspect — an operator's parameters, or a namespace's operators
            (operator='poliigon' lists ops; operator='poliigon.poliigon_material'
             lists that op's params, types, defaults, enum choices)
  run     — run bpy.ops.<namespace>.<operator>(**args)               (operator, args,
            exec_context)

`run` is a real mutation: logged, undoable (history op=undo), status-reported, and
blocked while the external-mutation lock is set. For BUILDING materials from local
texture files are applied via a local-texture material graph — vendor-neutral, no addon.
"""

from typing import Literal

from server._core import mcp, call_blender, _status
from ._common import tag, unknown

_OPS = ["list", "inspect", "run"]


@mcp.tool(name="addon")
def addon(
    op: Literal["list", "inspect", "run"],
    operator: tag(str, "[inspect/run] namespace ('poliigon') or full id ('poliigon.poliigon_material')") = "",
    args: tag(dict, "[run] operator properties, e.g. {\"size\": \"4K\", \"do_apply\": true}") = None,
    exec_context: tag(str, "[run] EXEC_DEFAULT (default) | INVOKE_DEFAULT | EXEC_REGION_WIN | INVOKE_REGION_WIN") = "EXEC_DEFAULT",
    filter: tag(str, "[list] name substring filter") = "",
    label: str = "",
) -> str:
    """Drive any installed addon. See the module docstring for the op menu. Typical
    flow: `addon op=list` → `addon op=inspect operator=<ns>` → `addon op=inspect
    operator=<ns.op>` → `addon op=run operator=<ns.op> args={...}`."""
    o = op.lower().strip()
    if o == "list":
        return _format_list(call_blender("addon_list", {"filter": filter}))
    if o == "inspect":
        return _format_inspect(call_blender("addon_inspect", {"operator": operator}))
    if o == "run":
        result = call_blender("addon_run",
                              {"operator": operator, "args": args or {}, "exec_context": exec_context},
                              label=label)
        if result.get("success"):
            main = f"ran {result['operator']} → {result['result']} [{result.get('op_id','')}]"
        elif "result" in result:  # operator ran but didn't FINISH (e.g. CANCELLED)
            main = f"{result['operator']} returned {result['result']} (not finished)"
        else:
            main = result.get("error", "failed")
        return main + _status(result)
    return unknown("addon", "op", op, _OPS)


def _format_list(result):
    if not result.get("success"):
        return result.get("error", "failed")
    rows = result.get("addons", [])
    if not rows:
        return "no enabled addons match."
    lines = [f"{len(rows)} enabled addon(s):"]
    for a in rows:
        ver = f" v{a['version']}" if a.get("version") else ""
        cat = f"  ({a['category']})" if a.get("category") else ""
        lines.append(f"  {a['name']}{ver}  —  {a['module']}{cat}")
    return "\n".join(lines)


def _format_inspect(result):
    if not result.get("success"):
        return result.get("error", "failed")
    if "operators" in result:  # namespace listing
        ops = result["operators"]
        head = f"{result['count']} operator(s) in '{result['namespace']}':"
        return head + "\n" + "\n".join(f"  {o}" for o in ops)
    lines = [f"{result['operator']}  —  {result.get('label','')}"]
    if result.get("description"):
        lines.append(f"  {result['description']}")
    params = result.get("params", [])
    if not params:
        lines.append("  (no parameters)")
    for p in params:
        bits = [p["type"].lower()]
        if "default" in p:
            bits.append(f"default={p['default']!r}")
        if p.get("values"):
            vals = p["values"]
            bits.append("one of: " + ", ".join(vals[:12]) + (" …" if len(vals) > 12 else ""))
        desc = f"  — {p['description']}" if p.get("description") else ""
        lines.append(f"  {p['name']} ({'; '.join(bits)}){desc}")
    return "\n".join(lines)
