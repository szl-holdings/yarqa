# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Verifiable, reproducible provenance receipts for yarqa runs.

Every compartmentalization can emit a *receipt*: a compact, canonical record of
the exact inputs (by content hash), the parameters, the code version, and the
result (by content hash). Anyone holding the original mesh can **replay** the run
and confirm the result hash matches the receipt — making a yarqa result
independently reproducible and tamper-evident, not "trust me."

This mirrors SZL's Khipu/receipt discipline. It is an **integrity** mechanism:
it proves *this output came from these inputs under this code*. It is NOT a
formal proof of correctness and carries NO locked-theorem or compliance claim.

The receipt is signing-ready: `receipt_digest()` returns the stable bytes you
would hand to cosign / an Ed25519 signer. Signing itself is left to the caller's
key-management (the platform's existing receipt chain), so this module stays
dependency-free and honest about what it does.
"""
from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

import numpy as np

from . import __version__
from .core import Mesh, compartmentalize, build_connection_map

_RECEIPT_SCHEMA = "szl.yarqa.receipt/v1"


def _hash_array(a: np.ndarray) -> str:
    """Stable content hash of an array: shape + dtype + canonical bytes."""
    a = np.ascontiguousarray(a)
    h = hashlib.sha256()
    h.update(str(a.shape).encode())
    h.update(str(a.dtype).encode())
    h.update(a.tobytes())
    return h.hexdigest()


def _hash_neighbors(neighbors: list[np.ndarray]) -> str:
    h = hashlib.sha256()
    for arr in neighbors:
        h.update(np.ascontiguousarray(np.asarray(arr, dtype=int)).tobytes())
        h.update(b"|")
    return h.hexdigest()


def mesh_fingerprint(mesh: Mesh) -> dict[str, str]:
    """Content fingerprint of a mesh — identical meshes hash identically."""
    fp = {
        "centers": _hash_array(mesh.centers),
        "velocities": _hash_array(mesh.velocities),
        "neighbors": _hash_neighbors(mesh.neighbors),
        "dim": str(mesh.dim),
        "n": str(mesh.n),
    }
    if mesh.corners is not None:
        ch = hashlib.sha256()
        for c in mesh.corners:
            ch.update(_hash_array(c).encode())
        fp["corners"] = ch.hexdigest()
    return fp


@dataclass
class Receipt:
    """A canonical, reproducible record of one yarqa run."""

    schema: str
    yarqa_version: str
    created_utc: str
    params: dict[str, Any]
    inputs: dict[str, str]      # mesh fingerprint
    result_hash: str            # hash of the labels array
    n_compartments: int
    environment: dict[str, str]
    # Honesty: this receipt asserts INTEGRITY/REPRODUCIBILITY, not correctness.
    claim_tier: str = "engineering-method-cfd; integrity-receipt; NOT a locked theorem"

    def to_canonical_json(self) -> str:
        """Deterministic JSON (sorted keys, no whitespace drift) for hashing/signing."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def receipt_digest(self) -> str:
        """SHA-256 of the canonical receipt — the bytes a signer would sign."""
        return hashlib.sha256(self.to_canonical_json().encode()).hexdigest()

    @classmethod
    def from_json(cls, text: str) -> "Receipt":
        """Reconstruct a Receipt from JSON (e.g. ``to_canonical_json`` output).

        Loading does not trust the contents; pass the result to
        :func:`verify` to confirm it reproduces from the mesh. Unknown keys are
        ignored and missing optional keys fall back to their defaults so older
        receipts remain loadable.
        """
        data = json.loads(text)
        return cls(
            schema=data["schema"],
            yarqa_version=data["yarqa_version"],
            created_utc=data["created_utc"],
            params=data["params"],
            inputs=data["inputs"],
            result_hash=data["result_hash"],
            n_compartments=int(data["n_compartments"]),
            environment=data["environment"],
            claim_tier=data.get(
                "claim_tier",
                "engineering-method-cfd; integrity-receipt; NOT a locked theorem",
            ),
        )


def compartmentalize_with_receipt(
    mesh: Mesh,
    *,
    align_threshold: float = 0.0,
    connection_map: list[np.ndarray] | None = None,
) -> tuple[np.ndarray, Receipt]:
    """Run compartmentalization and emit a reproducible provenance receipt."""
    labels = compartmentalize(
        mesh, align_threshold=align_threshold, connection_map=connection_map
    )
    receipt = Receipt(
        schema=_RECEIPT_SCHEMA,
        yarqa_version=__version__,
        created_utc=datetime.now(timezone.utc).isoformat(),
        params={"align_threshold": float(align_threshold)},
        inputs=mesh_fingerprint(mesh),
        result_hash=_hash_array(labels),
        n_compartments=int(len(np.unique(labels))),
        environment={
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
    )
    return labels, receipt


def verify(mesh: Mesh, receipt: Receipt) -> dict[str, Any]:
    """Replay the run from `mesh` and check it reproduces `receipt`.

    Returns a verdict dict with `ok` (bool) and per-check details. This is the
    crux of the innovation: a third party with only the mesh + receipt can
    confirm — deterministically — that the published compartments are exactly
    what this code produces from these inputs. Any tampering with inputs,
    params, or results flips `ok` to False.
    """
    checks: dict[str, bool] = {}

    # 1. Do the claimed inputs match the mesh we were handed?
    checks["inputs_match"] = mesh_fingerprint(mesh) == receipt.inputs

    # 2. Recompute with the receipt's parameters and compare result hash.
    align = float(receipt.params.get("align_threshold", 0.0))
    labels = compartmentalize(mesh, align_threshold=align)
    recomputed_hash = _hash_array(labels)
    checks["result_reproduces"] = recomputed_hash == receipt.result_hash
    checks["compartment_count_matches"] = (
        int(len(np.unique(labels))) == receipt.n_compartments
    )
    checks["schema_known"] = receipt.schema == _RECEIPT_SCHEMA

    ok = all(checks.values())
    return {
        "ok": ok,
        "checks": checks,
        "recomputed_result_hash": recomputed_hash,
        "receipt_digest": receipt.receipt_digest(),
    }
