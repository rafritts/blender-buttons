# blender-buttons: Vision

## The Idea

An MCP server that exposes full Blender functionality so an LLM can use Blender the way a human would.

The name says it all: the LLM is just a user sitting at a desk, hand on keyboard, pushing buttons.

## The Core Principle

Humans do not reason about vertices and edges mentally. Neither should LLMs.

A human using Blender looks at the viewport, decides what they want to change, picks an operation, executes it, and looks again. The LLM should do exactly the same thing — through rendered images and named operations.

Precise numerical reasoning over raw geometry will fail. Visual reasoning over viewport screenshots is tractable.

## The Core Iteration Loop

```
look → decide → act → look again
```

The LLM picks a viewport angle(s), takes a screenshot(s), reasons over the image(s), calls an operation, and repeats.

## Human and LLM as Co-Users

The LLM is not the owner of the Blender session. Neither is the human. Both are just users.

At any point the human can take over, make changes, and hand back. The LLM always looks at current state before acting — it never assumes the world matches what it last did. Human interventions are just state changes the LLM picks up naturally from the next screenshot.

## What the MCP Server Exposes

Everything a human user would reach for:

- **Viewport navigation** — numpad 1-9 for standard angles, 0 for camera, 5 for ortho/persp toggle
- **Screenshot** — current viewport as an image, the LLM's eyes
- **Scene tree** — scene collection in readable tree form: names, types, hierarchy, active selection
- **Mesh operations** — add primitive, extrude, inset, loop cut, bevel, merge, bridge, subdivide
- **Transforms** — scale, move, rotate, per axis
- **Selection** — objects, loops, elements, all/none
- **Modifiers** — add, configure, apply
- **Mode switching** — object, edit, sculpt
- **Render** — full render output

## What the LLM Never Does

- Reason over raw vertex coordinates
- Perform matrix calculations
- Assume scene state without looking first
