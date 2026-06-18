"""MCP wrapper for get_topology — the topology sense (SPEC-04).

Feels a mesh's STRUCTURE (not its bounding box): openings, branches, poles,
symmetry, curvature, hard edges, thickness. Returns named, grabbable landmarks
the LLM can pass straight into a select / cut / extrude verb — never a raw vertex
dump. This is the structural sense `describe` does not provide.
"""

from server._core import mcp, call_blender, _status


def _fmt_method(name: str, data: dict) -> list:
    if "error" in data:
        return [f"  {name}: {data['error']}"]
    lines = []
    if name == "components":
        lines.append(f"  components: {data['count']} shell(s)")
        for c in data.get("components", []):
            lines.append(f"    [{c['index']}] {c['verts']} verts, size {c['size_m']} m")
        if data.get("omitted"):
            lines.append(f"    (+{data['omitted']} smaller omitted — raise lod)")
    elif name == "genus":
        lines.append(f"  genus: {data['reading']} "
                     f"(χ={data['euler_characteristic']}, {data['boundary_loops']} boundary loop(s))")
    elif name == "boundaries":
        lines.append(f"  boundaries: {data['count']} open hole(s)")
        for b in data.get("boundaries", []):
            path = f"  path={len(b['path_vert_ids'])} ids" if "path_vert_ids" in b else ""
            lines.append(f"    [{b['index']}] {b['region']}: {b['circumference_cm']}cm around, "
                         f"{b['verts']} verts{path}")
    elif name == "structure":
        t = data.get("triage", {})
        regimes = ", ".join(data.get("regimes", [])) or "unclassified"
        lenses = ", ".join(data.get("lenses_run", [])) or "none"
        lines.append(f"  structure: regime [{regimes}] — {t.get('shells', '?')} shell(s), "
                     f"{t.get('open_loops', '?')} open loop(s), χ={t.get('euler', '?')}"
                     f"   [lenses: {lenses}]")
        p = data.get("protrusion")
        if p:
            lines.append(f"    protrusion lens: {p['n_protrusions']} protrusion(s) + "
                         f"{p['n_apertures']} flush aperture(s)")
            for pr in p.get("protrusions", []):
                lines.append(f"      ▸ protrusion: ø{pr['diameter_cm']}cm cap @ {pr['cap_region']}, "
                             f"runs {pr['extent_cm']}cm to a base @ {pr['base_region']} "
                             f"(girth {pr['base_girth_cm']}cm) ← cut the base to remove it")
                if "base_point" in pr:
                    lines.append(f"          base_point={pr['base_point']}  "
                                 f"cap={len(pr['cap_path_vert_ids'])} ids  "
                                 f"cut-ring={len(pr.get('base_ring_ids', []))} ids  "
                                 f"→ select op=limb which='{pr['cap_region']}'")
                if "girth_profile_cm" in pr:
                    lines.append(f"          girth→ {pr['girth_profile_cm']}")
            for a in p.get("apertures", []):
                lines.append(f"      ○ aperture: {a['circumference_cm']}cm @ {a['region']} "
                             f"(opens straight into the body)")
                if "girth_profile_cm" in a:
                    lines.append(f"          girth→ {a['girth_profile_cm']}")
        for u in data.get("unhandled", []):
            lines.append(f"    ⚠ {u}")
    elif name == "poles":
        bv = ", ".join(f"val{k}×{v}" for k, v in data["by_valence"].items()) or "none"
        lines.append(f"  poles: {data['count']} ({bv})")
        for p in data.get("poles", [])[:20]:
            lines.append(f"    valence {p['valence']} @ {p['region']} (id {p['vert_id']})")
    elif name == "symmetry":
        best = data["best_plane"]
        lines.append(f"  symmetry: best mirror = {best} plane, "
                     f"mean error {data['best_mean_error_mm']}mm")
        for ax, d in data["per_axis"].items():
            mark = "✓" if d["symmetric"] else " "
            lines.append(f"    {mark} {ax}: {d['mean_error_mm']}mm mean / {d['max_error_mm']}mm max")
    elif name == "frame":
        lines.append("  frame (principal axes):")
        for k, a in enumerate(data["principal_axes"]):
            lines.append(f"    {k+1}. {a['extent_m']}m along ~{a['aligns_world']} {a['direction']}")
    elif name == "sections":
        lines.append("  sections (slice the mesh & read each slice's shape — "
                     "O = closed ring/full wrap, C = open arc/partial coverage):")
        for a in data.get("axes", []):
            oreg = a.get("open_regions", [])
            where = ("; open arcs at " +
                     ", ".join(f"{o['region']}(×{o['count']})" for o in oreg)) if oreg else ""
            lines.append(f"    {a['axis']} axis ({a['extent_cm']}cm): "
                         f"{a['open_pct']}% open C / {a['closed_pct']}% closed O, "
                         f"up to {a['max_contours']} contour(s){where}")
            g = a.get("largest_gap")
            if g:  # a genuinely empty band (no material at all) — rare; worth shouting
                lines.append(f"      ⚠ empty band (true void): {g['span_cm']}cm @ {g['region']}")
            if "profile" in a:
                lines.append(f"      count/slice: {a['profile']}")
            for s in a.get("sections", []):
                cs = ", ".join(
                    f"{c['length_cm']}cm{'O' if c['closed'] else 'C'}@{c['region']}"
                    for c in s["contours"]) or "— void"
                lines.append(f"      {s['pos_cm']}cm: {cs}")
    elif name == "curvature":
        d = data["distribution_pct"]
        lines.append(f"  curvature [{data['tagged']}]: "
                     f"flat {d['flat']}% / convex {d['convex']}% / "
                     f"concave {d['concave']}% / saddle {d['saddle']}%")
        for h in data.get("high_curvature", [])[:15]:
            lines.append(f"    {h['kind']} @ {h['region']} (id {h['vert_id']})")
    elif name == "region_form":
        if "note" in data:
            lines.append(f"  region_form: {data['note']}")
        else:
            lines.append(f"  region_form ({data['selected']} selected verts @ {data['region']}, "
                         f"~{data['span_cm']}cm patch):")
            lines.append(f"    form: {data['curvature_verdict']}  "
                         f"(centre−rim {data['center_vs_rim_mm']}mm)")
            lines.append(f"    projection: +{data['projection_out_cm']}cm out / "
                         f"{data['projection_in_cm']}cm in, over the patch")
            lines.append(f"    L/R mirror (across X): {data['lr_mirror_mean_mm']}mm mean / "
                         f"{data['lr_mirror_max_mm']}mm max to nearest twin vert")
            if data.get("caveat"):
                lines.append(f"    ⚠ {data['caveat']}")
    elif name == "protrusion":
        if "note" in data:
            lines.append(f"  protrusion: {data['note']}")
        else:
            lines.append(f"  protrusion ({data['selected']} selected verts @ {data['region']}, "
                         f"base plane fit to {data['ring_verts']} ring verts):")
            lines.append(f"    sticks out: {data['max_protrusion_cm']}cm max / "
                         f"{data['mean_protrusion_cm']}cm mean above the surrounding surface "
                         f"(recess {data['base_recess_cm']}cm)")
            lines.append(f"    apex @ {data['apex_world']}  (absolute — diff before/after to confirm growth)")
            if data.get("caveat"):
                lines.append(f"    ⚠ {data['caveat']}")
    elif name == "features":
        lines.append(f"  features: {data['sharp_edges']} hard edge(s) ≥{data['threshold_deg']}° "
                     f"in {data['chains']} chain(s)")
    elif name == "thickness":
        if data.get("samples"):
            lines.append(f"  thickness: {data['min_mm']}–{data['max_mm']}mm "
                         f"(median {data['median_mm']}mm, {data['samples']} samples)")
        else:
            lines.append(f"  thickness: {data.get('note', 'no data')}")
    else:
        lines.append(f"  {name}: {data}")
    return lines


@mcp.tool()
def get_topology(target: str = "", method: str = "", lod: str = "low",
                 base: str = "cage", seed: str = "") -> str:
    """
    Feel a mesh's STRUCTURE — the sense `describe` does not give. Returns named,
    grabbable landmarks (openings, branches, poles, symmetry, curvature, hard
    edges, thickness), never a raw vertex dump. Use it before any cut / graft /
    reshape: it tells you WHERE to act.

    target: mesh object name. Empty = active object.
    method: comma-separated list. Empty = the cheap bundle
            (components,genus,boundaries,sections,poles,symmetry,frame).
            Also: curvature, features, thickness (v1).
            v2 (needs scipy, not yet built): geodesic, skeleton, segments.
    lod:  low (summary landmarks) | medium | high (adds ordered boundary paths,
          located poles/curvature). Scales how much is SAID, not which mesh.
    base: cage (base control mesh — default, the right thing for topology) |
          evaluated (modifier/particle result). On a subsurfed mesh these differ.
    seed: a handle for seeded methods (v2 geodesic/segments). Unused in v1.

    Methods, briefly:
      components — separate shells (fused vs not)
      genus      — sphere/tube/handled + how many holes through it
      boundaries — the open holes: size (cm) + location (+ grabbable vert path at high lod)
      poles      — valence≠4 verts (quad-flow breaks; messy to cut through)
      symmetry   — best mirror plane + error, per axis
      frame      — intrinsic principal axes (never assumes world-up)
      sections   — cross-section sweep: where the material IS (voids, partial wraps,
                   branch splits). The COVERAGE sense topology is blind to.
      curvature  — flats/ridges/domes/saddles (fuzzy; v2 = exact)
      region_form— FORM of the current selection: convex/concave verdict, how far it
                   projects (cm), L/R mirror error — the form scalars a bbox can't show.
                   Select a patch, then read this between sculpt strokes (needs >=4
                   selected verts; read in OBJECT mode so the selection is synced).
      protrusion — ABSOLUTE protrusion of the selection above its surrounding ring
                   (cm). Where region_form is shape-relative (invariant to self-similar
                   growth), this is a ruler that moves when the form grows — diff
                   before/after to confirm a size change (needs a selection + a ring).
      features   — hard dihedral edges in chains (the machine sense)
      thickness  — local wall/part diameter (the SDF part-segmentation cue)
    """
    methods = [m.strip() for m in method.split(",") if m.strip()] if method else None
    result = call_blender("get_topology", {
        "target": target or None, "method": methods,
        "lod": lod, "base": base, "seed": seed or None,
    })
    if not result.get("success"):
        return result.get("error", "failed")
    c = result["counts"]
    head = (f"{result['object']} [base={result['base']}, lod={result['lod']}] — "
            f"{c['verts']} verts / {c['edges']} edges / {c['faces']} faces")
    lines = [head]
    for name, data in result["topology"].items():
        lines.extend(_fmt_method(name, data))
    return "\n".join(lines) + _status(result)


def region_baseline(name: str = "", base: str = "cage") -> str:
    """G45 — snapshot the live selection's form as a named baseline to diff after an
    edit. Read-only-ish (no geometry change); no status block."""
    result = call_blender("region_baseline", {"name": name, "base": base})
    if not result.get("success"):
        return result.get("note") or result.get("error", "failed")
    m = result["metrics"]
    return (f"baseline '{result['name']}' captured ({result['verts']} verts on "
            f"{result['owner']}): span {m.get('span_cm','?')}cm, "
            f"proj +{m.get('projection_out_cm','?')}cm, "
            f"{m.get('curvature_verdict','?')}, "
            f"L/R {m.get('lr_mirror_mean_mm','?')}mm\n"
            f"  → edit, then feel op=diff name={result['name']} for the signed change")


def region_diff(name: str = "") -> str:
    """G45 — signed change per metric over a named baseline's SAME verts. The local,
    temporal verification a global bbox/symmetry read can't give."""
    result = call_blender("region_diff", {"name": name})
    if not result.get("success"):
        return result.get("error", "failed")
    d = result["delta"]
    units = {"span_cm": "cm", "projection_out_cm": "cm", "projection_in_cm": "cm",
             "center_vs_rim_mm": "mm", "lr_mirror_mean_mm": "mm",
             "max_protrusion_cm": "cm", "centroid_shift_cm": "cm"}
    lines = [f"region '{result['name']}' Δ since baseline (same verts):"]
    for k, v in d.items():
        sign = f"{v:+}" if k != "centroid_shift_cm" else f"{v}"
        lines.append(f"  {k}: {sign}{units.get(k,'')}")
    return "\n".join(lines)
