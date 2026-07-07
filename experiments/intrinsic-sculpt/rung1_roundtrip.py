# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "trimesh"]
# ///
"""Rung 1 — lengths are a sufficient handle.

Take an icosphere, record its edge lengths, mangle the vertex positions,
then solve for positions that satisfy the recorded lengths again.
If the recovered shape matches the original (up to rigid motion), the
intrinsic representation is invertible in practice, not just on paper.

Solver: local-global edge projection ("shape-up" style).
  local:  per-edge target vector = current direction * target length
  global: min_V sum ||(vi - vj) - t_ij||^2  (+ soft pins)
The global system matrix (graph Laplacian + pin weights) is constant, so
it is factorized once and each iteration is one back-substitution.
"""

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import factorized
import trimesh


def edges_of(mesh: trimesh.Trimesh) -> np.ndarray:
    return mesh.edges_unique  # (m, 2) int


def edge_lengths(V: np.ndarray, E: np.ndarray) -> np.ndarray:
    return np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)


def build_solver(n: int, E: np.ndarray, pin_idx: np.ndarray, w_pin: float = 1e3):
    """Factorize the constant global-step matrix. Returns solve(rhs)->V."""
    m = len(E)
    rows = np.repeat(np.arange(m), 2)
    cols = E.ravel()
    vals = np.tile([1.0, -1.0], m)
    A = sp.csr_matrix((vals, (rows, cols)), shape=(m, n))
    P = sp.csr_matrix(
        (np.full(len(pin_idx), np.sqrt(w_pin)), (np.arange(len(pin_idx)), pin_idx)),
        shape=(len(pin_idx), n),
    )
    M = (A.T @ A + P.T @ P).tocsc()
    return A, P, factorized(M)


def solve_lengths(
    V_init: np.ndarray,
    E: np.ndarray,
    L_target: np.ndarray,
    pin_idx: np.ndarray,
    pin_pos: np.ndarray,
    iters: int = 200,
    w_pin: float = 1e3,
) -> np.ndarray:
    n = len(V_init)
    A, P, solve = build_solver(n, E, pin_idx, w_pin)
    V = V_init.copy()
    pin_rhs = np.sqrt(w_pin) * pin_pos
    for _ in range(iters):
        d = V[E[:, 0]] - V[E[:, 1]]
        norms = np.linalg.norm(d, axis=1, keepdims=True)
        norms[norms < 1e-12] = 1e-12
        t = d / norms * L_target[:, None]
        rhs = A.T @ t + P.T @ pin_rhs
        V = np.column_stack([solve(rhs[:, k]) for k in range(3)])
    return V


def procrustes_rmse(X: np.ndarray, Y: np.ndarray) -> float:
    """RMSE between point sets after optimal rigid alignment of Y onto X."""
    Xc, Yc = X - X.mean(0), Y - Y.mean(0)
    U, _, Vt = np.linalg.svd(Yc.T @ Xc)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt
    return float(np.sqrt(((Yc @ R - Xc) ** 2).sum(axis=1).mean()))


def main():
    rng = np.random.default_rng(7)
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.0)  # 642 verts
    V0 = mesh.vertices.copy()
    E = edges_of(mesh)
    L0 = edge_lengths(V0, E)

    # Mangle: anisotropic squash + smooth low-frequency warp + noise.
    V_bad = V0 * np.array([1.4, 0.7, 1.1])
    V_bad += 0.15 * np.sin(3 * V0[:, [1, 2, 0]])
    V_bad += rng.normal(0, 0.02, V_bad.shape)

    # Pin a small anchor patch (kills the rigid-motion nullspace) at ORIGINAL pose.
    pin_idx = np.argsort(V0[:, 2])[-4:]  # 4 verts near the north pole
    pin_pos = V0[pin_idx]

    L_bad = edge_lengths(V_bad, E)
    print(f"verts={len(V0)} edges={len(E)}")
    print(f"mangled:   mean|L-L0|/L0 = {np.mean(np.abs(L_bad - L0) / L0):.4f},  "
          f"procrustes RMSE vs original = {procrustes_rmse(V0, V_bad):.4f}")

    V_rec = solve_lengths(V_bad, E, L0, pin_idx, pin_pos, iters=400)
    L_rec = edge_lengths(V_rec, E)
    print(f"recovered: mean|L-L0|/L0 = {np.mean(np.abs(L_rec - L0) / L0):.4f},  "
          f"max|L-L0|/L0 = {np.max(np.abs(L_rec - L0) / L0):.4f}")
    print(f"           procrustes RMSE vs original = {procrustes_rmse(V0, V_rec):.4f}"
          f"  (sphere radius = 1.0)")


if __name__ == "__main__":
    main()
