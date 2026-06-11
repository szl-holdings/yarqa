# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Tests for yarqa.core — synthetic meshes, no OpenFOAM dependency."""
import numpy as np

from yarqa import Mesh, compartmentalize, build_connection_map
from yarqa.core import compartment_summary, _straddles_front, _aligned


def _grid_2d(nx, ny):
    """Build a structured nx*ny 2-D grid with 4-neighbor adjacency."""
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
    return centers, neighbors


def test_uniform_flow_makes_plugflow_slices():
    # Uniform +x flow on an nx*ny grid should reduce to nx sequential plug-flow
    # slices (each slice = one compartment, constant x, spanning all y). This
    # is the defining behavior of a plug-flow reduction: a series of slices
    # perpendicular to the flow direction.
    nx, ny = 6, 6
    centers, neighbors = _grid_2d(nx, ny)
    velocities = np.tile([1.0, 0.0], (len(centers), 1))  # uniform +x
    mesh = Mesh(centers, velocities, neighbors)
    labels = compartmentalize(mesh)
    assert len(np.unique(labels)) == nx
    # each compartment is a single x-slice spanning every y row
    for c in np.unique(labels):
        xs = np.unique(centers[labels == c, 0])
        ys = np.unique(centers[labels == c, 1])
        assert len(xs) == 1 and len(ys) == ny


def test_opposing_streams_split():
    centers, neighbors = _grid_2d(6, 6)
    velocities = np.zeros((len(centers), 2))
    # left half flows +x, right half flows -x → must not merge (anti-aligned)
    for k, (x, _y) in enumerate(centers):
        velocities[k] = [1.0, 0.0] if x < 3 else [-1.0, 0.0]
    mesh = Mesh(centers, velocities, neighbors)
    labels = compartmentalize(mesh)
    assert len(np.unique(labels)) >= 2
    # no compartment may contain both a +x and a -x cell
    for c in np.unique(labels):
        vx = velocities[labels == c, 0]
        assert np.all(vx >= 0) or np.all(vx <= 0)


def test_every_cell_assigned():
    centers, neighbors = _grid_2d(5, 7)
    rng = np.random.default_rng(0)
    velocities = rng.normal(size=(len(centers), 2))
    mesh = Mesh(centers, velocities, neighbors)
    labels = compartmentalize(mesh)
    assert np.all(labels >= 0)
    assert labels.shape[0] == len(centers)


def test_connection_map_symmetric():
    centers, neighbors = _grid_2d(4, 4)
    velocities = np.ones((len(centers), 2))
    mesh = Mesh(centers, velocities, neighbors)
    adj = build_connection_map(mesh)
    for i, nbrs in enumerate(adj):
        for j in nbrs:
            assert i in adj[j], "adjacency must be symmetric"


def test_align_threshold_increases_compartments():
    centers, neighbors = _grid_2d(8, 8)
    rng = np.random.default_rng(1)
    velocities = rng.normal(size=(len(centers), 2))
    mesh = Mesh(centers, velocities, neighbors)
    loose = len(np.unique(compartmentalize(mesh, align_threshold=0.0)))
    strict = len(np.unique(compartmentalize(mesh, align_threshold=0.9)))
    assert strict >= loose


def test_straddle_and_align_helpers():
    u = np.array([1.0, 0.0])
    # points on both sides of the front through origin
    pts = np.array([[-0.5, 0.0], [0.5, 0.0]])
    assert _straddles_front(u, np.zeros(2), pts) is True
    # all downstream → does not straddle
    assert _straddles_front(u, np.zeros(2), np.array([[1.0, 0.0], [2.0, 0.0]])) is False
    assert _aligned(u, np.array([0.3, 0.9])) is True
    assert _aligned(u, np.array([-0.3, 0.9])) is False


def test_summary_shape():
    centers, neighbors = _grid_2d(4, 4)
    velocities = np.tile([0.0, 1.0], (len(centers), 1))
    mesh = Mesh(centers, velocities, neighbors)
    labels = compartmentalize(mesh)
    rep = compartment_summary(mesh, labels)
    assert rep["n_compartments"] == len(rep["compartments"])
