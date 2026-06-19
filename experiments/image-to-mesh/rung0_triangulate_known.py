"""
Rung 0 — Can we triangulate a KNOWN object?

Goal: validate the ortho-triangulation ENGINE on perfect input, with zero
computer vision. We take a known mesh, project its vertices onto three
orthographic planes (front / side / top), then hand ONLY those 2D projections
(plus ground-truth correspondence) to the triangulator and check it rebuilds
the original.

This is the easy, on-purpose case. With axis-aligned orthographic views the
"triangulation" is really coordinate-merging:
    front view -> (X, Z)
    side  view -> (Y, Z)
    top   view -> (X, Y)
Each world axis is seen by two views, so every coordinate is measured twice.
On a real object the two measurements AGREE (residual ~ 0). That same residual
becomes our INCOHERENCE METRIC later: when we feed AI-drawn views that are not
projections of one real object, the two measurements will DISAGREE and residual
spikes. So this engine pulls double duty:
    rung 0 (clean data)  -> residual ~ 0, exact reconstruction  [proves engine]
    rung 2 (AI data)     -> residual = how-incoherent-is-this   [the real test]

We also run a NEGATIVE CONTROL: corrupt the correspondence of one view and
confirm residual explodes -- proving the metric actually has teeth.
"""

import numpy as np


# ---------------------------------------------------------------------------
# A known object: an ellipsoid with three DIFFERENT radii.
# Different per-axis radii matter -- if the engine transposes an axis (a classic
# bug), the radii won't line up and we'll catch it. A sphere would hide it.
# ---------------------------------------------------------------------------
def make_ellipsoid(n_stacks=16, n_slices=24, rx=1.0, ry=1.6, rz=2.2):
    verts = []
    for i in range(n_stacks + 1):
        theta = np.pi * i / n_stacks          # 0..pi  (pole to pole, Z)
        for j in range(n_slices):
            phi = 2 * np.pi * j / n_slices    # 0..2pi (around)
            x = rx * np.sin(theta) * np.cos(phi)
            y = ry * np.sin(theta) * np.sin(phi)
            z = rz * np.cos(theta)
            verts.append((x, y, z))
    V = np.array(verts, dtype=np.float64)

    faces = []
    for i in range(n_stacks):
        for j in range(n_slices):
            a = i * n_slices + j
            b = i * n_slices + (j + 1) % n_slices
            c = (i + 1) * n_slices + (j + 1) % n_slices
            d = (i + 1) * n_slices + j
            faces.append((a, b, c, d))
    return V, faces


# ---------------------------------------------------------------------------
# Project to the three orthographic views. Returns 2D arrays indexed by vertex
# id == ground-truth correspondence (we know which 2D point is which vertex
# because we just made the projection).
# ---------------------------------------------------------------------------
def project(V):
    front = V[:, [0, 2]]   # (X, Z)
    side  = V[:, [1, 2]]   # (Y, Z)
    top   = V[:, [0, 1]]   # (X, Y)
    return front, side, top


# ---------------------------------------------------------------------------
# The triangulator. Sees ONLY the three 2D views (and the shared index order).
# Recovers each world axis from the two views that see it, and records the
# disagreement (residual) between the redundant measurements.
# ---------------------------------------------------------------------------
def triangulate(front, side, top):
    x_front, z_front = front[:, 0], front[:, 1]
    y_side,  z_side  = side[:, 0],  side[:, 1]
    x_top,   y_top   = top[:, 0],   top[:, 1]

    # each axis measured twice -> average; residual = how much they disagree
    X = 0.5 * (x_front + x_top)
    Y = 0.5 * (y_side + y_top)
    Z = 0.5 * (z_front + z_side)

    res_x = np.abs(x_front - x_top)
    res_y = np.abs(y_side - y_top)
    res_z = np.abs(z_front - z_side)
    residual = np.stack([res_x, res_y, res_z], axis=1)

    V_rec = np.stack([X, Y, Z], axis=1)
    return V_rec, residual


def report(name, V0, V_rec, residual):
    err = np.linalg.norm(V_rec - V0, axis=1)
    diag = np.linalg.norm(V0.max(0) - V0.min(0))   # bbox diagonal, for scale
    print(f"  [{name}]")
    print(f"    vertices                 : {len(V0)}")
    print(f"    object bbox diagonal     : {diag:.4f}")
    print(f"    max cross-view residual  : {residual.max():.3e}")
    print(f"    mean cross-view residual : {residual.mean():.3e}")
    print(f"    max reconstruction error : {err.max():.3e}")
    print(f"    mean reconstruction error: {err.mean():.3e}")
    print(f"    error as % of bbox diag  : {100 * err.max() / diag:.4f}%")
    return err.max()


def write_obj(path, V, faces):
    with open(path, "w") as f:
        for v in V:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for face in faces:
            f.write("f " + " ".join(str(i + 1) for i in face) + "\n")


if __name__ == "__main__":
    np.set_printoptions(precision=4, suppress=True)
    V0, faces = make_ellipsoid()
    front, side, top = project(V0)

    print("=" * 64)
    print("RUNG 0: triangulate a known object from ground-truth ortho views")
    print("=" * 64)

    # --- POSITIVE: clean projections of one real object ---
    print("\nPOSITIVE TEST (clean projections of a real object):")
    V_rec, residual = triangulate(front, side, top)
    max_err = report("clean", V0, V_rec, residual)
    clean_pass = max_err < 1e-9
    print(f"    => {'PASS' if clean_pass else 'FAIL'} (exact reconstruction)")

    # --- NEGATIVE CONTROL: corrupt correspondence in ONE view ---
    # Shuffle the top view's vertex order: now top[i] is NOT vertex i.
    # This simulates wrong correspondence / views that aren't of one object.
    print("\nNEGATIVE CONTROL (top-view correspondence scrambled):")
    rng = np.random.default_rng(0)
    perm = rng.permutation(len(V0))
    V_bad, res_bad = triangulate(front, side, top[perm])
    report("scrambled", V0, V_bad, res_bad)
    teeth = res_bad.max() > 0.1 * np.linalg.norm(V0.max(0) - V0.min(0))
    print(f"    => residual {'SPIKES' if teeth else 'did NOT spike'} "
          f"(metric {'has teeth' if teeth else 'is blind'})")

    # --- write OBJs for the Blender round-trip (rung 0, layer B) ---
    write_obj("original.obj", V0, faces)
    write_obj("reconstructed.obj", V_rec, faces)
    print("\nWrote original.obj and reconstructed.obj for Blender round-trip.")

    print("\n" + "=" * 64)
    verdict = clean_pass and teeth
    print(f"RUNG 0 VERDICT: {'PASS' if verdict else 'FAIL'} -- "
          f"engine reconstructs clean input exactly AND the incoherence "
          f"metric detects bad input.")
    print("=" * 64)
