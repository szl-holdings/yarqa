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

# --- PCGI spine (T201): one signed szl-receipt per surrogate prediction --------
# The receipt binds the canonical PCGI tuple: model id + input digest + output
# digest + governing policy id + energy (honest UNAVAILABLE, never fabricated) +
# optional BFT witnesses, all under a single DSSE/ECDSA-P256 signature via the
# shared ``szl_receipt.sign_receipt``. It is EVIDENCE binding the decision, never
# a proof the prediction is correct.
PCGI_RECEIPT_SCHEMA = "szl.pcgi.receipt/yarqa-surrogate/v1"
MODEL_ID = "yarqa-plugflow-surrogate"
DEFAULT_POLICY_ID = "szl.pcgi.policy/yarqa-surrogate-bounded-honest/v1"
DEFAULT_ORGAN = "yarqa"
ENERGY_UNAVAILABLE = "UNAVAILABLE"

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


# --- PCGI spine: one signed receipt per prediction (T201) ----------------------


def _digest(body: dict[str, Any]) -> str:
    """SHA-256 hex over the shared canonical JSON of ``body``.

    Uses ``szl_receipt.Receipt.digest`` (SHA-256 over the library's canonical
    JSON) so the digest is byte-for-byte the same primitive that binds every
    other SZL receipt — nothing is re-implemented here.
    """
    szl_receipt, _ = _require_szl_receipt()
    return szl_receipt.Receipt(kind="_digest", body=dict(body)).digest()


def prediction_input(prediction: SurrogatePrediction) -> dict[str, Any]:
    """The canonical INPUT that determines a prediction (digested into a receipt).

    Binds everything the estimate depends on: the surrogate identity, the mesh
    fingerprint, the VERBATIM measured anchors, the validated range, and the
    query threshold. Deriving this independently reproduces ``input_digest``.
    """
    prov = prediction.provenance
    return {
        "schema": prov.get("schema"),
        "method": prov.get("method"),
        "yarqa_version": prov.get("yarqa_version"),
        "target": prov.get("target"),
        "control": prov.get("control"),
        "physics_prior": prov.get("physics_prior"),
        "n_cells": prov.get("n_cells"),
        "mesh_fingerprint": prov.get("mesh_fingerprint"),
        "anchors": prov.get("anchors"),
        "validated_range": prov.get("validated_range"),
        "query": prov.get("query"),
    }


def prediction_output(prediction: SurrogatePrediction) -> dict[str, Any]:
    """The canonical OUTPUT of a prediction (the honest result record)."""
    return dict(prediction.provenance.get("result", {}))


def prediction_input_digest(prediction: SurrogatePrediction) -> str:
    """SHA-256 hex over :func:`prediction_input`."""
    return _digest(prediction_input(prediction))


def prediction_output_digest(prediction: SurrogatePrediction) -> str:
    """SHA-256 hex over :func:`prediction_output`."""
    return _digest(prediction_output(prediction))


def build_prediction_receipt_body(
    prediction: SurrogatePrediction,
    *,
    policy_id: str = DEFAULT_POLICY_ID,
    witnesses: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """Assemble the canonical PCGI receipt body for one prediction.

    Binds the spine tuple — model id, input digest, output digest, governing
    policy id, energy (honest ``UNAVAILABLE`` — yarqa measures no joules here),
    and optional BFT witnesses. The body is deterministic for a fixed prediction
    (no timestamps / nonces), so the same prediction always yields byte-identical
    canonical JSON and the same receipt digest.
    """
    prov = prediction.provenance
    return {
        "schema": PCGI_RECEIPT_SCHEMA,
        "kind": RECEIPT_KIND,
        "model_id": MODEL_ID,
        "yarqa_version": prov.get("yarqa_version"),
        "method": prov.get("method"),
        "input_digest": prediction_input_digest(prediction),
        "output_digest": prediction_output_digest(prediction),
        "policy_id": policy_id,
        "energy": {
            "status": ENERGY_UNAVAILABLE,
            "joules": None,
            "reason": (
                "yarqa surrogate inference energy is NOT measured here; reported "
                "UNAVAILABLE, never fabricated."
            ),
        },
        "witnesses": list(witnesses or []),
        "prediction": {
            "align_threshold": prediction.align_threshold,
            "status": prediction.status,
            "available": prediction.available,
            "value_int": prediction.value_int,
            "lower_bound": prediction.lower_bound,
            "upper_bound": prediction.upper_bound,
        },
        "honesty": {
            "tier": "engineering-method-cfd",
            "interval": (
                "indicative — EXPECTED, not guaranteed, to contain truth; EXACT + "
                "zero-width only at a measured anchor; UNAVAILABLE outside range"
            ),
            "asserts": "integrity/reproducibility, NOT correctness",
            "receipt_is": (
                "evidence trail binding this decision (model+input+output+policy+"
                "energy), NOT a proof the prediction is correct"
            ),
            "bounded": True,
            "extrapolates": False,
        },
    }


def prediction_receipt_body_digest(
    prediction: SurrogatePrediction,
    *,
    policy_id: str = DEFAULT_POLICY_ID,
    witnesses: Optional[list[Any]] = None,
) -> str:
    """Independently (re-)derive the signed receipt's content digest."""
    return _digest(
        build_prediction_receipt_body(
            prediction, policy_id=policy_id, witnesses=witnesses
        )
    )


def emit_prediction_receipt(
    prediction: SurrogatePrediction,
    *,
    private_key_pem: Optional[str | bytes] = None,
    policy_id: str = DEFAULT_POLICY_ID,
    organ: str = DEFAULT_ORGAN,
    keyid: str = "",
    witnesses: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """Emit ONE signed szl-receipt for a surrogate prediction (the PCGI spine).

    Wraps :func:`build_prediction_receipt_body` in a shared
    :class:`szl_receipt.Receipt` and signs it via
    :func:`szl_receipt.sign_receipt` (DSSE/ECDSA-P256-SHA256, cosign-compatible).

    When ``private_key_pem`` is ``None``/empty the shared library returns an
    UNSIGNED-honest envelope (``signed=False``) — never a fabricated signature.

    The returned DSSE envelope binds model id + input digest + output digest +
    governing policy id + honest ``UNAVAILABLE`` energy. It is an EVIDENCE trail
    for the decision, not a proof the prediction is correct; a prediction outside
    the validated range (``status=UNAVAILABLE``, ``value_int=None``) still emits a
    fully honest receipt.
    """
    szl_receipt, _ = _require_szl_receipt()
    body = build_prediction_receipt_body(
        prediction, policy_id=policy_id, witnesses=witnesses
    )
    receipt = szl_receipt.Receipt(kind=RECEIPT_KIND, body=body)
    return szl_receipt.sign_receipt(
        receipt, private_key_pem, organ=organ, keyid=keyid
    )


def verify_prediction_receipt(
    envelope: dict[str, Any],
    *,
    public_key_pem: Optional[str | bytes] = None,
    prediction: Optional[SurrogatePrediction] = None,
    policy_id: str = DEFAULT_POLICY_ID,
    witnesses: Optional[list[Any]] = None,
) -> tuple[bool, str]:
    """Verify a signed prediction receipt (and optionally rebind it).

    Delegates the cryptographic check to :func:`szl_receipt.verify_receipt`
    (keyless envelopes honestly return ``(False, "unsigned-honest")``). When
    ``prediction`` is supplied, additionally confirms the signed body's
    ``input_digest`` / ``output_digest`` re-derive from that prediction — so any
    post-hoc edit to the prediction flips a digest and fails the rebind.
    """
    szl_receipt, _ = _require_szl_receipt()
    ok, detail = szl_receipt.verify_receipt(envelope, public_key_pem=public_key_pem)
    if not ok:
        return ok, detail

    if prediction is not None:
        import base64
        import json

        try:
            body = json.loads(base64.b64decode(envelope["payload"]).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return False, f"payload decode error: {exc}"
        if body.get("input_digest") != prediction_input_digest(prediction):
            return False, "input-digest-rebind-mismatch"
        if body.get("output_digest") != prediction_output_digest(prediction):
            return False, "output-digest-rebind-mismatch"

    return True, "ok"
