"""Poly Haven API client + on-disk cache. Pure Python — NO bpy, NO Blender.

The server resolves Poly Haven asset ids to LOCAL FILE PATHS here (downloading
and caching as needed), then hands those paths to the addon for node wiring.
The addon never touches the network, and Blender's main thread never blocks on a
download. All Poly Haven assets are CC0, so we cache freely.

Cache layout under ~/.cache/blender-buttons/:
  catalog_<type>.json          the asset catalog (24h TTL)
  files/<asset_id>.json        the per-asset file manifest (immutable; no TTL)
  textures/<asset_id>/<res>/<map>.<ext>
  hdris/<asset_id>/<res>/hdri.<ext>
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.polyhaven.com"
USER_AGENT = "blender-buttons/1.0 (MCP texture client; https://polyhaven.com CC0 assets)"
CACHE_ROOT = Path.home() / ".cache" / "blender-buttons"
CATALOG_TTL = 24 * 3600  # seconds

# Which Poly Haven map keys feed each Principled input, and the format preference
# (jpg first — smallest; Displacement is deliberately skipped, Eevee handles it
# badly). Normal uses the GL variant.
TEXTURE_MAPS = {
    "diffuse":   (["Diffuse"], ["jpg", "png", "exr"]),
    "normal":    (["nor_gl"],  ["jpg", "png", "exr"]),
    "roughness": (["Rough"],   ["jpg", "png", "exr"]),
}
HDRI_FORMATS = ["hdr", "exr"]

# Network counter so tests can assert cache-vs-network behavior.
_download_count = 0


class PolyHavenError(Exception):
    """Any failure reaching Poly Haven or resolving an asset — raised so the
    server tool can degrade to a clean error with the scene left untouched."""


def reset_download_count():
    global _download_count
    _download_count = 0


def download_count():
    return _download_count


def _http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as e:
        raise PolyHavenError(f"GET {url} failed: {e}")


def _download(url, dest):
    global _download_count
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
            fh.write(resp.read())
        os.replace(tmp, dest)
        _download_count += 1
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        if tmp.exists():
            tmp.unlink()
        raise PolyHavenError(f"download {url} failed: {e}")


def catalog(asset_type="textures", force=False):
    """The asset catalog dict {id: {name, tags, categories, ...}}, cached 24h so
    search works offline after first use."""
    path = CACHE_ROOT / f"catalog_{asset_type}.json"
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < CATALOG_TTL
    if fresh and not force:
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            pass
    data = _http_json(f"{API}/assets?t={asset_type}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(data))
    except OSError:
        pass
    return data


def search(query, asset_type="textures", limit=10):
    """Return up to `limit` [{id, tags}] whose id/name/tags/categories match query."""
    cat = catalog(asset_type)
    q = (query or "").lower().strip()
    hits = []
    for aid, meta in cat.items():
        hay = " ".join([aid, meta.get("name", "")]
                       + meta.get("tags", []) + meta.get("categories", [])).lower()
        if not q or q in hay:
            hits.append({"id": aid, "tags": meta.get("tags", [])})
        if len(hits) >= limit and q:
            break
    return hits[:limit]


def _files(asset_id):
    """Per-asset file manifest, cached on disk (asset files are immutable)."""
    path = CACHE_ROOT / "files" / f"{asset_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            pass
    data = _http_json(f"{API}/files/{asset_id}")
    if not isinstance(data, dict) or not data:
        raise PolyHavenError(f"no files for asset '{asset_id}' (check the id)")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(data))
    except OSError:
        pass
    return data


def _pick(entry, resolution, formats):
    """From a {res: {fmt: {url,...}}} map entry, choose (resolution, format, url)."""
    res = resolution if resolution in entry else (sorted(entry)[0] if entry else None)
    if res is None:
        return None
    fmtdict = entry[res]
    fmt = next((f for f in formats if f in fmtdict), None)
    if fmt is None:
        return None
    return res, fmt, fmtdict[fmt]["url"]


def ensure_texture_maps(asset_id, resolution="1k"):
    """Resolve a texture asset to {map: local_path}, downloading on cache miss.
    Raises PolyHavenError on any failure (caller leaves the scene untouched)."""
    manifest = _files(asset_id)
    out = {}
    for mapname, (keys, formats) in TEXTURE_MAPS.items():
        entry = next((manifest[k] for k in keys if k in manifest), None)
        if entry is None:
            continue
        picked = _pick(entry, resolution, formats)
        if picked is None:
            continue
        res, fmt, url = picked
        dest = CACHE_ROOT / "textures" / asset_id / res / f"{mapname}.{fmt}"
        if not dest.exists():
            _download(url, dest)
        out[mapname] = str(dest)
    if "diffuse" not in out:
        raise PolyHavenError(f"asset '{asset_id}' has no usable diffuse map")
    return out


def ensure_hdri(asset_id, resolution="2k"):
    """Resolve an HDRI asset to a single local .hdr/.exr path (T7)."""
    manifest = _files(asset_id)
    entry = manifest.get("hdri")
    if not isinstance(entry, dict):
        raise PolyHavenError(f"asset '{asset_id}' is not an HDRI (no 'hdri' files)")
    picked = _pick(entry, resolution, HDRI_FORMATS)
    if picked is None:
        raise PolyHavenError(f"asset '{asset_id}' has no .hdr/.exr at any resolution")
    res, fmt, url = picked
    dest = CACHE_ROOT / "hdris" / asset_id / res / f"hdri.{fmt}"
    if not dest.exists():
        _download(url, dest)
    return str(dest)
