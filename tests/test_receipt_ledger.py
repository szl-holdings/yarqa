# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Run the offline receipt-ledger publisher fixtures through pytest discovery.

``.github/scripts/publish_receipt_ledger.cjs`` only runs on pushes to main (the
``publish-ledger`` job of ``receipt-sign.yml``), so its fail-closed and
append-only behaviour is pinned here against an in-memory GitHub double.
"""
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "receipt-sign.yml"


def test_receipt_ledger_publisher_fixtures():
    node = shutil.which("node")
    assert node is not None, "Node.js is required for the receipt-ledger fixtures"
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("receipt_ledger.test.cjs"))],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _job(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^  {name}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", text)
    assert match, f"job {name!r} missing from receipt-sign.yml"
    return match.group(1)


def test_only_the_ledger_job_can_write_and_it_runs_no_installs():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "continue-on-error" not in text
    sign = _job(text, "sign-and-verify")
    ledger = _job(text, "publish-ledger")
    # The job that pip-installs and runs package code holds no write token.
    assert "contents: write" not in sign
    assert "id-token: write" in sign
    assert "--require-hashes -r requirements/ci/receipt-sign.txt" in sign
    assert "persist-credentials: false" in sign
    # The job that writes the ledger installs nothing and has no OIDC token.
    assert "contents: write" in ledger
    assert "id-token" not in ledger
    assert "pip" not in ledger
    assert "persist-credentials: false" in ledger
    assert "needs: sign-and-verify" in ledger
    assert "github.event_name == 'push'" in ledger
    for action in re.findall(r"uses: (\S+)", text):
        assert re.search(r"@[0-9a-f]{40}$", action), action
