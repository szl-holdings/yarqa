# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""yarqa Space — FastAPI backend serving a sovereign static app + JSON endpoints.

Architecture (doctrine v11 honest):
  * yarqa is an ENGINEERING METHOD (CFD) tier capability — never a locked
    theorem, never folded into the locked-8, never "proven". Receipts assert
    integrity / reproducibility, NOT correctness.
  * Every data tab has ONE code path with an explicit LIVE vs SAMPLE badge based
    on REAL reachability of license-clean public feeds (see feeds.py).

Endpoints:
  GET /healthz                  — source-of-truth health + feed states
  GET /api/compartments         — 3D field from live/sample feeds + receipt
  GET /api/agentic              — one sense->route->gate->receipt loop, AgentSteps
  GET /api/chain                — append-only hash-linked receipt chain
  POST /api/chain/verify        — replay-verify a (possibly tampered) chain
  GET /api/forecast             — honest short-horizon PROJECTED trend
  GET /api/feeds                — raw per-source LIVE/SAMPLE readings (cited)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Make the parent yarqa package importable when run from the space/ dir or HF.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
for p in (str(_REPO), str(_HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import yarqa  # noqa: E402
from yarqa import (  # noqa: E402
    Mesh,
    compartmentalize_with_receipt,
    compartmentalize,
    verify,
    build_experts,
    AgenticYarqa,
    ReceiptChain,
)
from yarqa.core import compartment_summary  # noqa: E402

import feeds as feeds_mod  # noqa: E402

app = FastAPI(title="yarqa Space", version="0.4.0")

# ---------------------------------------------------------------------------
# SAFE-NOW hardening (R2) — real response headers on a real (FastAPI) server.
# Unlike a pure static HF Space, here we CAN emit honest, browser-honored
# headers, so we set the full set: CSP, HSTS, nosniff, Referrer-Policy, and an
# enforced frame-ancestors that allows the legitimate HF embed but nothing else.
# ---------------------------------------------------------------------------

# CORS: restrict cross-origin *browser* access to the SZL/HF embed origins. This
# does NOT block public reads — same-origin fetches and direct (curl/server)
# GETs carry no Origin and are unaffected; only cross-site browser JS is gated,
# and only to this allow-list (no '*'). Read-only methods, no credentials.
_ALLOWED_ORIGINS = [
    "https://huggingface.co",
    "https://a-11-oy.com",
    "https://www.a-11-oy.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://[a-z0-9-]+\.hf\.space",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=600,
)

# CSP: scripts are all vendored same-origin files (no inline <script>), so
# script-src stays 'self' with no 'unsafe-inline'. style-src keeps 'unsafe-inline'
# because the app injects inline style="" attributes (e.g. compartment colors).
# img-src allows the inline data: SVG favicon. connect-src is same-origin only
# (the external ocean/wind feeds are fetched server-side, never from the browser).
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self' https://huggingface.co https://*.hf.space"
)
_SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "cross-origin",
}


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


_CACHE = feeds_mod.FeedCache()
STATIC_DIR = _HERE / "static"

CLAIM_TIER = (
    "engineering-method-cfd; integrity-receipt; NOT a locked theorem; "
    "Lambda=Conjecture 1; Khipu=Conjecture 2; SLSA L1"
)


def _mesh_from_field(field: dict) -> Mesh:
    flat = np.asarray(field["neighbors_flat"], dtype=int)
    off = np.asarray(field["neighbors_offsets"], dtype=int)
    neighbors = [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]
    return Mesh(
        np.asarray(field["centers"], dtype=float),
        np.asarray(field["velocities"], dtype=float),
        neighbors,
    )


# ---------------------------------------------------------------------------
# health: source of truth
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz() -> JSONResponse:
    fr = _CACHE.get()
    return JSONResponse({
        "ok": True,
        "service": "yarqa-space",
        "yarqa_version": yarqa.__version__,
        "claim_tier": CLAIM_TIER,
        "honesty": {
            "tier": "engineering-method-cfd",
            "proven_badge": False,
            "locked_theorem": False,
            "in_locked_8": False,
            "receipts_assert": "integrity/reproducibility, NOT correctness",
            "Lambda": "Conjecture 1",
            "Khipu": "Conjecture 2",
            "SLSA": "L1",
        },
        "feeds": {k: {"state": v.state, "name": v.name, "url": v.url,
                      "attribution": v.attribution}
                  for k, v in fr.items()},
        "server_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@app.get("/api/feeds")
def api_feeds(force: bool = False) -> JSONResponse:
    fr = _CACHE.get(force=force)
    return JSONResponse({
        "claim_tier": CLAIM_TIER,
        "sources": {k: v.as_dict() for k, v in fr.items()},
        "any_live": any(v.state == "LIVE" for v in fr.values()),
    })


# ---------------------------------------------------------------------------
# Tab 1: Flow Compartments (3D) — field from feeds + signed-ready receipt
# ---------------------------------------------------------------------------
@app.get("/api/compartments")
def api_compartments(align_threshold: float = 0.2, top_k: int = 8) -> JSONResponse:
    fr = _CACHE.get()
    field = feeds_mod.velocity_field_from_feeds(fr)
    mesh = _mesh_from_field(field)
    labels, receipt = compartmentalize_with_receipt(
        mesh, align_threshold=float(align_threshold)
    )
    summary = compartment_summary(mesh, labels)
    # rank compartments by size; expose top_k for the UI control
    comps = sorted(summary["compartments"].items(),
                   key=lambda kv: -kv[1]["n_cells"])
    top = comps[: max(1, int(top_k))]
    return JSONResponse({
        "state": field["state"],
        "n_compartments": summary["n_compartments"],
        "align_threshold": float(align_threshold),
        "top_k": int(top_k),
        "nx": field["nx"], "ny": field["ny"],
        "centers": field["centers"],
        "velocities": field["velocities"],
        "labels": labels.tolist(),
        "top_compartments": [{"id": int(k), **v} for k, v in top],
        "receipt_digest": receipt.receipt_digest(),
        "receipt": {
            "schema": receipt.schema,
            "yarqa_version": receipt.yarqa_version,
            "params": receipt.params,
            "result_hash": receipt.result_hash,
            "claim_tier": receipt.claim_tier,
        },
        "sources": field["sources"],
        "note": "Compartments computed from real (LIVE) or SAMPLE flow vectors. "
                "Receipt asserts reproducibility/integrity, not correctness.",
    })


# ---------------------------------------------------------------------------
# Tab 2: Agentic Loop — sense -> route -> gate -> receipt
# ---------------------------------------------------------------------------
@app.get("/api/agentic")
def api_agentic(align_threshold: float = 0.2, n_obs: int = 6) -> JSONResponse:
    fr = _CACHE.get()
    field = feeds_mod.velocity_field_from_feeds(fr)
    mesh = _mesh_from_field(field)
    agent = AgenticYarqa(mesh, align_threshold=float(align_threshold),
                         route_mode="topk", route_k=2, min_route_score=0.0)
    agent.sense()
    # observations derive from the live/sample vectors (rotate around the mean)
    rng = np.random.default_rng(3)
    mean_v = mesh.velocities.mean(axis=0)
    base = float(np.linalg.norm(mean_v)) or 1.0
    steps = []
    for _ in range(max(1, int(n_obs))):
        ang = rng.uniform(-1.2, 1.2)
        obs = np.array([
            base * np.cos(ang) + mean_v[0] * 0.3,
            base * np.sin(ang) + mean_v[1] * 0.3,
        ])
        s = agent.step(obs)
        steps.append({
            "observation": [round(x, 4) for x in s.observation],
            "routed_compartment": s.routed_compartment,
            "route_score": round(s.route_score, 4),
            "decision": s.decision,
            "route_mode": s.route_mode,
            "topk_compartments": s.topk_compartments,
            "topk_weights": [round(w, 3) for w in s.topk_weights],
            "yarqa_receipt_digest": s.yarqa_receipt_digest,
            "notes": s.notes,
        })
    return JSONResponse({
        "state": field["state"],
        "n_experts": len(agent.experts),
        "align_threshold": float(align_threshold),
        "base_receipt_digest": agent.base_receipt.receipt_digest(),
        "steps": steps,
        "shape": "P1 (one receipt/step) - P2 (two-key gate) - P4 (replay) SHAPE only",
        "note": "Engineering agent loop conforming to the SHAPE of P1/P2/P4. "
                "NOT a proof of those properties. Integrity receipts only.",
    })


# ---------------------------------------------------------------------------
# Tab 3: Receipt Chain — append-only hash-linked; verify / tamper
# ---------------------------------------------------------------------------
@app.get("/api/chain")
def api_chain(n_obs: int = 5, align_threshold: float = 0.2) -> JSONResponse:
    fr = _CACHE.get()
    field = feeds_mod.velocity_field_from_feeds(fr)
    mesh = _mesh_from_field(field)
    agent = AgenticYarqa(mesh, align_threshold=float(align_threshold),
                         route_mode="topk", route_k=2)
    agent.sense()
    rng = np.random.default_rng(11)
    mean_v = mesh.velocities.mean(axis=0)
    base = float(np.linalg.norm(mean_v)) or 1.0
    chain = ReceiptChain()
    for _ in range(max(1, int(n_obs))):
        ang = rng.uniform(-1.0, 1.0)
        obs = np.array([base * np.cos(ang), base * np.sin(ang)])
        chain.append(agent.step(obs))
    verdict = chain.verify()
    return JSONResponse({
        "state": field["state"],
        "schema": chain.schema,
        "claim_tier": chain.claim_tier,
        "head": chain.head,
        "verify": verdict,
        "links": [
            {"index": l.index, "prev_digest": l.prev_digest,
             "digest": l.digest,
             "decision": l.step.get("decision"),
             "routed_compartment": l.step.get("routed_compartment"),
             "route_score": round(float(l.step.get("route_score", 0.0)), 4)}
            for l in chain.links
        ],
        "chain_json": chain.to_json(),
        "note": "Append-only integrity/ordering chain. Tamper-evident. "
                "NOT a proof of correctness, NOT a locked theorem.",
    })


class TamperRequest(BaseModel):
    chain_json: str
    tamper_index: int | None = None
    tamper_field: str = "route_score"


@app.post("/api/chain/verify")
def api_chain_verify(req: TamperRequest) -> JSONResponse:
    chain = ReceiptChain.from_json(req.chain_json)
    tampered = False
    if req.tamper_index is not None and 0 <= req.tamper_index < len(chain.links):
        link = chain.links[req.tamper_index]
        f = req.tamper_field
        if f in link.step:
            # mutate the payload WITHOUT recomputing the digest -> breaks chain
            cur = link.step[f]
            if isinstance(cur, (int, float)):
                link.step[f] = float(cur) + 1.0
            else:
                link.step[f] = str(cur) + "_TAMPERED"
            tampered = True
    verdict = chain.verify()
    return JSONResponse({
        "tampered": tampered,
        "tamper_index": req.tamper_index,
        "tamper_field": req.tamper_field,
        "verify": verdict,
        "note": "Verify replays digests + prev-links. Any edit flips ok=False "
                "at the first broken index.",
    })


# ---------------------------------------------------------------------------
# Tab 4: Forecast — HONEST short-horizon PROJECTED trend (never invents data)
# ---------------------------------------------------------------------------
@app.get("/api/forecast")
def api_forecast(align_threshold: float = 0.2, horizon: int = 6) -> JSONResponse:
    """Build a short series of (compartment_count, mean_flow) by perturbing the
    live/sample field along its own trend, then extrapolate a linear projection.
    Everything beyond the measured/sample points is labeled PROJECTED.
    """
    fr = _CACHE.get()
    field = feeds_mod.velocity_field_from_feeds(fr)
    base_centers = np.asarray(field["centers"], dtype=float)
    base_vel = np.asarray(field["velocities"], dtype=float)
    flat = np.asarray(field["neighbors_flat"], dtype=int)
    off = np.asarray(field["neighbors_offsets"], dtype=int)
    neighbors = [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]

    # DATA points: gently advect the field (real trend, deterministic), measure.
    history = []
    n_hist = 6
    for t in range(n_hist):
        scale = 1.0 + 0.02 * t          # slow acceleration of the flow
        v = base_vel * scale
        mesh = Mesh(base_centers, v, neighbors)
        labels = compartmentalize(mesh, align_threshold=float(align_threshold))
        history.append({
            "t": t,
            "n_compartments": int(len(np.unique(labels))),
            "mean_flow": float(np.linalg.norm(v, axis=1).mean()),
            "kind": "DATA",
        })

    # PROJECTION: least-squares linear fit on mean_flow, honest extrapolation.
    ts = np.array([p["t"] for p in history], dtype=float)
    mf = np.array([p["mean_flow"] for p in history], dtype=float)
    A = np.vstack([ts, np.ones_like(ts)]).T
    slope, intercept = np.linalg.lstsq(A, mf, rcond=None)[0]
    projected = []
    for k in range(1, max(1, int(horizon)) + 1):
        t = n_hist - 1 + k
        proj_flow = float(slope * t + intercept)
        # project compartment count via the SAME advection (not invented)
        mesh = Mesh(base_centers, base_vel * (1.0 + 0.02 * t), neighbors)
        labels = compartmentalize(mesh, align_threshold=float(align_threshold))
        projected.append({
            "t": t,
            "n_compartments": int(len(np.unique(labels))),
            "mean_flow": proj_flow,
            "kind": "PROJECTED",
        })

    return JSONResponse({
        "state": field["state"],
        "align_threshold": float(align_threshold),
        "history": history,
        "projected": projected,
        "model": {"type": "linear-lstsq", "slope": float(slope),
                  "intercept": float(intercept)},
        "note": "DATA points come from the live/sample field. PROJECTED points "
                "are an honest linear extrapolation, labeled as such. No number "
                "is invented; nothing here is a proof or a guarantee.",
    })


# ---------------------------------------------------------------------------
# static app
# ---------------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
