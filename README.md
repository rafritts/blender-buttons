# blender-buttons

An MCP server that lets an agent drive Blender by **intent, not coordinates**. It
perceives (`feel`), measures, validates, and mutates through **~15 verbs** — the same
menus a human uses (add, edit, select, transform, modifier, material, sculpt, pose,
scene, view, render, file, history) plus a perception verb (`feel`) and an always-on
correctness floor (`validate`). You place things *relationally* — on, between, left_of,
snap, at a named handle — and the server holds the coordinates so the model can hold
names and relationships.

It targets **Blender 5.x** (verified against 5.1).

> **New here?** Read [`GUIDANCE_FOR_LLMS.md`](GUIDANCE_FOR_LLMS.md) before you model
> anything, and see [`recipes/donut/donut.md`](recipes/donut/donut.md) for a verified
> end-to-end build written entirely in these verbs. The project's thesis and design
> principles live in [`project-vision.md`](project-vision.md).

## What makes it different

Three ideas do the work:

- **Intent-space, not coordinate-space.** LLMs (and humans) collapse when they carry
  `(x, y, z)` across calls and compute offsets in working memory. So every verb takes
  *dimensions* (`width=0.04`) and *relational anchors* (`on={"between": ["a","b"]}`,
  `snap_to`, a handle addressed by name). The typed-coordinate escape hatches are gone by
  design — if you can't reach a spot relationally, mint a handle there and address it.

- **Derive, don't divine (THE ONE RULE).** Your sense of where things are is a
  hypothesis, never ground truth. A number computed from something the server just handed
  you (a status-block bound, a `feel` read) or from a dimension you authored is legitimate
  arithmetic. A number *fabricated* from intuition — "nudge it ~0.02, looks about right" —
  is the sin. The test is **provenance**: for every number you type, you can name the
  measured or authored value it descends from.

- **Two forced senses.** Every mutating call comes back with a `feel` note (what you just
  changed — your eyes, no verdict) and a `validate` result (what's broken — z-fighting,
  non-manifold, flipped normals, degenerate geometry). The correctness floor is always on
  and unsilenceable; intended overlaps must be *declared* (`validate op=expect`), never
  ignored.

## Architecture

```
Agent / LLM harness
      │  MCP over stdio (JSON-RPC)  —  ~15 verbs, each dispatched by op=
      ▼
server/main.py          ← FastMCP server; the verb layer (server/verbs/)
      │  TCP socket, localhost:8765+, newline-delimited JSON
      ▼
extension/__init__.py   ← Blender addon, runs inside Blender's Python interpreter
      │  bpy / bmesh, on the main thread via a queue
      ▼
Blender 5.x
```

The MCP server is a thin wrapper: it routes each verb to a flat helper, which sends a
newline-delimited JSON command over the socket. All logic runs **inside Blender on the
main thread** via a queue; the addon enforces this so Blender's API is never called from a
background thread. Several Blender instances can run at once, each on its own port from
`8765` up; a session attaches to one (use the `connect` verb to list/attach/launch).

## Install & connect

**1. Build the addon zip** (bundles every module in `extension/` + the manifest):

```bash
./build_extension.sh          # → blender_buttons.zip (gitignored)
```

**2. Install it in Blender 5.x:** Edit → Preferences → Add-ons → *Install from Disk…* →
pick `blender_buttons.zip`, then enable **Blender Buttons**.

**3. Start the server:** in the addon's panel (Properties → Scene → Blender Buttons),
click **Start Server**. It listens on `localhost:8765`.

**4. Point your MCP client at it.** The repo ships a portable [`.mcp.json`](.mcp.json)
(relative paths — works from the repo root):

```json
{
  "mcpServers": {
    "blender-buttons": {
      "command": ".venv/bin/python",
      "args": ["server/main.py"]
    }
  }
}
```

Works in Claude Code (`.mcp.json`), Claude Desktop, Cursor, Windsurf, or any
MCP-compatible harness. Set up the venv once with [`uv`](https://docs.astral.sh/uv/):
`uv sync`.

> **Blender 4.x is not supported.** The manifest pins `blender_version_min = "5.0.0"`;
> several verbs (e.g. `modifier op=add_asset "Scatter on Surface"`) depend on the
> Geometry-Nodes Essentials assets that only ship in 5.x.

## The verb surface

Every verb is one MCP tool. It takes an `op=` (or `type=`) discriminator that selects the
operation, and a flat set of args — **the verb's own schema enumerates every op and the
args each one uses**, so the surface is self-describing. `tools/list` returns ~26 schemas,
not hundreds of flat tools.

| Verb | The menu it is |
|------|----------------|
| `add` | Add menu — box / cylinder / sphere / torus / curve / light / camera / … with dimensions + relational `on=` placement |
| `object` | Object Mode — select, rename, duplicate, join, group, delete |
| `edit` | Edit Mode / Mesh menu — loop-cut, extrude, bevel, ring shaping, noise-displace, smooth |
| `select` | Select menu — by axis, between, by radius, boundary, rings, grow/shrink, INTERSECT |
| `transform` | move / rotate / scale / resize / snap / mirror / array |
| `modifier` | Modifier Properties — add/apply, incl. `op=add_asset` for the native GN modifiers (Scatter on Surface, Array-Circular, …) |
| `material` | Material Properties / shading — solid colors, PBR-folder import, Principled values |
| `sculpt` | Sculpt Mode brushes |
| `pose` | Pose Mode / armature — rigging, weights, binding, shape keys |
| `scene` | Outliner + scene-level Properties |
| `view` | Viewport View menu + camera viewpoint — rig, framing/exposure checks, active camera |
| `render` | Render menu |
| `history` | Undo / Redo + the operation log |
| `file` | File menu — `.blend` persistence |
| `feel` | **The sense** — profile / section / anchor / verify / overlaps / contacts / facing / resting / aim, plus measurements |
| `validate` | **The always-on correctness floor** — and `op=expect` to declare an intended overlap |
| `connect` | Choose which Blender instance this session drives (list / attach / launch) |
| `collab` | Shared-state collaboration surface |
| `addon` | Drive any installed Blender addon/extension by name |
| `uv` | UV unwrap & texture-space mapping |

Six composite **macros** bundle multi-step operations behind one call, each tagged with
its native-Blender cousin:

| Macro | Purpose |
|-------|---------|
| `buttons-shell-macro` | Shell builders — e.g. `clad` mints an offset shell hugging a selected region (icing, armor, panels) |
| `buttons-blend-macro` | Algebraic mass/patch merge (boolean + smooth-union family) |
| `buttons-deform-macro` | Formula / sweep deforms |
| `buttons-lathe-macro` | Surface-of-revolution / ring-family builders |
| `buttons-connector-macro` | Swept, geometry-bound connectors |
| `buttons-npr-macro` | Non-photoreal look macros |

The depth — the battle-tested loops for *finding geometry* and *building forms* — lives in
the `guidance://llms` MCP resource (served verbatim from `GUIDANCE_FOR_LLMS.md`). Read it
before improvising any multi-step task.

## Auto-status

Every state-modifying verb appends a `── blender status ──` block to its return string, so
you never call a "get status" tool manually after an op — it fires automatically and is
**ground truth for that call**. Trust its world bounds over anything you remember.

```
── blender status ──────────────────────────────
  active:      Donut (MESH)
  selected:    ['Donut']
  dims:        [0.086, 0.086, 0.021]     (world bbox, rotation-aware)
  bounds:      x=[-0.043, 0.043]  y=[-0.043, 0.043]  z=[-0.0104, 0.0106]
  rot_deg:     [0.0, 0.0, 0.0]
  last_action: {id, label, tool}
  render:      BLENDER_EEVEE  view=AgX look=None exp=0.0 gamma=1.0
  ── edit ──                              ← only in Edit Mode
  component:   FACE
  selected:    {verts, edges, faces}  /  total: {verts, edges, faces}
  sel_z:       [min_z, max_z]
  sel_bounds:  x=[..]  y=[..]  z=[..]
  lr_balance:  0.0cm from X-center        ← the mesh's own left/right split
────────────────────────────────────────────────
```

When an op acts on a name-addressed object that isn't the viewport-active one, the block
labels the bounds `acted_on:` and shows the lagging `vp_active:` so the numbers are never
ambiguous. Read-only reads (`feel`, `history`, scene trees, screenshots) don't append it.

## Showcase — the donut

[`recipes/donut/donut.md`](recipes/donut/donut.md) is a verified transcript-recipe —
every number ran — that builds the classic Blender-tutorial donut end to end in these
verbs: a torus dough body, an offset **icing shell** (`buttons-shell-macro op=clad`) with a
draped organic drip rim, multi-color **sprinkles** via the native *Scatter on Surface* GN
modifier, PBR materials, a relationally-rigged light and camera, and a final render tuned
by reads (`view op=check_framing` / `check_exposure`) rather than trial renders. It doubles
as the best worked example of the whole verb surface.

## Repo layout

```
server/            MCP server — verb layer (server/verbs/) over flat helpers
extension/         Blender addon — socket server + bmesh/bpy operations (bundled by build)
recipes/           Verified end-to-end build recipes (donut, hand)
docs/              Specs (SPEC-##)
tests/             Headless e2e suites (need a live/background Blender)
GUIDANCE_FOR_LLMS.md   The depth — read before modeling (served as guidance://llms)
project-vision.md      Thesis, design principles, north star
gaps.md                Tool-surface friction log — the engine of the project
build_extension.sh     Builds blender_buttons.zip from extension/
```

## Rebuilding the addon

```bash
./build_extension.sh
```

Then reinstall the updated zip in Blender (Preferences → Add-ons → Install from Disk),
re-enable the addon, and click **Start Server**.

## License

MIT — see [`LICENSE`](LICENSE).
