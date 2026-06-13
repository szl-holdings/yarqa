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

## Agentic routing, receipt chains & CLI (v0.4.0, additive)
Everything below is additive — the v0.3.0 API and all prior tests are unchanged.

**Sparse top-k routing.** Alongside the original argmax `route()`, `route_topk()`
routes an observation to its *k* best-aligned compartments with normalized
softmax gating weights over their cosine scores (k=1 reproduces argmax):
```python
from yarqa import build_experts, route_topk
rk = route_topk(observation_velocity, experts, k=2, temperature=1.0)
rk.compartment_ids, rk.weights   # best-first ids; softmax weights summing to 1.0
```
Concept inspiration only: the sparsely-gated mixture-of-experts idea (Shazeer et
al., 2017). All code is original SZL work; the "experts" are physical flow
compartments, not learned networks.

**Append-only receipt chain.** `ReceiptChain` hash-links `AgentStep` receipts
(`prev_digest -> digest`) into a tamper-evident log: editing, reordering,
inserting, or deleting any past step breaks `verify()`. This is an
**integrity / ordering** mechanism, not a proof of correctness and not a locked
theorem.
```python
from yarqa import ReceiptChain
chain = ReceiptChain()
for step in agent_steps:
    chain.append(step)
chain.verify()["ok"]   # True only if the whole chain is intact
```

**CLI.** Real entry points over the simple `.npz` mesh format (numpy-only; no
OpenFOAM dependency). A `try_load_openfoam()` hook is a guarded, honest stub.
```bash
python -m yarqa.cli sample mesh.npz                 # SAMPLE synthetic mesh
python -m yarqa.cli compartmentalize mesh.npz --receipt r.json
python -m yarqa.cli verify mesh.npz r.json          # reproduce + confirm
```

## Provenance & honesty
Clean-room implementation from a published algorithm description — no third-party
(incl. AGPL) source copied. See [`PROVENANCE.md`](PROVENANCE.md). **`yarqa` is an
engineering/CFD method, not a lutar-lean locked-proven theorem** — never surface it
with a "proven" badge or fold it into the locked formula count.

---
*SZL Holdings · Apache-2.0 · Doctrine v11.*

## Signed provenance receipts (Sigstore keyless)

Every `compartmentalize_with_receipt(...)` run yields a canonical, reproducible
`Receipt`. In CI, that receipt is signed as a **genuine Sigstore keyless DSSE
attestation** — a GitHub Actions OIDC token is exchanged at **Fulcio** for a
short-lived ECDSA-P256 certificate, the receipt is wrapped as an in-toto v1
Statement and DSSE-signed, and the signature is recorded in the public **Rekor**
transparency log. No founder key, no stored secret.

```bash
# sign (requires a CI context with id-token: write; off-CI use --allow-placeholder)
python scripts/sign_receipt.py --nx 12 --ny 8 --seed 0

# independently verify the signature AND reproduce the run
python scripts/verify_receipt.py attestations/yarqa/<digest>.dsse.json \
  --identity "https://github.com/szl-holdings/yarqa/.github/workflows/receipt-sign.yml@refs/heads/master" \
  --issuer "https://token.actions.githubusercontent.com" \
  --replay
```

The signed statement embeds a deterministic **replay recipe** (`generator, nx,
ny, seed, align_threshold`), so any third party can regenerate the mesh,
reconstruct the receipt, and confirm via `yarqa.verify()` that the result
reproduces — independent of any data we host.

The `receipt-sign` workflow runs this on every push to `master` and publishes
each signed receipt to the append-only `governance-receipts` branch
(`receipts/<sha256>.dsse.json`).

**Honesty:** this signs the receipt, nothing more. `yarqa` is an
engineering-method / CFD tool — receipts attest **integrity + reproducibility**,
never correctness, and carry no locked-theorem or "proven" claim. SLSA level is
unchanged (**L1**). Outside CI there is no ambient identity, so `yarqa` declines
to sign rather than fabricate a signature (an honest placeholder is emitted only
with `--allow-placeholder`).
