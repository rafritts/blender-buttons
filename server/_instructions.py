"""The `instructions` bootstrap — a pseudo-system-prompt the MCP client MAY inject
into the model's context at `initialize` (per the MCP spec, this field is a hint
"added to the system prompt").

Kept deliberately TIGHT: it is standing context cost on *every* session, so it
carries only the server's identity, the one load-bearing rule, and a hard pointer
to the `guidance://llms` resource — which holds the depth. The source of truth for
that depth is GUIDANCE_FOR_LLMS.md (served verbatim by server/resources.py); do not
restate its full contents here.
"""

INSTRUCTIONS = """\
blender-buttons turns Blender into a mesh-modelling surface you drive by INTENT, not
coordinates. It perceives (`feel`), measures, and mutates through ~15 verbs (add, edit,
feel, select, transform, object, modifier, material, pose, sculpt, render, view, scene,
file, history). Each verb takes an `op=` that selects the operation; the verb's schema
enumerates every op and the args each one uses.

THE ONE RULE — you cannot reliably dead-reckon in 3D space. Not coordinates, and not
"which feel op / what radius" either. Your spatial intuition is a hypothesis, never
ground truth, in any scene you didn't just author. Therefore:
  • Stay in intent-space. Place things relationally (on / between / left_of / snap_to /
    gap, or a handle BY NAME). Typed at_x/y/z is the ripcord, not the default.
  • The status block returned by every mutating call is ground truth. Trust its world
    bounds over anything you remember, computed, or expected.
  • To find a feature you lack exact numbers for, do NOT guess one op/scale and trust the
    first plausible reading. Cast a WIDE net, verify its SHAPE, confirm CAPTURE, then
    drill — and cross-check with more than one `feel` read before you act.

BEFORE you improvise any multi-step task — locating geometry, constructing a form,
assembling parts — READ THE `guidance://llms` RESOURCE. It is battle-tested loops
distilled from real builds. Inventing your own path to the goal is the known, expensive
failure mode here; the loops exist precisely because winging it fails silently.

The core loop, by name: feel -> select -> measure -> verify -> act.
  feel op=profile / op=section  (judge the band from a read you can trust)
  -> select op=between / by_axis with action=INTERSECT  (the mesh's own lr_balance splits
     left from right — never type a centreline)
  -> feel op=anchor  (surface-snapped apex point + outward normal; the normal is your
     honesty check — wrong direction means the selection is wrong, not the tool)
  -> feel op=verify  (did the selection actually CATCH the feature, or clip / bleed into a
     neighbour?)  -> act at the handle/selection, never at a coordinate.
`verify` certifies CAPTURE, not IDENTITY: if it passes but you are unsure you landed on
the RIGHT feature, ask the human to eyeball it. Do not render to hunt for a feature —
vision self-confirms and launders the mistake.
"""
