import unittest

from readiness.readiness import (
    DeclarationError,
    DeclaredDependency,
    FRESH,
    NOT_READY,
    PROVEN,
    ReadinessEvaluator,
    UNKNOWN,
    UNKNOWN_STATUS,
    READY,
    UNPROVEN,
)

NOW = 1000000.0


class FreshnessTests(unittest.TestCase):
    def test_fresh_within_window(self):
        dep = DeclaredDependency("pg", proven=PROVEN, last_seen_ts=NOW - 5, window_s=30)
        self.assertEqual(dep.freshness(NOW)[0], FRESH)

    def test_stale_beyond_window(self):
        dep = DeclaredDependency("redis", proven=PROVEN, last_seen_ts=NOW - 100, window_s=30)
        self.assertEqual(dep.freshness(NOW)[0], "stale")

    def test_missing_observation_is_unknown(self):
        dep = DeclaredDependency("queue", proven=PROVEN)
        self.assertEqual(dep.freshness(NOW)[0], UNKNOWN)

    def test_negative_age_is_unknown(self):
        dep = DeclaredDependency("clock-skew", proven=PROVEN, last_seen_ts=NOW + 50, window_s=30)
        self.assertEqual(dep.freshness(NOW)[0], UNKNOWN)


class ReadinessTests(unittest.TestCase):
    def test_all_proven_fresh_is_ready(self):
        ev = ReadinessEvaluator([
            DeclaredDependency("pg", PROVEN, NOW - 6, 30),
            DeclaredDependency("redis", PROVEN, NOW - 6, 30),
        ])
        report = ev.evaluate(NOW)
        self.assertEqual(report.status, READY)
        self.assertEqual(report.reasons, [])
        self.assertEqual(sorted(report.per_dependency), ["pg", "redis"])

    def test_one_stale_is_not_ready(self):
        ev = ReadinessEvaluator([
            DeclaredDependency("pg", PROVEN, NOW - 6, 30),
            DeclaredDependency("redis", PROVEN, NOW - 100, 30),
        ])
        report = ev.evaluate(NOW)
        self.assertEqual(report.status, NOT_READY)
        self.assertTrue(any("redis" in r for r in report.reasons))

    def test_absent_data_is_unknown_never_green(self):
        ev = ReadinessEvaluator([DeclaredDependency("pg", PROVEN)])
        report = ev.evaluate(NOW)
        self.assertEqual(report.status, UNKNOWN_STATUS)
        self.assertTrue(any("freshness unknown" in r for r in report.reasons))

    def test_unproven_dependency_is_not_ready(self):
        ev = ReadinessEvaluator([DeclaredDependency("pg", UNPROVEN, NOW - 6, 30)])
        report = ev.evaluate(NOW)
        self.assertEqual(report.status, NOT_READY)
        self.assertTrue(any("unproven" in r for r in report.reasons))

    def test_empty_declaration_is_unknown(self):
        report = ReadinessEvaluator([]).evaluate(NOW)
        self.assertEqual(report.status, UNKNOWN_STATUS)

    def test_hard_failure_dominates_unknown(self):
        ev = ReadinessEvaluator([
            DeclaredDependency("pg", PROVEN, NOW - 100, 30),
            DeclaredDependency("queue", PROVEN),
        ])
        report = ev.evaluate(NOW)
        self.assertEqual(report.status, NOT_READY)

    def test_report_as_dict_roundtrip(self):
        ev = ReadinessEvaluator([DeclaredDependency("pg", PROVEN, NOW - 1, 30)])
        d = ev.evaluate(NOW).as_dict()
        self.assertEqual(d["status"], READY)
        self.assertEqual(d["per_dependency"]["pg"]["freshness"], FRESH)


class ContractTests(unittest.TestCase):
    def test_bad_name_rejected(self):
        with self.assertRaises(DeclarationError):
            DeclaredDependency("")

    def test_bad_proven_rejected(self):
        with self.assertRaises(DeclarationError):
            DeclaredDependency("pg", proven="maybe")

    def test_bad_window_rejected(self):
        with self.assertRaises(DeclarationError):
            DeclaredDependency("pg", PROVEN, NOW - 1, window_s=0)


if __name__ == "__main__":
    unittest.main()
