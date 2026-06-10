from server._core import mcp, call_blender, _status
from server import polyhaven


@mcp.tool()
def search_textures(query: str, limit: int = 10) -> str:
    """
    Search Poly Haven's CC0 texture library by keyword (material, surface, color,
    use — e.g. "brick", "rusty metal", "wood floor"). Returns asset ids to pass
    to set_textured_material. Works offline after the first call (catalog is cached
    24h).
    """
    try:
        results = polyhaven.search(query, "textures", limit)
    except polyhaven.PolyHavenError as e:
        return f"texture search failed: {e}"
    if not results:
        return f"No textures match '{query}'."
    return "\n".join(f"{r['id']}  [{', '.join(r['tags'][:6])}]" for r in results)


@mcp.tool()
def set_textured_material(target: str, asset_id: str, scale: float = 1.0,
                          resolution: str = "1k", material_name: str = "",
                          label: str = "") -> str:
    """
    Apply a real photo-scanned PBR material from Poly Haven (CC0) to an object or
    group. Downloads + caches the diffuse/normal/roughness maps server-side, then
    wires a Principled BSDF with BOX projection — no UV unwrap needed.

    target:     object OR group name.
    asset_id:   Poly Haven texture id (from search_textures), e.g. "brick_wall_02".
    scale:      texture tiling scale (higher = smaller, more-repeated texels).
    resolution: "1k" (default), "2k", "4k", "8k". Higher = sharper but slower/heavier.

    A bad id or a network failure returns a clean error and leaves the object's
    material unchanged. Subsequent calls for the same asset/resolution hit the
    local cache (no network).
    """
    try:
        maps = polyhaven.ensure_texture_maps(asset_id, resolution)
    except polyhaven.PolyHavenError as e:
        return f"could not fetch texture '{asset_id}': {e}. Object material unchanged."
    params = {"target": target, "maps": maps, "scale": scale,
              "resolution": resolution, "asset_id": asset_id}
    if material_name:
        params["material_name"] = material_name
    result = call_blender("set_textured_material", params, label=label)
    if result.get("success"):
        main = (f"textured '{result['target']}' with {asset_id}@{resolution} "
                f"(maps: {result['maps_wired']}) → {result['assigned_to']} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)
