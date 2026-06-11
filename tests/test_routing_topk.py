# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Tests for additive top-k softmax routing (yarqa.agentic.route_topk).

Concept inspiration only: sparsely-gated top-k MoE (Shazeer et al., 2017). All
code under test is original SZL work; experts here are physical compartments.
"""
import numpy as np

from yarqa import Mesh
from yarqa.agentic import (
    AgenticYarqa,
    Expert,
    build_experts,
    route,
    route_topk,
    _softmax,
)


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
    return [1.0, 0.0] if c[0] < 5 else [0.0, 1.0]


def _make_experts():
    # Three hand-built experts pointing +x, +y, and -x.
    return [
        Expert(0, np.array([1.0, 0.0]), np.array([0.0, 0.0]), 4),
        Expert(1, np.array([0.0, 1.0]), np.array([1.0, 0.0]), 4),
        Expert(2, np.array([-1.0, 0.0]), np.array([2.0, 0.0]), 4),
    ]


def test_softmax_normalizes_and_orders():
    w = _softmax(np.array([2.0, 1.0, 0.0]))
    assert abs(float(w.sum()) - 1.0) < 1e-12
    assert w[0] > w[1] > w[2]  # higher score -> higher weight


def test_softmax_rejects_nonpositive_temperature():
    import pytest
    with pytest.raises(ValueError):
        _softmax(np.array([1.0, 2.0]), temperature=0.0)


def test_topk_k1_matches_argmax_route():
    experts = _make_experts()
    obs = np.array([0.9, 0.1])  # clearly +x dominant
    cid, score = route(obs, experts)
    rk = route_topk(obs, experts, k=1)
    assert rk.compartment_ids == [cid]
    assert abs(rk.weights[0] - 1.0) < 1e-12  # all weight on the single expert
    assert abs(rk.scores[0] - score) < 1e-12


def test_topk_selects_k_best_and_weights_sum_to_one():
    experts = _make_experts()
    obs = np.array([1.0, 0.0])
    rk = route_topk(obs, experts, k=2)
    assert len(rk.compartment_ids) == 2
    # +x expert (id 0) should be first; second-best is +y (id 1), not -x (id 2)
    assert rk.compartment_ids[0] == 0
    assert rk.compartment_ids[1] == 1
    assert abs(sum(rk.weights) - 1.0) < 1e-12
    # best expert carries the larger softmax weight
    assert rk.weights[0] >= rk.weights[1]


def test_topk_k_is_clamped_to_number_of_experts():
    experts = _make_experts()
    rk = route_topk(np.array([1.0, 0.0]), experts, k=99)
    assert len(rk.compartment_ids) == len(experts)
    assert abs(sum(rk.weights) - 1.0) < 1e-12


def test_topk_rejects_bad_k():
    import pytest
    with pytest.raises(ValueError):
        route_topk(np.array([1.0, 0.0]), _make_experts(), k=0)


def test_topk_temperature_sharpens_distribution():
    experts = _make_experts()
    obs = np.array([1.0, 0.2])
    cold = route_topk(obs, experts, k=3, temperature=0.1)
    hot = route_topk(obs, experts, k=3, temperature=5.0)
    # lower temperature concentrates weight on the top expert
    assert cold.weights[0] > hot.weights[0]


def test_topk_is_deterministic():
    experts = _make_experts()
    obs = np.array([0.7, 0.3])
    a = route_topk(obs, experts, k=2)
    b = route_topk(obs, experts, k=2)
    assert a.compartment_ids == b.compartment_ids
    assert a.weights == b.weights


def test_empty_experts_safe():
    rk = route_topk(np.array([1.0, 0.0]), [], k=2)
    assert rk.compartment_ids == [] and rk.weights == []
    assert rk.top1 == -1
    cid, score = route(np.array([1.0, 0.0]), [])
    assert cid == -1


def test_agent_topk_mode_records_detail_and_preserves_gate():
    mesh = _grid(10, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3, route_mode="topk", route_k=2)
    step = agent.step(np.array([1.0, 0.0]))
    assert step.route_mode == "topk"
    assert len(step.topk_compartments) == 2
    assert abs(sum(step.topk_weights) - 1.0) < 1e-12
    # top-1 still drives routed_compartment and the gate decision
    assert step.routed_compartment == step.topk_compartments[0]
    assert step.decision == "ALLOW"


def test_agent_argmax_default_unchanged():
    mesh = _grid(10, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3)
    step = agent.step(np.array([1.0, 0.0]))
    assert step.route_mode == "argmax"
    assert step.topk_compartments == []
    assert step.topk_weights == []


def test_agent_topk_deterministic_replay():
    mesh = _grid(10, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3, route_mode="topk", route_k=2)
    obs = [np.array([1.0, 0.0]), np.array([0.1, 1.0]), np.array([1.0, -0.2])]
    first = [
        (s.routed_compartment, s.decision, tuple(s.topk_compartments))
        for s in (agent.step(o) for o in obs)
    ]
    replayed = [
        (s.routed_compartment, s.decision, tuple(s.topk_compartments))
        for s in agent.replay(obs)
    ]
    assert first == replayed
