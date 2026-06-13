# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Real keyless Sigstore DSSE signing for yarqa provenance receipts.

A yarqa ``Receipt`` (see :mod:`yarqa.provenance`) is already a canonical,
reproducible record of one compartmentalization run. This module *signs* that
receipt as a genuine Sigstore **keyless** DSSE attestation:

  1. An ambient OIDC token (GitHub Actions ``id-token: write``) is obtained.
  2. It is exchanged at **Fulcio** for a short-lived ECDSA-P256 certificate.
  3. The receipt is wrapped as an in-toto v1 ``Statement`` (subject digest =
     ``sha256`` of the canonical receipt; the receipt bytes are preserved
     base64 in the predicate, alongside a deterministic *replay recipe*) and
     signed as a DSSE envelope.
  4. The signature is recorded in the public **Rekor** transparency log.

Anyone can then verify -- with **no** secret material -- that this exact
receipt was produced by this exact GitHub Actions workflow identity, and (via
the replay recipe) reproduce the run to confirm the result.

HONESTY (doctrine v11)
----------------------
* This upgrades the receipt **signature** only. yarqa stays an
  engineering-method / CFD tier: receipts attest **integrity + reproducibility**,
  never correctness, and carry no locked-theorem or "proven" claim. The SLSA
  level is unchanged (**L1**).
* Real signing only works inside CI (a context with an ambient OIDC token).
  Outside CI there is no identity to mint a certificate from, so we **decline**
  rather than fabricate a signature (:class:`DsseSigningUnavailable`).
  :func:`sign_or_placeholder` instead emits a clearly-marked, unauthenticated
  PLACEHOLDER envelope.

Org policy permits only github-owned actions, so signing is driven by
``pip install sigstore`` + this module, never a third-party signing action.
"""
from __future__ import annotations

import base64
import json
import os
from hashlib import sha256
from typing import Any, Optional

YARQA_PAYLOAD_TYPE = "application/vnd.szl.yarqa-receipt+json"
YARQA_PREDICATE_TYPE = "https://szl-holdings.dev/attestations/yarqa-receipt/v1"
SIGSTORE_OIDC_ISSUER = "https://token.actions.githubusercontent.com"

_CLAIM_TIER = (
    "engineering-method-cfd; integrity+reproducibility receipt; "
    "NOT a locked theorem; SLSA L1"
)


class DsseSigningUnavailable(RuntimeError):
    """Raised when real Sigstore keyless signing cannot run in this runtime.

    Two honest causes: the ``sigstore`` Python SDK is not installed, or there is
    no ambient OIDC credential (i.e. we are not inside a CI job with
    ``id-token: write``). Callers MUST treat this as "keep the honest
    placeholder", never as "fabricate a signature".
    """


def _detect_oidc_token(identity_token: Optional[str] = None) -> Optional[str]:
    """Best-effort discovery of an ambient OIDC token (CI only).

    Order: explicit arg -> ``SIGSTORE_IDENTITY_TOKEN`` env -> sigstore's
    ``detect_credential()`` (reads ``ACTIONS_ID_TOKEN_REQUEST_URL``/``TOKEN`` in
    GitHub Actions). Returns ``None`` when no ambient identity exists.
    """
    if identity_token:
        return identity_token
    env_token = os.environ.get("SIGSTORE_IDENTITY_TOKEN")
    if env_token:
        return env_token
    try:
        from sigstore.oidc import detect_credential  # type: ignore
    except Exception:
        return None
    try:
        return detect_credential()
    except Exception:
        return None


def real_signing_available(identity_token: Optional[str] = None) -> bool:
    """True iff a genuine Sigstore keyless signature could be minted right now.

    Requires BOTH the sigstore SDK to import AND an ambient OIDC token. Pure
    predicate -- performs no network calls and mints nothing.
    """
    try:
        import sigstore  # noqa: F401
    except Exception:
        return False
    return bool(_detect_oidc_token(identity_token))


def _build_statement(receipt_canonical: bytes, replay: dict[str, Any], subject_name: str):
    from sigstore.dsse import DigestSet, StatementBuilder, Subject

    digest = sha256(receipt_canonical).hexdigest()
    return (
        StatementBuilder()
        .subjects([Subject(name=subject_name, digest=DigestSet(root={"sha256": digest}))])
        .predicate_type(YARQA_PREDICATE_TYPE)
        .predicate(
            {
                "dsse_payload_type": YARQA_PAYLOAD_TYPE,
                "payload_b64": base64.b64encode(receipt_canonical).decode(),
                "replay": replay,
                "claim_tier": _CLAIM_TIER,
                "doctrine": "v11",
            }
        )
        .build()
    )


def sign_receipt_dsse(
    receipt_canonical: bytes,
    replay: dict[str, Any],
    *,
    subject_name: str = "yarqa-receipt",
    identity_token: Optional[str] = None,
) -> dict:
    """Sign a canonical yarqa receipt with a GENUINE Sigstore keyless signature.

    ``receipt_canonical`` is ``Receipt.to_canonical_json().encode("utf-8")``.
    ``replay`` is a deterministic recipe (e.g. ``{generator, nx, ny, seed,
    align_threshold}``) sufficient to regenerate the mesh and reproduce the run.

    Returns the signed DSSE envelope (spec shape: ``payloadType`` / ``payload``
    / ``signatures``) enriched with ``_sigstore`` (full bundle + Rekor index)
    so any third party can verify it offline with :func:`verify_receipt_dsse`
    or the ``sigstore`` CLI.

    Raises :class:`DsseSigningUnavailable` when the SDK is missing or no ambient
    OIDC token exists. NEVER fabricates a signature.
    """
    raw_token = _detect_oidc_token(identity_token)
    if not raw_token:
        raise DsseSigningUnavailable(
            "no ambient OIDC credential: real Sigstore keyless signing requires a "
            "CI context with `id-token: write` (e.g. GitHub Actions). Keep the "
            "placeholder envelope in non-CI runtimes."
        )
    try:
        from cryptography.hazmat.primitives.serialization import Encoding
        from sigstore.models import ClientTrustConfig
        from sigstore.oidc import IdentityToken
        from sigstore.sign import SigningContext
    except Exception as exc:  # pragma: no cover - exercised only without the SDK
        raise DsseSigningUnavailable(
            f"sigstore SDK not importable ({exc}); add `sigstore>=2.0.0` to the "
            "signing component's requirements. Refusing to fabricate a signature."
        ) from exc

    statement = _build_statement(receipt_canonical, replay, subject_name)
    identity = IdentityToken(raw_token)
    trust_config = ClientTrustConfig.production()
    signing_ctx = SigningContext.from_trust_config(trust_config)
    with signing_ctx.signer(identity) as signer:
        bundle = signer.sign_dsse(statement)

    bundle_json = json.loads(bundle.to_json())
    dsse_part = bundle_json.get("dsseEnvelope", {})

    # Rekor inclusion data lives in the bundle's verificationMaterial. Read it
    # from the canonical JSON (camelCase, public) rather than a private SDK
    # attribute, so the recorded log index / time stay correct across versions.
    tlog_entries = (bundle_json.get("verificationMaterial", {}) or {}).get("tlogEntries", []) or []
    tlog0 = tlog_entries[0] if tlog_entries else {}

    cert = bundle.signing_certificate
    cert_fpr = sha256(cert.public_bytes(Encoding.DER)).hexdigest()

    return {
        "payloadType": dsse_part.get("payloadType"),
        "payload": dsse_part.get("payload"),
        "signatures": dsse_part.get("signatures", []),
        "_mode": "SIGSTORE-KEYLESS",
        "_note": (
            "REAL Sigstore keyless DSSE signature (ephemeral Fulcio ECDSA-P256 "
            "cert + Rekor transparency entry) over a yarqa receipt. Verify with "
            "verify_receipt_dsse() or the `sigstore` CLI. yarqa stays "
            "engineering-method/CFD; SLSA claim unchanged (L1)."
        ),
        "_szl": {
            "dsse_payload_type": YARQA_PAYLOAD_TYPE,
            "receipt_sha256": sha256(receipt_canonical).hexdigest(),
            "subject": subject_name,
            "replay": replay,
        },
        "_sigstore": {
            "bundle": bundle_json,
            "certificate_fpr_sha256": cert_fpr,
            "rekor_log_index": tlog0.get("logIndex"),
            "rekor_integrated_time": tlog0.get("integratedTime"),
            "oidc_issuer": SIGSTORE_OIDC_ISSUER,
        },
    }


def placeholder_envelope(
    receipt_canonical: bytes,
    replay: dict[str, Any],
    *,
    subject_name: str = "yarqa-receipt",
    reason: str = "",
) -> dict:
    """Honest, UNAUTHENTICATED placeholder envelope (no signature minted).

    Same overall shape as a real envelope, but ``_mode`` is ``PLACEHOLDER`` and
    there is no ``_sigstore`` block. The receipt bytes are preserved in
    ``_szl.payload_b64`` so the replay recipe is still usable offline.
    """
    return {
        "payloadType": "application/vnd.in-toto+json",
        "payload": None,
        "signatures": [],
        "_mode": "PLACEHOLDER",
        "_note": (
            "Honest PLACEHOLDER (NOT authenticated). Real Sigstore keyless "
            "signing unavailable here" + (f": {reason}" if reason else ".")
        ),
        "_szl": {
            "dsse_payload_type": YARQA_PAYLOAD_TYPE,
            "receipt_sha256": sha256(receipt_canonical).hexdigest(),
            "subject": subject_name,
            "replay": replay,
            "payload_b64": base64.b64encode(receipt_canonical).decode(),
        },
    }


def sign_or_placeholder(
    receipt_canonical: bytes,
    replay: dict[str, Any],
    *,
    subject_name: str = "yarqa-receipt",
    identity_token: Optional[str] = None,
) -> dict:
    """Real Sigstore keyless signature when CI can mint one; honest placeholder
    otherwise. The shape is always an envelope; ``_mode`` discloses which path.
    """
    try:
        return sign_receipt_dsse(
            receipt_canonical, replay,
            subject_name=subject_name, identity_token=identity_token,
        )
    except DsseSigningUnavailable as exc:
        return placeholder_envelope(
            receipt_canonical, replay, subject_name=subject_name, reason=str(exc)
        )


def verify_receipt_dsse(envelope: dict, *, identity: str, issuer: str = SIGSTORE_OIDC_ISSUER) -> dict:
    """Independently verify a :func:`sign_receipt_dsse` envelope against Rekor.

    Re-derives trust from the embedded Sigstore bundle: validates the Fulcio
    certificate chain, the Rekor inclusion proof, and the DSSE signature, and
    pins the signer ``identity`` (the GitHub Actions workflow SAN) + OIDC
    ``issuer``. Then recovers the authenticated receipt bytes from the signed
    statement and confirms they hash to the signed subject digest.

    Raises on any failure (never returns a false-positive).
    """
    sigstore_block = (envelope or {}).get("_sigstore") or {}
    bundle_json = sigstore_block.get("bundle")
    if not bundle_json:
        raise ValueError("envelope has no _sigstore.bundle to verify (not a real signature)")

    from sigstore.models import Bundle
    from sigstore.verify import Verifier
    from sigstore.verify.policy import Identity

    bundle = Bundle.from_json(json.dumps(bundle_json))
    verifier = Verifier.production()
    policy = Identity(identity=identity, issuer=issuer)
    payload_type, payload = verifier.verify_dsse(bundle, policy)

    statement = json.loads(payload)
    predicate = statement.get("predicate", {}) or {}
    payload_b64 = predicate.get("payload_b64")
    if not payload_b64:
        raise ValueError("signed statement has no predicate.payload_b64")
    receipt_canonical = base64.b64decode(payload_b64)
    recovered_digest = sha256(receipt_canonical).hexdigest()

    subjects = statement.get("subject", []) or []
    signed_digest = (subjects[0].get("digest", {}) if subjects else {}).get("sha256")
    if signed_digest != recovered_digest:
        raise ValueError(
            "subject digest in signed statement does not match the recovered "
            "receipt bytes (envelope is internally inconsistent)"
        )

    return {
        "verified": True,
        "payloadType": payload_type,
        "receipt_canonical": receipt_canonical,
        "receipt_sha256": recovered_digest,
        "replay": predicate.get("replay", {}),
        "rekor_log_index": sigstore_block.get("rekor_log_index"),
        "certificate_fpr_sha256": sigstore_block.get("certificate_fpr_sha256"),
    }
