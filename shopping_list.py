"""Implementation shopping list for blender-buttons.

Each entry is a self-contained spec for one tool/fix, written to be fulfilled
WITHOUT access to the conversation that produced it. Work them in `priority`
order. `complexity`/`risk` describe the nature of the work, not duration.

Conventions that apply to EVERY task:
- Architecture: FastMCP server (server/*.py) <-> TCP localhost:8765 <-> Blender
  addon (extension/*.py). All bpy/bmesh work runs on Blender's main thread via
  the addon's queue. Server wrappers are thin; logic lives in the extension.
- New modules follow the precedent of extension/curves.py + server/rings.py:
  themed module per side, registered the same way existing ones are.
- Every setter needs a getter: new material/object state must be readable back
  via describe() / get_object_info() (see gaps.md D4 for why).
- Every mutating tool returns the standard status block (see existing tools).
- Verify by extending tests/e2e_headless.py (headless flatpak Blender run)
  with assertions for each acceptance criterion. All existing assertions must
  still pass.
- gaps.md sections E1-E8 (treasure chest build) hold extra context for T3/T6/T7.
"""

SHOPPING_LIST = [
    {
        "id": "T1",
        "priority": 1,
        "title": "set_toon_material - anime/cel shader as a fixed parameterized node graph",
        "complexity": "medium - the node graph itself is boilerplate; the care is in "
                      "keeping parameters few, orthogonal, and visually judgeable",
        "risk": "low - additive, local, no existing behavior changes; a bad shader "
                "is just an ugly screenshot",
        "files": {
            "new": ["extension/shaders.py", "server/shaders.py"],
            "touch": ["extension/common.py (material_summary readback)",
                      "tests/e2e_headless.py"],
        },
        "spec": {
            "signature": "set_toon_material(target, base_color, shadow_color=None, "
                         "bands=2, shadow_softness=0.05, rim_color=None, "
                         "rim_width=0.2, gradient_top=None, gradient_bottom=None, "
                         "material_name='')",
            "semantics": [
                "target: object OR group name, same expansion rules as set_material.",
                "Builds ONE fixed node graph (agents never touch raw nodes):",
                "  ShaderNodeBsdfDiffuse -> ShaderNodeShaderToRGB -> ShaderNodeValToRGB",
                "  (ColorRamp, CONSTANT interpolation, `bands` stops between",
                "  shadow_color and white; shadow_softness > 0 switches the last stop",
                "  pair to LINEAR over that fraction) -> MixRGB(MULTIPLY) with the",
                "  base color -> ShaderNodeEmission -> Material Output.",
                "shadow_color default: base_color scaled 0.55 and hue-shifted slightly "
                "cool (anime shadows are cool, not black).",
                "rim_color set: ShaderNodeLayerWeight(facing) -> ColorRamp (cutoff at "
                "1 - rim_width) -> MixRGB(ADD) into the color path before Emission.",
                "gradient_top/bottom set: ShaderNodeTexCoord(Object) -> SeparateXYZ(Z) "
                "-> MapRange(object z min..max) -> ColorRamp(bottom->top) replaces the "
                "flat base color input.",
                "Idempotent: material reused by name, parameters updated in place "
                "(mirror set_material's reuse-by-name behavior).",
                "Store ALL parameters + {'graph_version': 1} as JSON in a custom "
                "property mat['bb_toon']. describe()/material_summary() report it "
                "verbatim instead of parsing the graph.",
            ],
            "constraints": [
                "Shader-to-RGB is Eevee-only. State this in both docstrings and note "
                "that Cycles renders of these materials will look wrong.",
                "Colors are scene-linear floats 0..1 (same convention as set_material; "
                "see gaps.md E6).",
            ],
        },
        "acceptance": [
            "e2e: create a sphere, set_toon_material with bands=3 -> material exists, "
            "mat['bb_toon'] round-trips all params, node tree contains ShaderNodeShaderToRGB "
            "and a CONSTANT-interpolation ColorRamp with 3 stops.",
            "e2e: calling it twice with different shadow_color updates the same "
            "material datablock (no .001 duplicates).",
            "e2e: describe(<object>) output contains the toon parameter summary.",
        ],
    },
    {
        "id": "T2",
        "priority": 2,
        "title": "add_outline - inverted-hull cartoon outline",
        "complexity": "low - one modifier plus one material, well-known technique",
        "risk": "low - additive; worst case is a visible artifact, removable via "
                "remove_outline",
        "files": {
            "new": [],
            "touch": ["extension/shaders.py", "server/shaders.py",
                      "tests/e2e_headless.py"],
        },
        "spec": {
            "signature": "add_outline(target, thickness=0.01, color=(0, 0, 0)) and "
                         "remove_outline(target)",
            "semantics": [
                "Inverted-hull method on the object itself (no duplicate object):",
                "1. Append a second material slot: emission shader in `color`, "
                "use_backface_culling=True.",
                "2. Add a Solidify modifier named 'bb_outline': thickness=thickness, "
                "use_flip_normals=True, material_offset=1, offset=1.",
                "target accepts object or group (expand like other tools).",
                "remove_outline deletes the modifier and the slot it added, nothing else.",
                "Record state in obj['bb_outline'] so describe() can report it and "
                "remove_outline knows exactly what to take out.",
            ],
            "constraints": [
                "Must compose with T1: outline slot is APPENDED, slot 0 keeps the toon "
                "material. Do not reorder slots.",
                "thickness is world meters - on a 1m prop, 0.005-0.015 is the sane range; "
                "say so in the docstring.",
            ],
        },
        "acceptance": [
            "e2e: box + add_outline -> modifier 'bb_outline' exists with flipped normals, "
            "2 material slots, slot 1 backface-culled emission.",
            "e2e: remove_outline restores 1 slot and 0 'bb_outline' modifiers.",
            "e2e: add_outline on a toon-shaded object leaves mat['bb_toon'] material in "
            "slot 0 untouched.",
        ],
    },
    {
        "id": "T3",
        "priority": 3,
        "title": "Fix undo/history desync + add redo (gaps.md E1 - CRITICAL)",
        "complexity": "medium - small code, but it touches global editor state and "
                      "must be reasoned about, not pattern-matched",
        "risk": "high - this is the one task that can corrupt scenes if wrong. "
                "gaps.md E1 documents undo(steps=2) resetting an entire 27-op build "
                "to the startup file. Do not ship without the e2e proof below.",
        "files": {
            "new": [],
            "touch": ["extension/history.py", "extension/server.py (op dispatch)",
                      "server/history.py", "tests/e2e_headless.py"],
        },
        "spec": {
            "semantics": [
                "1. After every MUTATING tool completes successfully, the addon calls "
                "bpy.ops.ed.undo_push(message=<op_id>) so one tool call == one undo step. "
                "Read-only tools (get_*, describe, screenshots, viewport moves) must NOT push.",
                "2. undo(steps=N) then walks back exactly N pushed steps and pops N "
                "entries from the history log - the log and Blender's stack stay 1:1.",
                "3. POST-UNDO VERIFICATION: before returning, compare live scene object "
                "names against the set recorded for the target history entry (record the "
                "scene's object-name set per entry at push time). On mismatch, return a "
                "loud warning naming what diverged - never report silent success.",
                "4. New tool redo(steps=1) wrapping bpy.ops.ed.redo(), same verification.",
                "5. If undo_push proves unreliable from the socket/timer context (known "
                "Blender quirk - test this FIRST), fall back to: undo_push still attempted, "
                "but undo() refuses to run when the verification snapshot is missing, with "
                "an error directing the agent to save_design checkpoints. A refusing undo "
                "is acceptable; a lying undo is not.",
            ],
        },
        "acceptance": [
            "e2e: add 5 boxes, undo(steps=2) -> exactly 3 boxes remain, history shows 3 "
            "entries, status reports what was reverted.",
            "e2e: redo(steps=1) after the above -> 4 boxes.",
            "e2e: undo past available depth returns an error, scene untouched.",
            "e2e: the D-series regression suite still passes start to finish after "
            "interleaving undo/redo mid-sequence.",
        ],
    },
    {
        "id": "T4",
        "priority": 4,
        "title": "Fix placement DSL resolving before rotation (gaps.md E2)",
        "complexity": "low - bbox math, fully specified in gaps.md E2",
        "risk": "medium - placement is load-bearing for every build; regressions are "
                "subtle (things land NEAR right). The e2e additions are the guard.",
        "files": {
            "new": [],
            "touch": ["extension/placement.py", "extension/primitives.py",
                      "tests/e2e_headless.py"],
        },
        "spec": {
            "semantics": [
                "resolve_placement currently uses the UNROTATED primitive bbox; rot_x/y/z "
                "is applied after, so rotated primitives land wrong (a rot_y=90 cylinder "
                "placed on= a surface floats above it).",
                "Fix: compute the post-rotation world bbox FIRST (rotate the 8 bbox corners "
                "by the rotation euler, take min/max), then resolve on/under/left_of/... "
                "against those extents.",
                "Update the PLACEMENT DSL doc comment in server/primitives.py - it currently "
                "documents the broken ordering ('rotation applied after placement').",
            ],
        },
        "acceptance": [
            "e2e: add_box floor; add_cylinder(radius=0.3, height=1, rot_y=90, "
            "on={'on': 'floor_box'}) -> cylinder bbox z_min == floor_box z_max +/- 1e-4 "
            "(it rests on the surface, not floating).",
            "e2e: same check for rot_x=90 with in_front_of (y_max flush).",
            "e2e: all existing unrotated placement assertions unchanged.",
        ],
    },
    {
        "id": "T5",
        "priority": 5,
        "title": "resize on rotated objects: refuse BEFORE mutating (gaps.md E3)",
        "complexity": "low",
        "risk": "low - converts a silent-corruption path into a clean error",
        "files": {
            "new": [],
            "touch": ["extension/transforms.py (or wherever resize lives)",
                      "tests/e2e_headless.py"],
        },
        "spec": {
            "semantics": [
                "Today resize on a rotated object computes scale from WORLD dims but "
                "applies it to LOCAL axes (asking width=0.98 on a rot_y=90 cylinder "
                "squashed its world HEIGHT), then warns after the damage.",
                "Minimum fix: for any target with non-zero rotation, ERROR before touching "
                "geometry; message suggests apply_transform(rotation=True) first or "
                "recreating at size.",
                "Better (do it if it stays simple): for axis-aligned rotations (multiples "
                "of 90 deg) map world->local axes through the rotation matrix exactly and "
                "proceed; refuse only for arbitrary rotations.",
            ],
        },
        "acceptance": [
            "e2e: resize(width=...) on a rot_y=90 cylinder either errors with dims "
            "untouched (minimum fix) or yields exactly the requested world width with "
            "other world dims unchanged (better fix). Either passes; silent shear fails.",
            "e2e: resize on unrotated objects byte-identical to current behavior.",
        ],
    },
    {
        "id": "T6",
        "priority": 6,
        "title": "Poly Haven client: textured PBR materials with box projection",
        "complexity": "medium - the design decisions are made (below); remaining work "
                      "is an API client, a cache, and node wiring",
        "risk": "low overall; one structural item: this is the project's FIRST runtime "
                "network dependency. Network failures must degrade to a clean tool error "
                "with the scene untouched. Licensing is CC0 - cache freely.",
        "files": {
            "new": ["server/polyhaven.py (API client + cache, NO bpy)",
                    "extension/textures.py (node wiring from local paths, NO network)"],
            "touch": ["server/finishes.py or new server/textures.py (MCP tools)",
                      "extension/designs.py (pack on save, see below)",
                      "tests/e2e_headless.py"],
        },
        "spec": {
            "api": [
                "Endpoints: GET https://api.polyhaven.com/assets?t=textures (catalog), "
                "GET /files/<asset_id> (per-map URLs by resolution). Unauthenticated; "
                "send a User-Agent identifying blender-buttons.",
                "Cache: ~/.cache/blender-buttons/textures/<asset_id>/<res>/. Cache-first; "
                "network only on miss. Cache the catalog JSON too (24h TTL) so "
                "search_textures works offline after first use.",
                "Default resolution 1k. Maps: diffuse, normal (prefer GL variant), "
                "roughness. Skip displacement entirely (Eevee handles it badly).",
            ],
            "tools": [
                "search_textures(query, limit=10) -> [{id, tags}] from the cached catalog.",
                "set_textured_material(target, asset_id, scale=1.0, resolution='1k') -> "
                "server downloads/caches, then dispatches LOCAL FILE PATHS to the addon. "
                "The addon never opens a socket to the internet, and Blender's main "
                "thread never waits on a download.",
            ],
            "node_wiring": [
                "Principled BSDF with Image Texture nodes: diffuse->Base Color (sRGB), "
                "roughness->Roughness (Non-Color), normal->Normal Map node->Normal "
                "(Non-Color).",
                "All Image Texture nodes: projection='BOX', projection_blend=0.2, fed by "
                "Texture Coordinate(Object) -> Mapping(scale=scale). No UV unwrap needed "
                "or attempted.",
                "Store {'asset_id', 'resolution', 'scale'} in mat['bb_texture'] for "
                "describe() readback.",
            ],
            "reproducibility": [
                "save_design must call bpy.ops.file.pack_all() before writing the .blend "
                "so saved designs do not dangle on cache paths.",
            ],
        },
        "acceptance": [
            "e2e (network-gated; skip cleanly when offline): set_textured_material on a "
            "box -> 3 Image Texture nodes with correct colorspaces and BOX projection; "
            "second call hits cache (no network; assert via client counter).",
            "e2e: download failure (bad asset id) -> tool error, object's material "
            "unchanged.",
            "e2e: save_design after texturing -> .blend reports packed files.",
        ],
    },
    {
        "id": "T7",
        "priority": 7,
        "title": "Poly Haven HDRIs through set_world_background",
        "complexity": "low - reuses T6's client and cache wholesale",
        "risk": "low - same network caveat as T6, same clean-failure rule",
        "depends_on": ["T6"],
        "files": {
            "new": [],
            "touch": ["server/polyhaven.py", "server scene/world module",
                      "extension/lighting.py or shading.py (wherever world bg lives)",
                      "tests/e2e_headless.py"],
        },
        "spec": {
            "semantics": [
                "set_world_background already accepts hdri=<path>. Extend: if the value "
                "is not an existing file path, treat it as a Poly Haven asset id -> "
                "fetch via the T6 client (t=hdris, .hdr/.exr, default 2k) -> pass the "
                "cached local path to the existing code path.",
                "search_hdris(query, limit=10) mirroring search_textures.",
            ],
        },
        "acceptance": [
            "e2e (network-gated): set_world_background(hdri='<known asset id>') -> world "
            "uses an Environment Texture node pointing at a file inside the cache dir.",
            "e2e: explicit file paths behave exactly as before.",
        ],
    },
]
