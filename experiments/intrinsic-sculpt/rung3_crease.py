# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "trimesh"]
# ///
"""Rung 3 — dihedrals as lengths (flap diagonals), for creases AND smoothness.

A shared edge's dihedral angle is encoded by the distance between the two
vertices OPPOSITE it (the flap diagonal): fold the flap, the diagonal shortens.
So bending stays inside the lengths-only language:
  - preserve current diagonals everywhere  -> bending regularizer (anti-wrinkle)
  - shorten diagonals along a line         -> a crease/fold with a target angle

Part A: fold a flat sheet into a ~90 deg tent along its midline by only
        shortening the flap diagonals that cross the fold line.
Part B: rerun rung 2's bulge WITH diagonal preservation; lumpiness should drop
        below the naive normal-push baseline.
"""

import numpy as np
import trimesh

from rung1_roundtrip import edges_of, edge_lengths, solve_lengths
from rung2_bulge import vertex_adjacency, roughness


def make_grid(nx=61, ny=31, spacing=0.05):
    xs = (np.arange(nx) - (nx - 1) / 2) * spacing
    ys = (np.arange(ny) - (ny - 1) / 2) * spacing
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    V = np.column_stack([X.ravel(), Y.ravel(), np.zeros(nx * ny)])
    idx = np.arange(nx * ny).reshape(nx, ny)
    quads = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], axis=-1).reshape(-1, 4)
    faces = np.concatenate([quads[:, [0, 1, 2]], quads[:, [0, 2, 3]]])
    return trimesh.Trimesh(V, faces, process=False)


def flap_diagonals(mesh):
    """(k,2) opposite-vertex pairs per interior edge + (k,2) the shared edges."""
    return mesh.face_adjacency_unshared, mesh.face_adjacency_edges


def fold_angles(mesh, edge_mask):
    """Dihedral (0 = flat) of interior edges selected by mask, in degrees."""
    return np.degrees(mesh.face_adjacency_angles[edge_mask])


def part_a_crease():
    mesh = make_grid()
    V0, E = mesh.vertices.copy(), edges_of(mesh)
    diag_pairs, shared_edges = flap_diagonals(mesh)

    # Fold line: shared edges whose both endpoints sit on x ~= 0.
    on_fold = np.all(np.abs(V0[shared_edges][:, :, 0]) < 1e-9, axis=1)

    E_all = np.vstack([E, diag_pairs])
    L_all = edge_lengths(V0, E_all)
    target = L_all.copy()
    fold_rows = len(E) + np.where(on_fold)[0]
    target[fold_rows] *= np.sin(np.radians(90) / 2)  # 90 deg tent: d -> d*sin(phi/2)

    # Pin one long border strip so the sheet folds instead of drifting.
    pin_idx = np.where(V0[:, 0] < V0[:, 0].min() + 0.051)[0]
    # Break the flat-sheet symmetry: a flat configuration has zero out-of-plane
    # gradient (buckling critical point), so seed a tiny upward bias that grows
    # toward the free edge. The solver picks the fold direction from it.
    V_seed = V0.copy()
    V_seed[:, 2] += 1e-3 * np.clip(V0[:, 0] - V0[:, 0].min(), 0, None)
    V = solve_lengths(V_seed, E_all, target, pin_idx, V0[pin_idx], iters=600)

    folded = trimesh.Trimesh(V, mesh.faces, process=False)
    folded.export("rung3_folded_sheet.obj")
    make_grid().export("rung3_flat_sheet.obj")
    ang_fold = fold_angles(folded, on_fold)
    off_fold = ~on_fold & np.all(np.abs(V0[shared_edges][:, :, 0]) > 0.15, axis=1)
    ang_else = fold_angles(folded, off_fold)
    print(f"A) crease: fold-line dihedral mean={ang_fold.mean():.1f} deg "
          f"(target 90), spread ±{ang_fold.std():.1f}")
    print(f"   away from fold: mean bend {ang_else.mean():.2f} deg (should stay ~flat)")
    print(f"   tent height (bbox z): {V[:, 2].max() - V[:, 2].min():.3f} m "
          f"(true 90-deg tent on this sheet ~ 1.06 m)")

    # v2: the tiny-bias seed lands in a ridge-wave local minimum (fold at the
    # line, counter-bends beside it, wing never lifts). Seed the WING PRE-ROTATED
    # 45 deg about the fold line instead — the solver only has to polish.
    V_seed2 = V0.copy()
    wing = V0[:, 0] > 0
    th = np.radians(45)
    V_seed2[wing, 2] = V0[wing, 0] * np.sin(th)
    V_seed2[wing, 0] = V0[wing, 0] * np.cos(th)
    V2 = solve_lengths(V_seed2, E_all, target, pin_idx, V0[pin_idx], iters=600)
    folded2 = trimesh.Trimesh(V2, mesh.faces, process=False)
    folded2.export("rung3_folded_sheet_v2.obj")
    ang2 = fold_angles(folded2, on_fold)
    ang2_else = fold_angles(folded2, off_fold)
    print(f"A2) rotated seed: fold dihedral mean={ang2.mean():.1f} deg "
          f"(target 90), spread ±{ang2.std():.1f}; away from fold {ang2_else.mean():.2f} deg")
    print(f"    tent height (bbox z): {V2[:, 2].max() - V2[:, 2].min():.3f} m")


def part_b_bulge_regularized():
    rng = np.random.default_rng(3)
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=1.0)
    V0 = mesh.vertices + rng.normal(0, 0.012, mesh.vertices.shape)
    mesh = trimesh.Trimesh(V0, mesh.faces, process=False)
    E = edges_of(mesh)
    nbrs = vertex_adjacency(len(V0), E)
    diag_pairs, _ = flap_diagonals(mesh)

    ang = np.arccos(np.clip(V0 @ [0, 0, 1] / np.linalg.norm(V0, axis=1), -1, 1))
    w = np.clip(1 - ang / (np.pi / 4), 0, 1) ** 2

    E_all = np.vstack([E, diag_pairs])
    L0 = edge_lengths(V0, E_all)
    w_pair = (w[E_all[:, 0]] + w[E_all[:, 1]]) / 2  # metric grows for diagonals too
    L_target = L0 * (1 + 0.25 * w_pair)
    pin_idx = np.where(w == 0)[0]
    V = solve_lengths(V0, E_all, L_target, pin_idx, V0[pin_idx], iters=400)

    trimesh.Trimesh(V, mesh.faces, process=False).export("rung3_bulge_bending.obj")
    r0 = np.linalg.norm(V0, axis=1)
    region_idx = np.where(w > 0.05)[0]
    delta = np.linalg.norm(V, axis=1) - r0
    print(f"B) bulge+bending: height max={delta[region_idx].max():.4f}  "
          f"delta-lumpiness={roughness(delta, nbrs, region_idx):.6f}  "
          f"(rung2: naive 0.001604, lengths-only 0.003009)")
    # Surface roughness (of the radius field itself): is the FINAL surface any
    # noisier than the jittered input it started from?
    normals = mesh.vertex_normals
    naive = V0 + normals * (w * 0.12)[:, None]
    for name, VV in [("input   ", V0), ("naive   ", naive), ("intrinsic", V)]:
        rr = np.linalg.norm(VV, axis=1)
        print(f"   surface roughness {name}: {roughness(rr, nbrs, region_idx):.6f}")


if __name__ == "__main__":
    part_a_crease()
    part_b_bulge_regularized()
