# Project Vision — blender-buttons

> The project's charter: its thesis, design principles, north star, and method. This was
> deliberately **moved out of Claude's auto-loaded memory** (2026-06-20). The reason is the
> first principle below — read it first.

## 0. Keep the dogfood BLIND (why this doc exists)

The whole project is a **dogfood**: every mesh Claude builds is a probe to find tool gaps,
and the real test is whether a **blind agent** — one that knows only what the server itself
teaches on connect (the `instructions` field + the `guidance://llms` resource) — can
succeed at the modeling task.

If Claude arrives at a modeling session with THE ONE RULE, the intent-space strategy, and
the `feel` philosophy already preloaded in memory, the dogfood is contaminated: it can no
longer distinguish *"the server taught me to succeed"* from *"my memory did."* A server that
only works because the operator memorized how to use it is not a finished server.

So the how-to-succeed knowledge was pulled out of memory and parked here.

**Therefore: do NOT read this doc at the start of, or during, a modeling session.** Consult
it for **server-development and gap work**, where the meta-context is the point — never as a
modeling cheat-sheet. The server must teach itself; that is the thing under test.

## 1. The thesis — the product is the server, not the mesh

The lever is the blender-buttons MCP server's **general tool surface**. Any specific mesh —
a watch, a chair, a character — is dogfooding: a probe to surface where the tools can't yet
express something. Every modeling request ("build a torso", "snap these", "fix the neck") is
really *"find the tool gap."*

The both/and, never collapse either half:

- **Quality meshes are the north star** — the goal, the market (a layman-with-taste directs
  the LLM to a Wuthering-Waves/Genshin-grade character), and the honest acceptance test of
  whether the tools are good enough.
- **But a mesh is only ever as good as the tools allow.** Tool functionality is the binding
  constraint; quality aspiration without capability is nothing. The work and the leverage
  are in the tools.

Direct from the user: *"I don't care at all about the meshes. The MCP server is the only
thing that matters... We don't build tools for the task at hand, ever. We build tools that
close gaps in functionality and make net-new tools."* Refined: *"The meshes will only be as
good as the tool is... BUT the quality meshes are the north star."*

Care about mesh quality **intensely — as the signal**, never as something to hand-fudge. A
mesh falling short = a tool gap to close.

## 2. Design principles

### 2.1 Dimensions over coordinates (intent-space)
Prefer **dimensions** (`width=4cm`) and **relational placement** (`snap`, `between`, `on`,
`left_of`) over coordinate enumeration. LLMs (and humans) collapse when carrying `(x,y,z)`
across calls and computing offsets in working memory — a 16-part chair hides it; a
hundreds-of-part character exposes it. The server holds the coordinates so the model can
hold **names and relationships**. The destructive thing is *enumerating points to construct
geometry*; simple arithmetic on dimensions is fine.

### 2.2 THE ONE RULE — derive, don't divine
**The canonical, current wording lives in `server/_instructions.py`** and is delivered to
the agent on connect — that is the source of truth; this is only the rationale.

The poison was never the coordinate; it's the **source**. A value computed from ground truth
(a status-block bound, a `feel` read) or from a dimension just authored is legitimate
arithmetic and needs no apology. What's forbidden is **fabricating** a spatial value from
intuition and committing to it unread. The test is **provenance**: name the measured or
authored value every number descends from; "it felt right" is not a provenance. Ground truth
is perishable — a value derived fifty calls ago is a guess wearing a fact's clothes. A raw
guess is allowed only as a *hypothesis you verify* before relying on it. (User co-signed the
sharper razor 2026-06-17; the derive/divine framing refined into the instructions 2026-06-20.)

### 2.3 `feel` = legibility, not divination
The `feel` tools must be **honest and legible**, not semantically "correct." Their job is to
emit handles, extents, profiles — enough that an operator who already knows the mesh and
their intent recognizes the thing they want, even when the classification reads "wrong."
Keep the intelligence in the agent and the tool dumb/clear. Only improve a `feel` output
when it's genuinely **ambiguous** (can't tell which handle is which), never to make it divine
meaning — a semantic guard both misfires eventually and trains the agent to trust the tool's
label instead of reading the geometry. The tool speaks geometry; the agent speaks meaning.

### 2.4 `feel` operates on un-perceived geometry, not un-authored geometry
THE ONE RULE is about geometry you have not **perceived**, not geometry you did not
**author**. The constraint is always perception, never provenance: a mesh you didn't make
(imported, reconstructed, handed over mid-build, recovered after compaction) is just a mesh
you haven't `feel`'d *yet*. The whole point of `feel` is to let the agent drive meshes it did
not create. Never treat authorship as the gate.

### 2.5 General primitives, never bespoke
blender-buttons is a **general Blender-interaction toolkit**, not a character-creation kit.
Every gap fix must be a general primitive that composes across any task — a character today,
a chair tomorrow, a building next week. If a proposed tool can't be restated without naming a
body part or domain object ("shoulder joint", "bangs builder", "neck snapper"), it's too
specific. Ask "what's the general operation underneath?" — "arms don't connect to torso" →
*weld/snap two meshes at their seam*; "hair needs strands" → *array shapes along a curve*.

## 3. North star

The MCP matures to where an agent can model a **full Wuthering-Waves / Genshin / Guilty-Gear-
Strive-grade stylized anime character** over a multi-hour session — because the user can't
hand-model one and neither can most people; that's the market. The Blender donut tutorial is
the smoke test, not the destination. Sculpt, retopo, UV, rigging, weight-paint, hair, cloth
are all eventually in scope. Every gap closed during real modeling is a step toward it.

## 4. Method / standing process

- **Log gaps after every build.** Any genuine tool gap hit during a session goes into
  `gaps.md` (repo root) in its existing ID-series format and design-principle voice, framed
  as a **general** primitive, committed without asking. `gaps.md` is the artifact of value —
  the engine of the project.
- **Verdicts in scene vocabulary, never coordinate dumps.** Introspection/verification tools
  should answer in relational, legible terms (coarse-to-fine), and stay **deterministic** —
  the user prefers deterministic reads over an LLM-summarizer sidecar.
- **The introspection representations are the agent's eyes, not the user's** — the user (a 3D
  layman) never reads them; design them for the model.
