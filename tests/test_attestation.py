# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Receipt verify + rebind tests for the yarqa surrogate attestation adapter.

The adapter must DELEGATE to the shared szl_receipt (v0.2.0) shapes: an in-toto
v1 Statement bound to the receipt digest plus the compliance-evidence bundle.
These tests only run when szl_receipt is installed (the `attest` extra); they are
skipped — never faked — otherwise.
"""
import copy

import numpy as np
import pytest

szl_receipt = pytest.importorskip("szl_receipt")

from yarqa import (  # noqa: E402
    Mesh,
    fit_plugflow_surrogate,
    attest_prediction,
    verify_prediction_attestation,
    prediction_receipt,
    prediction_digest,
)


def _spread_grid(nx=14, ny=10, seed=7):
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
    rng = np.random.default_rng(seed)
    vel = rng.normal(size=(nx * ny, 2))
    return Mesh(centers, vel, neighbors)


def _fit():
    return fit_plugflow_surrogate(_spread_grid(), n_anchors=6, lo=0.0, hi=0.9)


def test_attestation_delegates_to_shared_shapes():
    surr = _fit()
    p = surr.predict(0.33)
    att = attest_prediction(p, builder_id="yarqa-ci")
    stmt = att["statement"]
    # The in-toto shape comes from szl_receipt, not re-implemented here.
    assert stmt["_type"] == szl_receipt.IN_TOTO_STATEMENT_TYPE
    assert stmt["predicateType"] == att["predicate_type"]
    # subject is the receipt, bound by its content digest
    subj = stmt["subject"][0]
    assert subj["digest"]["sha256"] == att["receipt_digest"]
    assert len(att["receipt_digest"]) == 64


def test_receipt_digest_matches_independent_derivation():
    surr = _fit()
    p = surr.predict(0.5)
    att = attest_prediction(p)
    # digest re-derived independently from the prediction equals the bound one.
    assert prediction_digest(p) == att["receipt_digest"]
    assert prediction_receipt(p).digest() == att["receipt_digest"]


def test_attestation_verifies_and_rebinds():
    surr = _fit()
    p = surr.predict(0.42)
    att = attest_prediction(p)
    ok, reason = verify_prediction_attestation(att, p)
    assert ok is True
    assert reason == "ok"


def test_tampered_prediction_breaks_rebind():
    surr = _fit()
    p = surr.predict(0.42)
    att = attest_prediction(p)
    # An adversary edits the prediction after the fact; the digest re-derived
    # from the tampered prediction no longer matches the bound subject.
    tampered = copy.deepcopy(p)
    tampered.provenance["result"]["value_int"] = 9999
    ok, reason = verify_prediction_attestation(att, tampered)
    assert ok is False
    assert reason != "ok"


def test_tampered_statement_predicate_type_fails():
    surr = _fit()
    p = surr.predict(0.42)
    att = attest_prediction(p)
    att["statement"] = copy.deepcopy(att["statement"])
    att["statement"]["predicateType"] = "https://evil.example/attest/v0"
    ok, _reason = verify_prediction_attestation(att, p)
    assert ok is False


def test_compliance_is_evidence_not_conformance():
    surr = _fit()
    p = surr.predict(0.33)
    att = attest_prediction(p)
    comp = att["compliance"]
    assert comp["subject_digest"] == att["receipt_digest"]
    # Machine-readable EVIDENCE, never a conformity assessment.
    assert "not a conformity assessment" in comp["disclaimer"].lower()
    # energy is UNAVAILABLE — yarqa measures no joules, nothing fabricated.
    assert comp["measured_energy"] is False
    by_kind = {c["id"]: c for c in comp["controls"]}
    energy = by_kind["NIST-AI-RMF-MEASURE-2.x"]
    assert energy["status"] == szl_receipt.attest.UNAVAILABLE
    # integrity/logging capabilities are honestly supported
    integ = by_kind["EU-AI-Act-Art-15"]
    assert integ["status"] == "supports"
    assert "Does NOT establish model accuracy" in integ["does_not_establish"]


def test_unavailable_prediction_is_attestable_and_honest():
    surr = _fit()
    p = surr.predict(1.5)  # out of validated range -> UNAVAILABLE
    assert p.available is False and p.value is None
    att = attest_prediction(p)
    ok, reason = verify_prediction_attestation(att, p)
    assert ok is True and reason == "ok"
    # The attested predicate records the honest UNAVAILABLE status + no number.
    # (SLSA v1 shape from szl_receipt; `extra` is merged at the top level.)
    pred = att["statement"]["predicate"]
    assert pred["buildDefinition"]["externalParameters"]["status"] == "UNAVAILABLE"
    assert pred["prediction"]["value_int"] is None
