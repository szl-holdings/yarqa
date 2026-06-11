# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Tests for yarqa.provenance — determinism, reproducibility, tamper-detection."""
import numpy as np

from yarqa import Mesh, compartmentalize_with_receipt, verify, mesh_fingerprint


def _grid(nx, ny, vx=1.0, vy=0.0):
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
    vel = np.tile([vx, vy], (len(centers), 1))
    return Mesh(centers, vel, neighbors)


def test_fingerprint_is_deterministic():
    m1 = _grid(5, 5)
    m2 = _grid(5, 5)
    assert mesh_fingerprint(m1) == mesh_fingerprint(m2)


def test_fingerprint_changes_with_inputs():
    base = mesh_fingerprint(_grid(5, 5))
    assert mesh_fingerprint(_grid(5, 5, vx=2.0)) != base   # different velocity
    assert mesh_fingerprint(_grid(6, 5)) != base           # different size


def test_receipt_verifies_against_same_mesh():
    mesh = _grid(8, 6)
    labels, receipt = compartmentalize_with_receipt(mesh, align_threshold=0.1)
    verdict = verify(mesh, receipt)
    assert verdict["ok"] is True
    assert all(verdict["checks"].values())
    assert verdict["recomputed_result_hash"] == receipt.result_hash


def test_receipt_digest_is_stable():
    mesh = _grid(5, 5)
    _, r1 = compartmentalize_with_receipt(mesh)
    # digest must be stable across canonical re-serialization
    assert r1.receipt_digest() == r1.receipt_digest()
    assert len(r1.receipt_digest()) == 64  # sha256 hex


def test_tampered_inputs_fail_verification():
    mesh = _grid(8, 6)
    labels, receipt = compartmentalize_with_receipt(mesh)
    # Adversary presents a DIFFERENT mesh but the original receipt.
    tampered = _grid(8, 6, vx=3.0)
    verdict = verify(tampered, receipt)
    assert verdict["ok"] is False
    assert verdict["checks"]["inputs_match"] is False


def test_tampered_result_hash_fails():
    mesh = _grid(8, 6)
    _, receipt = compartmentalize_with_receipt(mesh)
    # Adversary edits the published result hash.
    receipt.result_hash = "0" * 64
    verdict = verify(mesh, receipt)
    assert verdict["ok"] is False
    assert verdict["checks"]["result_reproduces"] is False


def test_tampered_params_fail():
    # Use a VARIED velocity field so align_threshold genuinely changes the
    # partition (uniform flow would be threshold-invariant).
    nx, ny = 10, 8
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
    rng = np.random.default_rng(7)
    vel = rng.normal(size=(nx * ny, 2))
    mesh = Mesh(centers, vel, neighbors)

    labels0, receipt = compartmentalize_with_receipt(mesh, align_threshold=0.0)
    # Sanity: the two thresholds really do differ for this field.
    from yarqa import compartmentalize
    labels_strict = compartmentalize(mesh, align_threshold=0.95)
    assert len(np.unique(labels0)) != len(np.unique(labels_strict))
    # Now tamper the recorded param; verify must fail because the result
    # recorded under threshold=0.0 won't reproduce under 0.95.
    receipt.params["align_threshold"] = 0.95
    verdict = verify(mesh, receipt)
    assert verdict["ok"] is False


def test_receipt_carries_honest_claim_tier():
    mesh = _grid(4, 4)
    _, receipt = compartmentalize_with_receipt(mesh)
    assert "NOT a locked theorem" in receipt.claim_tier
    assert receipt.schema == "szl.yarqa.receipt/v1"
