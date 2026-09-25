# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Optional mesh I/O for yarqa — a simple, dependency-light ``.npz`` format.

yarqa never requires OpenFOAM (or any CFD package). This module defines a tiny,
self-describing **npz container** so that real mesh data (cell centers, cell
velocities, face neighbors) can be loaded with NumPy alone, and provides a
clearly **SAMPLE-labeled synthetic** generator for when no mesh is supplied.

The npz layout (centers, velocities and one neighbor encoding are required;
corners are optional):

    centers            : (N, D) float   cell-center coordinates
    velocities         : (N, D) float   cell-center velocity vectors
    neighbors_flat     : (E,) int       all neighbor ids, concatenated per cell
    neighbors_offsets  : (N+1,) int     cell i owns neighbors_flat[off[i]:off[i+1]]
    corners_flat       : (M, D) float   all corner points, concatenated per cell
    corners_offsets    : (N+1,) int     cell i owns corners_flat[off[i]:off[i+1]]

Because ``np.savez`` cannot store a ragged list of differing-length arrays as
one rectangular array, ragged per-cell data (neighbors, corners) is stored as
a flat CSR-like (flat, offsets) pair. For meshes where every cell has the same
count, a rectangular ``neighbors`` (N, K) integer array and a rectangular
``corners`` (N, K, D) numeric array are also accepted on load.

Every array is plain numeric. :func:`load_npz_mesh` opens files with
``allow_pickle=False`` and never unpickles anything: an ``.npz`` that carries a
``dtype=object`` array (the older ragged ``neighbors``/``corners`` encoding) is
refused with ``ValueError`` and must be re-saved with :func:`save_npz_mesh`.
Unpickling an untrusted file can run arbitrary code, so this refusal is
deliberate and has no opt-out.

Compatibility: yarqa builds from before this layout (every commit from
234afc4, 2026-06-11, where this module was added, through 99e16ae) wrote
corners as a pickled object array, which is now refused, and do not read
``corners_flat`` or ``corners_offsets``. Such a build loads a file written
here without its corners and silently falls back to center-derived points,
so read corner meshes with a build that has this layout. The version string
does not tell them apart: those builds from 668071b (2026-07-02) onward also
report ``yarqa.__version__`` 0.5.0; older ones report 0.4.0.

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

    Neighbors and (optional) corners are flattened to CSR-like (flat, offsets)
    pairs so the file is a plain rectangular-array npz with no pickled object
    arrays; it loads with ``allow_pickle=False``.
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
        # Corners are ragged (K_i points per cell); store them CSR-like, exactly
        # like neighbors, so the file never holds a pickled object array.
        dim = payload["centers"].shape[1]
        clouds = []
        for i, c in enumerate(mesh.corners):
            cloud = np.asarray(c, dtype=float)
            if cloud.ndim != 2 or cloud.shape[1] != dim:
                raise ValueError(
                    f"corners[{i}] must be a (K, {dim}) array, got shape {cloud.shape}"
                )
            clouds.append(cloud)
        payload["corners_flat"] = (
            np.concatenate(clouds, axis=0) if clouds else np.zeros((0, dim))
        )
        payload["corners_offsets"] = np.cumsum(
            [0] + [len(c) for c in clouds], dtype=int
        )
    np.savez(path, **payload)


_PICKLE_REFUSED = "legacy pickled npz refused; re-save with save_npz_mesh"

# Phrases in the ValueError NumPy raises when allow_pickle=False stops it from
# unpickling: an object array ("Object arrays cannot be loaded when
# allow_pickle=False") or a file that is neither .npz nor .npy ("Cannot load
# file containing pickled data ..." up to NumPy 2.0, "This file contains
# pickled (object) data ..." in 2.4/2.5). NumPy's max_header_size refusal also
# mentions allow_pickle but matches neither phrase, so it passes through
# unchanged. Only the error text depends on this match: with allow_pickle=False
# nothing is ever unpickled, whatever NumPy's wording.
_NUMPY_PICKLE_REFUSALS = ("Object arrays cannot be loaded", "pickled")


def _is_pickle_refusal(exc: ValueError) -> bool:
    return any(phrase in str(exc) for phrase in _NUMPY_PICKLE_REFUSALS)


def _field(data, key: str) -> np.ndarray:
    """Read one array from an ``allow_pickle=False`` npz, naming pickle refusals."""
    try:
        value = data[key]
    except ValueError as exc:
        # NumPy refuses dtype=object members because they are stored pickled.
        if _is_pickle_refusal(exc):
            raise ValueError(
                f"npz mesh field {key!r} is a pickled object array: {_PICKLE_REFUSED}"
            ) from exc
        raise
    if not isinstance(value, np.ndarray):
        # NpzFile hands back raw bytes for a member without the .npy header.
        raise ValueError(f"npz mesh field {key!r} is not a .npy array member")
    return value


def _split_csr(flat: np.ndarray, offsets: np.ndarray, name: str) -> list[np.ndarray]:
    """Split ``flat`` into per-cell rows using a CSR-like ``offsets`` array."""
    if offsets.ndim != 1 or offsets.dtype.kind not in "iu" or len(offsets) == 0:
        raise ValueError(f"'{name}_offsets' must be a non-empty 1-D integer array")
    offsets = offsets.astype(int)
    if offsets[0] != 0 or offsets[-1] != len(flat) or np.any(np.diff(offsets) < 0):
        raise ValueError(
            f"'{name}_offsets' must start at 0, be non-decreasing, and end at "
            f"len('{name}_flat')"
        )
    return [flat[offsets[i] : offsets[i + 1]] for i in range(len(offsets) - 1)]


def _neighbors_from_npz(data) -> list[np.ndarray]:
    """Recover the per-cell neighbor lists from either supported encoding."""
    # Membership is tested on ``data.files`` (a plain list of member names), not
    # ``key in data``: NpzFile has no __contains__ before NumPy 1.25, so there
    # ``in`` falls back to Mapping.__contains__, which reads the whole member.
    names = data.files
    if "neighbors_flat" in names and "neighbors_offsets" in names:
        flat = np.asarray(_field(data, "neighbors_flat"), dtype=int).ravel()
        return _split_csr(flat, _field(data, "neighbors_offsets"), "neighbors")
    if "neighbors" in names:
        raw = _field(data, "neighbors")
        if raw.ndim != 2 or raw.dtype.kind not in "iu":
            raise ValueError(
                "'neighbors' must be a rectangular (N, K) integer array; store "
                "ragged neighbors as 'neighbors_flat'+'neighbors_offsets'"
            )
        return [np.asarray(row, dtype=int) for row in raw]
    raise ValueError(
        "npz mesh is missing neighbors: provide either 'neighbors_flat'+"
        "'neighbors_offsets' or a rectangular (N, K) integer 'neighbors' array"
    )


def _corners_from_npz(data, dim: int) -> list[np.ndarray] | None:
    """Recover optional per-cell corner clouds (CSR pair or rectangular array)."""
    names = data.files  # not ``key in data``; see _neighbors_from_npz
    has_flat, has_off = "corners_flat" in names, "corners_offsets" in names
    if has_flat or has_off:
        if not (has_flat and has_off):
            raise ValueError(
                "'corners_flat' and 'corners_offsets' must be provided together"
            )
        flat = _field(data, "corners_flat")
        if flat.ndim != 2 or flat.shape[1] != dim or flat.dtype.kind not in "iuf":
            raise ValueError(f"'corners_flat' must be a numeric (M, {dim}) array")
        flat = np.asarray(flat, dtype=float)
        return _split_csr(flat, _field(data, "corners_offsets"), "corners")
    if "corners" in names:
        raw = _field(data, "corners")
        if raw.ndim != 3 or raw.shape[2] != dim or raw.dtype.kind not in "iuf":
            raise ValueError(
                f"'corners' must be a rectangular (N, K, {dim}) numeric array; "
                "store ragged corners as 'corners_flat'+'corners_offsets'"
            )
        return [np.asarray(c, dtype=float) for c in raw]
    return None


def load_npz_mesh(path: str) -> Mesh:
    """Load a :class:`Mesh` from a yarqa ``.npz`` file.

    Accepts the CSR-like neighbor/corner encoding written by
    :func:`save_npz_mesh` and rectangular numeric ``neighbors``/``corners``
    arrays. The file is opened with ``allow_pickle=False``: object arrays and
    pickled files are refused with ``ValueError`` and never unpickled. Raises
    ``ValueError`` with a clear message on a malformed file rather than failing
    obscurely.
    """
    try:
        npz = np.load(path, allow_pickle=False)
    except ValueError as exc:
        # Raised for input that is not an .npz/.npy file (NumPy would try to
        # unpickle it) and for an object-dtype .npy; neither is unpickled.
        if _is_pickle_refusal(exc):
            raise ValueError(
                f"{path} is not a plain .npz mesh archive and NumPy would have "
                "to try unpickling it: pickle loading refused; write meshes "
                "with save_npz_mesh"
            ) from exc
        raise
    if not isinstance(npz, np.lib.npyio.NpzFile):
        raise ValueError(f"{path} is a single .npy array, not an .npz mesh archive")
    with npz as data:
        if "centers" not in data.files or "velocities" not in data.files:
            raise ValueError("npz mesh must contain 'centers' and 'velocities'")
        centers = np.asarray(_field(data, "centers"), dtype=float)
        velocities = np.asarray(_field(data, "velocities"), dtype=float)
        neighbors = _neighbors_from_npz(data)
        dim = centers.shape[1] if centers.ndim == 2 else -1
        corners = _corners_from_npz(data, dim)
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
