#!/usr/bin/env python3
# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Produce a yarqa provenance receipt over a deterministic mesh and sign it.

Builds a reproducible ``sample_channel_mesh`` run, records its receipt, and signs
that receipt as a GENUINE Sigstore keyless DSSE attestation (Fulcio ephemeral
cert + Rekor transparency entry). Writes ``attestations/yarqa/<digest>.dsse.json``.

Off-CI there is no ambient OIDC identity, so by default this REFUSES (exit 2)
rather than fabricate a signature. Pass ``--allow-placeholder`` to emit an
honest, clearly-marked unauthenticated placeholder instead.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from yarqa import compartmentalize_with_receipt  # noqa: E402
from yarqa.meshio import sample_channel_mesh  # noqa: E402
from yarqa.signing import (  # noqa: E402
    DsseSigningUnavailable,
    real_signing_available,
    sign_or_placeholder,
    sign_receipt_dsse,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nx", type=int, default=12, help="mesh columns (default 12)")
    ap.add_argument("--ny", type=int, default=8, help="mesh rows (default 8)")
    ap.add_argument("--seed", type=int, default=0, help="deterministic mesh seed (default 0)")
    ap.add_argument("--align-threshold", type=float, default=0.0)
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "attestations" / "yarqa"))
    ap.add_argument("--subject", default="yarqa-receipt")
    ap.add_argument(
        "--allow-placeholder",
        action="store_true",
        help="emit an honest unauthenticated placeholder when real signing is unavailable",
    )
    args = ap.parse_args(argv)

    mesh = sample_channel_mesh(args.nx, args.ny, seed=args.seed)
    labels, receipt = compartmentalize_with_receipt(mesh, align_threshold=args.align_threshold)
    canonical = receipt.to_canonical_json().encode("utf-8")
    digest = receipt.receipt_digest()
    replay = {
        "generator": "sample_channel_mesh",
        "nx": args.nx,
        "ny": args.ny,
        "seed": args.seed,
        "align_threshold": args.align_threshold,
        "yarqa_version": receipt.yarqa_version,
    }

    print(f"[sign] receipt digest={digest} n_compartments={receipt.n_compartments}")
    print(f"[sign] real signing available: {real_signing_available()}")

    if args.allow_placeholder:
        envelope = sign_or_placeholder(canonical, replay, subject_name=args.subject)
    else:
        try:
            envelope = sign_receipt_dsse(canonical, replay, subject_name=args.subject)
        except DsseSigningUnavailable as exc:
            print(
                f"[sign] REFUSING to fabricate a signature: {exc}\n"
                "[sign] run inside GitHub Actions with `id-token: write`, or pass "
                "--allow-placeholder for an honest placeholder.",
                file=sys.stderr,
            )
            return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{digest}.dsse.json"
    out_path.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")

    mode = envelope.get("_mode")
    print(f"[sign] mode={mode} wrote {out_path}")
    if mode == "SIGSTORE-KEYLESS":
        print(f"[sign] rekor_log_index={envelope['_sigstore'].get('rekor_log_index')}")
        print(f"[sign] certificate_fpr_sha256={envelope['_sigstore'].get('certificate_fpr_sha256')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
