"""Fail-closed contract for YARQA's single committed Hugging Face writer."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
WRITER = WORKFLOWS / "hf-space.yml"
RETIRED_WRITER = WORKFLOWS / "hf-deploy.yml"
DOCKERFILE = ROOT / "space" / "Dockerfile"
SPACE_APP = ROOT / "space" / "app.py"
COMMAND_LAB_ROUTE = "https://szlholdings-szl-command-lab.hf.space/api/yarqa"
TARGET = "SZLHOLDINGS/yarqa"

REQUIRED_EXACTLY_ONCE = {
    "      hf-repo: SZLHOLDINGS/yarqa": "the writer must name its one target",
    "      ref: ${{ github.sha }}": "the deploy must use the exact pushed commit",
    "      require-default-branch-tip: true": "only the exact protected main tip may deploy",
    "      dockerfile-path: space/Dockerfile": "the deploy set comes from the Space Dockerfile",
    "      include-readme: false": "the GitHub project README must not overwrite the Space card",
    "      prune: true": "files removed from git must leave the Space",
    "      restart-space: true": "the Space must restart after publication",
    "      wait-running: 1200": "the deployer must wait for a stable runtime",
    "      source-revision-variable: SZL_GIT_SHA": "the source SHA must be bound into the Space",
    "      source-revision-probe-path: /api/build-info": "the served source identity must be read back",
    "  group: hf-write/space/SZLHOLDINGS/yarqa": "one lock per Hub asset",
    "  cancel-in-progress: false": "an in-flight deploy is never cancelled",
    "      HF_TOKEN: ${{ secrets.HF_TOKEN }}": "exactly one explicitly passed secret",
    "permissions:\n  contents: read": "read-only token",
    "  workflow_dispatch: {}": "manual redeploy stays possible",
}
FORBIDDEN = {
    "secrets: inherit": "secrets are passed explicitly",
    "pull_request": "the writer never runs on pull requests",
    "contents: write": "the writer needs no write token",
    "cancel-in-progress: true": "an in-flight deploy is never cancelled",
    "github.event_name": "the lock is never keyed by event",
}
REUSABLE = re.compile(
    r"(?m)^    uses: szl-holdings/\.github/\.github/workflows/reusable-hf-deploy\.yml@([0-9a-f]{40})$"
)


def _writer() -> str:
    return WRITER.read_text(encoding="utf-8")


def _push_paths(text: str) -> list[str]:
    block = re.search(r"(?ms)^  push:\n    branches: \[main\]\n(.*?)^  workflow_dispatch:", text)
    assert block, "push trigger must list branches [main] and its paths"
    return [m.strip().strip('"') for m in re.findall(r"(?m)^      - (.+)$", block.group(1))]


def _copy_sources() -> list[str]:
    sources = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^COPY\s+(?!--from)(\S+)\s+\S+\s*$", line)
        if match:
            sources.append(match.group(1).rstrip("/"))
    return sources


def test_exactly_one_committed_writer_targets_the_space() -> None:
    assert WRITER.is_file()
    assert not RETIRED_WRITER.exists()
    writers = sorted(
        path.name
        for path in WORKFLOWS.glob("*.y*ml")
        if TARGET in path.read_text(encoding="utf-8")
    )
    assert writers == ["hf-space.yml"], writers


def test_writer_calls_the_pinned_reusable_deployer_once() -> None:
    assert len(REUSABLE.findall(_writer())) == 1


def test_writer_contract_values_are_present_exactly_once() -> None:
    text = _writer()
    errors = [msg for token, msg in REQUIRED_EXACTLY_ONCE.items() if text.count(token) != 1]
    assert errors == []


def test_writer_forbids_unsafe_settings() -> None:
    text = _writer()
    assert [msg for token, msg in FORBIDDEN.items() if token in text] == []


def test_smoke_paths_cover_root_health_and_source_identity() -> None:
    match = re.search(r"(?m)^      smoke-paths: '(.+)'$", _writer())
    assert match
    paths = json.loads(match.group(1))
    for required in ("/", "/healthz", "/api/build-info"):
        assert required in paths


def test_push_paths_cover_every_published_input() -> None:
    paths = _push_paths(_writer())
    sources = _copy_sources()
    assert sources, "space/Dockerfile must COPY its sources"
    for source in sources:
        assert source in paths or f"{source}/**" in paths, source
    for extra in (".dockerignore", ".github/workflows/hf-space.yml"):
        assert extra in paths, extra
    # space/Dockerfile itself is published as the Space-root Dockerfile.
    assert "space/**" in paths


def test_probed_routes_exist_in_the_space_app() -> None:
    app = SPACE_APP.read_text(encoding="utf-8")
    for route in ('@app.get("/api/build-info")', '@app.get("/healthz")', '@app.get("/")'):
        assert route in app, route
    assert 'ARG SZL_GIT_SHA=""' in DOCKERFILE.read_text(encoding="utf-8")


def test_readme_names_both_runtimes_and_the_truth_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split())
    assert COMMAND_LAB_ROUTE in readme
    assert f"https://huggingface.co/spaces/{TARGET}" in readme
    assert "`.github/workflows/hf-space.yml`" in normalized
    assert "integrity and reproducibility" in readme
    assert "not CFD correctness" in readme
