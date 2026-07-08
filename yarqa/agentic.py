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


def _cosine_scores(observation_velocity: np.ndarray, experts: list[Expert]) -> np.ndarray:
    """Cosine alignment of the observation with every expert's mean flow.

    Returns a (len(experts),) array of scores in [-1, 1]. A score of 0.0 is
    used whenever either vector is (numerically) zero **or non-finite**
    (containing NaN / +-Inf), so the gate stays honest about "no information"
    rather than fabricating an alignment. Failing closed on non-finite inputs
    also keeps a NaN from leaking into ``argmax`` / softmax and silently
    corrupting the route (and its gate decision) downstream.
    """
    o = np.asarray(observation_velocity, dtype=float)
    on = float(np.linalg.norm(o))
    o_finite = bool(np.all(np.isfinite(o)))
    scores = np.zeros(len(experts), dtype=float)
    for i, e in enumerate(experts):
        m = np.asarray(e.mean_velocity, dtype=float)
        en = float(np.linalg.norm(m))
        if not o_finite or not np.all(np.isfinite(m)) or on < 1e-12 or en < 1e-12:
            scores[i] = 0.0
        else:
            scores[i] = float(np.dot(o, m) / (on * en))
    return scores


def route(observation_velocity: np.ndarray, experts: list[Expert]) -> tuple[int, float]:
    """Route an observation to the best-matching compartment ('expert').

    Gating score = cosine alignment of the observation's flow with each
    compartment's mean flow. Returns (compartment_id, score). Transparent and
    deterministic — no learned black-box gate. This is the original argmax
    router and remains the default; see :func:`route_topk` for the additive
    sparse top-k variant.
    """
    if not experts:
        return -1, -np.inf
    scores = _cosine_scores(observation_velocity, experts)
    # Deterministic tie-break: lowest index (and thus typically lowest
    # compartment_id, which is built in sorted order) wins on equal scores.
    best = int(np.argmax(scores))
    return experts[best].compartment_id, float(scores[best])


def _softmax(x: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """Numerically stable softmax over a 1-D score vector.

    Standard max-shift trick for stability. ``temperature`` > 0 sharpens (<1)
    or flattens (>1) the distribution; it must be strictly positive.
    """
    if temperature <= 0.0:
        raise ValueError("temperature must be > 0")
    z = np.asarray(x, dtype=float) / float(temperature)
    z = z - np.max(z)
    e = np.exp(z)
    s = float(e.sum())
    if s <= 0.0:  # pragma: no cover - defensive; exp() keeps this positive
        return np.full_like(e, 1.0 / len(e))
    return e / s


@dataclass
class RouteTopK:
    """Result of a sparse top-k route.

    Attributes
    ----------
    compartment_ids : list[int]
        The k chosen experts' compartment ids, ordered best-first.
    weights : list[float]
        Softmax gating weights over the chosen experts (sum to 1.0).
    scores : list[float]
        Raw cosine scores of the chosen experts (parallel to ``compartment_ids``).
    """

    compartment_ids: list[int]
    weights: list[float]
    scores: list[float]

    @property
    def top1(self) -> int:
        """The single best compartment id (matches :func:`route`'s argmax)."""
        return self.compartment_ids[0] if self.compartment_ids else -1


def route_topk(
    observation_velocity: np.ndarray,
    experts: list[Expert],
    *,
    k: int = 2,
    temperature: float = 1.0,
) -> RouteTopK:
    """Sparse top-k routing with softmax gating weights over cosine scores.

    Instead of committing all weight to a single expert (argmax), this selects
    the ``k`` best-aligned compartments and assigns each a normalized softmax
    weight computed over the SELECTED experts' cosine scores. The top-1
    compartment always matches :func:`route`, so this is a strict additive
    generalization (k=1 reproduces the argmax router with weight 1.0).

    Concept inspiration only: the *sparsely-gated mixture-of-experts* idea of
    routing each input to its top-k experts with normalized gate weights
    (Shazeer et al., 2017, "Outrageously Large Neural Networks: The
    Sparsely-Gated Mixture-of-Experts Layer"). We borrow the IDEA of top-k
    sparse gating only; all code here is original SZL work and the "experts"
    are physical flow compartments, not learned networks.

    Parameters
    ----------
    k : int
        Number of experts to route to. Clamped to ``[1, len(experts)]``.
    temperature : float
        Softmax temperature (> 0). Lower sharpens toward the top expert.

    Returns
    -------
    RouteTopK
        Chosen compartment ids (best-first), their softmax weights (sum 1.0),
        and their raw cosine scores. Deterministic for a given input.
    """
    if not experts:
        return RouteTopK(compartment_ids=[], weights=[], scores=[])
    if k < 1:
        raise ValueError("k must be >= 1")
    k = min(k, len(experts))
    scores = _cosine_scores(observation_velocity, experts)
    # Select the k highest scores. argsort is ascending, so take the tail and
    # reverse; a stable sort on (-score, index) gives a deterministic order
    # with lowest index winning ties.
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    chosen = order[:k]
    chosen_scores = np.array([scores[i] for i in chosen], dtype=float)
    weights = _softmax(chosen_scores, temperature=temperature)
    return RouteTopK(
        compartment_ids=[experts[i].compartment_id for i in chosen],
        weights=[float(w) for w in weights],
        scores=[float(s) for s in chosen_scores],
    )


# A "gate" returns ALLOW (True) / DENY (False). The default is permissive; the
# platform plugs in its real policy + kernel/doctrine gate here (P2 shape:
# allow only if BOTH return ALLOW).
GateFn = Callable[[dict], bool]


def _default_policy_gate(ctx: dict) -> bool:
    # Honest default: require a routing confidence floor; deny low-confidence.
    return bool(ctx.get("route_score", 0.0) >= ctx.get("min_route_score", 0.0))


def _default_doctrine_gate(ctx: dict) -> bool:
    # Honest default: only act on a real, finite, non-zero observation. A
    # non-finite (NaN / +-Inf) or empty/zero observation is not an actionable
    # measurement, so the gate fails closed (DENY). Note +Inf has a positive
    # norm, so the finiteness check is what actually blocks it.
    obs = np.asarray(ctx.get("observation", np.zeros(1)), dtype=float)
    return bool(np.all(np.isfinite(obs)) and np.linalg.norm(obs) > 0.0)


@dataclass
class AgentStep:
    """One governed step's record — the application-layer receipt envelope."""

    observation: list[float]
    routed_compartment: int
    route_score: float
    decision: str                      # "ALLOW" | "DENY"
    yarqa_receipt_digest: str          # ties to the cryptographic provenance receipt
    notes: str = ""
    # Optional sparse top-k routing detail. These default to empty so that the
    # original argmax path produces byte-identical AgentStep records; they are
    # only populated when the agent runs in route_mode="topk".
    route_mode: str = "argmax"
    topk_compartments: list[int] = field(default_factory=list)
    topk_weights: list[float] = field(default_factory=list)


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
    # Routing mode is additive: "argmax" (default, unchanged behavior) or
    # "topk" (sparse softmax-gated routing over the k best compartments). In
    # topk mode the gated decision still uses the TOP-1 score, so gate/replay
    # semantics are preserved; the extra experts/weights are recorded for
    # downstream weighted aggregation.
    route_mode: str = "argmax"
    route_k: int = 2
    route_temperature: float = 1.0

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
        topk_ids: list[int] = []
        topk_weights: list[float] = []
        if self.route_mode == "topk":
            rk = route_topk(
                obs, self.experts, k=self.route_k, temperature=self.route_temperature
            )
            # Top-1 drives the gate/score so gate + replay semantics are exactly
            # those of the argmax router; the rest is recorded as routing detail.
            cid = rk.top1
            score = rk.scores[0] if rk.scores else -np.inf
            topk_ids = rk.compartment_ids
            topk_weights = rk.weights
            note = (
                f"sparse top-{len(topk_ids)} MoE-style flow routing (softmax "
                "gating); integrity receipt, not a proof."
            )
        else:
            cid, score = route(obs, self.experts)
            note = "MoE-style flow routing; integrity receipt, not a proof."
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
            notes=note,
            route_mode=self.route_mode,
            topk_compartments=topk_ids,
            topk_weights=topk_weights,
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
            route_mode=self.route_mode,
            route_k=self.route_k,
            route_temperature=self.route_temperature,
        )
        fresh.sense()
        return [fresh.step(o) for o in observations]
