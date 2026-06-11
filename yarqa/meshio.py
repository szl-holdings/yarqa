# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Optional mesh I/O for yarqa — a simple, dependency-light ``.npz`` format.

yarqa never requires OpenFOAM (or any CFD package). This module defines a tiny,
self-describing **npz container** so that real mesh data (cell centers, cell
velocities, face neighbors) can be loaded with NumPy alone, and provides a
clearly **SAMPLE-labeled synthetic** generator for when no mesh is supplied.

The npz layout (all arrays optional except the first three):

    centers     : (N, D) float    cell-center coordinates
    velocities  : (N, D) float    cell-center velocity vectors
    neighbors   : object/ragged   per-cell neighbor id arrays  (see below)
    corners     : object/ragged   optional per-cell corner clouds

Because ``np.savez`` cannot store a ragged list of differing-length neighbor
arrays directly as one rectangular array, neighbors are stored in a flat CSR-like
pair: ``neighbors_flat`` (1-D int) + ``neighbors_offsets`` (length N+1 int), or,
when present, a single object array ``neighbors``. :func:`load_npz_mesh`
transparently accepts either encoding.

An OpenFOAM (or VTK) importer would simply translate that solver's data into
these same three arrays; doing so is intentionally OUT OF SCOPE here so yarqa
keeps **zero hard CFD dependencies**. The guarded :func:`try_load_openfoam`
hook documents that boundary and raises a clear, honest error rather than
pretending support exists.

Original SZL implementation; numpy-only. No third-party source copied.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .core import Mesh


def save_npz_mesh(path: str, mesh: Mesh) -> None:
    """Write a :class:`Mesh` to the simple yarqa ``.npz`` container.

    Neighbors are flattened to a CSR-like (flat, offsets) pair so the file is a
    plain rectangular-array npz with no pickled object arrays.
    """
    flat: list[int] = []
    offsets = [0]
    for nbrs in mesh.neighbors:
        arr = np.asarray(nbrs, dtype=int).ravel()
        flat.extend(int(x) for x in arr)
        offsets.append(len(flat))
    payload: dict[str, Any] = {
        "centers": np.asarray(mesh.centers, dtype=float),
        "velocities": np.asarray(mesh.velocities, dtype=float),
        "neighbors_flat": np.asarray(flat, dtype=int),
        "neighbors_offsets": np.asarray(offsets, dtype=int),
    }
    if mesh.corners is not None:
        # Corners are ragged; store as an object array (NumPy pickles it).
        payload["corners"] = np.array(
            [np.asarray(c, dtype=float) for c in mesh.corners], dtype=object
        )
    np.savez(path, **payload)


def _neighbors_from_npz(data) -> list[np.ndarray]:
    """Recover the per-cell neighbor lists from either supported encoding."""
    if "neighbors_flat" in data and "neighbors_offsets" in data:
        flat = np.asarray(data["neighbors_flat"], dtype=int).ravel()
        offsets = np.asarray(data["neighbors_offsets"], dtype=int).ravel()
        return [flat[offsets[i] : offsets[i + 1]] for i in range(len(offsets) - 1)]
    if "neighbors" in data:
        raw = data["neighbors"]
        # Object array of ragged arrays, or a 2-D rectangular array.
        return [np.asarray(a, dtype=int).ravel() for a in raw]
    raise ValueError(
        "npz mesh is missing neighbors: provide either 'neighbors_flat'+"
        "'neighbors_offsets' or a 'neighbors' object array"
    )


def load_npz_mesh(path: str) -> Mesh:
    """Load a :class:`Mesh` from a yarqa ``.npz`` file.

    Accepts both the CSR-like neighbor encoding written by :func:`save_npz_mesh`
    and a plain ``neighbors`` object/2-D array. Raises ``ValueError`` with a
    clear message on a malformed file rather than failing obscurely.
    """
    # allow_pickle is needed only for an optional 'corners'/'neighbors' object
    # array; the common path uses plain numeric arrays.
    with np.load(path, allow_pickle=True) as data:
        if "centers" not in data or "velocities" not in data:
            raise ValueError("npz mesh must contain 'centers' and 'velocities'")
        centers = np.asarray(data["centers"], dtype=float)
        velocities = np.asarray(data["velocities"], dtype=float)
        neighbors = _neighbors_from_npz(data)
        corners = None
        if "corners" in data:
            corners = [np.asarray(c, dtype=float) for c in data["corners"]]
    return Mesh(centers, velocities, neighbors, corners=corners)


def sample_channel_mesh(nx: int = 12, ny: int = 8, *, seed: int = 0) -> Mesh:
    """Return a **SAMPLE** synthetic channel-flow mesh (no real CFD data).

    Generates a structured ``nx*ny`` 2-D grid whose velocity field is mostly
    downstream (+x), accelerating, with a gentle convergence toward the
    centerline — a crude nozzle. Clearly labeled SAMPLE so it is never mistaken
    for measured or solver-produced data. Deterministic given ``seed``.
    """
    rng = np.random.default_rng(seed)
    centers: list[list[float]] = []
    neighbors: list[np.ndarray] = []

    def idx(i: int, j: int) -> int:
        return i * ny + j

    for i in range(nx):
        for j in range(ny):
            centers.append([float(i), float(j)])
    centers_arr = np.asarray(centers, dtype=float)

    for i in range(nx):
        for j in range(ny):
            nb: list[int] = []
            if i > 0:
                nb.append(idx(i - 1, j))
            if i < nx - 1:
                nb.append(idx(i + 1, j))
            if j > 0:
                nb.append(idx(i, j - 1))
            if j < ny - 1:
                nb.append(idx(i, j + 1))
            neighbors.append(np.asarray(nb, dtype=int))

    vel = np.zeros((nx * ny, 2), dtype=float)
    for i in range(nx):
        for j in range(ny):
            speed = 1.0 + 0.15 * i
            vy = -0.08 * (j - (ny - 1) / 2.0)
            # tiny deterministic jitter so the field is not perfectly uniform
            jitter = rng.normal(scale=1e-3, size=2)
            vel[idx(i, j)] = [speed + jitter[0], vy + jitter[1]]

    return Mesh(centers_arr, vel, neighbors)


def try_load_openfoam(case_dir: str) -> Mesh:  # pragma: no cover - documented stub
    """Guarded OpenFOAM hook — intentionally NOT a hard dependency.

    yarqa ships with **zero** CFD-package dependencies by design. A real
    importer would read an OpenFOAM case's cell centers, velocity field, and
    face connectivity and translate them into the three yarqa arrays. Rather
    than silently failing or implying support we do not have, this raises a
    clear, honest error directing callers to export to the ``.npz`` format and
    use :func:`load_npz_mesh`.
    """
    raise NotImplementedError(
        "yarqa has no hard OpenFOAM dependency by design. Export your case to "
        "the simple yarqa .npz format (centers, velocities, neighbors) and load "
        "it with yarqa.meshio.load_npz_mesh(). See module docstring for layout."
    )
