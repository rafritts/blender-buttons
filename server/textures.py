import os
import re

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


# ── generic PBR-folder importer ──────────────────────────────────────────────
# Build a material from a local texture-set folder (Poliigon, Megascans, ambientCG,
# loose folders) by classifying files on filename, with ZERO dependency on any
# vendor addon. The on-disk naming convention is a far more stable contract than an
# addon's Python API — the Poliigon addon itself versions it (convention 0 vs 1) —
# so an addon update never forces rework here.

_PBR_EXTS = (".exr", ".tiff", ".tif", ".png", ".webp", ".jpg", ".jpeg")
# Largest-first preference is by index in this list (watermark "WM" excluded on purpose).
_PBR_SIZES = ["256", "512", "1K", "2K", "3K", "4K", "6K", "8K", "12K", "16K", "18K", "HIRES"]
_PBR_SIZE_IDX = {s.lower(): i for i, s in enumerate(_PBR_SIZES)}

# token (lowercased, exact) → Principled role. Covers Poliigon convention-1 long
# names (BaseColor/AmbientOcclusion/…), Poliigon/Megascans convention-0 short codes
# (COL/NRM/AO/…), Poly Haven (nor/rough/…), and common generic names.
_ROLE_TOKENS = {
    "basecolor": "diffuse", "albedo": "diffuse", "diffuse": "diffuse",
    "color": "diffuse", "col": "diffuse", "diff": "diffuse", "alb": "diffuse",
    "roughness": "roughness", "rough": "roughness", "rgh": "roughness",
    "gloss": "gloss", "glossiness": "gloss",
    "metallic": "metal", "metalness": "metal", "metal": "metal", "met": "metal",
    "normal": "normal", "normalgl": "normal", "normaldx": "normal",
    "nrm": "normal", "nor": "normal", "norm": "normal",
    "displacement": "height", "disp": "height", "height": "height", "dsp": "height",
    "ambientocclusion": "ao", "ao": "ao", "occlusion": "ao",
    "emission": "emission", "emissive": "emission", "emit": "emission",
    "opacity": "alpha", "alpha": "alpha", "alphamasked": "alpha",
}


def _classify_map(filename: str):
    """Filename → role, by exact-token match (last match wins, since the map word
    sits closest to the extension). Exact tokens avoid substring false hits like
    'MetalPlate' reading as metal."""
    stem = os.path.splitext(filename)[0]
    role = None
    for tok in re.split(r"[ _\-.]+", stem):
        hit = _ROLE_TOKENS.get(tok.lower())
        if hit:
            role = hit
    return role


def _pick_map_dir(folder: str, size: str):
    """Resolve which directory actually holds the map files. Either `folder` holds
    images directly, or it holds resolution subfolders (4K/2K/…) and we pick `size`
    (or the largest present). Returns (map_dir, chosen_size, available_sizes, error)."""
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        return None, None, [], f"folder not found: {folder}"

    def images_in(d):
        return any(os.path.splitext(f)[1].lower() in _PBR_EXTS for f in os.listdir(d))

    subs = {e.lower(): e for e in os.listdir(folder)
            if e.lower() in _PBR_SIZE_IDX and os.path.isdir(os.path.join(folder, e))}
    if subs:
        avail = sorted(subs, key=lambda s: _PBR_SIZE_IDX.get(s, -1))
        labels = [subs[a] for a in avail]
        if size and size.lower() in subs:
            chosen = size.lower()
        elif size:
            return None, None, labels, f"size '{size}' not available"
        else:
            chosen = avail[-1]  # largest present
        return os.path.join(folder, subs[chosen]), subs[chosen], labels, None
    if images_in(folder):
        return folder, None, [], None
    return None, None, [], f"no texture maps or resolution subfolders found in {folder}"


def _scan_maps(map_dir: str):
    """Classify every image in map_dir into {role: path}, resolving collisions:
    prefer an OpenGL normal over a DX one, then higher-quality extension."""
    cands = {}
    for f in sorted(os.listdir(map_dir)):
        if os.path.splitext(f)[1].lower() not in _PBR_EXTS:
            continue
        role = _classify_map(f)
        if role:
            cands.setdefault(role, []).append(os.path.join(map_dir, f))
    chosen = {}
    for role, paths in cands.items():
        if role == "normal" and len(paths) > 1:
            gl = [p for p in paths if "dx" not in os.path.basename(p).lower()]
            paths = gl or paths
        paths.sort(key=lambda p: _PBR_EXTS.index(os.path.splitext(p)[1].lower()))
        chosen[role] = paths[0]
    return chosen


@mcp.tool()
def set_pbr_material(target: str, folder: str, size: str = "", scale: float = 1.0,
                     displacement: float = 0.0, base_color: list = None,
                     tint: list = None, metallic: float = None, roughness: float = None,
                     material_name: str = "", slot: int = None, use_alpha: bool = False,
                     label: str = "") -> str:
    """
    Build a PBR material from a LOCAL texture-set folder and apply it — vendor-neutral
    (Poliigon, Megascans, ambientCG, or any folder of maps). Maps are auto-detected by
    filename, so this needs no addon and no login; it just reads files off disk.

    target:     object OR group name.
    folder:     path to the texture-set folder. Either it holds the map files directly,
                or it holds resolution subfolders (e.g. .../4K/, .../2K/) — then `size`
                picks one (default: the largest present). For a Poliigon asset point at
                the asset dir, e.g. ~/.../Poliigon_StoneQuartzite_8060.
    size:       resolution subfolder/token to pick (e.g. "4K"). Default: largest present.
    scale:      texture tiling scale (BOX projection — no UV unwrap needed).
    displacement: bump-displacement strength from the height map. 0 (default) = off,
                normal-map detail only (what Poliigon does by default).
    base_color/tint/metallic/roughness: same overrides as `textured` — replace/tint the
                color, or force the metallic/roughness scalar over the scanned map.

    Recognised maps: base color (BaseColor/COL/albedo/diffuse), roughness, gloss
    (inverted into roughness), metallic, normal (GL preferred over DX), height/
    displacement, ambient occlusion (multiplied into base color), emission, opacity.
    A folder with no usable color map returns a clean error and changes nothing.
    """
    if not folder:
        return "pbr failed: 'folder' (a local texture-set directory) is required."
    map_dir, chosen_size, available, err = _pick_map_dir(folder, size)
    if err:
        extra = f" available sizes: {available}." if available else ""
        return f"pbr failed: {err}.{extra}"
    maps = _scan_maps(map_dir)
    if "diffuse" not in maps and base_color is None:
        return (f"pbr failed: no base-color/diffuse map found in {map_dir} "
                f"(classified: {sorted(maps) or 'nothing'}). Pass base_color= to override.")

    asset = os.path.basename(folder.rstrip("/\\")) or folder
    params = {"target": target, "maps": maps, "scale": scale,
              "resolution": chosen_size or "", "asset_id": asset,
              "displacement": displacement}
    if base_color is not None: params["base_color"] = base_color
    if tint is not None:       params["tint"] = tint
    if metallic is not None:   params["metallic"] = metallic
    if roughness is not None:  params["roughness"] = roughness
    if material_name:          params["material_name"] = material_name
    if slot is not None:       params["slot"] = slot
    if use_alpha:              params["use_alpha"] = True

    result = call_blender("set_textured_material", params, label=label)
    if result.get("success"):
        size_str = f"@{chosen_size}" if chosen_size else ""
        main = (f"pbr '{result['target']}' from {asset}{size_str} "
                f"(maps: {result['maps_wired']}) → {result['assigned_to']} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)


@mcp.tool()
def set_textured_material(target: str, asset_id: str, scale: float = 1.0,
                          resolution: str = "1k", base_color: list = None,
                          tint: list = None, metallic: float = None,
                          roughness: float = None, material_name: str = "",
                          slot: int = None, use_alpha: bool = False, label: str = "") -> str:
    """
    Apply a real photo-scanned PBR material from Poly Haven (CC0) to an object or
    group. Downloads + caches the diffuse/normal/roughness/metal maps server-side,
    then wires a Principled BSDF with BOX projection — no UV unwrap needed.

    target:     object OR group name.
    asset_id:   Poly Haven texture id (from search_textures), e.g. "brick_wall_02".
    scale:      texture tiling scale (higher = smaller, more-repeated texels).
    resolution: "1k" (default), "2k", "4k", "8k". Higher = sharper but slower/heavier.
    base_color: optional [r,g,b] scene-linear override — REPLACES the scan's
                diffuse so its roughness/normal/metal surface detail carries
                YOUR color. The trick for materials Poly Haven doesn't stock:
                gold trim = a scratched gray-metal scan + base_color gold.
    tint:       optional [r,g,b] multiplied over the scan's diffuse — keeps the
                grain and color variation but shifts it (e.g. [0.5,0.4,0.35]
                darkens + warms a pale wood). Ignored if base_color is given.
    metallic:   optional 0..1 — forces the Metallic input (overrides the metal
                map). Use 1.0 with base_color to turn any scan into a metal.
    roughness:  optional 0..1 — forces the Roughness input (overrides the
                roughness map). 1.0 = fully matte, no sheen at all.
    slot:       material slot index to assign into (default 0) — for texturing a
                multi-slot mesh's secondary material.

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
    if base_color is not None:
        params["base_color"] = base_color
    if tint is not None:
        params["tint"] = tint
    if metallic is not None:
        params["metallic"] = metallic
    if roughness is not None:
        params["roughness"] = roughness
    if material_name:
        params["material_name"] = material_name
    if slot is not None:
        params["slot"] = slot
    if use_alpha:
        params["use_alpha"] = True
    result = call_blender("set_textured_material", params, label=label)
    if result.get("success"):
        main = (f"textured '{result['target']}' with {asset_id}@{resolution} "
                f"(maps: {result['maps_wired']}) → {result['assigned_to']} "
                f"[{result.get('op_id','')}]")
    else:
        main = result.get("error", "failed")
    return main + _status(result)
