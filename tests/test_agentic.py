# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Tests for yarqa.agentic — routing, two-key gate, deterministic replay."""
import numpy as np

from yarqa import Mesh
from yarqa.agentic import AgenticYarqa, build_experts, route


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


def test_sense_builds_experts():
    mesh = _grid(10, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3)
    agent.sense()
    assert len(agent.experts) >= 2
    assert agent.base_receipt is not None


def test_routing_picks_aligned_compartment():
    mesh = _grid(10, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3)
    agent.sense()
    # an observation flowing +x should route to an +x-dominant compartment
    cid, score = route(np.array([1.0, 0.0]), agent.experts)
    matched = [e for e in agent.experts if e.compartment_id == cid][0]
    assert matched.mean_velocity[0] >= abs(matched.mean_velocity[1])
    assert score > 0.5


def test_two_key_gate_denies_zero_observation():
    mesh = _grid(8, 6, _two_stream)
    agent = AgenticYarqa(mesh)
    step = agent.step(np.array([0.0, 0.0]))  # doctrine gate must DENY
    assert step.decision == "DENY"


def test_gate_allows_valid_observation():
    mesh = _grid(8, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3)
    step = agent.step(np.array([1.0, 0.0]))
    assert step.decision == "ALLOW"
    assert step.routed_compartment >= 0
    assert len(step.yarqa_receipt_digest) == 64  # tied to provenance receipt


def test_min_route_score_floor_denies_low_confidence():
    mesh = _grid(8, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3, min_route_score=0.99)
    # an orthogonal-ish observation scores low -> policy gate denies
    step = agent.step(np.array([0.2, 0.98]))
    # may route, but low alignment to the chosen expert should trip the floor
    if step.route_score < 0.99:
        assert step.decision == "DENY"


def test_one_receipt_per_step_appendonly():
    mesh = _grid(8, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3)
    obs = [np.array([1.0, 0.0]), np.array([0.0, 1.0]), np.array([1.0, 0.1])]
    for o in obs:
        agent.step(o)
    assert len(agent.log) == len(obs)  # P1 shape: exactly one record per step


def test_deterministic_replay():
    mesh = _grid(10, 6, _two_stream)
    agent = AgenticYarqa(mesh, align_threshold=0.3)
    obs = [np.array([1.0, 0.0]), np.array([0.1, 1.0]), np.array([1.0, -0.2])]
    first = [(s.routed_compartment, s.decision) for s in (agent.step(o) for o in obs)]
    replayed = [(s.routed_compartment, s.decision) for s in agent.replay(obs)]
    assert first == replayed  # P4 shape: byte-stable decisions on replay
