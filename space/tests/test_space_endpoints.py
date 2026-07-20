# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Endpoint tests for the yarqa Space FastAPI app.

These run offline-safe: feeds may come up LIVE or SAMPLE depending on network
reachability, but the endpoints must always respond with a valid, HONEST shape
(badge in {LIVE, SAMPLE}, never synthetic-as-LIVE, no "proven" claims).
"""
import sys
from pathlib import Path

import pytest

_SPACE = Path(__file__).resolve().parent.parent
_REPO = _SPACE.parent
for p in (str(_REPO), str(_SPACE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient  # noqa: E402
import app as space_app  # noqa: E402

client = TestClient(space_app.app)
VALID_STATES = {"LIVE", "SAMPLE"}


def test_livez_is_local_only(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("/livez must not resolve external feeds")

    monkeypatch.setattr(space_app._CACHE, "get", fail_if_called)
    r = client.get("/livez")
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "service": "yarqa-space",
        "check": "liveness",
        "yarqa_version": space_app.yarqa.__version__,
    }


def test_healthz_source_of_truth():
    r = client.get("/healthz")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["service"] == "yarqa-space"
    # HARD honesty: engineering-method tier, never proven / locked / locked-8.
    h = j["honesty"]
    assert h["tier"] == "engineering-method-cfd"
    assert h["proven_badge"] is False
    assert h["locked_theorem"] is False
    assert h["in_locked_8"] is False
    assert "integrity" in h["receipts_assert"].lower()
    assert h["Lambda"] == "Conjecture 1"
    assert h["Khipu"] == "Conjecture 2"
    assert h["SLSA"] == "L1"


def test_feeds_states_are_honest():
    j = client.get("/api/feeds").json()
    assert set(j["sources"]) == {"marine", "wind", "noaa"}
    for k, s in j["sources"].items():
        assert s["state"] in VALID_STATES
        assert s["url"].startswith("https://")
        assert s["attribution"]            # cited
        # If SAMPLE, it must carry an error reason (never silent synthetic-LIVE)
        if s["state"] == "SAMPLE":
            assert s["error"], f"SAMPLE feed {k} must record why it is sample"


def test_compartments_field_and_receipt():
    j = client.get("/api/compartments?align_threshold=0.2&top_k=8").json()
    assert j["state"] in VALID_STATES
    assert j["n_compartments"] >= 1
    assert len(j["labels"]) == len(j["centers"]) == len(j["velocities"])
    assert len(j["receipt_digest"]) == 64       # sha-256 hex
    # receipt is honest about its tier
    assert "NOT a locked theorem" in j["receipt"]["claim_tier"]
    assert "proven" not in j["receipt"]["claim_tier"].lower()


def test_compartments_threshold_changes_partition():
    a = client.get("/api/compartments?align_threshold=0.0").json()["n_compartments"]
    b = client.get("/api/compartments?align_threshold=0.8").json()["n_compartments"]
    # stricter alignment yields at least as many compartments
    assert b >= a


def test_agentic_loop_steps_have_receipts():
    j = client.get("/api/agentic?n_obs=6").json()
    assert j["state"] in VALID_STATES
    assert len(j["steps"]) == 6
    for s in j["steps"]:
        assert s["decision"] in {"ALLOW", "DENY"}
        assert len(s["yarqa_receipt_digest"]) == 64
        assert "not a proof" in s["notes"].lower()


def test_chain_builds_and_verifies():
    j = client.get("/api/chain?n_obs=5").json()
    assert j["verify"]["ok"] is True
    assert len(j["links"]) == 5
    assert "NOT a locked theorem" in j["claim_tier"]
    # links are hash-linked: each prev_digest matches the previous digest
    links = j["links"]
    for i in range(1, len(links)):
        assert links[i]["prev_digest"] == links[i - 1]["digest"]


def test_chain_tamper_is_detected():
    chain_json = client.get("/api/chain?n_obs=5").json()["chain_json"]
    # clean re-verify
    clean = client.post("/api/chain/verify", json={"chain_json": chain_json}).json()
    assert clean["verify"]["ok"] is True
    # tamper link 2 -> chain must break at index 2
    tampered = client.post(
        "/api/chain/verify",
        json={"chain_json": chain_json, "tamper_index": 2, "tamper_field": "route_score"},
    ).json()
    assert tampered["tampered"] is True
    assert tampered["verify"]["ok"] is False
    assert tampered["verify"]["first_broken_index"] == 2


def test_forecast_labels_projected_honestly():
    j = client.get("/api/forecast?horizon=6").json()
    assert j["state"] in VALID_STATES
    assert all(p["kind"] == "DATA" for p in j["history"])
    assert all(p["kind"] == "PROJECTED" for p in j["projected"])
    assert len(j["projected"]) == 6
    assert "honest" in j["note"].lower() or "projected" in j["note"].lower()


def test_static_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "yarqa" in r.text.lower()


def test_vendored_three_is_r160_zero_cdn():
    # sovereign: THREE served from our own static path, not a CDN
    r = client.get("/lib/three.min.js")
    assert r.status_code == 200
    assert "REVISION = '160'" in r.text
    # index references the local vendored copy, never an external CDN
    idx = client.get("/").text
    assert "./lib/three.min.js" in idx
    assert "cdn" not in idx.lower()


def test_security_headers_present():
    # SAFE-NOW hardening (R2): real headers on every response, incl. /healthz.
    r = client.get("/healthz")
    assert r.status_code == 200
    h = r.headers
    csp = h["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    # frame-ancestors permits the legit HF embed but is not wide open
    assert "frame-ancestors 'self' https://huggingface.co https://*.hf.space" in csp
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert h["strict-transport-security"].startswith("max-age=")
    # NOT X-Frame-Options: DENY (that would break the HF iframe embed)
    assert h.get("x-frame-options", "").upper() != "DENY"


def test_cors_not_wildcard_but_allows_hf_embed():
    # An allowed cross-origin (an *.hf.space sibling) is echoed back...
    r = client.get("/healthz", headers={"Origin": "https://szlholdings-a11oy.hf.space"})
    aco = r.headers.get("access-control-allow-origin", "")
    assert aco != "*"
    assert aco == "https://szlholdings-a11oy.hf.space"
    assert r.status_code == 200  # public read still served
    # A random untrusted origin is NOT granted an ACAO header, but the read
    # itself still succeeds (CORS only gates cross-site *browser* JS).
    r2 = client.get("/healthz", headers={"Origin": "https://evil.example.com"})
    assert r2.headers.get("access-control-allow-origin") in (None, "")
    assert r2.status_code == 200
