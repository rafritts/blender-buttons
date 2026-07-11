import os
import re

from server._core import mcp, call_blender, _status, _targets
from server import polyhaven


# G188 — when a brief asks for a look "from Poliigon", the honest answer is NOT to
# silently search Poly Haven and quietly change what was asked for. Poliigon's library is
# reachable only through its installed, authenticated, version-specific addon API, which
# has to be driven LIVE — so point the caller at the real route (the generic addon bridge
# to search+download, then the vendor-neutral local-folder apply) rather than substitute.
_POLIIGON_SEARCH_GUIDE = (
    "Poliigon search isn't a first-class server path — its addon API is authenticated and "
    "version-specific, so it's driven live, not fetched by id server-side. To honour "
    "'from Poliigon' without substituting Poly Haven:\n"
    "  1. `addon op=list filter=poliigon`   — confirm the addon is enabled + logged in\n"
    "  2. `addon op=inspect operator=poliigon`   — list its search/download operators\n"
    "  3. drive the chosen download operator with `addon op=run`, then apply the downloaded "
    "maps from a local texture-set folder (vendor-neutral — Poliigon's "
    "own BaseColor/Normal/Roughness names directly).")
_POLIIGON_APPLY_GUIDE = (
    "'from Poliigon' can't be fetched by id server-side (authenticated addon API, live-only). "
    "Download the asset through the Poliigon addon (`addon op=inspect operator=poliigon` → "
    "`addon op=run`), then apply it via a local-texture material graph (target=<obj> "
    "folder=<downloaded asset dir>` — no Poly Haven substitution.")


@mcp.tool()
def search_textures(query: str, limit: int = 10, source: str = "polyhaven") -> str:
    """
    Search a PBR texture library by keyword (material, surface, color, use — e.g. "brick",
    "rusty metal", "wood floor"). Returns asset ids for use in a texture node graph.

    source: "polyhaven" (default, CC0, fully automated find→fetch→apply; catalog cached 24h)
      | "poliigon" — the licensed library; there is no server-side fetch-by-id (its addon API
      is authenticated + live-only), so this returns the exact live route rather than silently
      searching Poly Haven under a different library's name (G188).
    """
    if (source or "").strip().lower() in ("poliigon", "poliigon.com"):
        return _POLIIGON_SEARCH_GUIDE
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
