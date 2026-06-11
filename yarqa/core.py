# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
#
# Yarqa — plug-flow compartmentalization.
#
# Clean-room implementation. Written solely from the published high-level
# algorithm description (a region-growing partition of a CFD mesh by velocity
# alignment across a flow front). No third-party source was copied; data
# structures, control flow, vectorization, and API are original to SZL.
"""Core compartmentalization engine.

The method reduces a resolved CFD velocity field into a small number of
*plug-flow compartments*: maximal connected regions of cells whose local
velocity vectors point the same general direction and that together span a
coherent flow front. This is the classic reactor-engineering reduction of a
3-D field to a network of ideal plug-flow / well-mixed compartments.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np


@dataclass
class Mesh:
    """A finite-volume mesh with per-cell velocity and geometry.

    Parameters
    ----------
    centers : (N, D) float array
        Cell-center coordinates (D = 2 or 3).
    velocities : (N, D) float array
        Cell-center velocity vectors.
    neighbors : sequence of int arrays, length N
        ``neighbors[i]`` lists the cell ids sharing a face with cell ``i``.
    corners : optional list of (K_i, D) float arrays, length N
        Corner-point coordinates per cell. When omitted, each neighbor's
        center is used as its single representative point (a robust fallback
        that still captures the straddle test).
    """

    centers: np.ndarray
    velocities: np.ndarray
    neighbors: Sequence[np.ndarray]
    corners: list[np.ndarray] | None = None

    n: int = field(init=False)
    dim: int = field(init=False)

    def __post_init__(self) -> None:
        self.centers = np.asarray(self.centers, dtype=float)
        self.velocities = np.asarray(self.velocities, dtype=float)
        if self.centers.ndim != 2 or self.velocities.shape != self.centers.shape:
            raise ValueError("centers and velocities must be (N, D) and match")
        self.n, self.dim = self.centers.shape
        if len(self.neighbors) != self.n:
            raise ValueError("neighbors must have one entry per cell")
        self.neighbors = [np.asarray(a, dtype=int).ravel() for a in self.neighbors]
        if self.corners is not None:
            if len(self.corners) != self.n:
                raise ValueError("corners must have one entry per cell")
            self.corners = [np.asarray(c, dtype=float) for c in self.corners]

    def representative_points(self, cell_id: int) -> np.ndarray:
        """Points used for the straddle test for ``cell_id``.

        Returns this cell's corner points when available. Otherwise it
        synthesizes a small symmetric point cloud around the cell center using
        the half-spacing to the cell's nearest neighbor, so the straddle test
        remains meaningful without explicit corner geometry.
        """
        if self.corners is not None:
            return self.corners[cell_id]
        # Fallback: approximate the cell extent from nearest-neighbor distance.
        c = self.centers[cell_id]
        nbrs = self.neighbors[cell_id]
        if len(nbrs) == 0:
            return c[None, :]
        h = 0.5 * float(np.min(np.linalg.norm(self.centers[nbrs] - c, axis=1)))
        if h <= 0.0:
            return c[None, :]
        # +/- offsets along each axis form a symmetric cloud spanning the cell.
        offs = np.vstack([np.eye(self.dim), -np.eye(self.dim)]) * h
        return c[None, :] + offs


def _unit(v: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm > eps else v


def _straddles_front(
    u_seed: np.ndarray, r_seed: np.ndarray, neighbor_points: np.ndarray
) -> bool:
    """True if the neighbor spans the seed cell's flow front.

    The flow front through the seed is the plane normal to ``u_seed`` passing
    through ``r_seed``. A neighbor straddles it when at least one of its
    representative points lies on the downstream side (dot >= 0) and at least
    one lies on the upstream side (dot < 0). This admits cells that the front
    actually cuts through, which is what defines a plug-flow slice boundary.
    """
    rel = neighbor_points - r_seed  # (K, D)
    proj = rel @ u_seed  # (K,)
    return bool(np.any(proj >= 0.0) and np.any(proj < 0.0))


def _aligned(u_seed: np.ndarray, u_neighbor: np.ndarray) -> bool:
    """True if the neighbor's velocity points with the seed's (dot >= 0)."""
    return bool(np.dot(u_seed, u_neighbor) >= 0.0)


def build_connection_map(mesh: Mesh) -> list[np.ndarray]:
    """Return the symmetric face-adjacency map as a list of neighbor arrays.

    This normalizes whatever neighbor lists the mesh carries into a clean,
    de-duplicated, symmetric adjacency structure the grower can rely on.
    """
    adj: list[set[int]] = [set() for _ in range(mesh.n)]
    for i, nbrs in enumerate(mesh.neighbors):
        for j in nbrs:
            j = int(j)
            if j == i or j < 0 or j >= mesh.n:
                continue
            adj[i].add(j)
            adj[j].add(i)  # enforce symmetry
    return [np.array(sorted(s), dtype=int) for s in adj]


def compartmentalize(
    mesh: Mesh,
    *,
    align_threshold: float = 0.0,
    connection_map: list[np.ndarray] | None = None,
) -> np.ndarray:
    """Partition the mesh into plug-flow compartments.

    Region-growing partition: repeatedly pick an unassigned seed cell and grow
    a compartment outward through face-neighbors that (a) are velocity-aligned
    with the seed and (b) straddle the seed's flow front. Every cell ends up in
    exactly one compartment.

    Parameters
    ----------
    mesh : Mesh
    align_threshold : float
        Minimum ``dot(u_seed_unit, u_neighbor_unit)`` to count as aligned.
        ``0.0`` reproduces the half-space (>= 0) rule; raise toward 1.0 for
        stricter, more numerous compartments.
    connection_map : optional
        Precomputed adjacency (from :func:`build_connection_map`).

    Returns
    -------
    labels : (N,) int array
        Compartment id per cell, contiguous from 0.
    """
    adj = connection_map if connection_map is not None else build_connection_map(mesh)
    labels = np.full(mesh.n, -1, dtype=int)
    # Process in a deterministic order so results are reproducible.
    order = np.argsort(-np.linalg.norm(mesh.velocities, axis=1))  # fastest first
    current = 0

    for start in order:
        if labels[start] != -1:
            continue
        # Grow a new compartment from this seed.
        u_seed = mesh.velocities[start]
        r_seed = mesh.centers[start]
        u_seed_unit = _unit(u_seed)

        labels[start] = current
        frontier: deque[int] = deque([start])
        while frontier:
            cell = frontier.popleft()
            for k in adj[cell]:
                if labels[k] != -1:
                    continue
                u_k = mesh.velocities[k]
                if np.dot(u_seed_unit, _unit(u_k)) < align_threshold:
                    continue
                if not _straddles_front(u_seed, r_seed, mesh.representative_points(k)):
                    continue
                labels[k] = current
                frontier.append(k)
        current += 1

    return labels


def compartment_summary(mesh: Mesh, labels: np.ndarray) -> dict:
    """Lightweight report: per-compartment cell count and mean velocity."""
    out: dict[int, dict] = {}
    for c in np.unique(labels):
        mask = labels == c
        out[int(c)] = {
            "n_cells": int(mask.sum()),
            "mean_velocity": mesh.velocities[mask].mean(axis=0).tolist(),
            "centroid": mesh.centers[mask].mean(axis=0).tolist(),
        }
    return {"n_compartments": int(len(out)), "compartments": out}
