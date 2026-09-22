"""Admission contracts for required checks and the two existing dependency locks.

These checks compare direct requirement versions for the running interpreter.
They do not replace hash-locked installation, dependency closure checks, or the
container witness. ``packaging`` is part of the existing pytest environment.
"""
from pathlib import Path
import re
import unittest

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def requirement_records(text):
    """Read pip-compile style records; never execute includes or pip options."""
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        continued = line.endswith("\\")
        pending += line[:-1].rstrip() if continued else line
        if continued:
            pending += " "
            continue
        record, pending = pending, ""
        # Lock transport settings are validated by existing install/registry gates.
        if record.startswith(("--index-url ", "--extra-index-url ")):
            continue
        # Hashes remain enforced by pip --require-hashes, not this version check.
        record = re.split(r"\s+--hash=", record, maxsplit=1)[0]
        record = re.split(r"\s+#", record, maxsplit=1)[0]
        requirement = Requirement(record)
        if requirement.url is not None:
            raise ValueError("direct URLs are outside the version-lock contract")
        if requirement.marker is None or requirement.marker.evaluate():
            yield requirement
    if pending:
        raise ValueError("unterminated requirement continuation")


def assert_lock_satisfies(requirements_text, lock_text):
    """Reject absent, ambiguous, non-exact, or incompatible active lock records."""
    pins = {}
    for requirement in requirement_records(lock_text):
        specs = list(requirement.specifier)
        if len(specs) != 1 or specs[0].operator != "==" or "*" in specs[0].version:
            raise ValueError(f"non-exact lock for {requirement.name}")
        name = canonicalize_name(requirement.name)
        if name in pins:
            raise ValueError(f"duplicate active lock for {name}")
        pins[name] = Version(specs[0].version)
    for requirement in requirement_records(requirements_text):
        name = canonicalize_name(requirement.name)
        if name not in pins:
            raise ValueError(f"missing lock for {name}")
        if not requirement.specifier.contains(pins[name], prereleases=True):
            raise ValueError(f"{name}=={pins[name]} does not satisfy {requirement.specifier}")


class VersionContractFixtures(unittest.TestCase):
    def test_compatible_lock(self):
        assert_lock_satisfies("uvicorn[standard]>=0.52.4", "uvicorn[standard]==0.52.4")

    def test_unqualified_uvicorn_upgrade_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not satisfy"):
            assert_lock_satisfies("uvicorn[standard]>=0.53.0", "uvicorn[standard]==0.52.4")

    def test_names_are_canonicalized(self):
        assert_lock_satisfies("Foo_Bar>=1", "foo-bar==1.0")

    def test_missing_lock_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing lock"):
            assert_lock_satisfies("uvicorn>=0.53.0", "other==1")

    def test_non_exact_and_wildcard_locks_are_rejected(self):
        for lock in ("uvicorn>=0.53.0", "uvicorn==0.53.*"):
            with self.subTest(lock=lock), self.assertRaisesRegex(ValueError, "non-exact"):
                assert_lock_satisfies("uvicorn>=0.53.0", lock)

    def test_duplicate_active_lock_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate active"):
            assert_lock_satisfies("uvicorn>=0.53.0", "uvicorn==0.53.0\nuvicorn==0.53.1")

    def test_hash_continuations_and_comments(self):
        lock = "# generated\nuvicorn==0.53.0 \\\n    --hash=sha256:abc \\\n    --hash=sha256:def\n    # via runtime\n"
        assert_lock_satisfies("uvicorn>=0.53.0 # runtime", lock)

    def test_inactive_marker_is_not_required(self):
        assert_lock_satisfies('old; python_version < "2"', "other==1")

    def test_includes_urls_and_unterminated_records_are_rejected(self):
        for text in ("-r other.txt", "uvicorn @ https://example.invalid/package.whl", "uvicorn==0.53.0 \\"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                assert_lock_satisfies(text, "uvicorn==0.53.0")


class RequiredPinWorkflowContract(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/pin-check.yml").read_text(encoding="utf-8")

    def test_required_check_has_no_path_or_job_skip_filters(self):
        self.assertNotRegex(self.workflow, r"(?m)^\s*(?:paths|paths-ignore|branches-ignore|if):")

    def test_pr_main_and_merge_queue_events_are_present(self):
        for event in ("push", "pull_request", "merge_group"):
            self.assertRegex(self.workflow, rf"(?m)^  {event}:\s*$")
        self.assertIn("branches: [main, master]", self.workflow)
        self.assertNotIn("pull_request_target:", self.workflow)

    def test_existing_read_only_pinned_checker_is_preserved(self):
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertRegex(self.workflow, r"(?m)^  pin-check:\s*$")
        self.assertRegex(self.workflow, r"uses: szl-holdings/\.github/\.github/workflows/pin-check-reusable\.yml@[0-9a-f]{40}\s*$")
        self.assertNotIn("secrets: inherit", self.workflow)


class RepositoryDependencyLocks(unittest.TestCase):
    def test_runtime_lock_satisfies_declared_requirements(self):
        assert_lock_satisfies(
            (ROOT / "space/requirements.txt").read_text(encoding="utf-8"),
            (ROOT / "space/requirements.lock").read_text(encoding="utf-8"),
        )

    def test_test_lock_satisfies_declared_runtime_requirements(self):
        assert_lock_satisfies(
            (ROOT / "space/requirements.txt").read_text(encoding="utf-8"),
            (ROOT / ".github/requirements/space-ci.lock").read_text(encoding="utf-8"),
        )
