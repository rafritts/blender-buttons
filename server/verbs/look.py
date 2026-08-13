"""look — the loop's eyes (SPEC-21 §6).

Landmark LOD windows: `look target=<obj>` opens the root window (an orientation
line + salience-ranked landmarks); `look at=<landmark|position token>` descends,
re-running the same breakdown at that finer scale; `look up` pops. The window
stack — where you're looking, at what scale — is held server-side. Salience,
never semantics: the server names protrusions/islands/densities/rims; the agent
names the finger.
"""

from typing import Literal

from server._core import mcp, call_blender
from server.guidance import serve_guide
from ._common import tag


def _fmt_window(res: dict) -> str:
    w = res.get("window") or {}
    lines = []
    root = " (root)" if w.get("root") else ""
    lines.append(f"── look: {w.get('id')}  {w.get('label')}{root} "
                 f"{'─' * max(1, 46 - len(str(w.get('label'))))}")
    fv = w.get("face_view")
    if fv:
        # single-face vert view (§6.2) — the only place vert coords appear,
        # and only as Δs from the face centre (world axes)
        lines.append(f"  window:  face {fv['face']} · {w.get('n_verts')} verts · "
                     f"{fv['area']} · normal {fv['normal']}")
        lines.append("  verts (local frame — Δ from the face centre along world "
                     "axes; shares = face-incidence):")
        for v in fv["verts"]:
            lines.append(f"    {v['id']:<6} {v['at']:<34} shares {v['shares']} faces")
        lines.append("  edges: " + " · ".join(fv["edges"]))
        idx = ", ".join(v["id"][1:] for v in fv["verts"])
        lines.append(f"  act: select op=by_index indices=[{idx}] (any subset) · "
                     f"look up to widen")
        stack = w.get("stack") or []
        nav = " ▸ ".join(stack)
        lines.append(f"  stack: {nav} · back: look up")
        return "\n".join(lines)
    size = "×".join(w.get("size", []))
    shells = w.get("shells_in_window", 1)
    shell_s = f"{shells} shell{'s' if shells != 1 else ''} in window"
    lines.append(f"  window:  {w.get('n_faces')} faces / {w.get('n_verts')} verts · "
                 f"{size} · {shell_s}")
    if w.get("root"):
        if w.get("symmetric_x"):
            # front=−Y, up=+Z ⇒ subject-right = front×up = −X (G224). Position
            # tokens stay world-axis, so finish the sentence: translate the
            # character's handedness to the token the agent will actually type.
            sym = ("bilateral across X ⇒ subject's left = +X (window right), "
                   "subject's right = −X (window left)")
        else:
            sym = "no X symmetry detected"
        lines.append(f"  orient:  up=+Z · front=−Y · {sym}")
    lms = w.get("landmarks") or []
    if lms:
        lines.append("  landmarks (salience-ranked — descend: look at=<id or token>):")
        for lm in lms:
            extra = ""
            if lm.get("perimeter"):
                extra = f", rim perimeter {lm['perimeter']}"
            if lm.get("valence"):
                extra = f", valence-{lm['valence']} fan"
            twin = f"   (mirror twin: {lm['twin']})" if lm.get("twin") else ""
            lines.append(f"    {lm['id']:<3} {lm['token']:<18} {lm['channel']:<11} "
                         f"{lm['extent']:>7}  {lm['n_faces']} faces{extra}{twin}")
    else:
        lines.append("  landmarks: none stood out — the window is uniform at this "
                     "scale; descend by position token ('top-right') to zoom anyway")
    if w.get("tail"):
        lines.append(f"  tail (grouped, addressable as at=tail): {w['tail']}")
    cands = w.get("candidates") or []
    if cands:
        lines.append("  offered (claim: select op=claim candidate=<id> name=<yours>; "
                     "omit name to just select):")
        for c in cands:
            kind = c["kind"] + (f" '{c['label']}'" if c.get("label") else "")
            extra = f", rim {c['perimeter']}" if c.get("perimeter") else ""
            if c.get("in_window_verts") is not None:
                # G223: the vgroup spills past the window — n_verts is the WHOLE
                # entity (what a claim takes); flag how little is shown here.
                extra += (f" — whole vgroup; only {c['in_window_verts']} of "
                          f"{c['n_verts']} verts in this window, claim takes all")
            twin = f"   (mirror twin: {c['twin']})" if c.get("twin") else ""
            lines.append(f"    {c['id']:<3} {kind:<18} {c['token']:<18} "
                         f"{c['extent']:>7}  {c['n_faces']} faces / "
                         f"{c['n_verts']} verts{extra}{twin}")
    if w.get("coverage"):
        lines.append(f"  coverage: {w['coverage']}")
    frs = w.get("face_rings") or []
    if frs:
        lines.append("  faces (BFS rings out from the window centre — vert view: "
                     "look at=f<id>):")
        for ln in frs:
            lines.append(f"    {ln}")
    elif w.get("bottom_level"):
        lines.append("  bottom-level window (≤40 faces)")
    stack = w.get("stack") or []
    nav = " ▸ ".join(stack)
    up = " · back: look up" if len(stack) > 1 else ""
    lines.append(f"  stack: {nav}{up}")
    return "\n".join(lines)


@mcp.tool(name="look")
def look(
    op: Literal["window", "guide"] = "window",
    target: tag(str, "open the ROOT window on this mesh (replaces the stack)") = "",
    at: tag(str, "DESCEND within the current window: a landmark id (L2), its "
                 "position token (top-right), 'tail' (the grouped minor landmarks), "
                 "a bare position token to zoom a region with no landmark, or a "
                 "face id (f12) from the ring enumeration — the single-face vert "
                 "view") = "",
    up: tag(bool, "pop back to the parent window") = False,
    topic: tag(str, "[op=guide] which document: omit / 'llms' = field manual; "
                    "'techniques' = the index; a slug (shell, form-blockout, …) "
                    "= that technique. Same text as guidance://, for clients "
                    "with no resource reader (G228).") = "",
) -> str:
    """
    **The loop's eyes** — look → descend → claim → modify is how you work here.

    `op=guide` is the teaching channel for clients that have tools but no MCP
    resource reader (G228). `look op=guide` returns GUIDANCE_FOR_LLMS.md;
    `topic=techniques` is the index; `topic=<slug>` is one technique. The
    `guidance://llms` / `guidance://techniques/*` resources stay as the
    secondary route. Guide mutates nothing.

    `look target=<mesh>` opens the root window: one orientation line plus 5–9
    salience-ranked landmarks (protrusions, islands, dense patches, poles, open
    rims), each with a position token, a scale, and a face count. The tail is
    grouped, never dropped. `look at=<L#|token>` descends — the same breakdown,
    re-run at that finer scale (zoom IS the scale picker: a body-scale scan
    can't see a nose; the face window sees it natively). `look up` pops; bare
    `look` re-describes the current window. The window stack is held server-side
    — your attention persists between calls.

    Salience is not semantics: the server reports "two top protrusions"; you
    bring "those are arms". Every window also OFFERS candidates — pre-run
    segmentations (islands, crease-bounded regions, protrusion cuts, boundary
    loops, material/vgroup patches) you claim instead of hand-building:
    `select op=claim candidate=c2 name=left_arm` selects it and mints a durable
    handle (omit name= to just select). The coverage line says how much of the
    window the offer reaches — the rest needs hand selection. Candidates are
    ephemeral (per window); claimed handles persist in the .blend.

    Coordinate starvation (§6.2): faces are the currency. A bottom-level window
    (≤40 faces) enumerates them as BFS rings out from the window centre, areas
    only. `look at=f<id>` opens the single-face vert view — the ONLY place vert
    coordinates appear, as Δs from the face centre along world axes, each vert
    with its face-incidence ("shares 8 faces" = a pole). World XYZ never crosses
    the wire; frame transforms are the server's job.

    Windows invalidate on topology edits (the error says how to re-open — not
    your fault). For precise measurement, relational forensics, or when a window
    contradicts your expectation, drop to `feel` — the diagnostic instrument.
    """
    if (op or "window").lower().strip() == "guide":
        return serve_guide(topic)
    p = {}
    if target:
        p["target"] = target
    if at:
        p["at"] = at
    if up:
        p["up"] = True
    res = call_blender("look_window", p)
    if not res.get("success"):
        return res.get("error", "failed")
    return _fmt_window(res)
