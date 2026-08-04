from copy import deepcopy
import unittest

from support import ROOT, inventory, profile
from engine.profile_loader import load_profile
from engine.profile_validator import profile_hash, require_production_approval, validate_profile
from engine.scoring_errors import ScoringError


class ProfileLoaderTests(unittest.TestCase):
    def setUp(self):
        self.inventory = inventory()
        self.profile = profile()

    def assert_invalid(self, mutate):
        candidate = deepcopy(self.profile)
        mutate(candidate)
        with self.assertRaises(ScoringError):
            validate_profile(candidate, self.inventory)

    def test_valid_profile_loads_and_hash_is_stable(self):
        loaded, digest = load_profile(ROOT / "fixtures/profiles/experimental-scoring-profile-v1.json", self.inventory)
        self.assertEqual(digest, profile_hash(loaded))
        self.assertEqual(digest, profile_hash(deepcopy(loaded)))

    def test_bad_semver(self):
        self.assert_invalid(lambda row: row.update(version="v1"))

    def test_duplicate_metric_rule(self):
        self.assert_invalid(lambda row: row["metricRules"].append(deepcopy(row["metricRules"][0])))

    def test_duplicate_axis_rule(self):
        self.assert_invalid(lambda row: row["axisRules"].append(deepcopy(row["axisRules"][0])))

    def test_unknown_metric(self):
        self.assert_invalid(lambda row: row["metricRules"][0].update(metricId="UNKNOWN"))

    def test_unknown_axis(self):
        self.assert_invalid(lambda row: row["axisRules"][0].update(axis="CONTENT"))

    def test_unit_mismatch(self):
        self.assert_invalid(lambda row: row["metricRules"][0].update(unit="METER"))

    def test_duplicate_or_unsorted_anchor(self):
        self.assert_invalid(lambda row: row["metricRules"][0]["anchors"].__setitem__(1, {"value": 0, "score": 50}))

    def test_overlapping_band(self):
        self.assert_invalid(lambda row: row["metricRules"][1]["bands"].__setitem__(1, {"minimum": 9, "maximum": 25, "minimumInclusive": True, "maximumInclusive": True, "score": 50}))

    def test_weight_range(self):
        self.assert_invalid(lambda row: row["metricRules"][0].update(weight=1.1))

    def test_unknown_session_aggregation(self):
        self.assert_invalid(lambda row: row["sessionAggregation"].update(method="INFER"))

    def test_production_fails_closed(self):
        with self.assertRaises(ScoringError) as caught:
            require_production_approval(self.profile, self.inventory)
        self.assertEqual(caught.exception.code, "SCORING_PROFILE_NOT_APPROVED")


if __name__ == "__main__":
    unittest.main()
