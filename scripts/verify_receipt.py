#!/usr/bin/env python3
# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Independently verify a yarqa Sigstore-keyless DSSE receipt -- and reproduce it.

Two layers of evidence, both with NO secret material:

  1. Signature: validate the embedded Sigstore bundle (Fulcio certificate chain
     + Rekor inclusion proof + DSSE signature), pinning the expected signer
     ``--identity`` (the GitHub Actions workflow SAN) and ``--issuer``.
  2. Reproduction (``--replay``): regenerate the mesh from the *authenticated*
     replay recipe, reconstruct the receipt, and confirm ``yarqa.verify()``
     reproduces the result (inputs match + result reproduces).

Exit codes: 0 ok; 1 missing file; 2 placeholder (no signature to verify);
3 signature failure; 4 replay error; 5 replay mismatch.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from yarqa.signing import SIGSTORE_OIDC_ISSUER, verify_receipt_dsse  # noqa: E402


def _replay(receipt_canonical: bytes, replay: dict) -> dict:
    from yarqa import Receipt, compartmentalize_with_receipt, verify  # noqa: F401
    from yarqa.meshio import sample_channel_mesh

    receipt = Receipt.from_json(receipt_canonical.decode("utf-8"))
    mesh = sample_channel_mesh(int(replay["nx"]), int(replay["ny"]), seed=int(replay["seed"]))
    return verify(mesh, receipt)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("envelope", help="path to a *.dsse.json envelope")
    ap.add_argument("--identity", required=True, help="expected signer SAN (workflow identity)")
    ap.add_argument("--issuer", default=SIGSTORE_OIDC_ISSUER)
    ap.add_argument("--allow-placeholder", action="store_true", help="soft-pass placeholder envelopes")
    ap.add_argument("--replay", action="store_true", help="also reproduce the run and confirm the result")
    args = ap.parse_args(argv)

    env_path = Path(args.envelope)
    if not env_path.exists():
        print(f"[verify] ERROR: envelope not found: {env_path}", file=sys.stderr)
        return 1
    envelope = json.loads(env_path.read_text(encoding="utf-8"))
    mode = envelope.get("_mode")
    print(f"[verify] file={env_path.name} mode={mode}")

    if mode != "SIGSTORE-KEYLESS":
        msg = (
            f"[verify] envelope is '{mode}', NOT a real Sigstore keyless "
            "signature; nothing to cryptographically verify."
        )
        if args.allow_placeholder:
            print(msg + " (--allow-placeholder: soft pass)")
            return 0
        print(msg, file=sys.stderr)
        return 2

    try:
        result = verify_receipt_dsse(envelope, identity=args.identity, issuer=args.issuer)
    except Exception as exc:
        print(f"[verify] SIGNATURE VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 3

    print("[verify] VERIFIED signature (Fulcio cert chain + Rekor inclusion + DSSE sig)")
    print(f"[verify] receipt_sha256={result['receipt_sha256']}")
    print(f"[verify] rekor_log_index={result['rekor_log_index']}")
    print(f"[verify] identity={args.identity}")

    if args.replay:
        try:
            res = _replay(result["receipt_canonical"], result["replay"])
        except Exception as exc:
            print(f"[verify] REPLAY ERROR: {exc}", file=sys.stderr)
            return 4
        if not res.get("ok"):
            print(f"[verify] REPLAY MISMATCH: {json.dumps(res.get('checks', {}))}", file=sys.stderr)
            return 5
        print("[verify] REPRODUCED: inputs_match + result_reproduces (independent re-run)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
