import json
from pathlib import Path
import unittest

from support import REPOSITORY, ROOT, inventory


class ScoringFoundationTests(unittest.TestCase):
    def test_required_package_files_exist(self):
        for relative in ("contracts/metric-input.schema.json", "contracts/metric-inventory.schema.json", "contracts/evidence-record.schema.json", "contracts/threshold-profile.schema.json", "contracts/scoring-result.schema.json", "registries/scoring-axis-registry-v1.json", "registries/metric-inventory-v1.json"):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_schemas_are_json(self):
        for path in (ROOT / "contracts").glob("*.schema.json"):
            self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_metric_ids_unique_and_axes_valid(self):
        rows = inventory()["metrics"]
        self.assertEqual(len(rows), 18)
        self.assertEqual(len({row["metricId"] for row in rows}), len(rows))
        self.assertTrue({row["axis"] for row in rows} <= {"GAZE_HEAD", "POSTURE", "SPEECH_DELIVERY"})

    def test_implementation_paths_are_existing_repository_relative_files(self):
        for row in inventory()["metrics"]:
            path = Path(row["implementationPath"])
            self.assertFalse(path.is_absolute())
            self.assertTrue((REPOSITORY / path).is_file(), row["metricId"])

    def test_inventory_has_units_and_unmapped_defaults(self):
        for row in inventory()["metrics"]:
            self.assertTrue(row["unit"])
            self.assertEqual(row["evidenceStatus"], "UNMAPPED")
            self.assertIsNone(row["evidenceRelation"])
            self.assertFalse(row["eligibleForScoringCandidate"])

    def test_quality_metrics_are_not_score_candidates(self):
        rows = [row for row in inventory()["metrics"] if row.get("dataQualityOnly")]
        self.assertEqual({row["metricId"] for row in rows}, {"QUALITY_HEAD_AVAILABILITY_RATIO", "QUALITY_POSTURE_AVAILABILITY_RATIO"})

    def test_papers_and_outputs_are_git_ignored(self):
        evidence = (ROOT / "evidence/.gitignore").read_text(encoding="utf-8")
        self.assertIn("*.pdf", evidence)
        self.assertIn("private/", evidence)
        self.assertIn("*", (ROOT / "data/output/.gitignore").read_text(encoding="utf-8"))

    def test_existing_api_does_not_import_scoring(self):
        for server in ("vision-server", "analysis-server"):
            main = REPOSITORY / "ai-server" / server / "app" / "main.py"
            if main.is_file():
                self.assertNotIn("ai-server/scoring", main.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
