"""Headless hero still for README (bugs.md B5).

Builds a pink-glazed sprinkled donut with the same authored dimensions as
donut.md and writes recipes/donut/donut_hero.png. Run:

    flatpak run --filesystem=host org.blender.Blender --background --factory-startup \
        --python recipes/donut/render_hero.py
"""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402

from extension import server as bb  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "donut_hero.png")


def run(tool, **params):
    r = bb.execute_command({"tool": tool, "params": params})
    if not r.get("success"):
        raise RuntimeError(f"{tool} failed: {r}")
    return r


def nuke_defaults():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for name in ("Cube", "Light", "Camera"):
        o = bpy.data.objects.get(name)
        if o is not None:
            bpy.data.objects.remove(o, do_unlink=True)


def scatter_sprinkles(host_name, n=80, seed=3):
    host = bpy.data.objects[host_name]
    rng = random.Random(seed)
    colors = ("#e23b3d", "#f2c33d", "#3d7bf2", "#f0f0f0")
    proto_names = []
    for i, hex_color in enumerate(colors):
        name = f"Sprinkle_{i}"
        run("add_cylinder", name=name, radius=0.0011, height=0.006, segments=6)
        run("set_material", target=name, hex=hex_color, roughness=0.35,
            material_name=f"Sprinkle_{hex_color[1:]}")
        proto_names.append(name)

    mw = host.matrix_world
    tops = []
    for v in host.data.vertices:
        w = mw @ v.co
        if w.z > 0.002:
            tops.append(w)
    if not tops:
        raise RuntimeError("icing has no top verts to sit sprinkles on")

    for i in range(n):
        src = proto_names[i % len(proto_names)]
        name = f"Spr_{i:03d}"
        run("duplicate_object", name=src, new_name=name)
        obj = bpy.data.objects[name]
        p = tops[rng.randrange(len(tops))].copy()
        p.z += 0.0015
        obj.location = p
        obj.rotation_euler = (
            rng.uniform(-0.6, 0.6),
            rng.uniform(-0.6, 0.6),
            rng.uniform(0, math.tau),
        )

    run("group", name="SprinkleProto", parts=proto_names)
    for p in proto_names:
        bpy.data.objects[p].location.z = -0.3


def main():
    nuke_defaults()

    run("add_torus", name="Donut", major_radius=0.03, minor_radius=0.013,
        major_segments=48, minor_segments=24)
    run("resize", targets="Donut", height=0.021)
    run("apply_transform", targets="Donut", scale=True)
    run("add_modifier", target="Donut", type="SUBSURF", name="Subsurf",
        levels=2, render_levels=2)
    run("jitter_vertices", target="Donut", amount=0.0012, seed=1)
    run("shade_smooth", target="Donut")
    run("set_material", target="Donut", hex="#9c6233", roughness=0.75,
        material_name="Dough")

    # Glaze as a second torus — same authored radii as donut.md, slightly
    # slimmer and lifted so it reads as icing on the dough (the retired clad
    # macro is the recipe's shell path; this still is the README hero).
    run("add_torus", name="Icing", major_radius=0.0305, minor_radius=0.011,
        major_segments=48, minor_segments=24)
    run("resize", targets="Icing", height=0.015)
    run("apply_transform", targets="Icing", scale=True)
    run("nudge", targets="Icing", up=0.0035)
    run("add_modifier", target="Icing", type="SUBSURF", name="Subsurf",
        levels=2, render_levels=2)
    run("jitter_vertices", target="Icing", amount=0.002, seed=4)
    run("shade_smooth", target="Icing")
    run("set_material", target="Icing", hex="#f49ac1", roughness=0.3,
        material_name="Glaze")

    scatter_sprinkles("Icing")

    run("add_plane", name="floor", width=0.5, depth=0.5)
    run("nudge", targets="floor", down=0.0104)
    run("set_material", target="floor", hex="#e7ddcf", roughness=0.9,
        material_name="Table")

    run("add_light", name="Key", type="AREA", energy=40, size=0.35,
        x=0.12, y=0.10, z=0.18, target="Donut")
    run("add_light", name="Fill", type="AREA", energy=12, size=0.4,
        x=-0.14, y=-0.08, z=0.10, target="Donut")
    run("add_light", name="Rim", type="AREA", energy=18, size=0.2,
        x=-0.04, y=0.16, z=0.08, target="Donut")
    run("add_camera", name="Cam", lens=85,
        x=0.11, y=-0.15, z=0.09, target="Donut")

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.16, 0.14, 0.12, 1.0)
        bg.inputs[1].default_value = 0.6

    r = run("render_to_file", filepath=OUT, resolution_x=1400, resolution_y=1050,
            samples=64, engine="BLENDER_EEVEE", format="PNG")
    print(f"hero still → {r['filepath']} ({r['bytes']} bytes)")


if __name__ == "__main__":
    main()
