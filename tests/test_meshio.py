# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Tests for yarqa.meshio — guarded .npz mesh I/O and SAMPLE synthetic data.

No OpenFOAM (or any CFD package) dependency is exercised or required.
"""
import numpy as np
import pytest

from yarqa import Mesh, compartmentalize, mesh_fingerprint
from yarqa.meshio import (
    load_npz_mesh,
    save_npz_mesh,
    sample_channel_mesh,
    try_load_openfoam,
)


def _grid(nx, ny):
    centers, neighbors = [], []
    idx = lambda i, j: i * ny + j
    for i in range(nx):
        for j in range(ny):
            centers.append([float(i), float(j)])
    centers = np.array(centers)
    for i in range(nx):
        for j in range(ny):
            nb = []
            if i > 0: nb.append(idx(i - 1, j))
            if i < nx - 1: nb.append(idx(i + 1, j))
            if j > 0: nb.append(idx(i, j - 1))
            if j < ny - 1: nb.append(idx(i, j + 1))
            neighbors.append(np.array(nb))
    vel = np.tile([1.0, 0.0], (len(centers), 1))
    return Mesh(centers, vel, neighbors)


def test_npz_roundtrip_preserves_mesh(tmp_path):
    mesh = _grid(6, 5)
    path = str(tmp_path / "mesh.npz")
    save_npz_mesh(path, mesh)
    loaded = load_npz_mesh(path)
    assert loaded.n == mesh.n and loaded.dim == mesh.dim
    assert np.allclose(loaded.centers, mesh.centers)
    assert np.allclose(loaded.velocities, mesh.velocities)
    # Fingerprints must match exactly -> a saved/loaded mesh is bit-identical.
    assert mesh_fingerprint(loaded) == mesh_fingerprint(mesh)


def test_npz_roundtrip_preserves_compartments(tmp_path):
    mesh = _grid(6, 6)
    path = str(tmp_path / "mesh.npz")
    save_npz_mesh(path, mesh)
    loaded = load_npz_mesh(path)
    assert np.array_equal(compartmentalize(mesh), compartmentalize(loaded))


def test_npz_with_object_neighbors_array(tmp_path):
    # A hand-written npz using a single ragged 'neighbors' object array.
    centers = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    velocities = np.tile([1.0, 0.0], (3, 1))
    neighbors = np.array(
        [np.array([1]), np.array([0, 2]), np.array([1])], dtype=object
    )
    path = str(tmp_path / "obj.npz")
    np.savez(path, centers=centers, velocities=velocities, neighbors=neighbors)
    loaded = load_npz_mesh(path)
    assert loaded.n == 3
    assert list(loaded.neighbors[1]) == [0, 2]


def test_npz_missing_fields_raises(tmp_path):
    path = str(tmp_path / "bad.npz")
    np.savez(path, centers=np.zeros((3, 2)))  # no velocities
    with pytest.raises(ValueError):
        load_npz_mesh(path)


def test_npz_missing_neighbors_raises(tmp_path):
    path = str(tmp_path / "bad2.npz")
    np.savez(path, centers=np.zeros((3, 2)), velocities=np.zeros((3, 2)))
    with pytest.raises(ValueError):
        load_npz_mesh(path)


def test_sample_mesh_is_deterministic_and_valid():
    a = sample_channel_mesh(nx=10, ny=6, seed=42)
    b = sample_channel_mesh(nx=10, ny=6, seed=42)
    assert a.n == 60 and a.dim == 2
    assert mesh_fingerprint(a) == mesh_fingerprint(b)
    # downstream velocity dominates (channel flows +x)
    assert np.mean(a.velocities[:, 0]) > 1.0
    labels = compartmentalize(a, align_threshold=0.2)
    assert np.all(labels >= 0)


def test_sample_mesh_corners_roundtrip(tmp_path):
    base = sample_channel_mesh(nx=4, ny=4)
    corners = [np.array([base.centers[i]]) for i in range(base.n)]
    mesh = Mesh(base.centers, base.velocities, base.neighbors, corners=corners)
    path = str(tmp_path / "corners.npz")
    save_npz_mesh(path, mesh)
    loaded = load_npz_mesh(path)
    assert loaded.corners is not None
    assert len(loaded.corners) == mesh.n


def test_openfoam_hook_is_guarded():
    # Honest stub: must raise NotImplementedError, never a hard dependency.
    with pytest.raises(NotImplementedError):
        try_load_openfoam("/nonexistent/case")
