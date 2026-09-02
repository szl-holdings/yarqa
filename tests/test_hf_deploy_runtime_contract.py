"""Fail-closed contract for YARQA's governed Hugging Face deployment."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "hf-deploy.yml"


def contract_errors(text: str) -> list[str]:
    errors: list[str] = []
    required_exactly_once = {
        '- ".github/workflows/hf-deploy.yml"': "the workflow must trigger its own protected-main deployment",
        "      restart-space: true": "the Space must restart after publication",
        "      wait-running: 1200": "the deployer must wait for a stable runtime",
        "      smoke-paths: '[\"/\",\"/healthz\",\"/api/build-info\"]'": "root, health, and source identity must all be smoked",
        "      source-revision-variable: SZL_GIT_SHA": "the deployed source SHA must be bound into the Space",
        "      source-revision-probe-path: /api/build-info": "the served source identity must be read back",
        "      require-default-branch-tip: true": "only exact protected main may deploy",
    }
    for token, message in required_exactly_once.items():
        if text.count(token) != 1:
            errors.append(message)

    forbidden = {
        "      restart-space: false": "restart cannot be disabled",
        "      wait-running: 0": "runtime waiting cannot be disabled",
        "      source-revision-probe-path: /healthz": "health reachability cannot substitute for source identity",
    }
    for token, message in forbidden.items():
        if token in text:
            errors.append(message)

    if text.find("restart-space: true") > text.find("source-revision-probe-path: /api/build-info"):
        errors.append("restart admission must be declared before source readback")
    return errors


def test_committed_deployment_contract_passes() -> None:
    assert contract_errors(WORKFLOW.read_text(encoding="utf-8")) == []


def test_disabling_restart_fails_closed() -> None:
    text = WORKFLOW.read_text(encoding="utf-8").replace(
        "      restart-space: true", "      restart-space: false", 1
    )
    errors = contract_errors(text)
    assert "the Space must restart after publication" in errors
    assert "restart cannot be disabled" in errors


def test_omitting_health_or_source_smoke_fails_closed() -> None:
    text = WORKFLOW.read_text(encoding="utf-8").replace(
        "      smoke-paths: '[\"/\",\"/healthz\",\"/api/build-info\"]'",
        "      smoke-paths: '[\"/\"]'",
        1,
    )
    assert "root, health, and source identity must all be smoked" in contract_errors(text)


def test_removing_self_trigger_fails_closed() -> None:
    text = WORKFLOW.read_text(encoding="utf-8").replace(
        '      - ".github/workflows/hf-deploy.yml"\n', "", 1
    )
    assert "the workflow must trigger its own protected-main deployment" in contract_errors(text)


def test_health_cannot_replace_exact_source_readback() -> None:
    text = WORKFLOW.read_text(encoding="utf-8").replace(
        "      source-revision-probe-path: /api/build-info",
        "      source-revision-probe-path: /healthz",
        1,
    )
    errors = contract_errors(text)
    assert "the served source identity must be read back" in errors
    assert "health reachability cannot substitute for source identity" in errors
