"""Fail-closed contract for YARQA's consolidated Command Lab runtime."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "hf-deploy.yml"
COMMAND_LAB_ROUTE = "https://szlholdings-szl-command-lab.hf.space/api/yarqa"


def test_standalone_hugging_face_publisher_is_retired() -> None:
    assert not WORKFLOW.exists()
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    )
    assert "SZLHOLDINGS/yarqa" not in workflow_text


def test_readme_names_the_canonical_runtime_and_truth_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split())
    assert COMMAND_LAB_ROUTE in readme
    assert "There is no standalone `SZLHOLDINGS/yarqa` Space" in normalized
    assert "integrity and reproducibility" in readme
    assert "not CFD correctness" in readme
