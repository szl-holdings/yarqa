"""CI-executed wrapper for the readiness package test suite.

The space-ci dependency contract pins the workflow run block byte-for-byte,
so the suite runs via `python -m pytest tests/`. This module re-exports the
readiness package tests (canonical source: readiness/test_readiness.py) so
they execute in CI without modifying the locked workflow bytes.
"""

from readiness.test_readiness import *  # noqa: F401,F403
