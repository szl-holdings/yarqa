> **SZL Holdings** · Doctrine v11 · Λ = Conjecture 1 (advisory, never "green"/theorem) · canonical [a-11-oy.com](https://a-11-oy.com)

# yarqa

<!-- szl:header v1 -->
<!-- Native identity: szl-brand@4309f6fce89179331b0b3ed8c99494e76c5be256; Orbit v2 icon. -->
<p>
  <a href="https://github.com/szl-holdings">
    <img src="https://raw.githubusercontent.com/szl-holdings/szl-brand/4309f6fce89179331b0b3ed8c99494e76c5be256/kit/logos/orbit-v2/suite/szl-icon-32.svg" alt="SZL Holdings — Orbit v2" width="32" height="32" />
  </a>
</p>

**Control before action. Evidence after.**

[Product](https://a-11-oy.com) · [Proof](https://a11oy.net) · [GitHub organization](https://github.com/szl-holdings)
<!-- /szl:header -->

**Plug-flow compartmentalization for compartmental models.**

`yarqa` (Quechua: an Andean irrigation canal that divides and routes flowing
water) reduces a resolved CFD velocity field into a small network of plug-flow
compartments — maximal connected regions of velocity-aligned cells spanning a
coherent flow front. It's the classic reactor-engineering reduction of a 3-D
field to a series/network of ideal compartments.

Pure-Python + NumPy. No OpenFOAM dependency required (bring your own mesh as
centers + velocities + neighbor lists). Apache-2.0.

## Install

`yarqa` is not on PyPI yet (no release has been published), so install it
from source. NumPy is the only runtime dependency; Python 3.10 or newer.

```bash
git clone https://github.com/szl-holdings/yarqa.git
cd yarqa
python -m pip install -e .            # library + CLI
python -m pip install -e '.[test]'    # adds the test tooling
```

Without a checkout: `python -m pip install "git+https://github.com/szl-holdings/yarqa.git"`.

## Test

```bash
python -m pytest tests/ -q
```

`tests/test_space_frontend.py` and `tests/test_receipt_ledger.py` drive Node.js
fixtures, so `node` must be on `PATH`. `tests/test_attestation.py` and
`tests/test_prediction_receipt.py` skip (never fake) unless the optional
`szl_receipt` library is installed; see
[Surrogate and optional attestation](#surrogate-and-optional-attestation).
The Space endpoint tests need the Space requirements:

```bash
python -m pip install -r space/requirements.txt
python -m pytest space/tests/test_space_endpoints.py -q
```

CI (`.github/workflows/space-ci.yml`) runs both suites on Python 3.11 from the
hash-locked `.github/requirements/space-ci.lock`.

## Operational runtime

Two public runtimes serve this code:

- **Standalone Space**
  [`SZLHOLDINGS/yarqa`](https://huggingface.co/spaces/SZLHOLDINGS/yarqa). Its
  only writer is `.github/workflows/hf-space.yml`, which calls the org's
  reusable Dockerfile-derived deployer on each push to protected `main`. The
  deployer publishes the `space/Dockerfile` COPY set, binds the exact source
  SHA (`SZL_GIT_SHA`), restarts the Space, and attests the running Hub commit,
  every published file by sha256, and `/`, `/healthz` and `/api/build-info`.
  The Space card (the Hub `README.md`) is not published from this repository.
- **Command Lab route**
  <https://szlholdings-szl-command-lab.hf.space/api/yarqa>. Command Lab pins an
  exact commit from this repository, executes a bounded synthetic
  compartmentalization, emits a replayable receipt, and verifies that receipt
  before returning `READY`.

The standalone publisher was retired on 2026-09-08 (#63), but the Space stayed
public and running with no writer, so this repository is again its single
source. Both runtimes demonstrate integrity and reproducibility for their
disclosed synthetic input; they are not CFD correctness, validation for a
customer mesh, or authorization for an external action.

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
code produces — tamper-evident on inputs, params, or results. `yarqa.provenance`
itself stays dependency-free (NumPy only); keyless signing lives in
`yarqa.signing` and needs the optional `sigstore` package (see
[Signed provenance receipts](#signed-provenance-receipts-sigstore-keyless)).
This is an **integrity / reproducibility** guarantee, NOT a formal proof of
correctness.

## Agentic routing, receipt chains & CLI (v0.4.0, additive)
Everything below is additive — the v0.3.0 API and all prior tests are unchanged.

**Sparse top-k routing.** Alongside the original argmax `route()`, `route_topk()`
routes an observation to its *k* best-aligned compartments with normalized
softmax gating weights over their cosine scores (k=1 reproduces argmax):
```python
from yarqa import build_experts, route_topk
experts = build_experts(mesh, labels)          # one expert per compartment
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

## Surrogate and optional attestation

`fit_plugflow_surrogate()` runs the real `compartmentalize()` at a few anchor
thresholds (seven, evenly spaced over 0–0.98, by default) and interpolates the
compartment count between them. Outside the measured anchor range it returns
`UNAVAILABLE` with `value=None` instead of extrapolating; inside it reports the
two bracketing measured counts as an indicative interval, not a guarantee.
```python
from yarqa import fit_plugflow_surrogate
from yarqa.meshio import sample_channel_mesh

surrogate = fit_plugflow_surrogate(sample_channel_mesh(12, 8, seed=0))
p = surrogate.predict(0.9)
p.status, p.lower_bound, p.upper_bound   # ('PREDICTED', 29, 30); p.value ≈ 29.51
surrogate.predict(0.995).status          # 'UNAVAILABLE' (above the 0.98 anchor)
```

`yarqa.attestation` (`attest_prediction`, `emit_prediction_receipt`, …) wraps a
prediction in the shared SZL receipt shapes by delegating to the `szl_receipt`
library, which is not on PyPI. Without it those functions raise
`AttestationUnavailable` rather than build a receipt themselves. To enable them:
```bash
python -m pip install "szl_receipt @ git+https://github.com/szl-holdings/szl-receipt.git@v0.2.0"
```
The adapter's tests also pass against szl-receipt v0.3.4, whose distribution is
named `szl-receipt-dsse`. `emit_prediction_receipt()` without a private key
returns an honestly unsigned envelope.

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
  --identity "https://github.com/szl-holdings/yarqa/.github/workflows/receipt-sign.yml@refs/heads/main" \
  --issuer "https://token.actions.githubusercontent.com" \
  --replay
```

The signed statement embeds a deterministic **replay recipe** (`generator, nx,
ny, seed, align_threshold`), so any third party can regenerate the mesh,
reconstruct the receipt, and confirm via `yarqa.verify()` that the result
reproduces — independent of any data we host.

The `receipt-sign` workflow runs this on pull requests and pushes to `main`
that change the package, the signing scripts, their lock
(`requirements/ci/receipt-sign.txt`) or the workflow. On those pushes a
separate `publish-ledger` job, the only one holding a write token, appends each
verified receipt to the append-only `governance-receipts` branch
(`receipts/<sha256>.dsse.json`) and fails the run if it cannot.

**Honesty:** this signs the receipt, nothing more. `yarqa` is an
engineering-method / CFD tool — receipts attest **integrity + reproducibility**,
never correctness, and carry no locked-theorem or "proven" claim. SLSA level is
unchanged (**L1**). Outside CI there is no ambient identity, so `yarqa` declines
to sign rather than fabricate a signature (an honest placeholder is emitted only
with `--allow-placeholder`).

---

**Explore the SZL estate:** [a11oy console](https://a-11-oy.com) · [LLM Router](https://github.com/szl-holdings/szl-router) · [Receipt format spec](https://github.com/szl-holdings/governed-receipt-spec) · [Lean proofs](https://github.com/szl-holdings/lutar-lean) · [Docs (archived)](https://github.com/szl-holdings/docs-site) · [🤗 SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS)
