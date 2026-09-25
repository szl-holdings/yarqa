# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Refuse pickle-on-load in yarqa's own source (runs in Space CI via pytest).

Modeled on tests/test_no_unsafe_serialization.py in the SZL kernel repos, which
refuses a shipped model.joblib and joblib/pickle/dill load calls. This version
also refuses pickle files, ``pickle.Unpickler``, cloudpickle, ``torch.load``,
``read_pickle``, ``from <pickle module> import`` lines, and any NumPy
``allow_pickle`` value other than ``False``. Only yarqa-owned directories are
scanned, so a virtualenv created inside the checkout (CI uses ``.ci-venv``) is
ignored.

It is a line-based regex tripwire, not a full detector: aliased imports
(``import pickle as p``) and indirect calls are not seen. Review still applies.
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCANNED = ("yarqa", "space", "scripts", "examples", "tests")
CALL = re.compile(
    r"\b(?:joblib\.(?:load|dump)|pickle\.(?:loads?|Unpickler)|dill\.loads?"
    r"|cloudpickle\.loads?|torch\.load|read_pickle)\s*\("
    r"|\bfrom\s+(?:pickle|dill|cloudpickle|joblib)\s+import\b"
    r"|\ballow_pickle\s*=(?!\s*False\b)"
)


class NoUnsafeSerialization(unittest.TestCase):
    def test_no_pickle_files_in_tree(self) -> None:
        found = [
            str(path.relative_to(ROOT))
            for top in SCANNED
            for pattern in ("*.joblib", "*.pkl", "*.pickle", "*.dill")
            for path in (ROOT / top).rglob(pattern)
        ]
        self.assertEqual(found, [])

    def test_no_pickle_loader_calls(self) -> None:
        hits = []
        for top in SCANNED:
            for path in sorted((ROOT / top).rglob("*.py")):
                text = path.read_text(encoding="utf-8")
                for i, line in enumerate(text.splitlines(), 1):
                    if CALL.search(line):
                        hits.append(f"{path.relative_to(ROOT)}:{i}:{line.strip()}")
        self.assertEqual(hits, [])

    def test_pattern_catches_known_pickle_loaders(self) -> None:
        # Each sample is split across two literals so this file does not trip
        # its own scan above.
        caught = (
            "joblib" ".load(path)",
            "pickle" ".load(fh)",
            "pickle" ".loads(blob)",
            "pickle" ".Unpickler(fh).load()",
            "dill" ".loads(blob)",
            "cloudpickle" ".loads(blob)",
            "torch" ".load(path)",
            "pd.read" "_pickle(path)",
            "from pickle" " import load",
            "np.load(path, allow" "_pickle=True)",
            "np.load(path, allow" "_pickle=flag)",
            "np.load(path, allow" "_pickle = True)",
        )
        for line in caught:
            self.assertIsNotNone(CALL.search(line), line)
        allowed = (
            "np.load(path, allow" "_pickle=False)",
            "np.load(path, allow" "_pickle = False)",
            "np.load(path, allow" "_pickle= False)",
            "np.load(path, allow" "_pickle =False)",
            "blob = pickle" ".dumps(obj)",
        )
        for line in allowed:
            self.assertIsNone(CALL.search(line), line)


if __name__ == "__main__":
    unittest.main()
