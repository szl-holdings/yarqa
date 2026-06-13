# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Offline self-tests for ``yarqa.signing``.

These exercise the envelope/statement shape, the honest refuse-without-OIDC
behaviour, and the reproducibility replay -- all WITHOUT minting a real
signature (no network, no OIDC). The genuine keyless-signing path is exercised
by the ``receipt-sign`` GitHub Actions workflow.
"""
import base64

import pytest

from yarqa import Receipt, compartmentalize_with_receipt, verify
from yarqa.meshio import sample_channel_mesh
from yarqa.signing import (
    DsseSigningUnavailable,
    YARQA_PAYLOAD_TYPE,
    placeholder_envelope,
    real_signing_available,
    sign_or_placeholder,
    sign_receipt_dsse,
)


def _receipt(nx=10, ny=6, seed=3):
    mesh = sample_channel_mesh(nx, ny, seed=seed)
    _, r = compartmentalize_with_receipt(mesh)
    return mesh, r


def test_placeholder_shape_and_payload_roundtrip():
    _, r = _receipt()
    canonical = r.to_canonical_json().encode("utf-8")
    replay = {"generator": "sample_channel_mesh", "nx": 10, "ny": 6, "seed": 3}
    env = placeholder_envelope(canonical, replay)

    assert env["_mode"] == "PLACEHOLDER"
    assert env["signatures"] == []
    assert "_sigstore" not in env
    assert env["_szl"]["dsse_payload_type"] == YARQA_PAYLOAD_TYPE
    assert env["_szl"]["receipt_sha256"] == r.receipt_digest()
    # the embedded payload reconstructs the exact receipt bytes
    assert base64.b64decode(env["_szl"]["payload_b64"]) == canonical


def test_sign_refuses_without_oidc(monkeypatch):
    # no ambient identity must NEVER fabricate a signature
    monkeypatch.delenv("SIGSTORE_IDENTITY_TOKEN", raising=False)
    monkeypatch.setattr("yarqa.signing._detect_oidc_token", lambda *a, **k: None)
    with pytest.raises(DsseSigningUnavailable):
        sign_receipt_dsse(b"{}", {"nx": 1, "ny": 1, "seed": 0})


def test_sign_or_placeholder_offline_is_placeholder(monkeypatch):
    monkeypatch.delenv("SIGSTORE_IDENTITY_TOKEN", raising=False)
    monkeypatch.setattr("yarqa.signing._detect_oidc_token", lambda *a, **k: None)
    _, r = _receipt()
    env = sign_or_placeholder(r.to_canonical_json().encode("utf-8"), {"nx": 10, "ny": 6, "seed": 3})
    assert env["_mode"] == "PLACEHOLDER"
    assert real_signing_available(identity_token=None) in (True, False)  # pure predicate, no raise


def test_replay_reproduces_from_recipe():
    # the heart of independent verification: regenerate the mesh from the recipe,
    # reconstruct the receipt, and confirm yarqa.verify() reproduces the result.
    _, r = _receipt(nx=10, ny=6, seed=3)
    r2 = Receipt.from_json(r.to_canonical_json())
    mesh2 = sample_channel_mesh(10, 6, seed=3)
    res = verify(mesh2, r2)
    assert res["ok"] is True
    assert res["checks"]["inputs_match"] is True
    assert res["checks"]["result_reproduces"] is True
