# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Tests for yarqa.cli — compartmentalize / verify / sample subcommands.

Exercises both the in-process main() and a real subprocess invocation of
`python -m yarqa.cli` to confirm the module entry point works end-to-end.
"""
import json
import subprocess
import sys

import numpy as np

from yarqa.cli import main
from yarqa.meshio import sample_channel_mesh, save_npz_mesh


def _write_sample(tmp_path, nx=8, ny=6):
    mesh = sample_channel_mesh(nx=nx, ny=ny, seed=1)
    path = str(tmp_path / "mesh.npz")
    save_npz_mesh(path, mesh)
    return path


def test_cli_sample_then_compartmentalize_and_verify(tmp_path, capsys):
    npz = str(tmp_path / "s.npz")
    assert main(["sample", npz, "--nx", "8", "--ny", "6"]) == 0
    receipt = str(tmp_path / "r.json")
    rc = main(["compartmentalize", npz, "--align", "0.2", "--receipt", receipt])
    assert rc == 0
    out = capsys.readouterr().out
    assert "receipt_digest=" in out
    assert "NOT a locked theorem" in out  # honest claim_tier surfaced
    # verify must succeed against the same mesh + receipt
    rc2 = main(["verify", npz, receipt])
    assert rc2 == 0
    out2 = capsys.readouterr().out
    assert "VERIFY: OK" in out2


def test_cli_verify_detects_tamper(tmp_path, capsys):
    npz = _write_sample(tmp_path)
    receipt = str(tmp_path / "r.json")
    assert main(["compartmentalize", npz, "--receipt", receipt]) == 0
    capsys.readouterr()
    # Tamper the receipt's result hash, then verify must fail (exit code 1).
    with open(receipt) as fh:
        data = json.loads(fh.read())
    data["result_hash"] = "0" * 64
    with open(receipt, "w") as fh:
        fh.write(json.dumps(data))
    rc = main(["verify", npz, receipt])
    assert rc == 1
    out = capsys.readouterr().out
    assert "VERIFY: FAILED" in out


def test_cli_module_subprocess_roundtrip(tmp_path):
    # Real `python -m yarqa.cli` invocation (entry point wiring).
    repo = str(__import__("pathlib").Path(__file__).resolve().parents[1])
    npz = str(tmp_path / "m.npz")
    env = {"PYTHONPATH": repo, "PATH": "/usr/bin:/bin"}
    import os
    env = {**os.environ, "PYTHONPATH": repo}
    r1 = subprocess.run(
        [sys.executable, "-m", "yarqa.cli", "sample", npz],
        capture_output=True, text=True, env=env,
    )
    assert r1.returncode == 0, r1.stderr
    receipt = str(tmp_path / "m.json")
    r2 = subprocess.run(
        [sys.executable, "-m", "yarqa.cli", "compartmentalize", npz, "--receipt", receipt],
        capture_output=True, text=True, env=env,
    )
    assert r2.returncode == 0, r2.stderr
    r3 = subprocess.run(
        [sys.executable, "-m", "yarqa.cli", "verify", npz, receipt],
        capture_output=True, text=True, env=env,
    )
    assert r3.returncode == 0, r3.stderr
    assert "VERIFY: OK" in r3.stdout


def test_cli_requires_subcommand(capsys):
    import pytest
    with pytest.raises(SystemExit):
        main([])
