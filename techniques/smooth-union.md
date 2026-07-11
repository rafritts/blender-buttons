# Smooth union — merging two masses into one body

**When the form is:** two (or more) closed masses that must read as *one* — a handle
meeting a mug, a limb meeting a torso, a horn meeting a skull. The question is always
the **seam**: hard crease, filleted blend, or continuous flesh.

## Hard union (a crease is fine, or the seam will be hidden)

`edit op=boolean target=<A> cutter=<B> bool_op=UNION` — one call, one body. Then
`edit op=recalc_normals` if `validate` flags an inverted shell. Booleans want
**watertight operands**: cap open rims first (walls via `modifier op=add type=SOLIDIFY`,
or fill the rim with `edit op=grid_fill`) or EXACT leaves internal membranes — the
`validate` topology floor will tell you.

## Filleted seam (visible joint that should look built, not glued)

1. Hard-union as above.
2. Select the intersection seam: `look` at the joint region and claim the offered
   boundary/crease candidate, or `select op=flood` from a picked seam face
   (`select op=pick within=<zone>`) — the crease bounds the flood.
3. `edit op=bevel width=<fillet radius> segments=3` on the seam edges, then
   `material op=shade_smooth`. Small fillet, real chamfer — reads as a weld bead.

## Continuous flesh (organic — no visible seam at all)

After the hard union, `edit op=subdivide` the seam zone locally, then blend it away:
`sculpt brush=smooth` strokes across the seam. Verify with `feel op=fit model=quadric`
over the blend patch — a low residual says the flesh is now one smooth surface, not two
crashed ones.

Blender 5.x also ships a native **SDF grid family** in Geometry Nodes (Mesh to SDF
Grid → SDF Grid Boolean → SDF filters → Grid to Mesh) — the heavy-duty path for
blob-grade smooth unions. It is a node-graph setup, not a one-call op here; if a build
genuinely needs it, that's a gap to log, not a workaround to improvise.

## Patch-to-patch welds (open surfaces, not closed masses)

- Two patches sharing a **coincident** boundary: `object op=join`, then `edit op=merge`
  (by distance) welds the seam verts — check the narrated count matches the rim length.
- Two open **rims facing each other**: that's a bridge, not a union — see
  `guidance://techniques/ring-weld`.

## Failure modes

- UNION with EXACT that "succeeds" but the result loses a whole operand: read the
  status-block vert count — a merge that didn't grow didn't merge. FLOAT solver trades
  robustness for cleanup (non-manifold leftovers `edit op=merge` can close).
- Smoothing a seam on a shape-keyed mesh lands on the active key — the status block
  says which key took the edit; check it.
