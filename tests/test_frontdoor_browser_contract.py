"""The browser verifier's QA environment is declared, hash-locked and kept out of the Space runtime."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools" / "verify_frontdoor_browser.py"
QA_INPUT = ROOT / ".github" / "requirements" / "frontdoor-browser.in"
QA_LOCK = ROOT / ".github" / "requirements" / "frontdoor-browser.lock"
WORKFLOW = ROOT / ".github" / "workflows" / "frontdoor-browser.yml"
RUNTIME_FILES = (ROOT / "space" / "requirements.txt", ROOT / "space" / "requirements.lock",
                 ROOT / "space" / "Dockerfile", ROOT / "pyproject.toml")
ENTRY = re.compile(r"(?m)^([A-Za-z0-9_.-]+)==(\S+) \\\n((?:    --hash=sha256:[0-9a-f]{64}(?: \\)?\n)+)")


class FrontdoorBrowserContract(unittest.TestCase):
    def test_qa_lock_pins_every_package_with_hashes(self) -> None:
        lock = QA_LOCK.read_text(encoding="utf-8")
        entries = {name.lower(): version for name, version, _ in ENTRY.findall(lock)}
        requirement_lines = [line for line in lock.splitlines() if line and not line.startswith((" ", "#"))]
        self.assertEqual(len(requirement_lines), len(entries), "every requirement carries hashes")
        declared = re.search(r"(?m)^playwright==(\S+)$", QA_INPUT.read_text(encoding="utf-8"))
        self.assertIsNotNone(declared)
        self.assertEqual(declared.group(1), entries.get("playwright"))

    def test_space_runtime_does_not_ship_browser_qa_dependencies(self) -> None:
        for path in RUNTIME_FILES:
            self.assertNotIn("playwright", path.read_text(encoding="utf-8").lower(), path.name)

    def test_verifier_reports_missing_setup_instead_of_failing_at_import(self) -> None:
        tree = ast.parse(VERIFIER.read_text(encoding="utf-8"))
        top_level = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        modules = {getattr(node, "module", None) or node.names[0].name for node in top_level}
        self.assertFalse(any(name and name.startswith("playwright") for name in modules))
        source = VERIFIER.read_text(encoding="utf-8")
        self.assertIn(".github/requirements/frontdoor-browser.lock", source)
        self.assertIn('"complete": False', source)
        self.assertIn("exist_ok=False", source)

    def test_workflow_installs_the_lock_and_never_holds_a_credential(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--require-hashes -r .github/requirements/frontdoor-browser.lock", workflow)
        self.assertIn("playwright install --with-deps chromium", workflow)
        self.assertIn("tools/verify_frontdoor_browser.py --output", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("hf-repo:", workflow)
        for action in re.findall(r"uses: (\S+)", workflow):
            self.assertRegex(action, r"@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
