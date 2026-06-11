# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Agentic yarqa — a governed sense -> compartmentalize -> route -> act loop.

This is an *original* SZL design that applies two studied ideas to yarqa, our
own implementation, no third-party code:

  1. Mixture-of-Experts (MoE) routing — the published idea that a router sends
     each input to the most appropriate "expert". Here the routing is physical
     and honest: yarqa's flow **compartments are the experts**, and each new
     observation is routed to the compartment whose mean flow it best matches.
     (Concept: Jacobs et al. 1991 "Adaptive Mixtures of Local Experts";
     Shazeer et al. 2017 sparsely-gated MoE. Cited as inspiration only.)

  2. SZL's own governed loop — every agentic step leaves a signed, replayable
     receipt and passes a two-key gate, mirroring the platform's P1 (receipt
     completeness), P2 (gate soundness), and P4 (replay determinism). We do NOT
     re-prove those theorems here; we *conform to their shape* at the
     application layer and label maturity honestly.

HONESTY: this is an engineering agent loop, NOT a locked theorem and NOT a proof
of the P1-P6 properties (those live in lutar-lean, experimental tier). The agent
emits integrity receipts (see yarqa.provenance); it does not assert correctness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .core import Mesh, compartmentalize, compartment_summary
from .provenance import compartmentalize_with_receipt, Receipt


@dataclass
class Expert:
    """A flow compartment acting as a routing target ('expert')."""

    compartment_id: int
    mean_velocity: np.ndarray
    centroid: np.ndarray
    n_cells: int


def build_experts(mesh: Mesh, labels: np.ndarray) -> list[Expert]:
    """Turn compartments into routable experts (MoE-style, but physical)."""
    experts: list[Expert] = []
    for c in np.unique(labels):
        mask = labels == c
        experts.append(
            Expert(
                compartment_id=int(c),
                mean_velocity=mesh.velocities[mask].mean(axis=0),
                centroid=mesh.centers[mask].mean(axis=0),
                n_cells=int(mask.sum()),
            )
        )
    return experts


def route(observation_velocity: np.ndarray, experts: list[Expert]) -> tuple[int, float]:
    """Route an observation to the best-matching compartment ('expert').

    Gating score = cosine alignment of the observation's flow with each
    compartment's mean flow. Returns (compartment_id, score). Transparent and
    deterministic — no learned black-box gate.
    """
    o = observation_velocity
    on = np.linalg.norm(o)
    best_id, best_score = -1, -np.inf
    for e in experts:
        en = np.linalg.norm(e.mean_velocity)
        if on < 1e-12 or en < 1e-12:
            score = 0.0
        else:
            score = float(np.dot(o, e.mean_velocity) / (on * en))
        if score > best_score:
            best_id, best_score = e.compartment_id, score
    return best_id, best_score


# A "gate" returns ALLOW (True) / DENY (False). The default is permissive; the
# platform plugs in its real policy + kernel/doctrine gate here (P2 shape:
# allow only if BOTH return ALLOW).
GateFn = Callable[[dict], bool]


def _default_policy_gate(ctx: dict) -> bool:
    # Honest default: require a routing confidence floor; deny low-confidence.
    return bool(ctx.get("route_score", 0.0) >= ctx.get("min_route_score", 0.0))


def _default_doctrine_gate(ctx: dict) -> bool:
    # Honest default: never act on an empty/zero observation (no fabricated act).
    return bool(np.linalg.norm(ctx.get("observation", np.zeros(1))) > 0.0)


@dataclass
class AgentStep:
    """One governed step's record — the application-layer receipt envelope."""

    observation: list[float]
    routed_compartment: int
    route_score: float
    decision: str                      # "ALLOW" | "DENY"
    yarqa_receipt_digest: str          # ties to the cryptographic provenance receipt
    notes: str = ""


@dataclass
class AgenticYarqa:
    """Governed agent: sense flow -> compartmentalize -> route -> gated act.

    Conforms to the SHAPE of P1 (one receipt per step), P2 (two-key gate), and
    P4 (deterministic replay), at the engineering layer. Maturity of the
    underlying P-properties is unchanged and lives in lutar-lean (experimental;
    P5 axiom-gated).
    """

    mesh: Mesh
    align_threshold: float = 0.0
    policy_gate: GateFn = _default_policy_gate
    doctrine_gate: GateFn = _default_doctrine_gate
    min_route_score: float = 0.0

    experts: list[Expert] = field(init=False, default_factory=list)
    base_receipt: Receipt | None = field(init=False, default=None)
    log: list[AgentStep] = field(init=False, default_factory=list)

    def sense(self) -> None:
        """Compartmentalize the current field and build experts + base receipt."""
        labels, receipt = compartmentalize_with_receipt(
            self.mesh, align_threshold=self.align_threshold
        )
        self.experts = build_experts(self.mesh, labels)
        self.base_receipt = receipt

    def step(self, observation_velocity: np.ndarray) -> AgentStep:
        """Route one observation through the gated loop, recording a receipt."""
        if not self.experts:
            self.sense()
        obs = np.asarray(observation_velocity, dtype=float)
        cid, score = route(obs, self.experts)
        ctx = {
            "observation": obs,
            "route_score": score,
            "min_route_score": self.min_route_score,
        }
        # P2 shape: ALLOW only if BOTH gates allow; a single DENY is absorbing.
        allow = bool(self.policy_gate(ctx) and self.doctrine_gate(ctx))
        step = AgentStep(
            observation=obs.tolist(),
            routed_compartment=cid,
            route_score=score,
            decision="ALLOW" if allow else "DENY",
            yarqa_receipt_digest=self.base_receipt.receipt_digest()
            if self.base_receipt
            else "",
            notes="MoE-style flow routing; integrity receipt, not a proof.",
        )
        self.log.append(step)  # P1 shape: exactly one record per step, append-only
        return step

    def replay(self, observations: list[np.ndarray]) -> list[AgentStep]:
        """Deterministic replay (P4 shape): same field + same obs -> same log."""
        fresh = AgenticYarqa(
            self.mesh,
            align_threshold=self.align_threshold,
            policy_gate=self.policy_gate,
            doctrine_gate=self.doctrine_gate,
            min_route_score=self.min_route_score,
        )
        fresh.sense()
        return [fresh.step(o) for o in observations]
