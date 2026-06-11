# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Command-line interface for yarqa.

Two real commands, plus a synthetic-data helper:

    python -m yarqa.cli compartmentalize <mesh.npz> [--align A] [--receipt OUT.json]
    python -m yarqa.cli verify <mesh.npz> <receipt.json>
    python -m yarqa.cli sample <out.npz> [--nx N] [--ny M]

``compartmentalize`` loads a mesh from the simple yarqa ``.npz`` format (see
``yarqa.meshio``), partitions it into plug-flow compartments, prints a summary,
and emits a reproducible provenance **integrity** receipt (optionally written to
``--receipt``). ``verify`` re-runs the partition from the mesh and confirms it
reproduces the receipt — tamper-evident on inputs, params, and results.

HONESTY (doctrine v11): the receipt asserts integrity / reproducibility, not
correctness; yarqa is an engineering (CFD) method, never a locked theorem.

numpy-only; no third-party source copied.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

import numpy as np

from .core import compartmentalize, compartment_summary
from .meshio import load_npz_mesh, save_npz_mesh, sample_channel_mesh
from .provenance import compartmentalize_with_receipt, verify, Receipt


def _cmd_compartmentalize(args: argparse.Namespace) -> int:
    mesh = load_npz_mesh(args.mesh)
    labels, receipt = compartmentalize_with_receipt(
        mesh, align_threshold=args.align
    )
    summary = compartment_summary(mesh, labels)
    print(
        f"cells={mesh.n} dim={mesh.dim} "
        f"compartments={summary['n_compartments']} "
        f"align_threshold={args.align}"
    )
    print(f"receipt_digest={receipt.receipt_digest()}")
    print(f"claim_tier={receipt.claim_tier}")
    if args.receipt:
        with open(args.receipt, "w") as fh:
            fh.write(receipt.to_canonical_json())
        print(f"wrote receipt -> {args.receipt}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    mesh = load_npz_mesh(args.mesh)
    with open(args.receipt) as fh:
        receipt = Receipt.from_json(fh.read())
    verdict = verify(mesh, receipt)
    print(json.dumps(verdict, sort_keys=True, indent=2))
    if verdict["ok"]:
        print("VERIFY: OK (integrity/reproducibility confirmed; not a proof of correctness)")
        return 0
    print("VERIFY: FAILED (mesh, params, or result do not match the receipt)")
    return 1


def _cmd_sample(args: argparse.Namespace) -> int:
    mesh = sample_channel_mesh(nx=args.nx, ny=args.ny, seed=args.seed)
    save_npz_mesh(args.out, mesh)
    print(
        f"wrote SAMPLE synthetic mesh -> {args.out} "
        f"(cells={mesh.n}, nx={args.nx}, ny={args.ny}); NOT real CFD data"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser (exposed for testing)."""
    p = argparse.ArgumentParser(
        prog="yarqa.cli",
        description="Plug-flow compartmentalization with reproducible integrity receipts.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser(
        "compartmentalize", help="partition a mesh.npz and emit a receipt"
    )
    c.add_argument("mesh", help="path to a yarqa .npz mesh")
    c.add_argument(
        "--align", type=float, default=0.0, help="align_threshold (default 0.0)"
    )
    c.add_argument(
        "--receipt", default=None, help="optional path to write the receipt JSON"
    )
    c.set_defaults(func=_cmd_compartmentalize)

    v = sub.add_parser("verify", help="verify a mesh.npz reproduces a receipt.json")
    v.add_argument("mesh", help="path to a yarqa .npz mesh")
    v.add_argument("receipt", help="path to a receipt.json produced earlier")
    v.set_defaults(func=_cmd_verify)

    s = sub.add_parser("sample", help="write a SAMPLE synthetic mesh.npz")
    s.add_argument("out", help="output .npz path")
    s.add_argument("--nx", type=int, default=12)
    s.add_argument("--ny", type=int, default=8)
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(func=_cmd_sample)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess in tests
    sys.exit(main())
