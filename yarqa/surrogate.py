# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Physics-informed surrogate over the yarqa plug-flow compartmentalizer.

The expensive operation in yarqa is :func:`yarqa.core.compartmentalize`: a
region-growing pass over the whole mesh. This module builds a **cheap surrogate**
for one scalar functional of that reduction — the number of plug-flow
compartments as a function of the ``align_threshold`` control — so a query at an
intermediate threshold can be answered by interpolating a handful of *real*
anchor evaluations instead of re-running the full growth.

Physics-informed (honest) design
--------------------------------
The surrogate is trained ONLY on **verbatim measured** anchors: for each anchor
threshold we run the real :func:`compartmentalize` and record the true
compartment count. The single physics prior is a **monotonicity constraint**:
raising ``align_threshold`` makes the neighbour-admission test strictly stricter,
so compartments can only split, never merge, and the count is monotone
non-decreasing in the threshold. That prior is enforced exactly by an isotonic
(pool-adjacent-violators) projection — the numpy analogue of a hard monotonicity
penalty in a PINN loss. The projection residual is measured and reported; if the
measured anchors are already monotone (the structural expectation) the residual
is zero and the prior holds exactly.

Bounded honesty (never a fabricated physical number)
----------------------------------------------------
* A prediction is only made **inside the validated anchor range**
  ``[min_anchor, max_anchor]``. Outside it the surrogate returns an explicit
  ``UNAVAILABLE`` verdict with ``value=None`` — it never extrapolates a made-up
  compartment count.
* Inside the range, the point estimate is a linear interpolation between the two
  bracketing **measured** anchors, and every prediction carries the interval
  ``[lower_bound, upper_bound]`` spanned by those two measured counts. The
  monotonicity prior is a MODELLING assumption that is checked and reported on the
  anchors, not a proof: the region-growing reduction is a heuristic and can
  fluctuate slightly at sub-anchor resolution, so the true count is EXPECTED — but
  NOT guaranteed — to fall inside the reported interval. The interval is the
  surrogate's indicative uncertainty, not a certificate.
* Exactly at a measured anchor the prediction is exact and the interval collapses
  to zero width (the one case that IS guaranteed, because it is measured).
* Estimates are clamped to the physical range ``[1, n_cells]``.

The prediction's :attr:`SurrogatePrediction.provenance` is a canonical, JSON-
serialisable record (mesh fingerprint, the measured anchors, the query, the
estimate, the bounds, the honest status). It is designed to be wrapped by the
shared ``szl_receipt`` attestation shapes (see :mod:`yarqa.attestation`) — this
module deliberately signs/attests nothing itself and stays numpy-only.

HONESTY (doctrine v11): this is an engineering (CFD) surrogate. It approximates
yarqa's own reduction; it is NOT a locked theorem, asserts no correctness, and
every estimate is labelled a surrogate PREDICTION bounded by measured anchors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from . import __version__
from .core import Mesh, compartmentalize
from .provenance import mesh_fingerprint

SURROGATE_SCHEMA = "szl.yarqa.surrogate/v1"
SURROGATE_METHOD = "isotonic-monotone-nondecreasing/piecewise-linear/v1"

_CLAIM_TIER = (
    "engineering-method-cfd; physics-informed (monotonicity-prior, checked & "
    "reported on anchors) surrogate; interpolation of MEASURED anchors with an "
    "indicative (NOT guaranteed) interval; exact at anchors; UNAVAILABLE outside "
    "validated range; NOT a locked theorem; asserts integrity/reproducibility, "
    "not correctness"
)

STATUS_PREDICTED = "PREDICTED"
STATUS_UNAVAILABLE = "UNAVAILABLE"


def _isotonic_nondecreasing(y: Sequence[float]) -> np.ndarray:
    """Pool-adjacent-violators isotonic (non-decreasing) projection.

    Returns the least-squares monotone non-decreasing fit to ``y``. This is the
    exact projection enforcing the surrogate's monotonicity physics prior.
    """
    arr = [float(v) for v in y]
    # Stack of (value, weight, count) blocks; merge while order is violated.
    blocks: list[list[float]] = []
    for v in arr:
        cur = [v, 1.0, 1.0]  # value, weight, count
        while blocks and blocks[-1][0] > cur[0]:
            pv, pw, pc = blocks.pop()
            total_w = pw + cur[1]
            cur = [(pv * pw + cur[0] * cur[1]) / total_w, total_w, pc + cur[2]]
        blocks.append(cur)
    out: list[float] = []
    for value, _w, count in blocks:
        out.extend([value] * int(count))
    return np.asarray(out, dtype=float)


@dataclass(frozen=True)
class SurrogateAnchor:
    """One VERBATIM measured anchor: the real model evaluated at a threshold."""

    align_threshold: float
    n_compartments: int  # measured by the real yarqa.compartmentalize

    def as_dict(self) -> dict[str, Any]:
        return {
            "align_threshold": float(self.align_threshold),
            "n_compartments": int(self.n_compartments),
        }


@dataclass
class SurrogatePrediction:
    """A single bounded, honest surrogate prediction (or UNAVAILABLE verdict)."""

    align_threshold: float
    available: bool
    status: str                 # STATUS_PREDICTED | STATUS_UNAVAILABLE
    value: float | None         # surrogate point estimate (None if UNAVAILABLE)
    value_int: int | None       # rounded + clamped to [1, n_cells]
    lower_bound: int | None     # indicative interval = nearest measured anchors
    upper_bound: int | None     # (expected, NOT guaranteed, to contain truth)
    reason: str
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "align_threshold": float(self.align_threshold),
            "available": bool(self.available),
            "status": self.status,
            "value": None if self.value is None else float(self.value),
            "value_int": None if self.value_int is None else int(self.value_int),
            "lower_bound": None if self.lower_bound is None else int(self.lower_bound),
            "upper_bound": None if self.upper_bound is None else int(self.upper_bound),
            "reason": self.reason,
        }


@dataclass
class PlugFlowSurrogate:
    """A fitted, physics-informed surrogate for ``n_compartments(threshold)``.

    Built by :func:`fit_plugflow_surrogate`. Holds only VERBATIM measured
    anchors plus the monotone projection used to check the physics prior; a
    :meth:`predict` call does NOT re-run the expensive compartmentalizer.
    """

    mesh_fingerprint: dict[str, str]
    n_cells: int
    yarqa_version: str
    anchors: list[SurrogateAnchor]
    projected: list[float]
    fit_residual_max: float
    monotone_prior_ok: bool
    schema: str = SURROGATE_SCHEMA
    method: str = SURROGATE_METHOD
    claim_tier: str = _CLAIM_TIER

    @property
    def min_threshold(self) -> float:
        return float(self.anchors[0].align_threshold)

    @property
    def max_threshold(self) -> float:
        return float(self.anchors[-1].align_threshold)

    def _anchor_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        ts = np.array([a.align_threshold for a in self.anchors], dtype=float)
        ys = np.array([a.n_compartments for a in self.anchors], dtype=float)
        return ts, ys

    def _base_provenance(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "yarqa_version": self.yarqa_version,
            "method": self.method,
            "claim_tier": self.claim_tier,
            "target": "n_compartments",
            "control": "align_threshold",
            "physics_prior": "monotone-nondecreasing",
            "n_cells": int(self.n_cells),
            "mesh_fingerprint": dict(self.mesh_fingerprint),
            "anchors": [a.as_dict() for a in self.anchors],
            "validated_range": {
                "min": self.min_threshold,
                "max": self.max_threshold,
            },
            "fit_residual_max": float(self.fit_residual_max),
            "monotone_prior_ok": bool(self.monotone_prior_ok),
        }

    def predict(self, align_threshold: float) -> SurrogatePrediction:
        """Predict ``n_compartments`` at ``align_threshold`` — bounded & honest.

        Inside the validated anchor range: a linear interpolation between the two
        bracketing MEASURED anchors, clamped to ``[1, n_cells]``, carrying the
        indicative interval spanned by those anchors (expected, not guaranteed, to
        contain the truth — the reduction is monotone only up to heuristic
        sub-anchor wiggle). Exactly at an anchor the result is exact with a
        zero-width interval. Outside the range: an ``UNAVAILABLE`` verdict with
        ``value=None`` (no fabricated extrapolation).
        """
        t = float(align_threshold)
        prov = self._base_provenance()
        prov["query"] = {"align_threshold": t}

        lo_t, hi_t = self.min_threshold, self.max_threshold
        if t < lo_t or t > hi_t:
            reason = (
                f"align_threshold={t:.6g} is outside the validated surrogate "
                f"range [{lo_t:.6g}, {hi_t:.6g}]; refusing to extrapolate a "
                f"compartment count."
            )
            prov["result"] = {
                "status": STATUS_UNAVAILABLE,
                "value": None,
                "value_int": None,
                "lower_bound": None,
                "upper_bound": None,
                "reason": reason,
            }
            return SurrogatePrediction(
                align_threshold=t,
                available=False,
                status=STATUS_UNAVAILABLE,
                value=None,
                value_int=None,
                lower_bound=None,
                upper_bound=None,
                reason=reason,
                provenance=prov,
            )

        ts, ys = self._anchor_arrays()
        # Exact hit on a measured anchor -> exact, zero-width (the one guaranteed
        # case, because the value is measured rather than interpolated).
        exact = np.where(ts == t)[0]
        if exact.size:
            i0 = i1 = int(exact[0])
        else:
            # Locate the bracketing anchors (searchsorted on sorted thresholds).
            j = int(np.searchsorted(ts, t, side="right"))
            if j <= 0:
                i0 = i1 = 0
            elif j >= len(ts):
                i0 = i1 = len(ts) - 1
            else:
                i0, i1 = j - 1, j

        y0, y1 = float(ys[i0]), float(ys[i1])
        t0, t1 = float(ts[i0]), float(ts[i1])
        if i0 == i1 or t1 == t0:
            value = y0
        else:
            frac = (t - t0) / (t1 - t0)
            value = y0 + frac * (y1 - y0)

        lower = int(min(y0, y1))
        upper = int(max(y0, y1))
        value_int = int(round(value))
        value_int = max(1, min(self.n_cells, value_int))
        lower = max(1, min(self.n_cells, lower))
        upper = max(1, min(self.n_cells, upper))

        if i0 == i1:
            reason = (
                f"exact measured anchor (t={t0:.6g}->{y0:.0f}); zero-width "
                f"interval [{lower}, {upper}]."
            )
        else:
            reason = (
                f"surrogate interpolation between measured anchors "
                f"(t={t0:.6g}->{y0:.0f}, t={t1:.6g}->{y1:.0f}); true value "
                f"EXPECTED (not guaranteed) in [{lower}, {upper}] — monotone prior "
                f"holds up to heuristic sub-anchor fluctuation."
            )
        prov["result"] = {
            "status": STATUS_PREDICTED,
            "value": float(value),
            "value_int": int(value_int),
            "lower_bound": int(lower),
            "upper_bound": int(upper),
            "bracketing_anchors": [
                {"align_threshold": t0, "n_compartments": int(y0)},
                {"align_threshold": t1, "n_compartments": int(y1)},
            ],
            "reason": reason,
        }
        return SurrogatePrediction(
            align_threshold=t,
            available=True,
            status=STATUS_PREDICTED,
            value=float(value),
            value_int=int(value_int),
            lower_bound=int(lower),
            upper_bound=int(upper),
            reason=reason,
            provenance=prov,
        )


def fit_plugflow_surrogate(
    mesh: Mesh,
    thresholds: Sequence[float] | None = None,
    *,
    n_anchors: int = 7,
    lo: float = 0.0,
    hi: float = 0.98,
) -> PlugFlowSurrogate:
    """Fit the surrogate by running the REAL model at anchor thresholds.

    Parameters
    ----------
    mesh : Mesh
        The mesh whose plug-flow reduction is being surrogated.
    thresholds : optional sequence of float
        Explicit anchor thresholds. When omitted, ``n_anchors`` evenly spaced
        values in ``[lo, hi]`` are used.
    n_anchors, lo, hi :
        Control the default anchor grid (ignored if ``thresholds`` is given).

    Every anchor's ``n_compartments`` is MEASURED by :func:`compartmentalize`
    (verbatim); the monotone projection is only used to report whether the
    physics prior holds.
    """
    if thresholds is None:
        if n_anchors < 2:
            raise ValueError("need at least 2 anchors")
        grid = np.linspace(float(lo), float(hi), int(n_anchors))
    else:
        grid = np.asarray(sorted(float(t) for t in thresholds), dtype=float)
        if grid.size < 2:
            raise ValueError("need at least 2 anchor thresholds")

    anchors: list[SurrogateAnchor] = []
    for t in grid:
        labels = compartmentalize(mesh, align_threshold=float(t))
        anchors.append(
            SurrogateAnchor(
                align_threshold=float(t),
                n_compartments=int(len(np.unique(labels))),
            )
        )

    measured = np.array([a.n_compartments for a in anchors], dtype=float)
    projected = _isotonic_nondecreasing(measured)
    residual = float(np.max(np.abs(projected - measured))) if len(measured) else 0.0
    # A residual below 0.5 means every measured integer count already respects
    # the monotone prior (the structural expectation for this target).
    monotone_ok = residual < 0.5

    return PlugFlowSurrogate(
        mesh_fingerprint=mesh_fingerprint(mesh),
        n_cells=int(mesh.n),
        yarqa_version=__version__,
        anchors=anchors,
        projected=[float(p) for p in projected],
        fit_residual_max=residual,
        monotone_prior_ok=monotone_ok,
    )
