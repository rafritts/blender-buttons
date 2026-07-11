from server._core import mcp, call_blender, _status


@mcp.tool()
def remove_material_slot(target: str = "", slot: int = None, label: str = "") -> str:
    """
    Remove a single material slot from an object (Material Properties ▸ −).

    Reassign faces off the slot FIRST (`material op=assign`) — Blender re-homes any
    faces still on a removed slot to slot 0 and shifts every higher index down by one.

    target: object name (default: active object).
    slot:   slot index to remove (required).
    """
    result = call_blender("remove_material_slot",
                          {"target": target, "slot": slot}, label=label)
    if result.get("success"):
        main = (f"removed slot {result['removed_slot']} "
                f"({result.get('removed_material')}) — {result['slot_count']} "
                f"slot(s) left [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def remove_unused_material_slots(target: str = "", label: str = "") -> str:
    """
    Remove every material slot with NO faces assigned (Material Properties ▸ ⌄ ▸
    'Remove Unused Slots') — trim a consolidated mesh to its real slot count.

    target: object name (default: active object).
    """
    result = call_blender("remove_unused_material_slots",
                          {"target": target}, label=label)
    if result.get("success"):
        main = (f"removed {result['removed_count']} unused slot(s) — "
                f"{result['slot_count']} left [{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)
