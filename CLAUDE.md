# blender-buttons

An MCP server that lets an agent drive Blender through a small verb surface built on
legible perception, dimensions-over-coordinates, and relational placement. Start with
`README.md`; read `GUIDANCE_FOR_LLMS.md` before doing any actual modeling; process
lives in `gaps.md` (friction → numbered gap → fix → live-verify → clear).

## Sister project: ue-buttons

`~/workspace/ue-buttons` (github.com/rafritts/ue-buttons) is the same philosophy
projected onto Unreal Engine 5 — same author, same partnership model (human owns
taste/playtesting, agent owns precision/mechanical verification), same core concepts
(verb surface, auto-status, placement DSL, gaps discipline).

- Concepts proven here get ported there; friction found there sometimes reveals design
  debt here. When changing a core concept in either repo, consider whether the sister
  should follow.
- `experiments/ue5-buttons-handoff.md` in this repo is the historical origin of
  ue-buttons; the ue-buttons README and `docs/SPEC-00-Initial.md` supersede it.
- Conventions deliberately differ where the engines do: Blender is meters, front = −Y;
  UE is centimeters, front = +X. Don't "fix" one to match the other.
