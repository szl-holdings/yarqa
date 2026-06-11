# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Tests for yarqa.chain.ReceiptChain — append-only, tamper-evident linking.

The chain asserts INTEGRITY/ORDERING, not correctness; it is not a locked
theorem. These tests confirm linkage, tamper detection, and load/verify.
"""
import numpy as np

from yarqa import Mesh, ReceiptChain, GENESIS_PREV
from yarqa.agentic import AgenticYarqa
from yarqa.chain import ChainLink


def _grid(nx, ny, field_fn):
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
    vel = np.array([field_fn(c) for c in centers])
    return Mesh(centers, vel, neighbors)


def _two_stream(c):
    return [1.0, 0.0] if c[0] < 4 else [0.0, 1.0]


def _build_chain(n=4):
    mesh = _grid(8, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3)
    chain = ReceiptChain()
    obs = [np.array([1.0, 0.0]), np.array([0.0, 1.0]),
           np.array([1.0, 0.1]), np.array([0.2, 0.9])][:n]
    for o in obs:
        chain.append(agent.step(o))
    return chain


def test_empty_chain_head_is_genesis():
    chain = ReceiptChain()
    assert chain.head == GENESIS_PREV
    v = chain.verify()
    assert v["ok"] is True and v["n_links"] == 0


def test_chain_links_reference_predecessors():
    chain = _build_chain(4)
    assert len(chain.links) == 4
    assert chain.links[0].prev_digest == GENESIS_PREV
    for i in range(1, len(chain.links)):
        assert chain.links[i].prev_digest == chain.links[i - 1].digest
    assert chain.head == chain.links[-1].digest


def test_intact_chain_verifies():
    chain = _build_chain(4)
    v = chain.verify()
    assert v["ok"] is True
    assert v["first_broken_index"] is None
    assert all(v["checks"].values())


def test_indices_are_sequential():
    chain = _build_chain(3)
    assert [l.index for l in chain.links] == [0, 1, 2]


def test_tamper_payload_breaks_chain():
    chain = _build_chain(4)
    # Adversary edits a past step's decision but leaves digests untouched.
    chain.links[1].step["decision"] = "DENY"
    v = chain.verify()
    assert v["ok"] is False
    assert v["first_broken_index"] == 1
    assert v["checks"]["link_1"] is False


def test_tamper_digest_breaks_chain():
    chain = _build_chain(3)
    chain.links[2].digest = "0" * 64
    v = chain.verify()
    assert v["ok"] is False
    assert v["first_broken_index"] == 2


def test_reorder_breaks_chain():
    chain = _build_chain(4)
    chain.links[1], chain.links[2] = chain.links[2], chain.links[1]
    v = chain.verify()
    assert v["ok"] is False  # indices and prev-links no longer line up


def test_delete_link_breaks_chain():
    chain = _build_chain(4)
    del chain.links[2]  # removing a middle link breaks index + linkage
    v = chain.verify()
    assert v["ok"] is False


def test_roundtrip_json_preserves_and_verifies():
    chain = _build_chain(4)
    text = chain.to_json()
    loaded = ReceiptChain.from_json(text)
    assert loaded.verify()["ok"] is True
    assert loaded.head == chain.head
    assert len(loaded.links) == len(chain.links)


def test_loaded_tampered_json_fails():
    chain = _build_chain(3)
    loaded = ReceiptChain.from_json(chain.to_json())
    loaded.links[0].step["route_score"] = 999.0
    assert loaded.verify()["ok"] is False


def test_claim_tier_is_honest():
    chain = _build_chain(2)
    v = chain.verify()
    assert "NOT a locked theorem" in v["claim_tier"]
    assert "integrity" in v["claim_tier"]
    # never claims correctness or "proven"
    assert "proven" not in v["claim_tier"].lower()


def test_digest_recompute_matches():
    payload = {"observation": [1.0, 0.0], "decision": "ALLOW"}
    d = ChainLink.compute_digest(0, GENESIS_PREV, payload)
    link = ChainLink(index=0, prev_digest=GENESIS_PREV, step=payload, digest=d)
    assert link.recompute() == d
    assert len(d) == 64
