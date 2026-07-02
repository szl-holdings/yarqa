# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Thin attestation adapter: wrap a yarqa surrogate prediction with szl_receipt.

Every :class:`yarqa.surrogate.SurrogatePrediction` carries a canonical
provenance record. This module binds that record to the shared SZL receipt /
attestation shapes by **delegating** to ``szl_receipt`` (v0.2.0) — it does NOT
re-implement receipt digests, in-toto Statement shapes, SLSA predicates, or the
compliance catalogue. That is exactly how ``governed-inference-meter`` and
``szl-energy-attest`` consume the library: build a :class:`szl_receipt.Receipt`,
wrap it as an in-toto v1 Statement bound to the receipt digest, and attach the
EU-AI-Act / NIST-AI-RMF ``compliance_evidence`` bundle.

Honesty (doctrine v11)
----------------------
* The receipt is EVIDENCE of integrity + reproducibility, never a conformity
  assessment, certification, or correctness/safety guarantee — the shared
  library's ``compliance_evidence`` disclaimer is preserved verbatim.
* ``energy`` is reported ``UNAVAILABLE`` (yarqa measures no joules); only the
  capabilities the surrogate honestly provides are claimed.
* ``szl_receipt`` is an OPTIONAL dependency. When it is not installed this module
  raises :class:`AttestationUnavailable` rather than fabricating a receipt — the
  numpy-only surrogate in :mod:`yarqa.surrogate` keeps working without it.
"""
from __future__ import annotations

from typing import Any, Optional

from .surrogate import SurrogatePrediction

RECEIPT_KIND = "yarqa-plugflow-surrogate"
PREDICATE_TYPE = "https://a-11-oy.com/attest/yarqa-surrogate/v1"
BUILD_TYPE = "https://a-11-oy.com/attest/yarqa-plugflow-surrogate"
SUBJECT_NAME = "yarqa-surrogate-prediction"

# The capabilities the surrogate + its provenance record honestly provide.
# ``energy`` is deliberately False -> reported UNAVAILABLE by the shared lib.
_CAPABILITIES = {
    "integrity": True,   # receipt digest binds the exact prediction + anchors
    "logging": True,     # each prediction is a recorded, hash-anchored event
    "governance": True,  # the predict / decline-as-UNAVAILABLE decision is recorded
    "energy": False,     # yarqa measures no joules -> UNAVAILABLE, not fabricated
}


class AttestationUnavailable(RuntimeError):
    """Raised when the shared ``szl_receipt`` library is not importable.

    Callers MUST treat this as "no attestation here", never as a reason to
    fabricate a receipt or duplicate the library's shapes locally.
    """


def _require_szl_receipt():
    """Lazily import the shared library; fail honestly if it is absent."""
    try:
        import szl_receipt  # type: ignore
        from szl_receipt import attest  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only without the lib
        raise AttestationUnavailable(
            "szl_receipt (v0.2.0) is not installed; install "
            "`szl_receipt @ git+https://github.com/szl-holdings/szl-receipt.git"
            "@v0.2.0` (the `attest` extra) to attest yarqa surrogate predictions. "
            "Refusing to duplicate the shared receipt shapes."
        ) from exc
    return szl_receipt, attest


def prediction_receipt(prediction: SurrogatePrediction):
    """Build the shared :class:`szl_receipt.Receipt` for a prediction.

    The receipt body is the prediction's verbatim provenance record, so its
    digest binds the mesh fingerprint, the measured anchors, the query, and the
    honest status/estimate together.
    """
    szl_receipt, _ = _require_szl_receipt()
    return szl_receipt.Receipt(kind=RECEIPT_KIND, body=dict(prediction.provenance))


def prediction_digest(prediction: SurrogatePrediction) -> str:
    """Independently (re-)derive the receipt digest from a prediction."""
    return prediction_receipt(prediction).digest()


def attest_prediction(
    prediction: SurrogatePrediction,
    *,
    builder_id: Optional[str] = None,
) -> dict[str, Any]:
    """Attest a surrogate prediction via the shared szl_receipt shapes.

    Returns a bundle with the ``receipt_digest`` (subject anchor), the in-toto v1
    ``statement`` (SLSA-shaped predicate wrapping the prediction), and the
    ``compliance`` evidence bundle. All three shapes come from ``szl_receipt``;
    nothing is re-implemented here.
    """
    szl_receipt, attest = _require_szl_receipt()

    receipt = szl_receipt.Receipt(kind=RECEIPT_KIND, body=dict(prediction.provenance))
    digest = receipt.digest()

    result = prediction.provenance.get("result", {})
    predicate = attest.slsa_predicate(
        build_type=BUILD_TYPE,
        external_parameters={
            "align_threshold": prediction.align_threshold,
            "status": prediction.status,
            "validated_range": prediction.provenance.get("validated_range"),
        },
        internal_parameters={
            "method": prediction.provenance.get("method"),
            "physics_prior": prediction.provenance.get("physics_prior"),
            "yarqa_version": prediction.provenance.get("yarqa_version"),
            "monotone_prior_ok": prediction.provenance.get("monotone_prior_ok"),
        },
        builder_id=builder_id,
        extra={
            "claim_tier": prediction.provenance.get("claim_tier"),
            "prediction": {
                "value_int": prediction.value_int,
                "lower_bound": prediction.lower_bound,
                "upper_bound": prediction.upper_bound,
                "available": prediction.available,
            },
            "honesty": {
                "tier": "engineering-method-cfd",
                "asserts": "integrity/reproducibility, NOT correctness",
                "bounded": True,
                "extrapolates": False,
            },
        },
    )

    statement = attest.build_statement(
        subject_name=SUBJECT_NAME,
        subject_digest=digest,
        predicate=predicate,
        predicate_type=PREDICATE_TYPE,
    )

    compliance = attest.compliance_evidence(
        capabilities=_CAPABILITIES,
        subject_digest=digest,
        extra={"emitter": "yarqa", "doctrine": "v11", "receipt_kind": RECEIPT_KIND},
    )

    return {
        "receipt_digest": digest,
        "predicate_type": PREDICATE_TYPE,
        "statement": statement,
        "compliance": compliance,
    }


def verify_prediction_attestation(
    attestation: dict[str, Any],
    prediction: SurrogatePrediction,
) -> tuple[bool, str]:
    """Verify an attestation rebinds to a prediction held independently.

    Re-derives the receipt digest from ``prediction`` and confirms — via the
    shared :func:`szl_receipt.verify_statement` — that the attestation's in-toto
    statement is bound to exactly that digest and predicate type. Any tampering
    with the prediction's provenance flips the digest and fails the rebind.
    """
    _szl_receipt, attest = _require_szl_receipt()
    expected = prediction_digest(prediction)
    statement = attestation.get("statement", {})
    return attest.verify_statement(
        statement,
        expected_digest=expected,
        predicate_type=attestation.get("predicate_type", PREDICATE_TYPE),
    )
