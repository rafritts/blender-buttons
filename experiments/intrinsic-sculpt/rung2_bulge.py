# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "trimesh"]
# ///
"""Rung 2 — a bulge as a length field, vs the known inflate failure.

GUIDANCE_FOR_LLMS.md documents that `edit op=inflate` (per-vertex normal push)
lumps and collapses on dense irregular meshes because neighbouring normals
disagree. The intrinsic claim: scale target edge LENGTHS in a smooth falloff
region and solve — the metric grows, the embedding finds the swell, no normal
is ever consulted.

Test: an icosphere made deliberately irregular (surface jitter -> noisy
normals). Grow a bulge around the north pole two ways:
  A) naive normal push (what inflate does), displacement ~ same magnitude
  B) intrinsic: L_target = L0 * (1 + 0.25 * falloff(region)), solve

Metric: roughness of the radial displacement field = mean |delta_i - mean(delta_nbrs)|
(lumpiness), plus achieved bulge height and length residual.
"""

import numpy as np
import trimesh

from rung1_roundtrip import edges_of, edge_lengths, solve_lengths


def vertex_adjacency(n, E):
    nbrs = [[] for _ in range(n)]
    for a, b in E:
        nbrs[a].append(b)
        nbrs[b].append(a)
    return nbrs


def roughness(field, nbrs, at):
    """Mean |field[i] - mean(field[neighbours])| over the vertex indices `at`."""
    r = [abs(field[i] - np.mean(field[nbrs[i]])) for i in at if nbrs[i]]
    return float(np.mean(r))


def main():
    rng = np.random.default_rng(3)
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=1.0)  # 2562 verts
    V0 = mesh.vertices.copy()
    # Make it irregular: tangential + radial jitter so normals disagree locally.
    V0 += rng.normal(0, 0.012, V0.shape)
    mesh = trimesh.Trimesh(V0, mesh.faces, process=False)
    E = edges_of(mesh)
    L0 = edge_lengths(V0, E)
    nbrs = vertex_adjacency(len(V0), E)

    # Region: smooth falloff around the north pole (angular radius ~45deg).
    pole = np.array([0, 0, 1.0])
    ang = np.arccos(np.clip(V0 @ pole / np.linalg.norm(V0, axis=1), -1, 1))
    w = np.clip(1 - ang / (np.pi / 4), 0, 1) ** 2  # per-vertex falloff weight

    # --- A) naive normal push (inflate), same intent: grow the cap ---
    normals = mesh.vertex_normals
    push = 0.12
    V_naive = V0 + normals * (w * push)[:, None]

    # --- B) intrinsic: scale lengths by the mean falloff of their endpoints ---
    w_edge = (w[E[:, 0]] + w[E[:, 1]]) / 2
    L_target = L0 * (1 + 0.25 * w_edge)
    pin_idx = np.where(w == 0)[0]  # everything outside the region stays put
    V_intr = solve_lengths(V0, E, L_target, pin_idx, V0[pin_idx], iters=400)

    r0 = np.linalg.norm(V0, axis=1)
    region_idx = np.where(w > 0.05)[0]
    for name, V in [("naive inflate", V_naive), ("intrinsic    ", V_intr)]:
        delta = np.linalg.norm(V, axis=1) - r0  # radial displacement
        print(f"{name}: bulge height max={delta[region_idx].max():.4f}  "
              f"lumpiness={roughness(delta, nbrs, region_idx):.6f}")
    for name, V in [("input", V0), ("naive", V_naive), ("intrinsic", V_intr)]:
        trimesh.Trimesh(V, mesh.faces, process=False).export(f"rung2_{name}.obj")
    resid = np.abs(edge_lengths(V_intr, E) - L_target) / L_target
    print(f"intrinsic length residual: mean={resid.mean():.4f} max={resid.max():.4f}")
    still = np.linalg.norm(V_intr[pin_idx] - V0[pin_idx], axis=1).max()
    print(f"pinned region max drift: {still:.5f}")


if __name__ == "__main__":
    main()
