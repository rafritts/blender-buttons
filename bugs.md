# bugs.md — repo defects & open-source readiness

Unlike `gaps.md` (tool-surface friction found while modeling), this file tracks defects
in the repo itself — docs, packaging, tests, hygiene. Numbered **B#**, stable, delete
when fixed.

_Seeded 2026-07-09 by an open-source-readiness audit (goal: publishable, demoable,
not embarrassing). Trivial items were fixed in the same pass: MIT LICENSE added
(the addon manifest already declared `SPDX:MIT`), `recipies/` → `recipes/`,
`.mcp.json` made portable (relative paths), personal `.codex/` config untracked,
hardcoded home path in a test docstring genericized._

---

## B1 — README.md documents the retired flat-tool API — full rewrite needed

**Severity: release blocker.** The README is the repo's front page and it describes an
API that no longer exists. Anyone who clones and follows it fails at step 1.

- The entire Tool Reference is the pre-SPEC-05 flat surface (`add_box`, `select_ring`,
  `taper_end`, `get_viewport_screenshot`, `move_vertices`, …). The server has been the
  ~15-verb surface (`add`, `edit`, `feel`, `select`, `transform`, `modifier`, `material`,
  `sculpt`, `validate`, …) for a long time.
- Says "Blender 4.2+"; the server targets and is verified against **Blender 5.1**.
- Install section says to zip only `__init__.py` + manifest; `build_extension.sh` bundles
  every module in `extension/`. The "File layout" section lists 3 files; the repo is now
  `server/` + `extension/` packages plus docs/tests/recipes.
- References `blender_buttons.zip` as if it ships in the repo; it's gitignored — the
  README must point at `./build_extension.sh`.

Raw material for the rewrite already exists and is current: the server `instructions`
string, `GUIDANCE_FOR_LLMS.md`, `project-vision.md`, and `recipes/donut/donut.md` (a
verified end-to-end build — ideal as the README's showcase walkthrough). Keep the
architecture diagram and auto-status section; both are still accurate in spirit.

## B2 — Addon manifest pins `blender_version_min = "4.2.0"` but the server targets 5.x

`modifier op=add_asset` (Scatter on Surface etc.) depends on the GN Essentials assets
that only ship in Blender 5.x; on 4.2 those verbs dead-end. Bump to `5.0.0` on the next
rebuild cycle. Not fixed in this pass because a manifest change means rebuilding the zip
and reinstalling the addon.

## B3 — `tests/e2e_pbr_material.py` hardcodes a machine-local asset path

`ASSET = "/home/restless/workspace/poliigon-lib/Poliigon_StoneQuartzite_8060/4K"` —
fails on any other machine. Parameterize via an env var (e.g. `BB_PBR_ASSET_DIR`) and
skip with a clear message when unset.

## B4 — No CI

The e2e suite needs a live Blender, but a cheap GitHub Action — lint/import-sanity over
`server/` and `extension/`, plus a `build_extension.sh` zip build — would catch breakage
on PRs and put a green badge on the repo page.

## B5 — No demo media

For the X.com demo: a short screen capture of an agent running `recipes/donut/donut.md`
end-to-end (it's a verified transcript-recipe), cut to ~30–60s, plus a hero GIF/still of
the finished donut near the top of the README.

## B6 — `pyproject.toml` console script is never installed

`[project.scripts] blender-buttons = "server.main:mcp.run"` — there's no
`[build-system]` table, so uv treats the project as unpackaged and the entry point is
never materialized. Either add packaging config or drop the entry (the documented launch
path is `.venv/bin/python server/main.py` anyway). Minor.
