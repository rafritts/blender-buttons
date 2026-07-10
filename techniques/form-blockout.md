# Form blockout — from nothing to a proportioned mass

**When:** starting ANY new asset. This is the technique the form-analysis habit feeds:
classify what you're about to build *before* touching a tool, then block the masses
before any detail.

## Classify first

Ask of every major mass: what is its geometric condition?

- Silhouette swept around an axis → **revolved-vessel** (spin / shape_profile).
- A skin at an offset over another surface → **shell**.
- A profile pushed along a line/curve → extrude (`edit op=extrude`, or a curve +
  *Curve to Tube*).
- A soft closed blob → primitive + proportional edits (below), or `feel op=fit
  model=superquadric as_surface=` to author the mass as numbers.
- An assembly of the above → block each mass separately, place relationally, merge
  late (**smooth-union**) or never.

The wrong classification is the expensive mistake — a lathe-able goblet built as a
box-modelled blob costs 10× the calls. Classify, then pull the matching technique.

## Block the masses

1. **Primitives with authored dimensions**: `add type=box|cylinder|sphere|torus`
   with real meters — dimensions are the one thing you may type freely.
2. **Place relationally**, never by coordinate: `on={"between":…}`, `rest_on`,
   `snap_to`, gaps as numbers. Read every status block; the next part seats on the
   last one's reported bounds.
3. **One mesh per articulable mass** at blockout (head, torso, limb) — merging comes
   after proportions are signed off; separate meshes stay cheap to move.
4. **Proportion pass by read**: `feel op=profile axis=Z` per mass and against the
   whole — girth/width per slice is the honest proportion check, not eyeballing.
   The human owns taste: surface the silhouette question early, while it's one scale
   call to fix.

## Rough the soft masses

- Swells/bulges: `select op=shrink` to an apex core → `edit op=proportional_move`
  with a radius spanning the bulge (never `inflate` on a dense irregular cap — the
  disagreeing normals lump it).
- Keep bilateral work honest: shape one side, `edit op=symmetrize` to reflect it true.
- Add resolution only where shaping needs it: `edit op=subdivide` on the selection,
  never a global densify.
- Surface break-up (bark, rock, cloth rumple) comes LAST: `edit op=noise_displace`.

**Verify at every step:** the status block bounds ARE the blockout — keep a stack-up
of them; `validate` catches the coplanar z-fights that exact stacking invites (two
identical numbers in your table = a bug, not a coincidence).
