# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Signed PCGI receipt tests for the yarqa surrogate (T201, spine propagation).

Every surrogate prediction must be able to emit ONE signed szl-receipt that
binds the canonical PCGI tuple — model id + input digest + output digest +
governing policy id + energy (honest UNAVAILABLE) — via the SHARED
``szl_receipt`` DSSE/ECDSA-P256 signer. Nothing is re-implemented here; these
tests skip (never fake) when the optional library is absent.
"""
import base64
import copy
import json

import numpy as np
import pytest

szl_receipt = pytest.importorskip("szl_receipt")

from yarqa import (  # noqa: E402
    Mesh,
    fit_plugflow_surrogate,
    emit_prediction_receipt,
    verify_prediction_receipt,
    build_prediction_receipt_body,
    prediction_receipt_body_digest,
    prediction_input_digest,
    prediction_output_digest,
    DEFAULT_POLICY_ID,
    ENERGY_UNAVAILABLE,
    MODEL_ID,
    PCGI_RECEIPT_SCHEMA,
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


def _decode_body(envelope):
    return json.loads(base64.b64decode(envelope["payload"]).decode("utf-8"))


def test_signed_receipt_verifies_with_public_key():
    priv, pub = szl_receipt.generate_keypair()
    surr = _fit()
    p = surr.predict(0.33)
    env = emit_prediction_receipt(p, private_key_pem=priv, keyid="yarqa-ci")
    assert env["signed"] is True
    assert env["algo"] == "ECDSA-P256-SHA256"
    ok, detail = szl_receipt.verify_receipt(env, public_key_pem=pub)
    assert ok is True and detail == "ok"
    # And the yarqa convenience verifier rebinds it to the held prediction.
    ok2, detail2 = verify_prediction_receipt(env, public_key_pem=pub, prediction=p)
    assert ok2 is True and detail2 == "ok"


def test_receipt_binds_input_and_output_digests():
    surr = _fit()
    p = surr.predict(0.5)
    env = emit_prediction_receipt(p)  # unsigned-honest is fine for body inspection
    body = _decode_body(env)
    # The signed body binds exactly the independently re-derived digests.
    assert body["input_digest"] == prediction_input_digest(p)
    assert body["output_digest"] == prediction_output_digest(p)
    assert body["input_digest"] != body["output_digest"]
    assert len(body["input_digest"]) == 64
    assert len(body["output_digest"]) == 64
    # Model id + schema + policy id are bound on the spine.
    assert body["model_id"] == MODEL_ID
    assert body["schema"] == PCGI_RECEIPT_SCHEMA
    assert body["policy_id"] == DEFAULT_POLICY_ID


def test_energy_is_honest_unavailable():
    surr = _fit()
    p = surr.predict(0.42)
    body = _decode_body(emit_prediction_receipt(p))
    assert body["energy"]["status"] == ENERGY_UNAVAILABLE
    # No fabricated joule value — measured energy is honestly absent.
    assert body["energy"]["joules"] is None


def test_receipt_is_evidence_not_a_correctness_proof():
    surr = _fit()
    p = surr.predict(0.42)
    body = _decode_body(emit_prediction_receipt(p))
    honesty = body["honesty"]
    assert honesty["extrapolates"] is False
    assert honesty["bounded"] is True
    assert "NOT correctness" in honesty["asserts"]
    assert "NOT a proof" in honesty["receipt_is"]


def test_custom_policy_id_is_bound():
    surr = _fit()
    p = surr.predict(0.33)
    policy = "szl.pcgi.policy/custom-test/v9"
    body = _decode_body(emit_prediction_receipt(p, policy_id=policy))
    assert body["policy_id"] == policy


def test_receipt_body_is_deterministic():
    surr = _fit()
    p = surr.predict(0.33)
    b1 = build_prediction_receipt_body(p)
    b2 = build_prediction_receipt_body(p)
    # Byte-identical canonical JSON (no timestamps / nonces) -> stable digest.
    from szl_receipt._canonical import canonical_json

    assert canonical_json(b1) == canonical_json(b2)
    assert prediction_receipt_body_digest(p) == prediction_receipt_body_digest(p)


def test_tampered_payload_fails_signature():
    priv, pub = szl_receipt.generate_keypair()
    surr = _fit()
    p = surr.predict(0.42)
    env = emit_prediction_receipt(p, private_key_pem=priv)
    tampered = copy.deepcopy(env)
    body = _decode_body(env)
    body["output_digest"] = "0" * 64  # forge the bound output digest
    tampered["payload"] = base64.b64encode(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    ok, detail = szl_receipt.verify_receipt(tampered, public_key_pem=pub)
    assert ok is False
    assert detail != "ok"


def test_tampered_prediction_fails_rebind():
    priv, pub = szl_receipt.generate_keypair()
    surr = _fit()
    p = surr.predict(0.42)
    env = emit_prediction_receipt(p, private_key_pem=priv)
    # Signature still validates, but the digest no longer rebinds the edited
    # prediction, so the yarqa rebind check catches the mismatch.
    tampered = copy.deepcopy(p)
    tampered.provenance["result"]["value_int"] = 9999
    ok, detail = verify_prediction_receipt(env, public_key_pem=pub, prediction=tampered)
    assert ok is False
    assert detail == "output-digest-rebind-mismatch"


def test_unsigned_honest_when_no_key():
    surr = _fit()
    p = surr.predict(0.33)
    env = emit_prediction_receipt(p, private_key_pem=None)
    # No key present -> UNSIGNED-honest, never a fabricated signature.
    assert env["signed"] is False
    assert env["signature"] == ""
    ok, detail = verify_prediction_receipt(env)
    assert ok is False
    assert detail == "unsigned-honest"


def test_out_of_range_prediction_still_emits_honest_receipt():
    priv, pub = szl_receipt.generate_keypair()
    surr = _fit()
    p = surr.predict(1.5)  # outside validated range -> UNAVAILABLE
    assert p.available is False and p.value is None
    env = emit_prediction_receipt(p, private_key_pem=priv)
    ok, detail = verify_prediction_receipt(env, public_key_pem=pub, prediction=p)
    assert ok is True and detail == "ok"
    body = _decode_body(env)
    # The receipt honestly records the UNAVAILABLE verdict with no number, and
    # energy stays UNAVAILABLE — nothing is fabricated for a declined query.
    assert body["prediction"]["status"] == "UNAVAILABLE"
    assert body["prediction"]["value_int"] is None
    assert body["energy"]["status"] == ENERGY_UNAVAILABLE
    # A distinct query digests to a distinct receipt (bindings are query-specific).
    other = surr.predict(0.33)
    assert prediction_output_digest(p) != prediction_output_digest(other)
