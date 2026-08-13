# blender-buttons

**An MCP server that lets an AI agent drive Blender by intent, not coordinates.**

<!-- hero demo GIF goes here — see bugs.md B5 -->

Blender is uniquely hostile to an LLM. It is a modal, state-heavy design tool built
for a human with a mouse: the right mode, the right selection, an orbit, a grab,
undo, look again. The work is spatial and iterative. The atom it edits is an XYZ
vert — and a language model will invent a plausible one if you let it type
coordinates. Get any of that slightly wrong (stale mode, inverted axis, a guessed
offset) and the mesh is already dead; the next fifty lines just bury it.

That is why this project exists. A bpy-through-MCP session hands the model the
thing it is worst at and calls it a driver. blender-buttons refuses that currency.
The agent speaks **dimensions** (`width=0.04`) and **relationships**
(`on={"between": ["a","b"]}`, `snap`, a named handle). The server holds the
coordinates so the model can hold **names and relationships**. It reads the scene
(`look` → descend → claim → modify, with `feel` as the measuring instrument)
instead of imagining it, and an always-on `validate` floor so it cannot build on
broken geometry without noticing. Ask a model to carry `(x, y, z)` across fifty
tool calls and a 16-part chair hides the drift; a hundred-part character exposes
it. The answer is to stop asking.

Targets **Blender 5.x** (verified against 5.2 LTS). MIT.

> **New here?** [`GUIDANCE_FOR_LLMS.md`](GUIDANCE_FOR_LLMS.md) is the field manual
> (served to agents as the `guidance://llms` MCP resource), and
> [`recipes/donut/donut.md`](recipes/donut/donut.md) is a verified end-to-end build.
> The thesis lives in [`project-vision.md`](project-vision.md).

## What a build looks like

The classic donut tutorial, in the server's own verbs — no `(x, y, z)` typed anywhere:

```
add type=torus name=Donut major_radius=0.03 minor_radius=0.013
look target=Donut                              # a salience window: landmarks + offered selections
select op=claim candidate=c2 name=icing_zone   # claim the offered upper region — now a named handle
modifier op=add_asset target=Donut asset="Scatter on Surface" collection=Sprinkles
```

Every mutating call answers with ground truth the agent didn't ask for:

```
── blender status ──────────────────────────────
  active:      Icing (MESH)
  dims:        [0.088, 0.088, 0.014]
  bounds:      x=[-0.044, 0.044]  y=[-0.044, 0.044]  z=[-0.002, 0.012]
  ...
validate: clean — no defects, no undeclared clips
```

The agent reads those bounds, derives the next number from them, and keeps going. A
whole stacked assembly can be built as arithmetic on previous status blocks — zero
screenshots, zero placement corrections.

## Three ideas do the work

**1. Intent-space, not coordinate-space.** Every verb takes dimensions and relational
anchors. The typed-coordinate escape hatches are gone *by design* — if you can't reach
a spot relationally, you mint a handle there and address it by name forever after.

**2. THE ONE RULE — derive, don't divine.** The poison was never the coordinate; it's
the *source*. A number computed from something the server just handed you (a
status-block bound, a `feel` read) or from a dimension you authored is legitimate
arithmetic. A number fabricated from intuition — "nudge it ~0.02, looks about right" —
is the sin. The test is **provenance**: for every number the agent types, it can name
the measured or authored value it descends from. "It felt right" is not a provenance.

**3. Two forced senses — the agent doesn't get to close its eyes.** Every mutation
returns a `feel` note (what you just changed — eyes, no verdict) and a `validate`
result (what's broken — z-fighting, non-manifold edges, flipped normals, degenerate
faces). The correctness floor is unsilenceable. Intended overlaps — hair under a
scalp, a tenon in its mortise — must be *declared* (`validate op=expect` with a
reason); there is no "ignore," only "I intend this," and the declaration becomes a
tripwire if the overlap later drifts.

## How it's developed: the gap engine

This repo is built by the agent that uses it, against real modeling sessions — a
donut, a hand, a pocketwatch, a character blockout, a 14" MacBook Pro. The process:

1. The agent models something real and hits a wall — an intent it can't express, a
   read it can't take, a silent failure.
2. The wall goes into [`gaps.md`](gaps.md) as a numbered gap (**G#**), framed as a
   *general* primitive — never "add a bangs builder," always "what's the general
   operation underneath?"
3. The fix ships, gets verified live against a scene, and the entry is **deleted**.
   Numbers are never reused; the counter recently passed **G231**.

Two rules keep the loop honest. Every fix must be a **general primitive** that
composes across any task — if a proposed tool can't be described without naming a body
part or a domain object, it's too specific. And the dogfood is kept **blind**: the
modeling agent gets no cheat-sheet beyond what the server itself teaches on connect
(its `instructions` + the `guidance://llms` resource, or `look op=guide` when the
client has no resource reader). A server that only works
because the operator memorized it is not a finished server — *the server must teach
itself, and that is the thing under test.*

The same philosophy is being projected onto Unreal Engine 5 in a sister project
(`ue-buttons`).

## North star

An agent that can model a **stylized anime-grade character** — Genshin / Guilty Gear
Strive tier — over a multi-hour session: sculpt, retopo, UV, rig, weights, hair,
directed by a human who owns taste but can't hand-model. It isn't there yet; every gap
closed during real modeling is a step. The donut tutorial is the smoke test, not the
destination.

## The verb surface

Every verb is one MCP tool taking an `op=` discriminator; **each verb's schema
enumerates every op and its args**, so the surface is self-describing. `tools/list`
returns 22 schemas, not hundreds of flat tools.

| Verb | The menu it is |
|------|----------------|
| `look` | **The loop's eyes** — landmark LOD windows: `look target=` opens a salience window, `at=` descends, windows offer claimable selections |
| `add` | Add menu — box / cylinder / sphere / torus / curve / text / light / camera / … with dimensions + relational `on=` placement |
| `object` | Object Mode — rename, duplicate, join, group, delete, convert, visibility, remesh |
| `edit` | Edit Mode / Mesh menu — loop-cut, extrude, bevel, spin, bridge, boolean, grab/scale (with proportional editing), shrink_fatten, randomize, lattice |
| `select` | Select menu — claim offered candidates, pick, by axis/between/radius, boundary, rings, grow/shrink, INTERSECT |
| `transform` | place / nudge / rotate / scale / resize / snap / rest_on / seat / distribute |
| `modifier` | Modifier Properties — add/apply, incl. `op=add_asset` for the native GN modifiers (Scatter on Surface, Array-Circular, …) |
| `material` | Material Properties / shading — Principled scalars, `op=image` (packed image → base/emission, space=uv\|box), shade smooth/flat, texture/HDRI search |
| `sculpt` | Sculpt Mode brushes |
| `pose` | Pose Mode / armature — rigging, weights, binding, shape keys |
| `scene` | Outliner + scene-level Properties |
| `view` | Viewport View menu + camera viewpoint — rig, framing/exposure checks, active camera |
| `render` | Render menu |
| `history` | Undo / Redo + the operation log |
| `file` | File menu — `.blend` persistence |
| `feel` | **The measuring instrument** — profile / section / anchor / verify / overlaps / contacts / facing / resting / aim; diagnostics beside the `look` loop |
| `validate` | **The always-on correctness floor** — and `op=expect` to declare an intended overlap |
| `script` | SPEC-23 transport — `batch` / `exec` / `dry_run`, hard cap 25, one receipt per phase; progressive bulk, not a bpy megascript |
| `connect` | Choose which Blender instance this session drives (list / attach / launch) |
| `collab` | Shared-state collaboration surface |
| `addon` | Drive any installed Blender addon/extension by name |
| `uv` | UV unwrap & texture-space mapping |

There are no macro verbs. Multi-step methods — shells, drips, ring welds, revolved
vessels, smooth unions — are **techniques**: short method docs in native Blender
vocabulary, served on demand as `guidance://techniques/…` resources ([`techniques/`](techniques/)).
A macro compiles the adaptation between steps into code, where it can't happen; a
technique leaves it to the agent, live, with perception reads between steps (SPEC-21).

The depth — the loop, the reads, the failure modes — lives in
[`GUIDANCE_FOR_LLMS.md`](GUIDANCE_FOR_LLMS.md), served verbatim as the
`guidance://llms` MCP resource and as `look op=guide` (G228 — clients without a
resource reader). Agents are told to read it before improvising any multi-step task.

## Auto-status

Every state-modifying verb appends the `── blender status ──` block shown above to its
return string — mode, active object, world bounds, rotation, edit-mode selection
counts — so the agent never calls a "get status" tool after an op. It's ground truth
for that call; when an op acts on a name-addressed object that isn't the
viewport-active one, the block labels the bounds `acted_on:` so the numbers are never
ambiguous. Read-only reads (`feel`, `history`, scene trees) don't append it.

## Architecture

```
Agent / LLM harness
      │  MCP over stdio (JSON-RPC)  —  22 verbs, each dispatched by op=
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
main thread** via a queue, so Blender's API is never touched from a background thread.
Several Blender instances can run at once, each on its own port from `8765` up; a
session attaches to one (the `connect` verb lists / attaches / launches).

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

## Showcase — the donut

[`recipes/donut/donut.md`](recipes/donut/donut.md) is a verified transcript-recipe —
every number ran — that builds the classic Blender-tutorial donut end to end in these
verbs: a torus dough body, an offset **icing shell** (the
[shell technique](techniques/shell.md); the old `buttons-shell-macro op=clad` is
retired) with a draped organic drip rim, multi-color **sprinkles** via the native
*Scatter on Surface* GN modifier, PBR materials, a relationally-rigged light and
camera, and a final render tuned by reads (`view op=check_framing` /
`check_exposure`) rather than trial renders. It doubles as the best worked example
of the whole verb surface.

## Repo layout

```
server/            MCP server — verb layer (server/verbs/) over flat helpers
extension/         Blender addon — socket server + bmesh/bpy operations (bundled by build)
recipes/           Verified end-to-end build recipes (donut, hand) — a recipe promises a RESULT
techniques/        Named multi-step methods in native vocabulary (guidance://techniques) — an APPROACH
docs/              Specs (SPEC-##)
tests/             Headless e2e suites (need a live/background Blender)
GUIDANCE_FOR_LLMS.md   The field manual — read before modeling (served as guidance://llms)
project-vision.md      Thesis, design principles, north star
gaps.md                The gap engine — tool-surface friction log
bugs.md                Repo defects (docs, packaging, hygiene)
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
