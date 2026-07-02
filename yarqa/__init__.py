"""Yarqa — plug-flow compartmentalization for compartmental models.

`yarqa` (Quechua: an Andean irrigation canal that divides and routes flowing
water) partitions a CFD mesh into plug-flow compartments by grouping cells whose
velocity fields are aligned and that lie across a common flow front.

Clean-room implementation by SZL Holdings, written from the published algorithm
description only. Apache-2.0. See PROVENANCE.md.
"""

__version__ = "0.5.0"

from .core import (
    Mesh,
    compartmentalize,
    build_connection_map,
)
from .provenance import (
    Receipt,
    compartmentalize_with_receipt,
    verify,
    mesh_fingerprint,
)
from .agentic import (
    AgenticYarqa,
    Expert,
    build_experts,
    route,
    route_topk,
    RouteTopK,
)
from .chain import ReceiptChain, ChainLink, GENESIS_PREV
from .meshio import (
    load_npz_mesh,
    save_npz_mesh,
    sample_channel_mesh,
    try_load_openfoam,
)
from .surrogate import (
    PlugFlowSurrogate,
    SurrogateAnchor,
    SurrogatePrediction,
    fit_plugflow_surrogate,
    SURROGATE_SCHEMA,
    SURROGATE_METHOD,
    STATUS_PREDICTED,
    STATUS_UNAVAILABLE,
)
from .attestation import (
    AttestationUnavailable,
    attest_prediction,
    verify_prediction_attestation,
    prediction_receipt,
    prediction_digest,
)

__all__ = [
    "Mesh",
    "compartmentalize",
    "build_connection_map",
    "Receipt",
    "compartmentalize_with_receipt",
    "verify",
    "mesh_fingerprint",
    "AgenticYarqa",
    "Expert",
    "build_experts",
    "route",
    "route_topk",
    "RouteTopK",
    "ReceiptChain",
    "ChainLink",
    "GENESIS_PREV",
    "load_npz_mesh",
    "save_npz_mesh",
    "sample_channel_mesh",
    "try_load_openfoam",
    "PlugFlowSurrogate",
    "SurrogateAnchor",
    "SurrogatePrediction",
    "fit_plugflow_surrogate",
    "SURROGATE_SCHEMA",
    "SURROGATE_METHOD",
    "STATUS_PREDICTED",
    "STATUS_UNAVAILABLE",
    "AttestationUnavailable",
    "attest_prediction",
    "verify_prediction_attestation",
    "prediction_receipt",
    "prediction_digest",
]
