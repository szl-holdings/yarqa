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

## Verifiable provenance receipts (the SZL innovation)
`yarqa` is, to our knowledge, the first plug-flow compartmentalizer that emits a
**signed-ready, replayable provenance receipt** for every run — applying SZL's
receipt discipline to CFD:
```python
from yarqa import compartmentalize_with_receipt, verify
labels, receipt = compartmentalize_with_receipt(mesh, align_threshold=0.2)
receipt.receipt_digest()      # 64-char SHA-256 — the bytes a signer/cosign would sign
verify(mesh, receipt)["ok"]    # True — anyone with the mesh can reproduce + confirm
```
The receipt records input content-hashes, params, code version, and the result
hash. A third party holding only the mesh + receipt can **deterministically
replay** the run and confirm the published compartments are exactly what this
code produces — tamper-evident on inputs, params, or results. Signing itself is
left to the platform's existing key chain (Ed25519/cosign), so the module stays
dependency-free. This is an **integrity / reproducibility** guarantee, NOT a
formal proof of correctness.

## Provenance & honesty
Clean-room implementation from a published algorithm description — no third-party
(incl. AGPL) source copied. See [`PROVENANCE.md`](PROVENANCE.md). **`yarqa` is an
engineering/CFD method, not a lutar-lean locked-proven theorem** — never surface it
with a "proven" badge or fold it into the locked formula count.

---
*SZL Holdings · Apache-2.0 · Doctrine v11.*
