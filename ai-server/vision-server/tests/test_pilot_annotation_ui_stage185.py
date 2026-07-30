from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from app.vision.pilot_annotation_ui import AnnotationWorkspace
from app.vision.pilot_video_intake import load_strict_json


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACKAGE = ROOT / "data" / "output" / "pilot_annotation" / "SES_000001"
VIDEO = ROOT / "data" / "pilot" / "incoming" / "PTC_000001_SES_000001.mp4"


class PilotAnnotationUiStage185Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.package = Path(self.temp.name) / "SES_000001"
        shutil.copytree(SOURCE_PACKAGE, self.package)
        self.template = self.package / "rater_a" / "annotation_events.template.json"
        self.template_hash = hashlib.sha256(self.template.read_bytes()).hexdigest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def workspace(self, rater: str = "RATER_A") -> AnnotationWorkspace:
        return AnnotationWorkspace(self.package, session_id="SES_000001", rater_id=rater, video_path=VIDEO)

    def test_rater_id_and_workspace_isolation_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "rater"):
            self.workspace("RATER_C")
        workspace = self.workspace()
        self.assertEqual(workspace.rater_directory.name, "rater_a")
        self.assertNotIn("rater_b", str(workspace.rater_directory))

    def test_registry_labels_are_loaded_from_rater_package(self) -> None:
        workspace = self.workspace()
        self.assertEqual(len(workspace.labels), 19)
        self.assertEqual(workspace.labels[0]["label_id"], "HEAD_TURN_LEFT")
        self.assertNotIn("CONFIDENCE", {item["label_id"] for item in workspace.labels})

    def test_add_update_delete_and_monotonic_event_ids(self) -> None:
        workspace = self.workspace()
        first = workspace.add_event(answer_id="ANS_000001", label_id="HEAD_TURN_LEFT", direction="LEFT", start_timestamp_ms=15000, end_timestamp_ms=17000)
        workspace.update_event(first, label_id="HEAD_TURN_RIGHT", direction="RIGHT")
        workspace.delete_event(first)
        second = workspace.add_event(answer_id="ANS_000001", label_id="HEAD_TURN_LEFT", direction="LEFT", start_timestamp_ms=18000, end_timestamp_ms=19000)
        self.assertEqual(first, "RATER_A_EVT_000001")
        self.assertEqual(second, "RATER_A_EVT_000002")

    def test_invalid_range_direction_and_duplicate_are_rejected(self) -> None:
        workspace = self.workspace()
        with self.assertRaisesRegex(ValueError, "outside"):
            workspace.add_event(answer_id="ANS_000001", label_id="HEAD_TURN_LEFT", direction="LEFT", start_timestamp_ms=10000, end_timestamp_ms=12000)
        with self.assertRaisesRegex(ValueError, "direction"):
            workspace.add_event(answer_id="ANS_000001", label_id="HEAD_TURN_LEFT", direction="RIGHT", start_timestamp_ms=15000, end_timestamp_ms=17000)
        workspace.add_event(answer_id="ANS_000001", label_id="HEAD_TURN_LEFT", direction="LEFT", start_timestamp_ms=15000, end_timestamp_ms=17000)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            workspace.add_event(answer_id="ANS_000001", label_id="HEAD_TURN_LEFT", direction="LEFT", start_timestamp_ms=15000, end_timestamp_ms=17000)

    def test_draft_uses_atomic_strict_json_and_template_is_unchanged(self) -> None:
        workspace = self.workspace()
        workspace.add_event(answer_id="ANS_000001", label_id="FACE_NOT_VISIBLE", direction=None, start_timestamp_ms=15000, end_timestamp_ms=17000)
        draft = workspace.save_draft()
        self.assertTrue(draft.exists())
        self.assertEqual(load_strict_json(draft)["completed_at"], None)
        self.assertEqual(hashlib.sha256(self.template.read_bytes()).hexdigest(), self.template_hash)
        self.assertEqual(list(draft.parent.glob("*.tmp")), [])

    def test_completion_requires_explicit_empty_confirmation_and_preserves_flags(self) -> None:
        workspace = self.workspace()
        self.assertFalse(workspace.result_path.exists())
        with self.assertRaisesRegex(ValueError, "empty"):
            workspace.complete()
        result = workspace.complete(confirm_empty_events=True, completed_at="2026-07-29T21:30:00+09:00")
        value = load_strict_json(result)
        self.assertEqual(value["completed_at"], "2026-07-29T21:30:00+09:00")
        self.assertTrue(value["blinded_to_model_metrics"])
        self.assertTrue(value["blinded_to_other_raters"])

    def test_existing_result_requires_explicit_replace(self) -> None:
        workspace = self.workspace()
        workspace.complete(confirm_empty_events=True, completed_at="2026-07-29T21:30:00+09:00")
        with self.assertRaises(FileExistsError):
            workspace.complete(confirm_empty_events=True)


if __name__ == "__main__":
    unittest.main()
