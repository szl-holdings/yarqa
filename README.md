# yarqa

**Plug-flow compartmentalization for compartmental models.**

`yarqa` (Quechua: an Andean irrigation canal that divides and routes flowing
water) reduces a resolved CFD velocity field into a small network of plug-flow
compartments — maximal connected regions of velocity-aligned cells spanning a
coherent flow front. It's the classic reactor-engineering reduction of a 3-D
field to a series/network of ideal compartments.

Pure-Python + NumPy. No OpenFOAM dependency required (bring your own mesh as
centers + velocities + neighbor lists). Apache-2.0.

## Install
```bash
pip install numpy
# then add this package to your path / install -e .
```

## Use
```python
import numpy as np
from yarqa import Mesh, compartmentalize
from yarqa.core import compartment_summary

mesh = Mesh(
    centers=cell_centers,        # (N, D)
    velocities=cell_velocities,  # (N, D)
    neighbors=face_neighbors,    # list of int arrays, length N
    corners=cell_corners,        # optional list of (K_i, D); falls back to centers
)
labels = compartmentalize(mesh, align_threshold=0.0)   # (N,) compartment id per cell
report = compartment_summary(mesh, labels)             # counts, mean velocity, centroids
```

## Algorithm (summary)
1. Build a symmetric face-adjacency connection map.
2. Pick the fastest unassigned cell as a seed; grow a compartment outward through
   neighbors that are **velocity-aligned** with the seed (`dot(û_seed, û_k) ≥ threshold`)
   **and straddle the seed's flow front** (representative points on both sides of
   the plane normal to the seed velocity).
3. Repeat until every cell is assigned. Result: sequential plug-flow slices.

## Provenance & honesty
Clean-room implementation from a published algorithm description — no third-party
(incl. AGPL) source copied. See [`PROVENANCE.md`](PROVENANCE.md). **`yarqa` is an
engineering/CFD method, not a lutar-lean locked-proven theorem** — never surface it
with a "proven" badge or fold it into the locked formula count.

---
*SZL Holdings · Apache-2.0 · Doctrine v11.*
