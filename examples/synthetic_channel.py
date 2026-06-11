# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Synthetic example: a converging channel flow, no OpenFOAM needed.

Builds a 2-D grid whose velocity field accelerates and bends through a neck,
then compartmentalizes it and prints the plug-flow slice summary.
"""
import numpy as np

from yarqa import Mesh, compartmentalize
from yarqa.core import compartment_summary


def build(nx=20, ny=12):
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
    # velocity: mostly +x, accelerating downstream, gently converging toward
    # the centerline (a crude nozzle/neck).
    vel = np.zeros((nx * ny, 2))
    for i in range(nx):
        for j in range(ny):
            speed = 1.0 + 0.15 * i
            vy = -0.08 * (j - (ny - 1) / 2.0)  # converge toward center
            vel[idx(i, j)] = [speed, vy]
    return Mesh(centers, vel, neighbors)


if __name__ == "__main__":
    mesh = build()
    labels = compartmentalize(mesh, align_threshold=0.2)
    rep = compartment_summary(mesh, labels)
    print(f"cells={mesh.n}  compartments={rep['n_compartments']}")
    for cid, info in list(rep["compartments"].items())[:8]:
        mv = info["mean_velocity"]
        print(f"  comp {cid:2d}: {info['n_cells']:3d} cells  "
              f"mean_v=({mv[0]:.2f},{mv[1]:.2f})  centroid={[round(x,1) for x in info['centroid']]}")
