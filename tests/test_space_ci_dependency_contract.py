"""Fail-closed regression for the hosted Space dependency environment."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import unittest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - hosted contract runs on Python 3.11
    tomllib = None


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "space-ci.yml"
HF_DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "hf-deploy.yml"
CI_LOCK = ROOT / ".github" / "requirements" / "space-ci.lock"
PRODUCTION_LOCK = ROOT / "space" / "requirements.lock"
PRODUCTION_REQUIREMENTS = ROOT / "space" / "requirements.txt"
DOCKERFILE = ROOT / "space" / "Dockerfile"
PYPROJECT = ROOT / "pyproject.toml"
STEP_NAME = "Install, attest, and test the locked graph"
EXPECTED_RUN_SHA256 = "2fb61c79caa2a142e1cfd4288844f0b4a94c783350d3c4341039f935e5dc2bc9"
EXPECTED_WORKFLOW_SHA256 = "25e3fb4d3360b04c598be2364b924f89419374cc30355f8b2deb46ef27e1e100"
EXPECTED_HF_DEPLOY_SHA256 = "daf5935570e35191df980f92e6c78d7e76e68376dde8585ecbae95edac9f8711"
EXPECTED_DOCKERFILE_SHA256 = "6fc4c6627ac06a8a8f51f6ad28653f728d4a70792efcc5db79927173b371e3ed"

PACKAGE_INSTALL = re.compile(
    r"(?ix)(?<![A-Za-z0-9_.-])(?:"
    r"(?:[A-Za-z0-9_.$/{}/-]+/)?pip(?:3(?:\.\d+)?)?"
    r"|(?:[A-Za-z0-9_.$/{}/-]+/)?python(?:3(?:\.\d+)?)?\s+-m\s+pip"
    r"|(?:[A-Za-z0-9_.$/{}/-]+/)?python(?:3(?:\.\d+)?)?\s+-m\s+ensurepip"
    r"|uv(?:\s+pip)?"
    r"|pipx"
    r"|poetry"
    r"|pdm"
    r"|rye"
    r"|pixi"
    r"|easy_install"
    r"|conda"
    r"|mamba"
    r")\b[^\n#]*\b(?:install|add|sync|upgrade)\b"
)
LOCK_ENTRY = re.compile(
    r"(?m)^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\s\\]+)\s*\\?\n"
)
LOCK_HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _lock_entries(path: Path) -> dict[str, tuple[str, frozenset[str]]]:
    text = path.read_text(encoding="utf-8")
    matches = list(LOCK_ENTRY.finditer(text))
    if not matches:
        raise AssertionError(f"no exact requirements found in {path}")
    entries: dict[str, tuple[str, frozenset[str]]] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        hashes = frozenset(LOCK_HASH.findall(text[match.start() : end]))
        if not hashes:
            raise AssertionError(f"unhashed requirement {match.group(1)!r} in {path}")
        name = _canonical(match.group(1))
        if name in entries:
            raise AssertionError(f"duplicate requirement {name!r} in {path}")
        entries[name] = (match.group(2), hashes)
    return entries


def _extract_run_block(workflow: str) -> tuple[str, str]:
    marker = f"      - name: {STEP_NAME}\n        run: |\n"
    if workflow.count(marker) != 1:
        raise AssertionError(f"expected exactly one {STEP_NAME!r} step")
    start = workflow.index(marker)
    body_start = start + len(marker)
    lines = workflow[body_start:].splitlines(keepends=True)
    body_lines: list[str] = []
    for line in lines:
        if line.startswith("      - name:") or (
            line and not line.startswith(" ") and line.strip()
        ):
            break
        body_lines.append(line)
    body = "".join(body_lines).rstrip("\n") + "\n"
    without = workflow[:start] + workflow[body_start + len("".join(body_lines)) :]
    return body, without


def dependency_contract_errors(workflow: str) -> list[str]:
    errors: list[str] = []
    workflow_digest = hashlib.sha256(workflow.encode("utf-8")).hexdigest()
    if workflow_digest != EXPECTED_WORKFLOW_SHA256:
        errors.append("workflow bytes drifted")
    try:
        body, outside = _extract_run_block(workflow)
    except AssertionError as exc:
        return [str(exc)]

    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if digest != EXPECTED_RUN_SHA256:
        errors.append("locked install/test run block drifted")

    for match in PACKAGE_INSTALL.finditer(outside):
        errors.append(f"package-manager command outside locked step: {match.group(0)!r}")
    return errors


class SpaceCiDependencyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def assert_rejected(self, workflow: str, fragment: str) -> None:
        errors = dependency_contract_errors(workflow)
        self.assertTrue(
            any(fragment in error for error in errors),
            f"expected {fragment!r}; got {errors!r}",
        )

    def test_repository_workflow_satisfies_contract(self) -> None:
        self.assertEqual([], dependency_contract_errors(self.workflow))

    def test_environment_attestation_excludes_checkout_metadata(self) -> None:
        body, _ = _extract_run_block(self.workflow)
        self.assertEqual(1, body.count(".ci-venv/bin/python -I - <<'PY'"))

    def test_rejects_alternate_package_installs(self) -> None:
        marker = "  container-contract:\n"
        variants = (
            "      - name: Unhashed pip3\n        run: pip3 install requests\n\n",
            "      - name: Option before install\n        run: python -m pip --disable-pip-version-check install requests\n\n",
            "      - name: Unhashed uv\n        run: uv pip install requests\n\n",
            "      - name: Absolute pip\n        run: /usr/bin/pip3 install requests\n\n",
            "      - name: Shell indirection\n        run: sh -c 'pip install requests'\n\n",
            "      - name: Executable alias\n        run: ${PYTHON} -m pip install requests\n\n",
            "      - name: Unlocked uv sync\n        run: uv sync\n\n",
            "      - name: Unlocked pipx\n        run: pipx install requests\n\n",
            "      - name: Unlocked Poetry\n        run: poetry install\n\n",
            "      - name: Unlocked PDM\n        run: pdm sync\n\n",
            "      - name: Bootstrap ambient pip\n        run: python -m ensurepip --upgrade\n\n",
        )
        for variant in variants:
            with self.subTest(variant=variant):
                unsafe = self.workflow.replace(marker, variant + marker, 1)
                self.assertNotEqual(unsafe, self.workflow)
                self.assert_rejected(unsafe, "outside locked step")

    def test_rejects_any_other_workflow_drift(self) -> None:
        unsafe = self.workflow.replace("timeout-minutes: 10", "timeout-minutes: 11", 1)
        self.assertNotEqual(unsafe, self.workflow)
        self.assert_rejected(unsafe, "workflow bytes drifted")

    def test_rejects_locked_step_mutation(self) -> None:
        unsafe = self.workflow.replace(
            "          .ci-venv/bin/python -m pip check\n",
            "          .ci-venv/bin/python -m pip check\n"
            "          .ci-venv/bin/python -m pip install requests\n",
            1,
        )
        self.assertNotEqual(unsafe, self.workflow)
        self.assert_rejected(unsafe, "run block drifted")

    def test_rejects_missing_environment_attestation(self) -> None:
        unsafe = self.workflow.replace(
            "          from importlib.metadata import distributions\n",
            "",
            1,
        )
        self.assertNotEqual(unsafe, self.workflow)
        self.assert_rejected(unsafe, "run block drifted")

    def test_ci_lock_is_hashed_and_contains_the_exact_production_graph(self) -> None:
        production = _lock_entries(PRODUCTION_LOCK)
        ci = _lock_entries(CI_LOCK)
        self.assertTrue(production)
        self.assertTrue(ci)
        for name, requirement in production.items():
            self.assertIn(name, ci)
            self.assertEqual(requirement, ci[name], name)

        expected_versions = {
            "fastapi": "0.141.1",
            "httpx": "0.28.1",
            "pip": "26.2.1",
            "pytest": "8.4.2",
            "setuptools": "84.0.0",
            "uvicorn": "0.52.4",
            "wheel": "0.48.0",
        }
        self.assertEqual(
            expected_versions,
            {name: ci[name][0] for name in expected_versions},
        )

    @unittest.skipIf(tomllib is None, "TOML contract requires Python 3.11+")
    def test_project_declares_the_exact_ci_build_toolchain(self) -> None:
        assert tomllib is not None
        project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        self.assertEqual(
            ["setuptools==84.0.0", "wheel==0.48.0"],
            project["build-system"]["requires"],
        )
        test_extra = set(project["project"]["optional-dependencies"]["test"])
        self.assertTrue(
            {
                "httpx==0.28.1",
                "pip==26.2.1",
                "pytest==8.4.2",
                "setuptools==84.0.0",
                "wheel==0.48.0",
            }.issubset(test_extra)
        )

    def test_production_build_uses_the_same_exact_hashed_toolchain(self) -> None:
        production = _lock_entries(PRODUCTION_LOCK)
        expected_build_tools = {
            "pip": "26.2.1",
            "setuptools": "84.0.0",
            "wheel": "0.48.0",
        }
        self.assertEqual(
            expected_build_tools,
            {name: production[name][0] for name in expected_build_tools},
        )
        declared = {
            line.strip()
            for line in PRODUCTION_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertTrue(
            {f"{name}=={version}" for name, version in expected_build_tools.items()}
            .issubset(declared)
        )

        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertEqual(
            EXPECTED_DOCKERFILE_SHA256,
            hashlib.sha256(dockerfile.encode("utf-8")).hexdigest(),
        )
        for fragment in (
            "--require-hashes --force-reinstall -r space/requirements.lock",
            "--no-deps --no-build-isolation .",
            "python -m pip check",
            "PYTHONDONTWRITEBYTECODE=1",
        ):
            self.assertEqual(1, dockerfile.count(fragment), fragment)
        self.assertNotIn("--no-build-isolation -e .", dockerfile)
        self.assertNotIn("chown -R yarqa:yarqa /app", dockerfile)

    def test_hf_deploy_prunes_deleted_managed_copy_sources(self) -> None:
        workflow = HF_DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(
            EXPECTED_HF_DEPLOY_SHA256,
            hashlib.sha256(workflow.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(1, workflow.count("      prune: true\n"))
        self.assertEqual(1, workflow.count("      include-readme: false\n"))
        self.assertEqual(1, workflow.count("      dockerfile-path: space/Dockerfile\n"))


if __name__ == "__main__":
    unittest.main()
